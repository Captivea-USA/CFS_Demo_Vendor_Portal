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

from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero
from itertools import groupby


CEO_MIN_AMOUNT = 50000


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    #EOI-222 - Fields required
    state = fields.Selection([
    ('draft', 'Draft PO'),
    ('sent', 'Draft PO Sent'),
    ('to approve', 'To Approve'),
    ('to reapprove', 'To Reapprove'),
    ('approved', 'Approved'),
    ('purchase', 'Released'),
    ('cancel', 'Cancelled'),
    ('revised', 'Revised'),
    ('done', 'Locked'),
    ('closed', 'Closed'),    
    ], string='Status', readonly=True, index=True, copy=False, default='draft', tracking=True)

    cfs_released_by = fields.Char(string="Release By", required=False, )
    acknowledged = fields.Selection(string="Acknowledged", selection=[('waiting', 'Waiting'), ('acknowledged', 'Acknowledged'), ('denied', 'Denied')], required=False, )

    # EOI 477 - Duplicated POs need to say not approved - Rewrite field definitions to explicitly not copy.
    #add required multi.approval fields that would be created by third party module
    x_has_request_approval = fields.Boolean('x_has_request_approval', copy=False)
    x_need_approval = fields.Boolean('x_need_approval', compute='_compute_x_need_approval')
    x_review_result = fields.Char('x_review_result')
    cfs_is_transfer_return = fields.Boolean(string="Transfer Return?",)
    acknowledged = fields.Selection(string="Acknowledged", selection=[('waiting', 'Waiting'), ('acknowledged', 'Acknowledged'), ('denied', 'Denied')], required=False, )
    is_hazardous = fields.Boolean(string='Hazardous', compute="_compute_hazardous_product", store=True)

    # EOI-349: Needed for _is_approval_approved > _compute_approval
    is_approved = fields.Boolean(string="Approved", copy=False, default=False, compute='_is_approval_approved')
    is_being_approved = fields.Boolean(string="Being Approved", copy=False, default=False, readonly=True)
    is_editable = fields.Boolean('Editable',default=True, copy=False)
    approval_ids = fields.Many2many('approval.request', string="Approval Requests", compute='_compute_approvals')
    
    # EOI-349: Fields required for MLA smart button on purchase order
    multi_approval_ids = fields.Many2many('multi.approval', string="Multi Level Approvals", compute="_compute_purchase_multi_approval_id")
    multi_approval_count = fields.Integer(string='Multi Approval Count', compute='compute_multi_approval_count')

    # EOI-452: Hide 'Close by Credit Card' button
    cfs_just_indirect_category_items = fields.Boolean(string="Only indirect Category Items",compute="_compute_indirect_category")

    # EOI-487: Paid by credit card field for budget burden
    paid_by_credit_card = fields.Boolean(string="Paid by Credit Card")

    @api.depends('order_line','date_planned')
    def _compute_indirect_category(self):
        for rec in self:
            indirect_category_id = 3

            lines_categories = rec.order_line.mapped("product_id").mapped('categ_id')

            belongs_to_indirect_categorie = [category.id == indirect_category_id for category in lines_categories]
            for comparison in belongs_to_indirect_categorie:
                if not comparison:
                    rec.cfs_just_indirect_category_items = comparison
                    break
                else:
                    rec.cfs_just_indirect_category_items = comparison

            if rec.cfs_just_indirect_category_items and rec.state != 'purchase':
                rec.cfs_just_indirect_category_items = False


    # EOI-349: Multi Approval Smart Button
    @api.depends('multi_approval_ids')
    def compute_multi_approval_count(self):
        for record in self:
            record.multi_approval_count = len(record.multi_approval_ids)

    # EOI-349: Maps Approval IDs to Purchase Orders by the PO Sequencing
    @api.depends('name')
    def _compute_purchase_multi_approval_id(self):
        for record in self:
            origin_ref = '{model},{res_id}'.format(model='purchase.order', res_id=record.id)
            record.multi_approval_ids = self.env['multi.approval'].search([('reference', 'ilike', record.name)])

    # EOI-349: Window Action for Multi Approval Smart Button
    def multi_app_smart_button_window_action(self):
        
        # Opens Tree View
        mla_tree = self.env.ref('multi_level_approval.cfs_multi_approval_smart_button_view').id

        # Opens Form View
        mla_form = self.env.ref('multi_level_approval.multi_approval_view_form_inherit').id
        
        return {
            'name':'Multi Approval for Purchase Order Action',
            'view_mode': 'tree',
            'view_type':'form',
            'res_model': 'multi.approval',
            'type':'ir.actions.act_window',
            'view_id': mla_tree,
            'views':[(mla_tree,'tree'),(mla_form,'form')],
            'domain': [('id', 'in', self.multi_approval_ids.ids)],
            # 'target': 'new',
        }

    #EOI-222 - Comes from multi.approval module
    def _compute_x_need_approval(self):
        for rec in self:
            rec['x_need_approval'] = rec.env['multi.approval.type'].compute_need_approval(rec)
    
    @api.depends('order_line')
    def _compute_hazardous_product(self):
        for rec in self:
            rec.is_hazardous = False
            hazard = rec.order_line.filtered(
                lambda line: line.is_hazardous == True)
            if len(hazard) >= 1:
                rec.is_hazardous = True
  
    #EOI-452: Dont create vendor bill when closed by credit card
    #EOI-487: Budget Burden Calc
    def button_close_by_credit_card(self):
        self.paid_by_credit_card = True
        self.state='closed'

    #EOI-222 - Button needs to change state to approve instead of confirm
    def button_confirm(self):
        for order in self:
            if not self.order_line:
                raise UserError('You must have at least one line in the purchase order before it can be released')
            if order.state not in ['approved']:
                continue
            order._add_supplier_to_product()
            # Deal with double validation process
            if order._approval_allowed():
                order.button_approve()
                order.cfs_released_by = self.env.user
            else:
                order.write({'state': 'to approve'})
            if order.partner_id not in order.message_partner_ids:
                order.message_subscribe([order.partner_id.id])
        return True
    
    #EOI-222 - Set stage
    def button_send_for_approval(self):
        self.state = 'to approve'
       
        #EOI-222 - [FIX] Prevents user from making a Draft PO/PO with no lines
        if not self.order_line:
            raise UserError('You must have at least one line in the purchase order before you can send for approval')


    #EOI-222 - Determine multi approvals required
    def first_approval(self):
        if not self.order_line:
            raise UserError('You must have at least one line in the purchase order before it can be approved')
        if self.amount_total > 50000:
            self.state = 'to reapprove'
            self.x_has_request_approval = False
            self.x_review_result = 'reapprove'
        else:
            self.state = 'approved'
    
    #EOI-222 - Second approval
    def second_approval(self):
        if not self.order_line:
            raise UserError('You must have at least one line in the purchase order before it can be approved')
        self.state = 'approved'
    

    #EOI 227,226 - Set burden Values
    def write(self, vals):
        vals, partner_vals = self._write_partner_values(vals)
        res = super().write(vals)
        if partner_vals:
            self.partner_id.sudo().write(partner_vals)  
        ################################### EOI - 227,226
        self.env['purchase.order.line'].set_burden_vals(self.order_line)
        ###################################
        return res
    
    # EOI 227,226 - Set burden Values
    @api.model
    def create(self, vals):
        company_id = vals.get('company_id', self.default_get(['company_id'])['company_id'])
        self_comp = self.with_company(company_id)
        if vals.get('name', 'New') == 'New' or vals.get('name'):
            seq_date = None
            if 'date_order' in vals:
                seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(vals['date_order']))
            ############## EOI 310 - Format Sequence as PO/YY/XXXXX
            sequence_number = self_comp.env['ir.sequence'].next_by_code('purchase.order', sequence_date=seq_date) or '/'
            year_part = datetime.now().strftime('%y')
            vals['name'] =  'PO/{}/{}'.format(year_part, sequence_number)
            ##############
        vals, partner_vals = self._write_partner_values(vals)
        res = super(PurchaseOrder, self_comp).create(vals)
        ################################### EOI - 227,226
        self.env['purchase.order.line'].set_burden_vals(res.order_line)
        ###################################
        if partner_vals:
            res.sudo().write(partner_vals) 
        return res

    # EOI-349: Create Multi Approval Request in draft state
    def action_request(self):
        self.state = 'to approve'
        # EOI 312 - Block PO stage progress if no PO Lines
       
        if not self.order_line:
            raise UserError('You must have at least one line in the purchase order before it can be sent for approval')

        request = self.env['multi.approval']
        budget = self.order_line.account_analytic_id.crossovered_budget_line.crossovered_budget_id
        ra_request = self.env['request.approval']

        model_name = 'purchase.order'
        vendor = self.partner_id.name
        res_id = self.id
        types = self.env['multi.approval.type']._get_types(model_name)
        approval_type = self.env['multi.approval.type'].filter_type(
                    types, model_name, res_id)


        # Calc Subtotal
        total = 0.00
        for line in self.order_line:
            # eoi398 - take currency into account (try/except for div by zero)
            try:
                converted_amount = line.price_subtotal / self.currency_rate
            except:
                converted_amount = line.price_subtotal
            total += converted_amount
        format_total = "{:.2f}".format(total)
        
        # name = "Draft PO " + self.name + " from " + vendor + " for " + "$" + str(format_total) + "."
        
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
            'deadline': self.date_planned,
            # 'line_ids': 'TEST',
            'state':'Draft',
            'origin_ref': '{model},{res_id}'.format(
                model=model_name,
                res_id=res_id)
        }
        
        # Create Multi Approval Request (state = draft)
        req = request.create(vals)

        # Gather and write all approvers onto Multi Level Approval Request Lines
        request.update_approver_ids(res_id,req,total,model_name,budget)

        # Window Action opens form view
        return {
            'name': _('My Requests'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'multi.approval',
            'view_id': self.env.ref('multi_level_approval.multi_approval_view_form_inherit').id,
            'res_id': req.id,
        }
    
    #EOI 443 - Email Acknowledge
    def action_cancel_email(self):
        # self.ensure_one()
        ir_model_data = self.env['ir.model.data']
        send_mail = False
        if self.state == 'purchase':
            send_mail = True
        self.button_cancel()
        if send_mail:
            # template_id = ir_model_data.get_object_reference('purchase', 'cancel_email_template_purchase')[1]
            template_id = self.env.ref('cfs_email_acknowledgement.cancel_email_template_purchase', raise_if_not_found=False)
            ctx = dict(self.env.context or {})
            ctx.update({
                'default_model': 'purchase.order',
                'active_model': 'purchase.order',
                'active_id': self.ids[0],
                'default_res_id': self.ids[0],
                'default_use_template': bool(template_id),
                'default_template_id': template_id.id,
                'default_composition_mode': 'comment',
                'force_email': True,
            })

            try:
                compose_form_id = ir_model_data.get_object_reference('mail', 'email_compose_message_wizard_form')[1]
            except ValueError:
                compose_form_id = False

            email = {
                'name': _('Compose Email'),
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'mail.compose.message',
                'views': [(compose_form_id, 'form')],
                'view_id': compose_form_id,
                'target': 'new',
                'context': ctx,
            }
            return email


    # EOI-349: Preparing Approver Values
    def get_approver_vals(self, request, amount_total):
        if not self:
            return []

        vals = []
        approver_ids = []

        # LEVEL 10 ==============================================================================
        requesters = [id for id in self.order_line.mapped('requester_id').ids if id not in approver_ids]
        if self.user_id and requesters:   # Assign level 10 only if its manual (not run by scheduler)
            vals.append({'user_ids': [(4, id, 0) for id in requesters],
                    'name': 'Test10',
                    'everyone_approves': True,
                    'min_approval': 1,
                    'level': 10,
                    'sequence':10,
                    'require_opt': 'Optional',
                    'user_id': requesters[0],
                    'approval_id': request.id,
                    'status': 'new'})
            approver_ids.append(requesters)

        # LEVEL 20 ==============================================================================
        if not self.user_id:
            design_owners = [id for id in self.order_line.mapped('product_id.design_owner').ids if id not in approver_ids]
            if design_owners:
                vals.append({'user_ids': [(4, id, 0) for id in design_owners],
                        'name': 'Test20',
                        'everyone_approves': True,
                        'min_approval': 1,
                        'level': 20,
                        'sequence':20,
                        'require_opt': 'Optional',
                        'user_id': design_owners[0],
                        'approval_id': request.id,
                        'status': 'new'})
                approver_ids.extend(design_owners)

        # LEVEL 30 ==============================================================================
        budget = self.order_line.account_analytic_id.crossovered_budget_line.crossovered_budget_id
        finance_param = self.env['ir.config_parameter'].sudo().get_param('cap_settings.cfs_purchase_order_finance_users')

        if finance_param:
            finance_user_ids = [int(user.strip()) for user in finance_param.split(',')]

       
       # EOI-349: Finding sum of the budget line variables
        planned_amount = 0
        practical_amount = 0
        for line in budget.crossovered_budget_line:
            planned_amount += line.abs_planned_amount

        for line in budget.crossovered_budget_line:
            practical_amount += line.abs_practical_amount
        if planned_amount < practical_amount:
            if finance_user_ids:
                vals.append({'user_ids': [(4, id, 0) for id in finance_user_ids],
                        'name': 'Test30',
                        'everyone_approves': False,
                        'min_approval': 1,
                        'level': 30,
                        'sequence':30,
                        'require_opt': 'Optional',
                        'user_id': finance_user_ids[0],
                        'approval_id': request.id,
                        'status': 'new'})
                approver_ids.extend(finance_user_ids)

        # LEVEL 40 ==============================================================================
        # ALWAYS ASSIGN THIS LEVEL, NO MATTER IF THERE IS BUDGET OR NOT, EXCEPT IF FINANCE USER ALREADY ASKED
        if budget.user_id and budget.user_id not in finance_user_ids:
            if budget.user_id.id == requesters[0]:
                vals.pop(0)
            vals.append({'user_ids': [(4, budget.user_id.id, 0)],
                    'name': 'Test40',
                    'everyone_approves': True,
                    'min_approval': 1,
                    'level': 40,
                    'sequence':40,
                    'require_opt': 'Optional',
                    'user_id': budget.user_id.id,
                    'approval_id': request.id,
                    'status': 'new'})
            # raise UserError(str(vals))
            approver_ids.append(budget.user_id.id)

        # LEVEL 50 ==============================================================================
        purchase_param = self.env['ir.config_parameter'].sudo().get_param('cap_settings.cfs_purchase_manager_users')
        skip_purchase_param = self.env['ir.config_parameter'].sudo().get_param('cap_settings.cfs_skip_purchase_manager_users')

        if skip_purchase_param:
            skip_user_ids = [int(user.strip()) for user in skip_purchase_param.split(',')] if skip_purchase_param else []
            level_skipped = self.order_line.mapped('requester_id').ids in skip_user_ids

        if purchase_param and not level_skipped and amount_total > 50000:
            purchase_user_ids = [int(user.strip()) for user in purchase_param.split(',')]
            ids = [id for id in purchase_user_ids if id not in approver_ids]
            if ids:
                vals.append({'user_ids': [(4, id, 0) for id in ids],
                        'name': 'Test50',
                        'everyone_approves': False,
                        'min_approval': 1,
                        'level': 50,
                        'sequence':50,
                        'require_opt': 'Optional',
                        'user_id': ids[0],
                        'approval_id': request.id,
                        'status': 'new'})
                approver_ids.extend(ids)

        # LEVEL 60 ==============================================================================
        ceo_user = self.env['ir.config_parameter'].sudo().get_param('cap_settings.cfs_purchase_order_ceo_id')
        ceo_amount = self.env['ir.config_parameter'].sudo().get_param('cap_settings.cfs_min_amount_ceo') or CEO_MIN_AMOUNT
        if ceo_user and amount_total > float(ceo_amount):
            ceo_ids = [int(user.strip()) for user in ceo_user.split(',')]
            ids = [id for id in ceo_ids]
            if ids:
                vals.append({'user_ids': [(4, id, 0) for id in ids],
                        'name': 'Test60',
                        'everyone_approves': False,
                        'min_approval': 1,
                        'level': 60,
                        'sequence':60,
                        'require_opt': 'Optional',
                        'user_id': ids[0],
                        'approval_id': request.id,
                        'status': 'new'})
                approver_ids.extend(ids)
        
        return vals

    # EOI-349: Checks to see if a request was approved, needed by _compute_approval & action_approve
    @api.depends('approval_ids')
    def _is_approval_approved(self):
        for rec in self:
            if rec.approval_ids:
                approve = rec.approval_ids.filtered(lambda app: app.request_status == 'approved')
                if approve:
                    rec.is_approved = True
                    rec.is_editable = False
                    rec.is_being_approved = False
                    if rec.state in ['draft','sent','to reapprove']:
                        rec.state = 'approved'
                else:
                    rec.is_approved = False
                    if rec.state == 'approved':
                        rec.state = 'to reapprove'
                        rec.is_editable = True
                    rec.is_being_approved = rec.approval_ids.filtered(lambda app: app.request_status not in ['cancel', 'refused'])
                    rec.is_editable = not rec.is_being_approved
            else:
                rec.is_approved = False

    # EOI-349: Needs to be computed for _is_approval_approved
    @api.depends('approval_ids')
    def _compute_approvals(self):
        for record in self:
            approvals = [rec.id for rec in self.env['approval.request'].search([]) if rec.res_id == record.id and rec.res_model == 'purchase.order']
            record.approval_ids = [(6, 0, approvals)]

    # EOI-428: Overrides base code in step 5 (Pulled from UAT modules)
    def action_create_invoice(self):
        """Create the invoice associated to the PO.
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        # 1) Prepare invoice vals and clean-up the section lines
        invoice_vals_list = []
        for order in self:
            if order.invoice_status != 'to invoice':
                continue

            order = order.with_company(order.company_id)
            pending_section = None
            # Invoice values.
            invoice_vals = order._prepare_invoice()
            # Invoice line values (keep only necessary sections).
            for line in order.order_line:
                if line.display_type == 'line_section':
                    pending_section = line
                    continue
                if not float_is_zero(line.qty_to_invoice, precision_digits=precision):
                    if pending_section:
                        invoice_vals['invoice_line_ids'].append((0, 0, pending_section._prepare_account_move_line()))
                        pending_section = None
                    invoice_vals['invoice_line_ids'].append((0, 0, line._prepare_account_move_line()))
            invoice_vals_list.append(invoice_vals)

        if not invoice_vals_list:
            raise UserError(_('There is no invoiceable line. If a product has a control policy based on received quantity, please make sure that a quantity has been received.'))

        # 2) group by (company_id, partner_id, currency_id) for batch creation
        new_invoice_vals_list = []
        for grouping_keys, invoices in groupby(invoice_vals_list, key=lambda x: (x.get('company_id'), x.get('partner_id'), x.get('currency_id'))):
            origins = set()
            payment_refs = set()
            refs = set()
            ref_invoice_vals = None
            for invoice_vals in invoices:
                if not ref_invoice_vals:
                    ref_invoice_vals = invoice_vals
                else:
                    ref_invoice_vals['invoice_line_ids'] += invoice_vals['invoice_line_ids']
                origins.add(invoice_vals['invoice_origin'])
                payment_refs.add(invoice_vals['payment_reference'])
                refs.add(invoice_vals['ref'])
            ref_invoice_vals.update({
                'ref': ', '.join(refs)[:2000],
                'invoice_origin': ', '.join(origins),
                'payment_reference': len(payment_refs) == 1 and payment_refs.pop() or False,
            })
            new_invoice_vals_list.append(ref_invoice_vals)
        invoice_vals_list = new_invoice_vals_list

        # 3) Create invoices.
        moves = self.env['account.move']
        AccountMove = self.env['account.move'].with_context(default_move_type='in_invoice')
        for vals in invoice_vals_list:
            moves |= AccountMove.with_company(vals['company_id']).create(vals)

        # 4) Some moves might actually be refunds: convert them if the total amount is negative
        # We do this after the moves have been created since we need taxes, etc. to know if the total
        # is actually negative or not
        moves.filtered(lambda m: m.currency_id.round(m.amount_total) < 0).action_switch_invoice_into_refund_credit_note()
        
        # Custom code 
        # 5) Change account on Bill's invoice_order_lines with product to purchase order line GL account
        products = {}
        for pol in self.order_line:
            products[pol.product_id.id] = pol.override_account_id.id
        if len(products.keys()) > 0:
            for ml in self.env["account.move.line"].search([('move_id', 'in', moves.ids), ('product_id', 'in', list(products.keys()))]):
                ml.write({
                    "account_id": products[ml.product_id.id]
                })
        self.env['purchase.order.line'].set_burden_vals(self.order_line)
        return self.action_view_invoice(moves)

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    date_promised = fields.Date(string='Promise Date', required=True, copy=True)
    is_hazardous = fields.Boolean(string='Hazardous')

    # EOI 227,226 - Calc burden values by stage
    def set_burden_vals(self, input_lines):
        for line in input_lines:
            budgets = self.env['crossovered.budget.lines'].search([
                ('analytic_account_id','=', line.account_analytic_id.id)
                ])
            for budget in budgets:
                po_lines = self.env['purchase.order.line'].search([
                    ('account_analytic_id.id','=', budget.analytic_account_id.id),                    
                    ('date_promised', '>=', budget.date_from ),
                    ('date_promised', '<=', budget.date_to )
                ])
                draft = 0
                approved = 0
                released = 0
                closed = 0
                total = 0

                for po_line in po_lines:
                    amount = 0
                    if po_line.product_qty != 0:
                        units = (po_line.product_qty - po_line.qty_invoiced)
                        amount = po_line.price_unit * units                  
                    if po_line.order_id.state in ['draft','sent','to approve', 'to reapprove']:
                        draft += amount
                        total += amount
                    if po_line.order_id.state in ['approved']:
                        approved += amount
                        total += amount
                    #EOI-487 - Handle credit card budget burden
                    if po_line.order_id.state in ['done', 'closed'] and po_line.order_id.paid_by_credit_card:
                        closed += amount
                    if po_line.order_id.state in ['purchase']:
                        released += amount
                        total += amount
                budget.draft_burden = draft
                budget.approved_burden = approved
                budget.closed_burden = closed
                budget.released_burden = released
                budget.total_burden = total 
