from odoo import models, api


class Website(models.Model):
    _inherit = 'website'

    def _prepare_order_values(self, partner, pricelist):
        order_vals = super()._prepare_order_values(partner, pricelist)

        # Check if multi-warehouse is enabled
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('website_sale_multi_warehouse.enable_multi_warehouse_for_website'):
            # Set multi-warehouse flag
            order_vals['is_website_multi_warehouse'] = True

            # Set distribution center
            distribution_warehouse_id = int(ICP.get_param(
                'website_sale_multi_warehouse.default_distribution_warehouse_id', '0'))
            if distribution_warehouse_id:
                order_vals['distribution_warehouse_id'] = distribution_warehouse_id

        return order_vals