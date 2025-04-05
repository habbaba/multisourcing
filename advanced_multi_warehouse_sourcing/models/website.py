# -*- coding: utf-8 -*-
from odoo import fields, models

class Website(models.Model):
    _inherit = 'website'

    multi_warehouse_fulfillment_enabled = fields.Boolean(
        string="Enable Multi-Warehouse Fulfillment",
        help="Enable multi-warehouse fulfillment features for orders originating from this website.",
    )
    multi_warehouse_fulfillment_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string="Distribution Center Warehouse",
        help="The central warehouse where products will be collected when direct multi-warehouse delivery is not used.",
        domain="[('company_id', '=', company_id)]" # Ensure warehouse belongs to website's company
    )

    # Also add related fields to res.config.settings for easy configuration
class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    website_multi_warehouse_fulfillment_enabled = fields.Boolean(
        related='website_id.multi_warehouse_fulfillment_enabled',
        readonly=False
    )
    website_multi_warehouse_fulfillment_warehouse_id = fields.Many2one(
        related='website_id.multi_warehouse_fulfillment_warehouse_id',
        readonly=False
    )