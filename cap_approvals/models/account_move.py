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

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import datetime

class AccountMove(models.Model):
    _inherit = 'account.move'

    #EOI - 350
    acc_type = fields.Selection([
        ('bank', 'Normal'),
        ('iban','IBAN')
    ], compute='_compute_acc_type')
    should_be_paid = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No'),
        ('exception', 'Exception'),
    ])
    level_one_approval = fields.Boolean('First Approval')
    # EOI-349: Added compute field to update is_approved
    is_approved = fields.Boolean('Approved', compute="_compute_is_approved")

    # EOI-349: Computes product type
    check_product_type = fields.Selection([
        ('receivable', 'Receivable'),
        ('service', 'Service'),
        ('empty','Empty')
    ], compute="_compute_check_product_type")

    # EOI-480: Gives total for services
    service_total = fields.Monetary(string='Services Total')
    on_hold = fields.Boolean('On Hold')
    bank_info_check = fields.Boolean('Bank Check', compute='_compute_bank_info_check')
    terms_due_date = fields.Date('Discounted Due Date', compute='_compute_terms_due_date')
    terms_amount = fields.Monetary('Discounted Amount', compute='_compute_terms_amount')
    linked_purchase_id = fields.Many2one('purchase.order', 'Linked Purchase Order', readonly=True)
    multi_approval_ids = fields.Many2many('multi.approval', string='Approvals', compute='_compute_multi_approval_ids')
    multi_approval_id_count = fields.Integer(string='Count Approvals', compute='_compute_multi_approval_id_count')

    #add required multi.approval fields that would be created by third party module
    x_has_request_approval = fields.Boolean('x_has_request_approval', copy=False)
    x_need_approval = fields.Boolean('x_need_approval', compute='_compute_x_need_approval')
    x_review_result = fields.Char('x_review_result', copy=False)
    
    @api.depends('invoice_line_ids')
    def _compute_check_product_type(self):
        # product_types = []
        for rec in self:
            line_has_service = rec.invoice_line_ids.filtered(lambda line: line.product_id.detailed_type == 'service')
        # raise UserError(str(product_types))

            if line_has_service:
                rec.check_product_type = 'service'
                rec.release_to_pay_manual = 'no'
                rec.service_total = 0
                # EOI-491: Check if is approved, then change should be paid field to yes
                if rec.is_approved == True:
                    rec.release_to_pay_manual = 'yes'
                # EOI-480: Totals all the service products in the lines
                for line in line_has_service:
                    rec.service_total += line.price_subtotal
            elif not line_has_service and rec.release_to_pay_manual != 'yes':
                rec.check_product_type = 'empty'
            elif not line_has_service and rec.release_to_pay_manual == 'yes':
                rec.check_product_type = 'receivable'
            else:
                rec.check_product_type = 'receivable'


    # EOI-349: Checks if corresponding multi_level_approval is 'Approved'
    @api.depends('multi_approval_ids')
    def _compute_is_approved(self):

        for rec in self:
            ma_req = rec.multi_approval_ids.filtered(lambda request: request.state == 'Approved')
            if ma_req or rec.check_product_type == 'receivable':
                rec.is_approved = True
                rec.x_need_approval = False
                rec.x_review_result = False
            else:
                rec.is_approved = False
            
    # EOI-349: Recreating the Request Approval Button for Account Move
    def action_request(self):
        budget = self.invoice_line_ids.analytic_account_id.crossovered_budget_line.crossovered_budget_id
        ma_request = self.env['multi.approval']
        ra_request = self.env['request.approval']

        # EOI-480: Override amount_total if there is a service in the invoice lines
        line_has_service = self.invoice_line_ids.filtered(lambda line: line.product_id.detailed_type == 'service')
        if line_has_service:
            self.amount_total = self.service_total

        model_name = 'account.move'
        vendor = self.partner_id.name
        res_id = self.id
        types = self.env['multi.approval.type']._get_types(model_name)
        approval_type = self.env['multi.approval.type'].filter_type(
                    types, model_name, res_id)

        record = self.env[model_name].browse(res_id)
        record_name = record.display_name or _('this object')
        title = _('Request approval for {}').format(record_name)
        record_url = ra_request._get_obj_url(record)
        if approval_type.request_tmpl:
            descr = _(approval_type.request_tmpl).format(
                record_url=record_url,
                record_name=record_name,
                record=record
            )
        else:
            descr = ''

        # Multi Level Approval Request Data
        vals = {
            'name': title,
            'type_id': approval_type.id,
            'description': descr,
            'reference':self.name,
            'deadline': self.invoice_date,
            'state':'Draft',
            'origin_ref': '{model},{res_id}'.format(
                model=model_name,
                res_id=res_id)
        }
        req = ma_request.create(vals)

        # Gather and write all approvers onto Multi Level Approval Request Lines
        ma_request.update_approver_ids(res_id,req,self.amount_total,model_name,budget)
            

        return {
            
            'name': _('My Requests'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'multi.approval',
            'view_id': self.env.ref('multi_level_approval.multi_approval_view_form_inherit').id,
            'res_id': req.id,
        }

    @api.onchange('ref')
    def _onchange_ref(self):
        self.payment_reference = self.ref
    
    @api.onchange('purchase_vendor_bill_id', 'purchase_id')
    def _onchange_purchase_auto_complete(self):
        ''' Load from either an old purchase order, either an old vendor bill.
        When setting a 'purchase.bill.union' in 'purchase_vendor_bill_id':
        * If it's a vendor bill, 'invoice_vendor_bill_id' is set and the loading is done by '_onchange_invoice_vendor_bill'.
        * If it's a purchase order, 'purchase_id' is set and this method will load lines.
        /!\ All this not-stored fields must be empty at the end of this function.
        '''
        if self.purchase_vendor_bill_id.vendor_bill_id:
            self.invoice_vendor_bill_id = self.purchase_vendor_bill_id.vendor_bill_id
            self._onchange_invoice_vendor_bill()
        elif self.purchase_vendor_bill_id.purchase_order_id:
            self.purchase_id = self.purchase_vendor_bill_id.purchase_order_id
        self.purchase_vendor_bill_id = False

        if not self.purchase_id:
            return

        # Copy data from PO
        invoice_vals = self.purchase_id.with_company(
            self.purchase_id.company_id)._prepare_invoice()
        invoice_vals['currency_id'] = self.line_ids and self.currency_id or invoice_vals.get(
            'currency_id')
        del invoice_vals['ref']
        self.update(invoice_vals)

        # Copy purchase lines.
        po_lines = self.purchase_id.order_line - \
            self.line_ids.mapped('purchase_line_id')
        new_lines = self.env['account.move.line']
        sequence = max(self.line_ids.mapped('sequence')) + \
            1 if self.line_ids else 10
        for line in po_lines.filtered(lambda l: not l.display_type):
            line_vals = line._prepare_account_move_line(self)
            line_vals.update({'sequence': sequence})
            ############ Modification to base code
            line_vals.update({'account_id': line.override_account_id})
            ############
            new_line = new_lines.new(line_vals)
            sequence += 1
            new_line.account_id = new_line._get_computed_account()
            new_line._onchange_price_subtotal()
            new_lines += new_line
        new_lines._onchange_mark_recompute_taxes()

        # Compute invoice_origin.
        origins = set(self.line_ids.mapped('purchase_line_id.order_id.name'))
        self.invoice_origin = ','.join(list(origins))
        #################### Modification to base code
        if self.linked_purchase_id or len(self.invoice_line_ids.mapped('purchase_order_id')) > 1:
            self.linked_purchase_id = False
        else:
            self.linked_purchase_id = self.invoice_line_ids.mapped('purchase_order_id')
        ####################

        # Compute ref.
        refs = self._get_invoice_reference()
        self.ref = ', '.join(refs)

        # Compute payment_reference.
        if len(refs) == 1:
            self.payment_reference = refs[0]

        self.purchase_id = False
        self._onchange_currency()

    #Copied from third party module
    def _compute_x_need_approval(self):
        for rec in self:
            rec['x_need_approval'] = rec.env['multi.approval.type'].compute_need_approval(rec)

    #EOI 350
    def _compute_acc_type(self):
        for record in self:
            record.acc_type = False
            if record.partner_bank_id:
                if record.partner_bank_id.type:
                    record.acc_type = record.partner_bank_id.type

    #EOI 350
    def _compute_bank_info_check(self):
        for record in self:
            record.bank_info_check = False
            if record.partner_bank_id:
                if record.partner_bank_id.acc_number:
                    record.bank_info_check = True
    #EOI 350
    def _compute_terms_due_date(self):
        for record in self:
            if record.invoice_payment_term_id.id == 9:
                if (record.invoice_payment_term_id.line_ids[0].value == 'percent'):
                    record['terms_due_date'] = record.date + \
                        datetime.timedelta(
                            days=record.invoice_payment_term_id.line_ids[0].days)
            else:
                record['terms_due_date'] = False
    
    #EOI 350
    def _compute_terms_amount(self):
        for record in self:
            if record.invoice_payment_term_id.id == 9:
                record['terms_amount'] = record.amount_total
                if (record.invoice_payment_term_id.line_ids[0].value == 'percent'):
                    record['terms_amount'] = record['terms_amount'] * \
                        (record.invoice_payment_term_id.line_ids[0].value_amount * .01)
            else:
                record['terms_amount'] = 0

    #EOI 350
    def _compute_multi_approval_ids(self):
        for record in self:
            origin_ref = '{model},{res_id}'.format(model='account.move', res_id=record.id)
            record.multi_approval_ids = self.env['multi.approval'].search([('origin_ref', '=', origin_ref)])
    
    #EOI 350
    def _compute_multi_approval_id_count(self):
        for record in self:
            record.multi_approval_id_count = len(self.multi_approval_ids)

    #EOI 350
    def action_view_approvals(self):
        return {
            'name': 'Approvals',
            'view_mode': 'tree,form',
            'res_model': 'multi.approval',
            'type': 'ir.actions.act_window',
            'target' : 'current',
            'domain': [('id', 'in', self.multi_approval_ids.mapped('id'))],
        }

    # def first_approval(self):
    #     if self.amount_total > 50000:
    #         self.x_review_result = 'reapprove'
    #         self.level_one_approval = True
    #         self.x_need_approval = True
    #         self.x_has_request_approval = False
    #         self.is_approved = False
    #     else:
    #         self.is_approved = True
    
    # def second_approval(self):
    #     self.is_approved = True
    #     self.x_review_result = 'complete'

    # EOI-444:Raise warning when confirming a vendor bill with amount = $0
    def action_post(self):
        if self.move_type == 'in_invoice' and sum(self.invoice_line_ids.mapped('price_subtotal')) == 0:
            raise UserError(str('Warning: You are confirming a Vendor Bill with a $0 amount'))
        super(AccountMove, self).action_post()

