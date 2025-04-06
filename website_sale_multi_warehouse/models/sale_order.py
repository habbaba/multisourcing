# models/sale_order.py
from odoo import models, fields, api
from collections import defaultdict


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_multi_warehouse = fields.Boolean(
        string="Multi-Warehouse Order",
        compute="_compute_is_multi_warehouse",
        store=True,
        help="Indicates if this order will be fulfilled from multiple warehouses"
    )

    is_website_multi_warehouse = fields.Boolean(
        string="Website Multi-Warehouse Order",
        default=False,
        help="Marks orders from website for multi-warehouse processing"
    )

    distribution_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string="Distribution Center",
        domain=[('is_distribution_center', '=', True)]
    )

    sourcing_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string="Sourcing Warehouses",
        compute="_compute_sourcing_warehouses",
        store=True
    )

    internal_transfer_ids = fields.One2many(
        'stock.picking', 'sale_id',
        string="Internal Transfers",
        domain=[('picking_type_code', '=', 'internal')],
        help="Internal transfers created for multi-warehouse fulfillment"
    )

    def _cart_update(self, product_id=None, line_id=None, add_qty=0, set_qty=0, **kwargs):
        result = super()._cart_update(product_id, line_id, add_qty, set_qty, **kwargs)

        if self.website_id:
            # Mark as website multi-warehouse order
            ICP = self.env['ir.config_parameter'].sudo()
            if ICP.get_param('website_sale_multi_warehouse.enable_multi_warehouse_for_website'):
                self.is_website_multi_warehouse = True

            # Update distribution warehouse if needed and not already set
            if not self.distribution_warehouse_id:
                distribution_warehouse_id = int(ICP.get_param(
                    'website_sale_multi_warehouse.default_distribution_warehouse_id', '0'))
                if distribution_warehouse_id:
                    self.distribution_warehouse_id = distribution_warehouse_id

        return result

    @api.depends('order_line.product_id', 'order_line.product_uom_qty', 'website_id')
    def _compute_sourcing_warehouses(self):
        param = self.env['ir.config_parameter'].sudo()
        enable_multi_warehouse = param.get_param('website_sale_multi_warehouse.enable_multi_warehouse_for_website',
                                                 False)

        for order in self:
            warehouses = self.env['stock.warehouse']

            # Only apply for website orders if enabled
            if not (order.website_id and enable_multi_warehouse):
                order.sourcing_warehouse_ids = warehouses
                continue

            # Find eligible warehouses (that are marked as eCommerce sources)
            eligible_warehouses = self.env['stock.warehouse'].search([
                ('is_ecommerce_source', '=', True),
            ], order='ecommerce_priority asc')  # Order by priority (lowest first)

            if eligible_warehouses:
                order.sourcing_warehouse_ids = eligible_warehouses
            elif order.distribution_warehouse_id:
                order.sourcing_warehouse_ids = order.distribution_warehouse_id
            else:
                # Fallback to default warehouse
                default_warehouse = self.env['stock.warehouse'].search([], limit=1)
                order.sourcing_warehouse_ids = default_warehouse

    @api.depends('sourcing_warehouse_ids', 'is_website_multi_warehouse')
    def _compute_is_multi_warehouse(self):
        for order in self:
            # Mark as multi-warehouse if multiple warehouses OR it's a flagged website order
            order.is_multi_warehouse = len(order.sourcing_warehouse_ids) > 1 or order.is_website_multi_warehouse

    def _action_confirm(self):
        res = super()._action_confirm()

        # Only process if this is a multi-warehouse order
        for order in self:
            if not order.is_website_multi_warehouse or not order.distribution_warehouse_id:
                continue

            # For each order line
            for line in order.order_line:
                needed_qty = line.product_uom_qty
                # Use the computed field, not the compute method
                for warehouse in order.sourcing_warehouse_ids:
                    available = self._get_available_qty(warehouse, line.product_id)
                    if available > 0:
                        # Create move from this warehouse to distribution
                        qty_to_take = min(available, needed_qty)
                        self._create_warehouse_transfer(line, warehouse, qty_to_take)
                        needed_qty -= qty_to_take
                        if needed_qty <= 0:
                            break

        return res

    def _get_available_qty(self, warehouse, product):
        """Get available quantity of product in specified warehouse"""
        # Get the stock location of this warehouse
        location = warehouse.lot_stock_id
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', 'child_of', location.id),
            ('location_id.usage', '=', 'internal'),
        ])

        # Sum the available quantities
        available_qty = sum(quant.available_quantity for quant in quants)
        return available_qty

    def _create_warehouse_transfer(self, line, warehouse, qty):
        """Create inter-warehouse transfer from source warehouse to distribution center"""
        if not self.distribution_warehouse_id or not qty:
            return

        # Get or create procurement group
        if not self.procurement_group_id:
            vals = {
                'name': self.name,
                'move_type': self.picking_policy,
                'sale_id': self.id,
                'partner_id': self.partner_id.id,
            }
            self.procurement_group_id = self.env["procurement.group"].create(vals)

        procurement_group = self.procurement_group_id

        # Get internal transfer types
        source_internal_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id),
        ], limit=1)

        dest_internal_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', self.distribution_warehouse_id.id),
        ], limit=1)

        if not source_internal_type or not dest_internal_type:
            return

        # Ensure we have valid locations
        source_location = warehouse.lot_stock_id
        dest_location = self.distribution_warehouse_id.lot_stock_id

        if not source_location or not dest_location:
            return

        # Use guaranteed internal location as transit
        transit_location = self.env.ref('stock.stock_location_inter_wh', raise_if_not_found=False)
        if not transit_location:
            transit_location = self.env['stock.location'].search([('usage', '=', 'transit')], limit=1)
        if not transit_location:
            transit_location = self.env['stock.location'].create({
                'name': 'Inter-Warehouse Transit',
                'usage': 'transit',
            })

        # Create outgoing transfer
        out_picking = self.env['stock.picking'].create({
            'picking_type_id': source_internal_type.id,
            'location_id': source_location.id,
            'location_dest_id': transit_location.id,
            'origin': f"{self.name} (To DC)",
            'partner_id': self.partner_id.id,
            'sale_id': self.id,
            'group_id': procurement_group.id,
        })

        # Create incoming transfer
        in_picking = self.env['stock.picking'].create({
            'picking_type_id': dest_internal_type.id,
            'location_id': transit_location.id,
            'location_dest_id': dest_location.id,
            'origin': f"{self.name} (From {warehouse.name})",
            'partner_id': self.partner_id.id,
            'sale_id': self.id,
            'group_id': procurement_group.id,
        })

        # Create moves
        out_move = self.env['stock.move'].create({
            'name': line.product_id.name,
            'product_id': line.product_id.id,
            'product_uom_qty': qty,
            'product_uom': line.product_uom.id,
            'picking_id': out_picking.id,
            'location_id': source_location.id,
            'location_dest_id': transit_location.id,
            'sale_line_id': line.id,
            'group_id': procurement_group.id,
        })

        in_move = self.env['stock.move'].create({
            'name': line.product_id.name,
            'product_id': line.product_id.id,
            'product_uom_qty': qty,
            'product_uom': line.product_uom.id,
            'picking_id': in_picking.id,
            'location_id': transit_location.id,
            'location_dest_id': dest_location.id,
            'sale_line_id': line.id,
            'group_id': procurement_group.id,
        })

        # Link the moves
        out_move.move_dest_ids = [(4, in_move.id)]
        in_move.move_orig_ids = [(4, out_move.id)]

        # Confirm pickings
        out_picking.action_confirm()
        in_picking.action_confirm()

        return out_picking, in_picking

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_procurement_values(self, group_id=False):
        """Override to use the distribution warehouse for website orders"""
        values = super(SaleOrderLine, self)._prepare_procurement_values(group_id)

        # Check if this is a website order with multi-warehouse enabled
        if (self.order_id.website_id and self.order_id.is_website_multi_warehouse and
                self.order_id.distribution_warehouse_id):
            # Use the distribution warehouse
            warehouse = self.order_id.distribution_warehouse_id
            values['warehouse_id'] = warehouse

            # Update route_ids if needed
            if warehouse.delivery_route_id:
                # Important: Use a proper recordset with a specific field, not direct assignment
                if 'route_ids' in values:
                    # Append to existing routes
                    values['route_ids'] += warehouse.delivery_route_id
                else:
                    # Create new routes field
                    values['route_ids'] = warehouse.delivery_route_id

        return values