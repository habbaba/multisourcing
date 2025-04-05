from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    website_multi_wh_enabled = fields.Boolean(
        related='website_id.multi_wh_enabled',
        readonly=False,
        string="Enable Multi-Warehouse Sourcing")
    website_default_warehouse_id = fields.Many2one(
        'stock.warehouse',
        related='website_id.default_warehouse_id',
        readonly=False,
        string="Default Delivery Warehouse")
    website_use_multi_wh_setting = fields.Boolean(
        related='website_id.use_multi_wh_setting',
        readonly=False,
        string="Enable Multi-Warehouse Delivery")