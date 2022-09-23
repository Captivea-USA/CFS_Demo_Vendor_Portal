from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.analytic.account'

    user_id = fields.Many2one('Responsible', 'res.users') 
