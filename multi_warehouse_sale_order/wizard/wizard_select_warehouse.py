from odoo import fields, models, _
from odoo.exceptions import ValidationError


class OrderLineWarehouse(models.TransientModel):
    _name = 'short.order.line.warehouse'
    _description = 'Select Warehouse Wizard'

    order_line_id = fields.Many2one('sale.order.line', required=True)
    order_line_warehouse = fields.One2many(comodel_name='sale.order.line.warehouse',
                                           related='order_line_id.order_line_warehouse', readonly=False, )

    product_id = fields.Many2one('product.product', string='Product', related='order_line_id.product_id', readonly=True)
    product_uom_qty = fields.Float(string='Picked Quantity', related='order_line_id.product_uom_qty', readonly=True)
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure', related='order_line_id.product_uom',
                                  readonly=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True,
                                 related='order_line_id.company_id')

    def save_selected_warehouse(self):
        if sum(self.order_line_warehouse.mapped('product_uom_qty')) != self.product_uom_qty:
            raise ValidationError(_('Total picked quantity must be equal to %s.' % str(self.product_uom_qty)))
