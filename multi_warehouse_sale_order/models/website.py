from odoo import models, fields

class Website(models.Model):
    _inherit = 'website'

    multi_wh_enabled = fields.Boolean("Enable Multi-Warehouse Sourcing", default=True)
    default_warehouse_id = fields.Many2one('stock.warehouse', string="Default Delivery Warehouse")
    use_multi_wh_setting = fields.Boolean("Enable Multi-Warehouse Delivery", default=False,
        help="When enabled, orders from this website will use multi-warehouse delivery settings")