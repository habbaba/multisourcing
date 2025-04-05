# -*- coding: utf-8 -*-
from odoo import fields, models

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    source_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string="Allowed Source Warehouses",
        help="Warehouses that can potentially source this product for multi-warehouse fulfillment."
    )