# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AccountMove(models.Model):
    """Extend account.move to link invoices to subscription contracts."""
    _inherit = 'account.move'

    subscription_contract_id = fields.Many2one(
        'subscription.contract',
        string='Subscription Contract',
        ondelete='set null',
        index=True,
        copy=False,
    )


class ResPartner(models.Model):
    """Extend res.partner with subscription contract summary."""
    _inherit = 'res.partner'

    contract_ids = fields.One2many(
        'subscription.contract',
        'partner_id',
        string='Subscription Contracts',
    )
    contract_count = fields.Integer(
        string='Contracts',
        compute='_compute_contract_count',
    )
    active_contract_count = fields.Integer(
        string='Active Contracts',
        compute='_compute_contract_count',
    )

    def _compute_contract_count(self):
        Contract = self.env['subscription.contract']
        for partner in self:
            contracts = Contract.search([('commercial_partner_id', '=', partner.commercial_partner_id.id)])
            partner.contract_count = len(contracts)
            partner.active_contract_count = len(contracts.filtered(lambda c: c.state == 'active'))

    def action_view_contracts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contracts'),
            'res_model': 'subscription.contract',
            'view_mode': 'list,kanban,form',
            'domain': [('commercial_partner_id', '=', self.commercial_partner_id.id)],
            'context': {'default_partner_id': self.id},
        }
