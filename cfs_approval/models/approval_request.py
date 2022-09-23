from odoo import models, fields, api


class ApprovalRequest(models.Model):

    _inherit = "approval.request"

    reason = fields.Text(required=True)
    po_canceled = fields.Boolean(compute='_compute_po_cancelled')

    api.depends('purchase_order.state')
    def _compute_po_cancelled(self):
        """EOI377 - compute if the POs are canceled
        """
        for pr in self:
            pos = pr.product_line_ids.purchase_order_line_id.order_id
            pr.po_canceled = not pos.filtered(lambda po: po.state != 'cancel')


    # EOI-322: Auto populate Buyer on Purchase Orders
    # EOI-469: Commented due to duplication, not deleting
    # def action_create_purchase_orders(self):
    #     """ Create and/or modifier Purchase Orders. """
    #     self.check_line_vendors()
    #     self.ensure_one()    

    #     for line in self.product_line_ids:
    #         seller = line._get_seller_id()
    #         vendor = seller.name
    #         if not seller :
    #             vendor = line.cap_vendor_name
    #         # The rest of the code was inside the "else" in line 108
    #         po_vals = line._get_purchase_order_values(vendor)
    #         po_vals['partner_id'] = line.cap_vendor_name.id 
    #         po_vals["cfs_buyer"] = self.env.user.id
    #         new_purchase_order = self.env['purchase.order'].create(po_vals)
    #         po_line_vals = self.env['purchase.order.line']._prepare_purchase_order_line(
    #             line.product_id,
    #             line.quantity,
    #             line.product_uom_id,
    #             line.company_id,
    #             seller,
    #             new_purchase_order,
    #         )
    #         po_line_vals['price_unit'] = line.cap_price

    #         new_po_line = self.env['purchase.order.line'].create(po_line_vals)
    #         line.purchase_order_line_id = new_po_line.id
    #         new_purchase_order.order_line = [(4, new_po_line.id)]

    # EOI-322: Auto populate Buyer on Purchase Orders
    @api.model
    def create(self, vals):
        vals["cap_buyer_ids"] = []
        for line in vals["product_line_ids"]:
            if line[2] and line[2]["buyer_id"]:
                vals["cap_buyer_ids"].append(line[2]["buyer_id"])
            # vals["cap_buyer_ids"].append(line.buyer_id)
        vals["cap_buyer_ids"] = [(6, 0, set(vals["cap_buyer_ids"]))] 
        return super(ApprovalRequest, self).create(vals)

    # EOI-372: Warehouse onchange action events
    @api.onchange('cap_warehouse')
    def _onchange_warehouse(self):
        for rec in self:
            if rec.cap_warehouse.wh_type == 'production':
                rec.product_line_ids.write({'is_prod': True})
                # rec.product_line_ids._onchange_buyer()
            else:
                rec.product_line_ids.write({'is_prod': False})
