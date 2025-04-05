# models/stock_warehouse.py
from odoo import models, fields, api


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    website_ids = fields.Many2many('website', string="Websites")

    is_distribution_center = fields.Boolean(
        string="Is Distribution Center",
        default=False,
        help="Mark this warehouse as a distribution center for multi-warehouse fulfillment"
    )

    is_ecommerce_source = fields.Boolean(
        string="Use for eCommerce Sourcing",
        default=False,
        help="When enabled, this warehouse may be used to source products for eCommerce orders"
    )

    ecommerce_priority = fields.Integer(
        string="eCommerce Priority",
        default=10,
        help="Lower numbers have higher priority for eCommerce sourcing"
    )

    delivery_route_id = fields.Many2one(
        'stock.route',
        string="Delivery Route",
        domain="[('warehouse_ids', '!=', False), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Default route to use for deliveries from this distribution center"
    )

    website_ids = fields.Many2many(
        'website',
        string="Websites",
        help="Websites that can use this warehouse"
    )

    @api.onchange('is_distribution_center')
    def _onchange_is_distribution_center(self):
        if self.is_distribution_center:
            # A distribution center should also be an e-commerce source
            self.is_ecommerce_source = True