from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Multi-Warehouse settings
    enable_multi_warehouse_for_website = fields.Boolean(
        string="Enable Multi-Warehouse",
        config_parameter='website_sale_multi_warehouse.enable_multi_warehouse_for_website'
    )

    website_specific_warehouse = fields.Boolean(
        string="Use Website-Specific Warehouse",
        config_parameter='website_sale_multi_warehouse.website_specific_warehouse'
    )

    # For relational fields, use the default_model attribute
    default_distribution_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Default Distribution Center',
        default_model='stock.warehouse',
    )

    website_id = fields.Many2one(
        'website',
        string='Website',
        default_model='website',
        default=lambda self: self.env['website'].search([], limit=1)
    )

    website_distribution_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Website Distribution Center',
        default_model='stock.warehouse',
    )

    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()

        # Get default warehouse ID
        warehouse_id_str = ICP.get_param('website_sale_multi_warehouse.default_distribution_warehouse_id', '0')
        if warehouse_id_str.isdigit() and int(warehouse_id_str) > 0:
            res.update(default_distribution_warehouse_id=int(warehouse_id_str))

        # Get website-specific warehouse
        if self.website_id:
            website_warehouse_id_str = ICP.get_param(
                f'website_sale_multi_warehouse.website_{self.website_id.id}_warehouse_id', '0')
            if website_warehouse_id_str.isdigit() and int(website_warehouse_id_str) > 0:
                res.update(website_distribution_warehouse_id=int(website_warehouse_id_str))

        return res

    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()

        # Store default warehouse ID
        if self.default_distribution_warehouse_id:
            ICP.set_param('website_sale_multi_warehouse.default_distribution_warehouse_id',
                          str(self.default_distribution_warehouse_id.id))

        # Store website-specific warehouse ID
        if self.website_specific_warehouse and self.website_id and self.website_distribution_warehouse_id:
            ICP.set_param(f'website_sale_multi_warehouse.website_{self.website_id.id}_warehouse_id',
                          str(self.website_distribution_warehouse_id.id))

    @api.onchange('website_id')
    def _onchange_website_id(self):
        if self.website_id:
            ICP = self.env['ir.config_parameter'].sudo()
            website_warehouse_id_str = ICP.get_param(
                f'website_sale_multi_warehouse.website_{self.website_id.id}_warehouse_id', '0')
            if website_warehouse_id_str.isdigit() and int(website_warehouse_id_str) > 0:
                self.website_distribution_warehouse_id = int(website_warehouse_id_str)
            else:
                self.website_distribution_warehouse_id = False