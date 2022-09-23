from datetime import datetime
from odoo import api,fields, models
from odoo.exceptions import UserError

class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    # EOI-341: Needed for relation from approval.product.line
    purchase_order = fields.Many2one('purchase.order',string="Previous PO")

    name = fields.Char(string='Purchase Request', tracking=True)
    cap_type = fields.Selection([('new', 'New'), ('change_order', 'Change Order')], string="Type", required=True, default='new')
    cap_ship_to = fields.Selection([('cfs', 'CFS'), ('external', 'External'), ('request_new_address', 'Request New Address')], string="Ship To", required=True, default='cfs')

    cap_warehouse = fields.Many2one('stock.warehouse', string="Warehouse")
    cap_remote_warehouse = fields.Many2one('stock.warehouse', string="Remote Warehouse")
    cap_address = fields.Char(string="Address")
    cap_need_date = fields.Date(string="Need Date")
    cap_request_notes = fields.Text(string="Requestor Notes")
    cap_project_id = fields.Many2one('project.project', string='Project')
    cap_notes = fields.Text(string=" RequesterNotes")

    cap_self_approved = fields.Boolean(string="Self Approved")
    cap_self_approved_timestamp = fields.Datetime(string="Self Approved Timestamp")

    cap_buyer_ids = fields.Many2many('res.users', string="Buyers")
    cap_vendor_ids = fields.Many2one('res.partner', string="Vendors")

    # EOI-464: Budget and requester fields needed to pass into Draft PO
    budget_id = fields.Many2one('crossovered.budget', string="Budget")
    requester_id = fields.Many2one('res.users', string="Requester")

    @api.onchange('cap_self_approved')
    def self_approved_timestamp(self):
        if self.cap_self_approved:
            self.cap_self_approved_timestamp = fields.Datetime.now()

    # EOI-341: Function to open a view (instead of using a window_action)
    def open_ap_lines(self):
        context = {
            'default_approval_request_id':self.id,
        }
        # raise UserError(str(context))
        return {
            'res_model': 'approval.product.line',
            'type':'ir.actions.act_window',
            'name':'Purchase Request Lines',
            'view_mode':'tree',
            'domain':[['approval_request_id.id','=',self.id]],
            'view_id': self.env.ref('cap_purchase_form_view.approval_product_line_view_tree_expanded_inherit').id,
            'context': context,
        }

    # EOI-433: validate every line in Request has vendor
    def check_line_vendors(self):
        lines_without_vendor = self.product_line_ids.filtered(lambda line: not line.cap_vendor_name)
        if lines_without_vendor :
            msg  = 'Vendor is missing from ' 
            msg += self.name
            raise UserError(msg)


    # EOI-433: Override base function to create PO's after approved
    def action_create_purchase_orders(self):
        res = super(ApprovalRequest, self).action_create_purchase_orders()
        """ Create and/or modifier Purchase Orders. """
        self.check_line_vendors()
        self.ensure_one()
        # self.product_line_ids._check_products_vendor()

        vendor_ids = self.product_line_ids.mapped('cap_vendor_name')

        # EOI-469: Creating Draft POs grouped by Vendors, by looping by vendors instead of lines
        for vendor in vendor_ids:
            lines_with_vendors = self.product_line_ids.filtered(lambda line: line.cap_vendor_name.id == vendor.id)
            po_line_vals = []
            po_vals = {
                    'partner_id':vendor.id,
                    'budget_id':self.budget_id.id,
                    'cfs_buyer':self.env.user.id,
                    }
            # EOI-464: Passes the budget_id and requester_id into PO
            # po_vals['budget_id'] = self.budget_id.id
            po_vals['requester_id'] = self.requester_id.id


            new_purchase_order = self.env['purchase.order'].create(po_vals)

            for line in lines_with_vendors:

                # EOI-464: Passes the account_id dependent on what is available
                if line.product_id.product_tmpl_id.property_account_expense_id.id:
                    account = line.product_id.product_tmpl_id.property_account_expense_id.id
                elif line.product_id.product_tmpl_id.categ_id.property_account_expense_categ_id.id:
                    account = line.product_id.product_tmpl_id.categ_id.property_account_expense_categ_id.id
                elif line.cap_vendor_name.property_account_payable_id.id:
                    account = line.cap_vendor_name.property_account_payable_id.id

                # EOI-469: Build and Add dictionaries for every line with the same vendor
                po_line_vals += [{
                    'product_id': line.product_id.id,
                    'product_qty': line.quantity,
                    'product_uom': line.product_uom_id.id,
                    'company_id': self.company_id.id,
                    'date_promised': datetime.today(),
                    'price_unit': line.cap_price,
                    'override_account_id': account,
                    'name':line.cap_vendor_name.name,
                    'order_id': new_purchase_order.id,
                    }]
                
                # EOI-372: Add Quality Codes on PO creation
                po_line_vals['cfs_quality_codes'] = line.quality_codes

                new_po_line = self.env['purchase.order.line'].create(po_line_vals)

                # EOI-469: Re-factored for PO creation by vendor (For Smart Button)
                for po_line in new_po_line:
                    line.purchase_order_line_id = po_line.id
                    new_purchase_order.order_line = [(4, po_line.id)]
                
                # EOI-472: Passes Link into Purchase Request (approval.request) Chatter
                product_name = ''
                if line.cap_vendor_part:
                    product_name += '[' + line.cap_vendor_part + '] '
                if line.description:
                    product_name += line.description

                body = '%s from request <a href="#" data-oe-model="approval.request" data-oe-id="%s">%s</a> added' % \
                (product_name, str(line.approval_request_id.id), str(line.approval_request_id.name))
        
            new_purchase_order.message_post(body=body)
            body = 'Reason for Request: %s' % self.reason
            new_purchase_order.message_post(body=body)
            if self.cap_notes:
                body = 'Requester Notes: %s' % self.cap_notes
                new_purchase_order.message_post(body=body)

            self.message_post(body=body)

        return res


