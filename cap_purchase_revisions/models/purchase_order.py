# -*- coding: utf-8 -*-
######################################################################################
#
#    Captivea LLC
#
#    This program is under the terms of the Odoo Proprietary License v1.0 (OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the Software
#    or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
#    ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
########################################################################################

from odoo import models, fields, api
from odoo.exceptions import UserError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    state = fields.Selection(selection_add=[('revised', 'Revised')])
    active = fields.Boolean(default=True)
    po_is_revision = fields.Boolean('Is Revised PO', readonly=True)
    prior_po = fields.Many2one("purchase.order", string="Prior PO", readonly=True,)


    def button_revise_po(self):
        for record in self:
            new_po = record.copy(default=None)
            sequence = self.env['ir.sequence'].search([('code','=','purchase.order')])
            sequence['number_next_actual']=sequence.number_next_actual - 1
            
            #EOI 321 - PO Revision Routing
            #EOI 323 - Prior PO Logic
            new_po.x_review_result = False
            new_po.x_has_request_approval = False
            new_po.prior_po = record.id

            #EOI 324 - Old q and $ logic
            new_po.po_is_revision = True
            for po_line in new_po.order_line:
                old_po_line = record.order_line.filtered(lambda x: x.product_id == po_line.product_id )
                po_line.prior_product_qty = old_po_line.product_qty
                po_line.prior_price_unit = old_po_line.price_unit
                po_line.prior_line = True

            if str('-') in record.name:
                new_po['name'] = record.name[:record.name.rindex('-')] + str('-') + \
                    str(int(record.name[record.name.rindex('-')+1:])+1).zfill(3)
            else:
                new_po['name'] = record.name + '-001'
            
            
            record.state = 'revised'
            record.active = False
            
            form_id = self.env.ref('purchase.purchase_order_form', False).id
            result = {
                'name' : 'Purchase Order',
                'type' : 'ir.actions.act_window',
                'view_mode' : 'form',
                'res_model' : 'purchase.order',
                'view_id' : form_id,
                'target' : 'current',
                'res_id' : new_po.id
                }
            return result

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    #EOI 324 - Old q and $ logic
    prior_product_qty = fields.Float(string="Old Q", readonly=True )
    prior_price_unit = fields.Float(string='Old $', readonly=True)
    prior_line = fields.Boolean(string="Old Line", readonly=True)
    change_type = fields.Selection([
        ('new', 'New'), 
        ('delete', 'Delete'), 
        ('price', 'Price'),
        ('qty', 'Qty'),
        ('price_qty', 'Price + Qty'),
    ],compute='_compute_change_type')

    # EOI-454 New PO - Tax Field: Tax field no longer allows user to add both Exempt and Taxable tags
    taxes_id = fields.Many2many('account.tax', string='Taxes', domain=['|', ('active', '=', False), ('active', '=', True)])

    @api.onchange('taxes_id')
    def onchange_taxes_id(self):
        if 'Exempt' in self.taxes_id.mapped('name'):
            if 'Taxable' in self.taxes_id.mapped('name'):
                raise UserError('Line item cannot be both Taxable and Exempt from Taxes.')

    #EOI 324 - Old q and $ logic
    @api.depends('prior_product_qty', 'prior_price_unit', 'prior_line')
    def _compute_change_type(self):
        for record in self:
            if not record.prior_line:
                record.change_type = 'new'
            elif record.prior_product_qty != record.product_qty and record.prior_price_unit != record.price_unit:
                record.change_type = 'price_qty'
            elif record.prior_product_qty != record.product_qty:
                record.change_type = 'qty'
            elif record.prior_price_unit != record.price_unit:
                record.change_type = 'price'
            else:
                record.change_type = False




