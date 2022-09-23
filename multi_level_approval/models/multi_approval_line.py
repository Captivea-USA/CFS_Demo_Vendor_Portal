# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright Domiup (<http://domiup.com>).
#
##############################################################################

from odoo import api, models, fields
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

APPROVED = 10
REFUSED = 6

class MultiApprovalLine(models.Model):
    _name = 'multi.approval.line'
    _description = 'Multi Aproval Line'
    _order = 'sequence'

    name = fields.Char(string='Title', required=True)
    user_id = fields.Many2one(string='User', comodel_name="res.users",
                              required=True)
    sequence = fields.Integer(string='Sequence')
    require_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ], string="Type of Approval", default='Required')
    approval_id = fields.Many2one(
        string="Approval", comodel_name="multi.approval")
    state = fields.Selection(
        [('Draft', 'Draft'),
         ('Waiting for Approval', 'Waiting for Approval'),
         ('Approved', 'Approved'),
         ('Refused', 'Refused'),
         ('Cancel', 'Cancel'),
         ], default="Draft")
    refused_reason = fields.Text('Refused Reason')
    deadline = fields.Date(string='Deadline')

    # EOI-349: Adding fields to match UAT v14
    user_approval_ids = fields.One2many('user.approval.tags', inverse_name='request_level_id', string='Done', readonly="True")
    level = fields.Integer(string="Level")
    min_approval = fields.Integer(string="Min. To Approve")
    everyone_approves = fields.Boolean(string="Everyone Approves")
    request_id = fields.Many2one('res.users',string="Requester")
    user_ids = fields.Many2many('res.users',string="To Approve")
    # to_approve = fields.Many2many('approval.approver')
    status = fields.Selection([
        ('new','New'),
        ('pending','To Approve'),
        ('approved','Approved'),
        ('refused','Refused'),
        ('cancel','Cancel')
    ], string="Status")
    action_timestamp = fields.Datetime(string="Action Timestamp")

    # 13.0.1.1
    def set_approved(self):
        self.ensure_one()
        self.state = 'Approved'

    def set_refused(self, reason=''):
        self.ensure_one()
        self.write({
            'state': 'Refused',
            'refused_reason': reason
        })

    # EOI-349: Changes tag color to green if APPROVED
    def is_level_approved(self):
        """Returns True if the number of approvals in the level is greater than or equal to the minimum approvals."""
        self.ensure_one()
        min_approvals = len(self.mapped('user_ids')) if self.everyone_approves else self.min_approval
        current_approvals = len(self.user_approval_ids.filtered(lambda a: a.color == APPROVED))
        # raise UserError(str(current_approvals))
        if current_approvals >= min_approvals:
            return True
        return False
    # EOI-349: Changes tag color to red if REFUSED
    def is_level_refused(self):
        """Returns True if at least one user in this level refused the request."""
        self.ensure_one()
        return True if self.user_approval_ids.filtered(lambda a: a.color == REFUSED) else False

    # EOI-349: Creates activities for users when it is time for them to approve
    def _create_activity(self):
        """EOI499 - Use an approval activity type
        """
        for approver in self:
            pending_users = approver.user_ids.filtered(lambda u: u not in approver.user_approval_ids.mapped('user_id'))
            for user in pending_users:
                if not approver.approval_id._get_user_approval_activities(user=user):
                    approver.approval_id.activity_schedule(
                        'approvals.mail_activity_data_approval',
                        user_id=user.id)
