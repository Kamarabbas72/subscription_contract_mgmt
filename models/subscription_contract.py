# -*- coding: utf-8 -*-
import logging
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SubscriptionContract(models.Model):
    """
    Core model representing a B2B subscription contract.

    State machine:
        draft → active → pending_renewal → suspended → cancelled
                   ↑______________|  (renewed)
                   └── cancelled (early termination)

    Audit trail is maintained via mail.thread tracking on every
    state-changing field. All automated transitions are triggered
    by ir.cron jobs defined in data/ir_cron_data.xml.
    """
    _name = 'subscription.contract'
    _description = 'Subscription Contract'
    _order = 'date_start desc, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'reference'

    # ──────────────────────────────────────────────
    # Identity
    # ──────────────────────────────────────────────
    reference = fields.Char(
        string='Contract Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    name = fields.Char(
        string='Contract Name',
        required=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Client',
        required=True,
        tracking=True,
        domain=[('is_company', '=', True)],
        index=True,
    )
    commercial_partner_id = fields.Many2one(
        'res.partner',
        string='Commercial Entity',
        related='partner_id.commercial_partner_id',
        store=True,
        index=True,
        help='Used for portal record rule scoping',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Account Manager',
        default=lambda self: self.env.user,
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='plan_id.currency_id',
        store=True,
    )

    # ──────────────────────────────────────────────
    # Plan & Pricing
    # ──────────────────────────────────────────────
    plan_id = fields.Many2one(
        'subscription.plan',
        string='Subscription Plan',
        required=True,
        tracking=True,
        ondelete='restrict',
    )
    billing_cycle = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annual', 'Annual'),
    ], string='Billing Cycle', required=True, default='monthly', tracking=True)

    recurring_amount = fields.Monetary(
        string='Recurring Amount',
        currency_field='currency_id',
        compute='_compute_recurring_amount',
        store=True,
        tracking=True,
    )
    discount = fields.Float(
        string='Discount (%)',
        default=0.0,
        tracking=True,
        help='Custom discount applied on top of plan pricing',
    )
    final_amount = fields.Monetary(
        string='Final Amount',
        currency_field='currency_id',
        compute='_compute_final_amount',
        store=True,
    )

    # ──────────────────────────────────────────────
    # Dates
    # ──────────────────────────────────────────────
    date_start = fields.Date(
        string='Start Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    date_trial_end = fields.Date(
        string='Trial End Date',
        compute='_compute_date_trial_end',
        store=True,
    )
    date_end = fields.Date(
        string='End / Renewal Date',
        tracking=True,
        help='Date contract expires and renewal cycle begins',
    )
    date_next_invoice = fields.Date(
        string='Next Invoice Date',
        tracking=True,
    )
    date_suspended = fields.Date(
        string='Suspended On',
        readonly=True,
    )
    date_cancelled = fields.Date(
        string='Cancelled On',
        readonly=True,
    )

    # ──────────────────────────────────────────────
    # State Machine
    # ──────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('pending_renewal', 'Pending Renewal'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ], string='Status',
        default='draft',
        tracking=True,
        index=True,
        group_expand='_group_expand_states',
    )

    # ──────────────────────────────────────────────
    # Invoice / Renewal tracking
    # ──────────────────────────────────────────────
    invoice_ids = fields.One2many(
        'account.move',
        'subscription_contract_id',
        string='Invoices',
    )
    invoice_count = fields.Integer(
        string='Invoices',
        compute='_compute_invoice_count',
    )
    renewal_count = fields.Integer(
        string='Renewals',
        default=0,
        readonly=True,
    )
    cancellation_reason = fields.Text(
        string='Cancellation Reason',
        tracking=True,
    )
    renewal_requested = fields.Boolean(
        string='Renewal Requested by Client',
        default=False,
        tracking=True,
        help='Set via portal when client clicks Request Renewal',
    )

    # ──────────────────────────────────────────────
    # Computed / utility
    # ──────────────────────────────────────────────
    days_until_renewal = fields.Integer(
        string='Days Until Renewal',
        compute='_compute_days_until_renewal',
    )
    is_overdue = fields.Boolean(
        string='Overdue',
        compute='_compute_is_overdue',
        store=True,
    )
    portal_url = fields.Char(
        string='Portal URL',
        compute='_compute_portal_url',
    )

    # ──────────────────────────────────────────────
    # Computes
    # ──────────────────────────────────────────────
    @api.depends('plan_id', 'billing_cycle')
    def _compute_recurring_amount(self):
        for rec in self:
            if rec.plan_id:
                rec.recurring_amount = rec.plan_id._get_price_for_cycle(rec.billing_cycle)
            else:
                rec.recurring_amount = 0.0

    @api.depends('recurring_amount', 'discount')
    def _compute_final_amount(self):
        for rec in self:
            rec.final_amount = rec.recurring_amount * (1 - rec.discount / 100)

    @api.depends('date_start', 'plan_id')
    def _compute_date_trial_end(self):
        for rec in self:
            if rec.plan_id and rec.plan_id.trial_days and rec.date_start:
                rec.date_trial_end = rec.date_start + timedelta(days=rec.plan_id.trial_days)
            else:
                rec.date_trial_end = False

    @api.depends('date_end')
    def _compute_days_until_renewal(self):
        today = date.today()
        for rec in self:
            if rec.date_end:
                rec.days_until_renewal = (rec.date_end - today).days
            else:
                rec.days_until_renewal = 0

    @api.depends('date_next_invoice', 'state')
    def _compute_is_overdue(self):
        today = date.today()
        for rec in self:
            if rec.state == 'active' and rec.date_next_invoice:
                rec.is_overdue = rec.date_next_invoice < today
            else:
                rec.is_overdue = False

    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    def _compute_portal_url(self):
        for rec in self:
            rec.portal_url = '/my/contracts/%d' % rec.id

    # ──────────────────────────────────────────────
    # State machine actions
    # ──────────────────────────────────────────────
    def action_activate(self):
        """draft → active"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only Draft contracts can be activated.'))
            rec._validate_activation()
            rec.write({
                'state': 'active',
                'date_next_invoice': rec._compute_next_invoice_date(rec.date_start),
            })
            rec.message_post(
                body=_('Contract activated. First invoice due on %s.') % rec.date_next_invoice,
                message_type='notification',
            )
        return True

    def action_set_pending_renewal(self):
        """active → pending_renewal (triggered by cron or manually)"""
        for rec in self:
            if rec.state != 'active':
                raise UserError(_('Only Active contracts can be set to Pending Renewal.'))
            rec.write({'state': 'pending_renewal'})
            template = self.env.ref(
                'subscription_contract_mgmt.email_template_renewal_reminder',
                raise_if_not_found=False,
            )
            if template:
                template.send_mail(rec.id, force_send=True)
        return True

    def action_renew(self):
        """pending_renewal → active (generates new invoice, extends dates)"""
        for rec in self:
            if rec.state not in ('pending_renewal', 'suspended'):
                raise UserError(_('Only Pending Renewal or Suspended contracts can be renewed.'))
            new_end = rec._extend_contract_dates()
            invoice = rec._generate_renewal_invoice()
            rec.write({
                'state': 'active',
                'date_end': new_end,
                'date_next_invoice': rec._compute_next_invoice_date(date.today()),
                'renewal_count': rec.renewal_count + 1,
                'renewal_requested': False,
                'date_suspended': False,
            })
            rec.message_post(
                body=_(
                    'Contract renewed for cycle %s. New end date: %s. Invoice: %s'
                ) % (rec.billing_cycle, new_end, invoice.name),
                message_type='notification',
            )
        return True

    def action_suspend(self):
        """active/pending_renewal → suspended"""
        for rec in self:
            if rec.state not in ('active', 'pending_renewal'):
                raise UserError(_('Cannot suspend a contract in state: %s') % rec.state)
            rec.write({
                'state': 'suspended',
                'date_suspended': fields.Date.today(),
            })
            template = self.env.ref(
                'subscription_contract_mgmt.email_template_suspension_notice',
                raise_if_not_found=False,
            )
            if template:
                template.send_mail(rec.id, force_send=True)
        return True

    def action_cancel(self):
        """Any non-cancelled state → cancelled"""
        for rec in self:
            if rec.state == 'cancelled':
                raise UserError(_('Contract is already cancelled.'))
            rec.write({
                'state': 'cancelled',
                'date_cancelled': fields.Date.today(),
            })
            rec.message_post(
                body=_('Contract cancelled. Reason: %s') % (rec.cancellation_reason or 'N/A'),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_reset_to_draft(self):
        """cancelled → draft (for correction)"""
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Only cancelled contracts can be reset to draft.'))
            rec.write({
                'state': 'draft',
                'date_cancelled': False,
                'cancellation_reason': False,
            })
        return True

    # ──────────────────────────────────────────────
    # Cron-driven automation
    # ──────────────────────────────────────────────
    @api.model
    def _cron_check_renewals(self):
        """
        Cron: daily check.
        Contracts expiring within 30 days → pending_renewal.
        """
        threshold = date.today() + timedelta(days=30)
        contracts = self.search([
            ('state', '=', 'active'),
            ('date_end', '<=', threshold),
            ('date_end', '>=', date.today()),
        ])
        _logger.info('Subscription cron: %d contracts approaching renewal.', len(contracts))
        contracts.action_set_pending_renewal()

    @api.model
    def _cron_suspend_overdue(self):
        """
        Cron: daily check.
        Contracts overdue beyond grace period → suspended.
        """
        to_suspend = self.env['subscription.contract']
        actives = self.search([('state', '=', 'active')])
        for contract in actives:
            if not contract.date_next_invoice:
                continue
            grace = contract.plan_id.grace_period_days if contract.plan_id else 7
            overdue_since = contract.date_next_invoice + timedelta(days=grace)
            if overdue_since < date.today():
                # Check unpaid invoices
                unpaid = contract.invoice_ids.filtered(
                    lambda inv: inv.payment_state not in ('paid', 'in_payment')
                                and inv.state == 'posted'
                )
                if unpaid:
                    to_suspend |= contract
        _logger.info('Subscription cron: suspending %d overdue contracts.', len(to_suspend))
        to_suspend.action_suspend()

    @api.model
    def _cron_generate_invoices(self):
        """
        Cron: daily check.
        Generate renewal invoice for active contracts due today.
        """
        today = date.today()
        due = self.search([
            ('state', '=', 'active'),
            ('date_next_invoice', '=', today),
        ])
        _logger.info('Subscription cron: generating invoices for %d contracts.', len(due))
        for contract in due:
            try:
                contract._generate_renewal_invoice()
            except Exception as e:
                _logger.error('Invoice generation failed for contract %s: %s', contract.reference, e)

    # ──────────────────────────────────────────────
    # Business helpers
    # ──────────────────────────────────────────────
    def _validate_activation(self):
        self.ensure_one()
        if not self.date_end:
            raise UserError(_('Please set a contract End / Renewal Date before activating.'))
        if not self.plan_id.product_id:
            raise UserError(_(
                'Plan "%s" has no invoicing product configured. '
                'Please set one in Subscriptions → Plans.'
            ) % self.plan_id.name)

    def _compute_next_invoice_date(self, from_date):
        """Return next invoice date based on billing cycle."""
        self.ensure_one()
        if self.billing_cycle == 'monthly':
            return from_date + relativedelta(months=1)
        elif self.billing_cycle == 'quarterly':
            return from_date + relativedelta(months=3)
        elif self.billing_cycle == 'annual':
            return from_date + relativedelta(years=1)
        return from_date + relativedelta(months=1)

    def _extend_contract_dates(self):
        """Extend date_end by one billing cycle."""
        self.ensure_one()
        base = self.date_end or date.today()
        if self.billing_cycle == 'monthly':
            return base + relativedelta(months=1)
        elif self.billing_cycle == 'quarterly':
            return base + relativedelta(months=3)
        elif self.billing_cycle == 'annual':
            return base + relativedelta(years=1)
        return base + relativedelta(months=1)

    def _generate_renewal_invoice(self):
        """
        Create a draft invoice for this contract's recurring amount.
        Returns the created account.move record.
        """
        self.ensure_one()
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'journal_id': journal.id,
            'invoice_date': fields.Date.today(),
            'subscription_contract_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.plan_id.product_id.id,
                'name': _('%s — %s (%s)') % (
                    self.plan_id.name,
                    self.reference,
                    self.billing_cycle,
                ),
                'quantity': 1,
                'price_unit': self.final_amount,
            })],
            'narration': _('Subscription renewal — Contract %s') % self.reference,
        }
        invoice = self.env['account.move'].create(invoice_vals)
        _logger.info('Created invoice %s for contract %s', invoice.name, self.reference)
        return invoice

    def _prorated_amount(self, days_used, total_days):
        """Calculate prorated amount for mid-cycle plan upgrades."""
        self.ensure_one()
        if total_days <= 0:
            return 0.0
        return round((self.final_amount / total_days) * days_used, 2)

    # ──────────────────────────────────────────────
    # ORM overrides
    # ──────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code(
                    'subscription.contract'
                ) or _('New')
        return super().create(vals_list)

    def write(self, vals):
        # Prevent changing plan on active/suspended contracts without going through renew
        # Skip this check during module installation (loading context)
        if 'plan_id' in vals and not self.env.context.get('install_mode') and \
                any(r.state in ('active', 'suspended') for r in self):
            raise UserError(_(
                'Cannot change the plan on an active or suspended contract. '
                'Please cancel and create a new contract, or use the Renew action.'
            ))
        return super().write(vals)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end <= rec.date_start:
                raise ValidationError(_('End date must be after start date.'))

    @api.constrains('discount')
    def _check_discount(self):
        for rec in self:
            if not (0 <= rec.discount <= 100):
                raise ValidationError(_('Discount must be between 0 and 100%.'))

    @staticmethod
    def _group_expand_states(states, domain, order):
        return ['draft', 'active', 'pending_renewal', 'suspended', 'cancelled']

    # ──────────────────────────────────────────────
    # UI Actions
    # ──────────────────────────────────────────────
    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices — %s') % self.reference,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('subscription_contract_id', '=', self.id)],
            'context': {'default_subscription_contract_id': self.id},
        }

    def action_generate_invoice_now(self):
        """Manual invoice generation from form view."""
        self.ensure_one()
        if self.state not in ('active', 'pending_renewal'):
            raise UserError(_('Can only generate invoices for Active or Pending Renewal contracts.'))
        invoice = self._generate_renewal_invoice()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
        }
