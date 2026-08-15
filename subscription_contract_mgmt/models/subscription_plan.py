# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SubscriptionPlan(models.Model):
    """
    Defines reusable subscription tiers (e.g. Starter, Pro, Enterprise).
    Each plan sets pricing, billing cycle, and included features.
    """
    _name = 'subscription.plan'
    _description = 'Subscription Plan'
    _order = 'price_monthly asc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Plan Name',
        required=True,
        tracking=True,
        help='e.g. Starter, Professional, Enterprise',
    )
    code = fields.Char(
        string='Plan Code',
        required=True,
        copy=False,
        help='Short unique identifier, e.g. STARTER_MONTHLY',
    )
    active = fields.Boolean(default=True, tracking=True)
    description = fields.Html(string='Plan Description')

    # Pricing
    price_monthly = fields.Monetary(
        string='Monthly Price',
        currency_field='currency_id',
        required=True,
        tracking=True,
    )
    price_annual = fields.Monetary(
        string='Annual Price',
        currency_field='currency_id',
        compute='_compute_price_annual',
        store=True,
        help='Computed as 10x monthly (2 months free)',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )

    # Billing
    billing_cycle = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annual', 'Annual'),
    ], string='Default Billing Cycle', default='monthly', required=True, tracking=True)

    trial_days = fields.Integer(
        string='Trial Days',
        default=0,
        help='Number of free trial days before billing begins',
    )
    grace_period_days = fields.Integer(
        string='Grace Period (days)',
        default=7,
        help='Days after invoice due date before contract is suspended',
    )

    # Features / Limits
    max_users = fields.Integer(string='Max Users', default=5)
    max_storage_gb = fields.Integer(string='Max Storage (GB)', default=10)
    feature_ids = fields.Many2many(
        'subscription.feature',
        string='Included Features',
    )

    # Product link for invoicing
    product_id = fields.Many2one(
        'product.product',
        string='Invoicing Product',
        domain=[('type', '=', 'service')],
        help='Service product used when generating renewal invoices',
    )

    contract_count = fields.Integer(
        string='Active Contracts',
        compute='_compute_contract_count',
    )

    @api.depends('price_monthly')
    def _compute_price_annual(self):
        for plan in self:
            plan.price_annual = plan.price_monthly * 10

    def _compute_contract_count(self):
        Contract = self.env['subscription.contract']
        for plan in self:
            plan.contract_count = Contract.search_count([
                ('plan_id', '=', plan.id),
                ('state', 'in', ['active', 'pending_renewal']),
            ])

    @api.constrains('price_monthly')
    def _check_price(self):
        for plan in self:
            if plan.price_monthly < 0:
                raise ValidationError(_('Monthly price cannot be negative.'))

    @api.constrains('grace_period_days')
    def _check_grace_period(self):
        for plan in self:
            if plan.grace_period_days < 1:
                raise ValidationError(_('Grace period must be at least 1 day.'))

    def action_view_contracts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contracts — %s') % self.name,
            'res_model': 'subscription.contract',
            'view_mode': 'list,kanban,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id},
        }

    def _get_price_for_cycle(self, billing_cycle):
        """Return the price for a given billing cycle."""
        self.ensure_one()
        if billing_cycle == 'monthly':
            return self.price_monthly
        elif billing_cycle == 'quarterly':
            return self.price_monthly * 3
        elif billing_cycle == 'annual':
            return self.price_annual
        return self.price_monthly


class SubscriptionFeature(models.Model):
    """Tag-like model listing discrete features included in a plan."""
    _name = 'subscription.feature'
    _description = 'Subscription Feature'
    _order = 'name'

    name = fields.Char(string='Feature', required=True, translate=True)
    icon = fields.Char(string='FA Icon', default='fa-check', help='FontAwesome class')
    description = fields.Text(string='Description', translate=True)
