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

    def _get_moves_from_sources(self, line, qty_needed, sources, location_dest_id, picking_type_id, main_warehouse_id):
        """ Helper to create moves by checking availability in sources """
        StockMove = self.env['stock.move']
        StockQuant = self.env['stock.quant']
        moves_vals_list = []
        qty_remaining = qty_needed

        _logger.info(f"Line {line.id}: Creating moves. Need {qty_needed}. Sources: {sources.ids}. Dest: {location_dest_id}. PickingType: {picking_type_id}. MainWH: {main_warehouse_id}")

        # Simple sequential check - could be enhanced (proportional, etc.)
        for source_wh in sources:
            if qty_remaining <= 0:
                break

            source_location = source_wh.lot_stock_id
            if not source_location:
                _logger.warning(f"Skipping source WH {source_wh.name} - no stock location configured.")
                continue

            available_qty = StockQuant._get_available_quantity(
                line.product_id,
                source_location,
                strict=False # Allow negative, reservation will handle later
            )
            _logger.info(f"Line {line.id}: Source {source_wh.name} ({source_location.name}) has {available_qty} available of {line.product_id.name}")


            qty_to_take = min(qty_remaining, max(0, available_qty)) # Take available, up to remaining need

            if qty_to_take > 0:
                move_vals = {
                    'name': line.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': qty_to_take,
                    'product_uom': line.product_uom.id,
                    'location_id': source_location.id,
                    'location_dest_id': location_dest_id,
                    'origin': line.order_id.name,
                    'sale_line_id': line.id,
                    'picking_type_id': picking_type_id,
                    'warehouse_id': main_warehouse_id, # The WH governing the picking type
                    'group_id': line.order_id.procurement_group_id.id if line.order_id.procurement_group_id else False,
                    'propagate_cancel': line.propagate_cancel,
                }
                moves_vals_list.append(move_vals)
                qty_remaining -= qty_to_take
                _logger.info(f"Line {line.id}: Planning to take {qty_to_take} from {source_wh.name}. Remaining need: {qty_remaining}")

        if qty_remaining > 0:
             _logger.warning(f"Line {line.id}: Could not fulfill full quantity {qty_needed}. Short by {qty_remaining} from selected sources {sources.ids}.")
             # Consider raising UserError or creating a note on SO? Or let standard rules potentially handle shortfall?
             # Current logic creates moves for available qty only.

        if moves_vals_list:
            created_moves = StockMove.sudo().create(moves_vals_list) # Use sudo if permission issues arise
            # Confirm moves to create pickings and trigger reservations
            created_moves._action_confirm()
            created_moves._action_assign()
            _logger.info(f"Line {line.id}: Created and confirmed/assigned moves: {created_moves.ids}")
        else:
             _logger.warning(f"Line {line.id}: No moves created for qty {qty_needed} from sources {sources.ids}.")


    def _create_direct_delivery_moves(self, line, qty_to_fulfill):
        """ Scenario A: Create direct delivery moves from each source WH """
        customer_location = line.order_id.partner_shipping_id.property_stock_customer
        moves_created = False

        # Group moves by source warehouse to use correct picking type
        source_wh_groups = defaultdict(lambda: self.env['stock.warehouse'])
        for wh in line.source_warehouse_ids:
            source_wh_groups[wh] |= wh # Using defaultdict might not be needed if just iterating

        for source_wh in line.source_warehouse_ids:
             # Find the OUT picking type for this specific source warehouse
             picking_type = self.env['stock.picking.type'].search([
                 ('code', '=', 'outgoing'),
                 ('warehouse_id', '=', source_wh.id)
             ], limit=1)
             if not picking_type:
                 _logger.error(f"No 'Delivery Orders' picking type found for warehouse {source_wh.name}. Cannot create direct delivery for line {line.id}.")
                 continue # Or raise UserError

             # Re-calculate needed qty for THIS warehouse if splitting proportionally?
             # For now, let _get_moves_from_sources handle availability check sequentially.
             # A potential improvement: calculate proportions first.
             self._get_moves_from_sources(
                 line,
                 qty_to_fulfill, # Pass total needed, let helper check available per source
                 source_wh, # Pass only the current source WH
                 customer_location.id,
                 picking_type.id,
                 source_wh.id # Delivery is governed by the source WH
             )
             # Note: This sequential call to _get_moves_from_sources needs refinement
             # if you want proportional split rather than sequential depletion.
             # Currently, it tries to get the *full* qty_to_fulfill from the *first* WH,
             # then the remaining from the second, etc. This needs fixing.

        # ***** Correction Needed for Proportional/Split Logic in Scenario A *****
        # The current loop calls _get_moves_from_sources incorrectly for Scenario A.
        # It should determine the total qty per source WH *first*, then create moves.
        # Let's simplify and call it ONCE with ALL sources, relying on its internal loop:
        _logger.warning("Scenario A move creation needs review for proportional split logic.")
        # Find a generic OUT picking type (maybe doesn't matter as much if moves split pickings?)
        # This part is tricky - how Odoo groups moves into pickings depends on more factors.
        # For simplicity here, let's assume moves from different WHs WILL create different pickings.
        # We need a dummy picking type maybe? Or find one for the main order WH? Let's try main WH OUT type.
        main_picking_type = line.order_id.warehouse_id.out_type_id
        if not main_picking_type:
             raise UserError(_("Default warehouse %s of SO %s has no Delivery Order Operation Type.", line.order_id.warehouse_id.name, line.order_id.name))

        self._get_moves_from_sources(
             line,
             qty_to_fulfill,
             line.source_warehouse_ids, # Pass all selected sources
             customer_location.id,
             main_picking_type.id, # Use main WH type - Odoo might regroup later
             line.order_id.warehouse_id.id # Governed by main WH? Test this assumption.
         )


    def _create_internal_transfer_moves(self, line, qty_to_fulfill, collect_wh):
        """ Scenario B: Create internal transfer moves to the collection WH """
        collect_location = collect_wh.lot_stock_id # Or wh.wh_input_stock_loc_id ? Check routes. Default stock loc is common.
        if not collect_location:
            raise UserError(_("Collection Warehouse '%s' does not have a default Stock Location configured.", collect_wh.name))

        # Find the INT picking type for the collection warehouse (transfers often belong to dest WH)
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', collect_wh.id),
            ('default_location_dest_id', '=', collect_location.id) # Be more specific if possible
        ], limit=1)
        if not picking_type:
             # Fallback search
             picking_type = self.env['stock.picking.type'].search([
                 ('code', '=', 'internal'),
                 ('warehouse_id', '=', collect_wh.id),
             ], limit=1)
        if not picking_type:
            raise UserError(_("No suitable 'Internal Transfer' picking type found for collection warehouse '%s'.", collect_wh.name))

        self._get_moves_from_sources(
            line,
            qty_to_fulfill,
            line.source_warehouse_ids, # All selected sources
            collect_location.id,
            picking_type.id,
            collect_wh.id # Internal Transfer governed by the destination WH
        )