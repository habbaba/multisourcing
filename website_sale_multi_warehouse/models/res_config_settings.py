# models/res_config_settings.py
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Changed field name to avoid "default_" prefix
    distribution_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string="Default Distribution Center",
        domain=[('is_distribution_center', '=', True)],
        config_parameter='website_sale_multi_warehouse.default_distribution_warehouse_id'
    )

    enable_multi_warehouse_for_website = fields.Boolean(
        string="Enable Multi-Warehouse for Website Sales",
        config_parameter='website_sale_multi_warehouse.enable_multi_warehouse_for_website',
        default=True
    )

    sourcing_method = fields.Selection([
        ('priority', 'Warehouse Priority'),
        ('availability', 'Stock Availability'),
        ('distance', 'Customer Distance')
    ], string="Warehouse Sourcing Method",
        config_parameter='website_sale_multi_warehouse.sourcing_method',
        default='availability')