# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    source_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string="Selected Source Warehouses",
        copy=False, # Do not copy when duplicating SO/lines
        help="Warehouses selected (e.g., via website or manually) to source this specific line item."
    )

    allowed_source_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        compute='_compute_allowed_source_warehouse_ids',
        string="Allowed Source Warehouses (Domain Helper)",
        help="Technical field for UI domain, listing warehouses from the product template.",
    )

    @api.depends('product_id', 'product_id.source_warehouse_ids')
    def _compute_allowed_source_warehouse_ids(self):
        for line in self:
            if line.product_id:
                line.allowed_source_warehouse_ids = line.product_id.source_warehouse_ids
            else:
                line.allowed_source_warehouse_ids = False  # Or self.env['stock.warehouse']

    # Override the method responsible for triggering procurement for the line
    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """
        Override to implement custom multi-warehouse logic BEFORE standard
        procurement rules are triggered.
        """
        # Pre-check: Only applies to storable products
        product_lines = self.filtered(lambda l: l.product_id.type == 'product')
        if not product_lines:
            return super(SaleOrderLine, self)._action_launch_stock_rule(previous_product_uom_qty)

        handled_lines = self.env['sale.order.line']
        standard_lines = self.env['sale.order.line']
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        for line in product_lines:
            order = line.order_id
            website = order.website_id
            use_multi_wh = (
                website
                and website.multi_warehouse_fulfillment_enabled
                and line.source_warehouse_ids # Check if sources were actually selected
            )

            if not use_multi_wh:
                # Scenario C: Standard Odoo Behavior
                standard_lines |= line
                continue # Let standard logic handle this line

            # --- Multi-Warehouse Logic ---
            handled_lines |= line
            qty_to_fulfill = line.product_uom_qty # Adjust based on previous_product_uom_qty if needed

            if order.multi_warehouse_delivery_enabled:
                # Scenario A: Direct Multi-Ship
                _logger.info(f"SO Line {line.id}: Running Scenario A (Direct Multi-Ship)")
                self._create_direct_delivery_moves(line, qty_to_fulfill)
            else:
                # Scenario B: Collect at DC
                _logger.info(f"SO Line {line.id}: Running Scenario B (Collect at DC)")
                collect_wh = website.multi_warehouse_fulfillment_warehouse_id
                if not collect_wh:
                    raise UserError(_("Website '%s' is configured for multi-warehouse collection, but no Distribution Center Warehouse is set.", website.name))

                # Set the main Order warehouse? Do this carefully - maybe better to just route moves
                # order.write({'warehouse_id': collect_wh.id}) # Consider implications

                # 1. Create Internal Transfers to Collection WH
                self._create_internal_transfer_moves(line, qty_to_fulfill, collect_wh)

                # 2. Let standard logic run BUT targeted at the collection warehouse
                # The standard logic will create the demand in the collection WH
                # which waits for the internal transfers.
                # We need to ensure the context/line points to the collect_wh.
                # This might happen automatically if order.warehouse_id is set,
                # or we might need to pass context.
                # Add line back to standard processing, but it should now use collect_wh route.
                standard_lines |= line

        # Launch standard procurement only for lines not fully handled or requiring downstream steps
        if standard_lines:
            # Ensure context or order warehouse directs standard rules correctly for Scenario B lines
            for line in standard_lines:
                 if line in handled_lines and not line.order_id.multi_warehouse_delivery_enabled:
                     # Ensure the order warehouse is set for collect@DC scenario before std rule runs
                     collect_wh = line.order_id.website_id.multi_warehouse_fulfillment_warehouse_id
                     if line.order_id.warehouse_id != collect_wh:
                         _logger.warning(f"SO {line.order_id.name}: Temporarily setting WH to {collect_wh.name} for std rule launch for line {line.id}")
                         # This write might be contentious - test carefully
                         # line.order_id.sudo().write({'warehouse_id': collect_wh.id}) # Use sudo if needed

            _logger.info(f"Launching standard stock rules for lines: {standard_lines.ids}")
            super(SaleOrderLine, standard_lines)._action_launch_stock_rule(previous_product_uom_qty)

        # Return True for handled lines if super() expects a return value indicating success
        # The specific return value depends on Odoo version and context. Often it's implicitly True or returns created procurements.
        # Since we create moves directly, returning True might suffice. Check Odoo source if issues arise.
        return True # Assuming True indicates processing occurred

    def _calculate_source_quantities(self, line, qty_needed, sources):
        """
        Calculates the quantity to pull from each source warehouse based on availability.

        :param line: The sale.order.line record
        :param qty_needed: The total float quantity needed for the line product.
        :param sources: A recordset of stock.warehouse records selected as sources.
        :return: A tuple: (dict {wh.id: qty_to_pull}, float shortfall_qty)
                 The dict maps warehouse IDs to the float quantity to pull from them.
                 shortfall_qty is the quantity still needed after checking all sources.
        """
        StockQuant = self.env['stock.quant']
        qty_to_pull_map = defaultdict(float)
        availability_map = {}
        qty_remaining = qty_needed
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        # 1. Check availability in all sources first
        for source_wh in sources:
            source_location = source_wh.lot_stock_id
            if not source_location:
                _logger.warning(f"Line {line.id}: Skipping source WH {source_wh.name} - no stock location configured.")
                availability_map[source_wh.id] = 0.0
                continue

            available_qty = StockQuant._get_available_quantity(
                line.product_id,
                source_location,
                strict=False # Consider actual reservation strategy later if needed
            )
            availability_map[source_wh.id] = available_qty
            _logger.info(f"Line {line.id}: Source {source_wh.name} ({source_location.name}) has {available_qty:.{precision}f} available of {line.product_id.name}")

        # 2. Distribute the pull based on availability (simple sequential fill strategy)
        #    Sort sources for consistent behavior (e.g., by ID or name)
        sorted_sources = sources.sorted(key=lambda w: w.id)

        for source_wh in sorted_sources:
            if qty_remaining <= 1e-9: # Use tolerance for float comparison
                break

            available = availability_map.get(source_wh.id, 0.0)
            if available <= 0:
                continue

            # Determine qty to take from this source
            qty_to_take = min(available, qty_remaining)

            if qty_to_take > 1e-9: # Use tolerance
                 qty_to_pull_map[source_wh.id] += qty_to_take # Use += in case WH appears twice? Unlikely but safe.
                 qty_remaining -= qty_to_take
                 _logger.info(f"Line {line.id}: Planning to take {qty_to_take:.{precision}f} from {source_wh.name}. Remaining need: {qty_remaining:.{precision}f}")

        shortfall = max(0.0, qty_remaining)
        if shortfall > 1e-9:
             _logger.warning(f"Line {line.id}: Could not fulfill full quantity {qty_needed:.{precision}f}. Shortfall: {shortfall:.{precision}f} from sources {sources.ids}.")

        return dict(qty_to_pull_map), shortfall

    def _create_direct_delivery_moves(self, line, qty_to_fulfill):
        """ Scenario A: Create direct delivery moves from each source WH """
        StockMove = self.env['stock.move']
        customer_location = line.order_id.partner_shipping_id.property_stock_customer
        moves_vals_list = []
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        if not line.source_warehouse_ids:
            _logger.warning(f"Line {line.id}: Scenario A called but no source warehouses selected.")
            return

        # Calculate how much to pull from each source
        qty_to_pull_map, shortfall = self._calculate_source_quantities(line, qty_to_fulfill, line.source_warehouse_ids)

        if not qty_to_pull_map:
            _logger.warning(f"Line {line.id}: No available stock found in any selected source for Scenario A.")
            # Handle shortfall maybe by logging or creating a note? Or let standard rules try?
            # For now, we just log in _calculate_source_quantities
            return

        # Create one move per source warehouse that has quantity assigned
        for wh_id, qty_to_pull in qty_to_pull_map.items():
            if qty_to_pull <= 1e-9:  # Use tolerance
                continue

            source_wh = self.env['stock.warehouse'].browse(wh_id)
            source_location = source_wh.lot_stock_id
            # Use the specific OUT picking type for THIS source warehouse
            picking_type = source_wh.out_type_id
            if not picking_type:
                _logger.error(
                    f"No 'Delivery Orders' picking type found for source warehouse {source_wh.name}. Cannot create direct delivery move for line {line.id}.")
                # Consider raising UserError or skipping this source
                continue
            if not source_location:
                _logger.error(
                    f"No stock location found for source warehouse {source_wh.name}. Cannot create direct delivery move for line {line.id}.")
                continue

            move_vals = {
                'name': line.name,
                'product_id': line.product_id.id,
                'product_uom_qty': qty_to_pull,
                'product_uom': line.product_uom.id,
                'location_id': source_location.id,
                'location_dest_id': customer_location.id,
                'origin': line.order_id.name,
                'sale_line_id': line.id,
                'picking_type_id': picking_type.id,
                'warehouse_id': source_wh.id,  # Move governed by the source WH
                'group_id': line.order_id.procurement_group_id.id if line.order_id.procurement_group_id else False,
                'propagate_cancel': line.propagate_cancel,
                'company_id': line.company_id.id,  # Ensure company is set
            }
            moves_vals_list.append(move_vals)
            _logger.info(
                f"Line {line.id}: Prepared direct delivery move vals: {qty_to_pull:.{precision}f} from WH {source_wh.name} ({source_location.name}) using picking type {picking_type.name}")

        if moves_vals_list:
            try:
                created_moves = StockMove.sudo().create(moves_vals_list)
                # Confirm moves to create pickings (should group by WH/partner/picking_type) and trigger reservations
                created_moves._action_confirm()
                created_moves._action_assign()  # Try to reserve
                _logger.info(f"Line {line.id}: Created Scenario A moves: {created_moves.ids}")
            except Exception as e:
                _logger.error(f"Line {line.id}: Error creating/confirming Scenario A moves: {e}", exc_info=True)
                # Consider raising UserError to rollback transaction
                raise UserError(_("Failed to create direct delivery moves for line %s. Error: %s") % (line.name, e))
        # If there was a shortfall, it was logged by _calculate_source_quantities

    def _create_internal_transfer_moves(self, line, qty_to_fulfill, collect_wh):
        """ Scenario B: Create internal transfer moves to the collection WH """
        StockMove = self.env['stock.move']
        moves_vals_list = []
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        if not line.source_warehouse_ids:
            _logger.warning(f"Line {line.id}: Scenario B called but no source warehouses selected.")
            return
        if not collect_wh:
            _logger.error(f"Line {line.id}: Scenario B called but no collection warehouse provided.")
            # This should have been caught earlier, but double-check
            raise UserError(_("Cannot create internal transfers without a destination Collection Warehouse."))

        # Determine destination location and picking type for the collection WH
        collect_location = collect_wh.lot_stock_id  # Assume default stock loc for simplicity
        if not collect_location:
            raise UserError(
                _("Collection Warehouse '%s' does not have a default Stock Location configured.", collect_wh.name))

        # Find the INT picking type for the collection warehouse
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', collect_wh.id),
            # ('default_location_dest_id', '=', collect_location.id) # This might be too restrictive
        ], limit=1)
        if not picking_type:
            raise UserError(
                _("No 'Internal Transfer' picking type found for collection warehouse '%s'.", collect_wh.name))

        # Calculate how much to pull from each source
        qty_to_pull_map, shortfall = self._calculate_source_quantities(line, qty_to_fulfill, line.source_warehouse_ids)

        if not qty_to_pull_map:
            _logger.warning(f"Line {line.id}: No available stock found in any selected source for Scenario B.")
            # If no stock, no transfers are made. Standard rule will run later but likely fail/wait.
            # Shortfall logged by _calculate_source_quantities
            return

        # Create one move per source warehouse that has quantity assigned
        for wh_id, qty_to_pull in qty_to_pull_map.items():
            if qty_to_pull <= 1e-9:  # Use tolerance
                continue

            source_wh = self.env['stock.warehouse'].browse(wh_id)
            source_location = source_wh.lot_stock_id
            if not source_location:
                _logger.error(
                    f"No stock location found for source warehouse {source_wh.name}. Cannot create internal transfer move for line {line.id}.")
                continue  # Skip this source

            move_vals = {
                'name': line.name,
                'product_id': line.product_id.id,
                'product_uom_qty': qty_to_pull,
                'product_uom': line.product_uom.id,
                'location_id': source_location.id,  # Source varies
                'location_dest_id': collect_location.id,  # Destination is fixed
                'origin': line.order_id.name,
                'sale_line_id': line.id,  # Link back to SO line
                'picking_type_id': picking_type.id,  # Use the INT type of collect WH
                'warehouse_id': collect_wh.id,  # Internal Transfer governed by the destination WH
                'group_id': line.order_id.procurement_group_id.id if line.order_id.procurement_group_id else False,
                'propagate_cancel': line.propagate_cancel,
                'company_id': line.company_id.id,  # Ensure company is set
            }
            moves_vals_list.append(move_vals)
            _logger.info(
                f"Line {line.id}: Prepared internal transfer move vals: {qty_to_pull:.{precision}f} from WH {source_wh.name} ({source_location.name}) to WH {collect_wh.name} ({collect_location.name}) using picking type {picking_type.name}")

        if moves_vals_list:
            try:
                created_moves = StockMove.sudo().create(moves_vals_list)
                # Confirm moves to create Internal Transfer picking(s) and trigger reservations if possible
                created_moves._action_confirm()
                created_moves._action_assign()  # Try to reserve source stock
                _logger.info(f"Line {line.id}: Created Scenario B internal transfer moves: {created_moves.ids}")
            except Exception as e:
                _logger.error(f"Line {line.id}: Error creating/confirming Scenario B internal transfer moves: {e}",
                              exc_info=True)
                # Consider raising UserError to rollback transaction
                raise UserError(_("Failed to create internal transfer moves for line %s. Error: %s") % (line.name, e))

        # If there was a shortfall, it was logged by _calculate_source_quantities
        # The standard rule launched later for this line will handle the demand in the collect_wh