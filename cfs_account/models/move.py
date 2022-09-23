from odoo import fields, models, _
from odoo.exceptions import ValidationError, UserError

class AccountMove(models.Model):
    _inherit = "account.move"

    # EOI-392: Add default Journal on Register Payment wizard
    def action_register_payment(self):
        res = super(AccountMove, self).action_register_payment()
        default_journal = self.env["account.journal"].search([("payment_default", "=", True)])
        if default_journal:
            res["context"]["default_journal_id"] = default_journal.id
        # raise UserError(str(self))
        # EOI-491: Added check to make sure all bill's should be paid field are 'True'
        should_not_pay = self.filtered(lambda rec: rec.release_to_pay_manual != 'yes')
        if should_not_pay:
            raise UserError("Cannot register payment. Need to verify 2-way and/or 3-way match.")
        return res
