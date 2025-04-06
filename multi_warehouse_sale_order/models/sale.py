from odoo import api, models, fields, _
from odoo.tools import float_compare
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_multi_wh_line = fields.Selection([
        ('0', 'Choose one warehouse on sale order line.'),
        ('1', 'Choose multi warehouse on sale order line.'),
        ('2', 'Choose sale order warehouse.'),
    ], "Multi Warehouse Sale Order", default='0', copy=False,
        help="Sale person is able to choose one or multi warehouse on sale order line.")

    @api.onchange('is_multi_wh_line')
    def multi_wh_change(self):
        for line in self.order_line:
            line._update_available_warehouse()
            line._compute_qty_at_date()

    @api.onchange('warehouse_id')
    def warehouse_change(self):
        if self.is_multi_wh_line == '2':
            for line in self.order_line:
                line._update_available_warehouse()
                line._compute_qty_at_date()

    @api.model_create_multi
    def create(self, vals):
        res = super(SaleOrder, self).create(vals)
        for o in res:
            if o.website_id:
                o.is_multi_wh_line = '1'
                for line in o.order_line:
                    line._update_available_warehouse()
                    line._compute_qty_at_date()
        return res

    def action_confirm(self):
        if self.is_multi_wh_line == '0' and any(not line.sale_warehouse_id and not line.display_type for line in self.order_line):
            for line in self.order_line:
                line._update_available_warehouse()
                line._update_warehouse_line_details()

        if self.is_multi_wh_line != '1' and self.website_id:
            self.is_multi_wh_line = '1'

        if self.is_multi_wh_line == '1' and self.website_id:
            for line in self.order_line:
                line._update_available_warehouse()
                line._compute_qty_at_date()
        return super(SaleOrder, self).action_confirm()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    order_line_warehouse = fields.One2many('sale.order.line.warehouse', 'order_line_id', copy=False)

    sale_warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', copy=False,
                                        states={'draft': [('readonly', False)], 'sent': [('readonly', False)]},
                                        check_company=True)

    sale_warehouse_ids = fields.Many2many(
        'stock.warehouse', string='Warehouses', copy=False,
        states={'draft': [('readonly', False)], 'sent': [('readonly', False)]},
        check_company=True)

    warehouse_id = fields.Many2one(related='sale_warehouse_id')

    show_button_warehouse = fields.Boolean(compute='_compute_show_button_warehouse')

    @api.onchange('product_id')
    def _onchange_product_id_warning(self):
        self._update_available_warehouse()
        result = super(SaleOrderLine, self)._onchange_product_id_warning()
        return result

    @api.onchange('product_uom', 'product_uom_qty')
    def product_uom_change(self):
        self._update_available_warehouse()
        self._compute_qty_at_date()


    @api.model_create_multi
    def create(self, vals_list):
        lines = super(SaleOrderLine, self).create(vals_list)
        if lines.order_id.is_multi_wh_line == '1':
            for line in lines:
                if not line.order_line_warehouse:
                    total_available_qty = 0
                    warehouse_count = 0
                    for w in line.sale_warehouse_ids:
                        warehouse_count += 1
                        available_qty = self.env['stock.quant']._get_available_quantity(line.product_id, w.lot_stock_id)
                        if available_qty >= line.product_uom_qty:
                            self.env['sale.order.line.warehouse'].create({
                                'warehouse_id': w.id,
                                'company_id': line.company_id.id,
                                'order_line_id': line.id,
                                'product_uom_qty': line.product_uom_qty,
                                'product_uom': line.product_uom.id
                            })

                            break
                        elif available_qty > 0 and line.product_uom_qty > total_available_qty:
                            qty = available_qty if line.product_uom_qty - total_available_qty > available_qty else line.product_uom_qty - total_available_qty
                            total_available_qty += available_qty

                            # Last warehouse
                            if total_available_qty < line.product_uom_qty and warehouse_count == len(line.sale_warehouse_ids):
                                qty = line.product_uom_qty - (total_available_qty - available_qty)

                            self.env['sale.order.line.warehouse'].create({
                                'warehouse_id': w.id,
                                'company_id': line.company_id.id,
                                'order_line_id': line.id,
                                'product_uom_qty': qty,
                                'product_uom': line.product_uom.id
                            })
                        elif available_qty == 0:
                            self.env['sale.order.line.warehouse'].create({
                                'warehouse_id': w.id,
                                'company_id': line.company_id.id,
                                'order_line_id': line.id,
                                'product_uom_qty': line.product_uom_qty - total_available_qty,
                                'product_uom': line.product_uom.id
                            })

            lines.filtered(lambda line: line.state == 'sale')._action_launch_stock_rule()
        return lines

    def write(self, values):
        if self.order_id.is_multi_wh_line != '1' and self.order_line_warehouse:
            self.order_line_warehouse.unlink()
        res = super(SaleOrderLine, self).write(values)

        if 'product_uom_qty' in values:
            self._update_available_warehouse()

            if self.order_id.is_multi_wh_line == '1' and self.sale_warehouse_ids:
                if self.order_line_warehouse:
                    self.order_line_warehouse.unlink()
                self._update_warehouse_line_details()

        if 'order_line_warehouse' in values:
            if sum(self.order_line_warehouse.mapped('product_uom_qty')) != self.product_uom_qty:
                raise ValidationError(_('Total picked quantity must be equal to %s.' % str(self.product_uom_qty)))

        for o_line in self:
            if not isinstance(o_line.id, models.NewId) and o_line.order_id.is_multi_wh_line == '1' and o_line.sale_warehouse_ids:
                if not o_line.order_line_warehouse:
                    o_line._update_warehouse_line_details()
                elif o_line.order_line_warehouse and 'order_line_warehouse' in values:
                    available_warehouse = []
                    # Delete order line warehouse
                    if len(o_line.order_line_warehouse) < len(o_line.sale_warehouse_ids):
                        for line in o_line.sale_warehouse_ids:
                            if line.id in o_line.order_line_warehouse.mapped("warehouse_id").ids:
                                available_warehouse.append(line.id)

                    # Add new order line warehouse
                    elif len(o_line.order_line_warehouse) > len(o_line.sale_warehouse_ids):
                        for wh_id in o_line.order_line_warehouse.mapped("warehouse_id").ids:
                            available_warehouse.append(wh_id)

                    if available_warehouse:
                        val = {'sale_warehouse_ids': [[6, False, available_warehouse]]}
                        o_line.write(val)

        return res

    def action_select_warehouse(self):
        view_id = self.env.ref('multi_warehouse_sale_order.select_warehouse_view_form').id
        name = _('Manual Select Warehouse')

        context = {
            'default_order_line_id': self.id,
            'current_product_id': self.product_id.id,
        }

        return {
            'name': name,
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'short.order.line.warehouse',
            'view_id': view_id,
            'views': [(view_id, 'form')],
            'target': 'new',
            'context': context
        }

    def _update_available_warehouse(self):
        if not self.product_id:
            return

        self.sale_warehouse_ids = False
        self.sale_warehouse_id = False
        total_available_qty = 0
        available_warehouse = []

        if self.order_id.is_multi_wh_line == '2':
            self.sale_warehouse_id = self.order_id.warehouse_id
            self.sale_warehouse_ids = self.order_id.warehouse_id
        else:
            biggest_available_qty = 0
            wh_available = False

            warehouses = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)])
            for w in warehouses:
                available_qty = self.env['stock.quant']._get_available_quantity(self.product_id, w.lot_stock_id)
                if self.order_id.is_multi_wh_line == '1':
                    if available_qty >= self.product_uom_qty:
                        self.sale_warehouse_ids = w
                        break
                    elif available_qty > 0:
                        if total_available_qty < self.product_uom_qty:
                            available_warehouse.append(w.id)
                            total_available_qty += available_qty
                else:
                    if available_qty > biggest_available_qty:
                        biggest_available_qty = available_qty
                        wh_available = w

            if self.order_id.is_multi_wh_line == '0' and wh_available:
                self.sale_warehouse_id = wh_available
                self.sale_warehouse_ids = wh_available
            elif self.order_id.is_multi_wh_line == '0' and not wh_available:
                self.sale_warehouse_id = self.order_id.warehouse_id
                self.sale_warehouse_ids = self.order_id.warehouse_id

        if self.order_id.is_multi_wh_line == '1' and not self.sale_warehouse_ids:
            if available_warehouse:
                self.write({'sale_warehouse_ids': [[6, False, available_warehouse]]})
            else:
                # Default
                self.sale_warehouse_ids = self.order_id.warehouse_id

    def _update_warehouse_line_details(self):
        total_picked_qty = 0
        count = 0
        for w in self.sale_warehouse_ids:
            count += 1
            available_qty = self.env['stock.quant']._get_available_quantity(self.product_id, w.lot_stock_id)
            if available_qty >= self.product_uom_qty:
                vals = self._prepare_line_warehouse(w, self.product_uom_qty)
                i = self.env['sale.order.line.warehouse'].create(vals)
                break
            elif 0 < available_qty < self.product_uom_qty - total_picked_qty:
                if count < len(self.sale_warehouse_ids):
                    vals = self._prepare_line_warehouse(w, available_qty)
                    total_picked_qty += available_qty
                else:
                    vals = self._prepare_line_warehouse(w, self.product_uom_qty - total_picked_qty)
                self.env['sale.order.line.warehouse'].create(vals)
            elif 0 < available_qty and available_qty >= self.product_uom_qty - total_picked_qty:
                vals = self._prepare_line_warehouse(w, self.product_uom_qty - total_picked_qty)
                total_picked_qty += self.product_uom_qty - total_picked_qty
                self.env['sale.order.line.warehouse'].create(vals)
            elif available_qty == 0:
                vals = self._prepare_line_warehouse(w, self.product_uom_qty - total_picked_qty)
                self.env['sale.order.line.warehouse'].create(vals)

    def _prepare_line_warehouse(self, warehosue, product_uom_qty):
        return {
            'warehouse_id': warehosue.id,
            'company_id': self.company_id.id,
            'order_line_id': self.id,
            'product_uom_qty': product_uom_qty,
            'product_uom': self.product_uom.id
        }

    @api.onchange('sale_warehouse_ids')
    def sale_warehouse_ids_change(self):
        if self.sale_warehouse_ids:
            warehouses = self.env['stock.warehouse'].search(
                [('id', 'in', self.sale_warehouse_ids.ids), ('company_id', '=', self.company_id.id)])
            if len(self.sale_warehouse_ids) == 1:
                self.sale_warehouse_id = warehouses
            elif len(self.sale_warehouse_ids) > 1:
                self.sale_warehouse_id = False
            self._compute_qty_at_date()

    @api.onchange('sale_warehouse_id')
    def sale_warehouse_id_change(self):
        if self.sale_warehouse_id:
            self.sale_warehouse_ids = self.sale_warehouse_id
            self._compute_qty_at_date()

    def _compute_show_button_warehouse(self):
        for line in self:
            if line.order_id.is_multi_wh_line in ['0', '2'] or line.state in ['sale', 'done', 'cancel'] \
                    or not line.product_id.type in ('consu', 'product'):
                line.show_button_warehouse = False
            else:
                line.show_button_warehouse = True

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """
        Launch procurement group run method with required/custom fields genrated by a
        sale order line. procurement group will launch '_run_pull', '_run_buy' or '_run_manufacture'
        depending on the sale order line product rule.
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        warehouses = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)])
        order_id = self.order_id
        for w in warehouses:
            procurements = []

            if order_id.is_multi_wh_line == '1':
                lines = self.filtered(
                    lambda l: l.order_line_warehouse and w.id in l.order_line_warehouse.mapped('warehouse_id').ids)
            else:
                lines = self.filtered(lambda l: l.sale_warehouse_ids and w.id in l.sale_warehouse_ids.ids)

            for line in lines:
                line = line.with_company(line.company_id)
                if line.state != 'sale' or not line.product_id.type in ('consu','product'):
                    continue
                qty = line._get_qty_procurement(previous_product_uom_qty)
                if float_compare(qty, line.product_uom_qty, precision_digits=precision) == 0:
                    continue

                group_id = line._get_procurement_group()
                if not group_id:
                    group_id = self.env['procurement.group'].create(line._prepare_procurement_group_vals())
                    line.order_id.procurement_group_id = group_id
                else:
                    # In case the procurement group is already created and the order was
                    # cancelled, we need to update certain values of the group.
                    updated_vals = {}
                    if group_id.partner_id != line.order_id.partner_shipping_id:
                        updated_vals.update({'partner_id': line.order_id.partner_shipping_id.id})
                    if group_id.move_type != line.order_id.picking_policy:
                        updated_vals.update({'move_type': line.order_id.picking_policy})
                    if updated_vals:
                        group_id.write(updated_vals)

                values = line._prepare_procurement_values(group_id=group_id)
                product_qty = line.product_uom_qty - qty

                if line.order_id.is_multi_wh_line == '1':
                    line_warehouse = line.mapped("order_line_warehouse").filtered(
                        lambda l: l.order_line_id.id == line.id and w.id == l.warehouse_id.id)
                    if not line_warehouse:
                        raise UserError(
                            _('Warehouse does not exist on line %s.' % line.product_id.name))
                    product_qty = line_warehouse.product_uom_qty

                values.update({
                    'warehouse_id': w,
                })

                line_uom = line.product_uom
                quant_uom = line.product_id.uom_id
                product_qty, procurement_uom = line_uom._adjust_uom_quantities(product_qty, quant_uom)
                procurements.append(line._create_procurement(product_qty, procurement_uom, values))
            if procurements:
                self.env['procurement.group'].run(procurements)

        # This next block is currently needed only because the scheduler trigger is done by picking confirmation rather than stock.move confirmation
        orders = self.mapped('order_id')
        for order in orders:
            pickings_to_confirm = order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done'])
            if pickings_to_confirm:
                # Trigger the Scheduler for Pickings
                pickings_to_confirm.action_confirm()
        return True
