# -*- coding: utf-8 -*-
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class WebsiteSaleMultiWarehouse(WebsiteSale):

    def _prepare_order_line_values(self, product_id, quantity, **kwargs):
        """
        Override to capture selected source warehouses from website form
        and add them to the sale order line values.
        """
        values = super(WebsiteSaleMultiWarehouse, self)._prepare_order_line_values(
            product_id, quantity, **kwargs
        )

        website = request.website
        if website.multi_warehouse_fulfillment_enabled:
            # source_warehouse_ids might be sent as a list of strings from the form
            source_warehouse_ids_str = request.httprequest.form.getlist('source_warehouse_ids')
            if source_warehouse_ids_str:
                try:
                    # Convert string IDs to integers
                    source_warehouse_ids = [int(wh_id) for wh_id in source_warehouse_ids_str]
                    # Use Odoo's command format for Many2many fields
                    values['source_warehouse_ids'] = [(6, 0, source_warehouse_ids)]
                    _logger.info(f"Adding source warehouses {source_warehouse_ids} to line values for product {product_id}")
                except ValueError as e:
                    _logger.error(f"Could not convert source warehouse IDs: {source_warehouse_ids_str}. Error: {e}")
                    # Optionally handle the error, e.g., ignore, show message

        return values