# models/stock_picking.py
from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sale_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        index=True,
        help="Sales order from which this transfer was created"
    )