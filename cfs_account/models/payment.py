from odoo import fields, models, api
import json


class AccountPayment(models.Model):
    _inherit = "account.payment"

    # EOI-388: Add remittance emails
    vendor_credit_ids = fields.Many2many(
        comodel_name="account.move",
        compute="_compute_vendor_credits",
        store=True,
        readonly=False,
    )

    @api.depends("reconciled_bill_ids")
    def _compute_vendor_credits(self):
        # EOI-388: Add remittance emails
        for bill in self.reconciled_bill_ids:
            self.vendor_credit_ids = None
            # Test that the widget exists and that we can get the proper data from the widget
            str_widget = bill.invoice_payments_widget
            if str_widget and "move_id" in str_widget:
                # Parse the json of the widget so that we can get the bill id
                widget = json.loads(str_widget)
                move_ids = [content.get("move_id") for content in widget["content"]]
                for move_id in move_ids:
                    # Since we only have the id number, we need to search for the record
                    account_move = self.env["account.move"].search(
                        [("id", "=", move_id)], limit=1
                    )
                    move_type = account_move.move_type
                    if move_type and move_type == "in_refund":
                        self.vendor_credit_ids += account_move