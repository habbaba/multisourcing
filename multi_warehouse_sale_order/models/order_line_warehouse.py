from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SaleOrderLineWarehouse(models.Model):
    _name = "sale.order.line.warehouse"

    name_report = fields.Char(compute='_compute_name_report')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True, check_company=True)
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True,
                                 default=lambda self: self.env.company)
    order_line_id = fields.Many2one('sale.order.line', string='Order Line', ondelete='cascade')

    product_uom_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', required=True, default=1.0)
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure')

    available_quantity = fields.Float(string='Available Quantity', compute='_compute_available_quantity')

    _sql_constraints = [
        ('uniqueness_employee', 'UNIQUE(order_line_id,warehouse_id)',
         'Duplicate warehouse. It should be one warehouse for one line.'),
    ]

    @api.depends('warehouse_id')
    def _compute_available_quantity(self):
        product = self.env['product.product'].browse(int(self.env.context.get('current_product_id')))

        for line in self:
            available_qty = 0.0
            if line.warehouse_id:
                available_qty = self.env['stock.quant']._get_available_quantity(product,
                                                                                line.warehouse_id.lot_stock_id)
            line.available_quantity = available_qty

    @api.onchange('product_uom_qty')
    def product_uom_qty_change(self):
        if self.product_uom_qty <= 0:
            raise ValidationError(_('The Quantity must be greater than 0.'))

    def name_get(self):
        res = []
        for line in self:
            name = "%s(%s)" % (line.warehouse_id.name, line.product_uom_qty)
            res.append((line.id, name))
        return res

    def unlink(self):
        return super(SaleOrderLineWarehouse, self).unlink()

    def _compute_name_report(self):
        for line in self:
            line.name_report = "%s(%s)" % (line.warehouse_id.name, line.product_uom_qty)
