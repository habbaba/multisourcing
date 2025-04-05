from odoo import models, api, fields


class Website(models.Model):
    _inherit = 'website'

    def _prepare_order_values(self, partner, pricelist):
        """Prepare the values for the creation of a new sale order for website orders.
        Adds distribution warehouse data for multi-warehouse functionality."""
        order_vals = super()._prepare_order_values(partner, pricelist)

        # Check if multi-warehouse is enabled
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('website_sale_multi_warehouse.enable_multi_warehouse_for_website'):
            # Set multi-warehouse flag
            order_vals['is_website_multi_warehouse'] = True

            # Set distribution center based on current website
            distribution_warehouse_id = int(ICP.get_param(
                f'website_sale_multi_warehouse.default_distribution_warehouse_id_website_{self.id}', '0'))
            if not distribution_warehouse_id:
                # Fall back to company's default if website-specific isn't set
                distribution_warehouse_id = int(ICP.get_param(
                    f'website_sale_multi_warehouse.default_distribution_warehouse_id_company_{self.company_id.id}',
                    '0'))
            if not distribution_warehouse_id:
                # Fall back to global default if neither is set
                distribution_warehouse_id = int(ICP.get_param(
                    'website_sale_multi_warehouse.default_distribution_warehouse_id', '0'))

            if distribution_warehouse_id:
                # Verify the warehouse exists and is accessible to the company
                warehouse = self.env['stock.warehouse'].sudo().browse(distribution_warehouse_id)
                if warehouse.exists() and (not warehouse.company_id or warehouse.company_id == self.company_id):
                    order_vals['distribution_warehouse_id'] = distribution_warehouse_id

            # Set company on the order
            order_vals['company_id'] = self.company_id.id

        return order_vals

    def sale_get_order(self, force_create=False, update_pricelist=False):
        """Override to ensure warehouse settings are updated when needed."""
        order = super().sale_get_order(force_create, update_pricelist)
        if order and not order.distribution_warehouse_id:
            # Check if multi-warehouse is enabled
            ICP = self.env['ir.config_parameter'].sudo()
            if ICP.get_param('website_sale_multi_warehouse.enable_multi_warehouse_for_website'):
                # Get the appropriate distribution warehouse
                distribution_warehouse_id = int(ICP.get_param(
                    f'website_sale_multi_warehouse.default_distribution_warehouse_id_website_{self.id}', '0'))
                if not distribution_warehouse_id:
                    distribution_warehouse_id = int(ICP.get_param(
                        f'website_sale_multi_warehouse.default_distribution_warehouse_id_company_{self.company_id.id}',
                        '0'))
                if not distribution_warehouse_id:
                    distribution_warehouse_id = int(ICP.get_param(
                        'website_sale_multi_warehouse.default_distribution_warehouse_id', '0'))

                if distribution_warehouse_id:
                    # Verify the warehouse exists and is accessible
                    warehouse = self.env['stock.warehouse'].sudo().browse(distribution_warehouse_id)
                    if warehouse.exists() and (not warehouse.company_id or warehouse.company_id == self.company_id):
                        order.with_company(order.company_id).write({
                            'distribution_warehouse_id': distribution_warehouse_id,
                            'is_website_multi_warehouse': True
                        })
        return order

    def _get_warehouse_available(self):
        """Get warehouses available for the current website"""
        self.ensure_one()
        warehouse_domain = [
            '|', ('website_ids', '=', False),
            ('website_ids', 'in', self.id),
            '|', ('company_id', '=', False),
            ('company_id', '=', self.company_id.id)
        ]
        return self.env['stock.warehouse'].sudo().search(warehouse_domain)