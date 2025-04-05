# -*- coding: utf-8 -*-
from odoo import fields, models, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    multi_warehouse_delivery_enabled = fields.Boolean(
        string="Enable Direct Multi-Warehouse Delivery",
        copy=False, # Don't copy this flag when duplicating SO
        help="If checked, and multi-warehouse fulfillment is enabled for the website, "
             "attempt to ship directly from selected source warehouses to the customer."
             "If unchecked, products will be gathered at the Distribution Center first.",
        default=False,
    )

    # Override _action_confirm is one option, but overriding _action_launch_stock_rule
    # on the line level is often cleaner for conditional procurement logic.
    # The logic will now live in sale.order.line

    @api.onchange('website_id')
    def _onchange_website_id_check_multi_warehouse(self):
        """
        Optionally: Reset the multi_warehouse_delivery_enabled flag if the
        website doesn't support the feature. Or set the order warehouse if needed.
        """
        if self.website_id and not self.website_id.multi_warehouse_fulfillment_enabled:
            self.multi_warehouse_delivery_enabled = False
        # You might want to automatically set self.warehouse_id based on website settings here too,
        # especially for Scenario B (Collect at DC), but this might conflict with user choice.
        # Do this carefully. Consider doing it when _action_launch_stock_rule runs for Scenario B.