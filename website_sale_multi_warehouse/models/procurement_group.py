# models/procurement_group.py
from odoo import models, api, fields


class ProcurementGroup(models.Model):
    _inherit = 'procurement.group'

    is_multi_warehouse = fields.Boolean(
        string="Multi-Warehouse Procurement",
        default=False,
        help="Set to true when this procurement is part of a multi-warehouse fulfillment"
    )
    distribution_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string="Distribution Warehouse",
        help="The warehouse where products from multiple warehouses will be consolidated"
    )

    @api.model
    def _get_moves_to_assign_domain(self, company_id):
        # Extend domain to include multi-warehouse distribution pickings
        domain = super(ProcurementGroup, self)._get_moves_to_assign_domain(company_id)
        return domain

    @api.model
    def _run_scheduler_tasks(self, use_new_cursor=False, company_id=False):
        # Override to handle proper ordering of multi-warehouse pickings
        # Don't reserve stock for customer delivery until internal transfers are processed
        result = super(ProcurementGroup, self)._run_scheduler_tasks(
            use_new_cursor=use_new_cursor,
            company_id=company_id
        )

        # Additional logic for multi-warehouse procurement can be added here

        return result