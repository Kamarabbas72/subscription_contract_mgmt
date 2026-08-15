# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestSubscriptionContract(TransactionCase):
    """
    Integration tests for subscription.contract state machine,
    date logic, invoice generation, and cron behavior.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Subscription Service',
            'type': 'service',
        })
        # Plan
        cls.plan = cls.env['subscription.plan'].create({
            'name': 'Test Pro Plan',
            'code': 'TEST_PRO',
            'price_monthly': 300.0,
            'billing_cycle': 'monthly',
            'grace_period_days': 7,
            'trial_days': 0,
            'product_id': cls.product.id,
        })
        # Partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Company Ltd',
            'is_company': True,
            'email': 'billing@testcompany.com',
        })

    def _create_contract(self, state='draft', **kwargs):
        today = date.today()
        defaults = {
            'name': 'Test Contract',
            'partner_id': self.partner.id,
            'plan_id': self.plan.id,
            'billing_cycle': 'monthly',
            'date_start': today,
            'date_end': today + relativedelta(months=1),
        }
        defaults.update(kwargs)
        contract = self.env['subscription.contract'].create(defaults)
        if state == 'active':
            contract.action_activate()
        elif state == 'pending_renewal':
            contract.action_activate()
            contract.action_set_pending_renewal()
        elif state == 'suspended':
            contract.action_activate()
            contract.action_suspend()
        elif state == 'cancelled':
            contract.action_activate()
            contract.action_cancel()
        return contract

    # ── Reference generation ──────────────────────────────────
    def test_reference_auto_generated(self):
        """Reference should be auto-assigned from ir.sequence on create."""
        contract = self._create_contract()
        self.assertNotEqual(contract.reference, 'New',
                            'Reference should be generated from sequence.')
        self.assertTrue(contract.reference.startswith('SUB/'))

    # ── Computed fields ───────────────────────────────────────
    def test_recurring_amount_computed_from_plan(self):
        contract = self._create_contract()
        self.assertEqual(contract.recurring_amount, 300.0)

    def test_final_amount_with_discount(self):
        contract = self._create_contract(discount=10.0)
        self.assertAlmostEqual(contract.final_amount, 270.0, places=2)

    def test_final_amount_no_discount(self):
        contract = self._create_contract(discount=0.0)
        self.assertEqual(contract.final_amount, 300.0)

    def test_days_until_renewal_positive(self):
        contract = self._create_contract(
            date_end=date.today() + relativedelta(months=1)
        )
        self.assertGreater(contract.days_until_renewal, 0)

    # ── State machine: happy paths ────────────────────────────
    def test_activate_from_draft(self):
        contract = self._create_contract()
        self.assertEqual(contract.state, 'draft')
        contract.action_activate()
        self.assertEqual(contract.state, 'active')

    def test_pending_renewal_from_active(self):
        contract = self._create_contract(state='active')
        contract.action_set_pending_renewal()
        self.assertEqual(contract.state, 'pending_renewal')

    def test_renew_from_pending_renewal(self):
        contract = self._create_contract(state='pending_renewal')
        original_end = contract.date_end
        contract.action_renew()
        self.assertEqual(contract.state, 'active')
        self.assertGreater(contract.date_end, original_end,
                           'date_end should be extended after renewal.')
        self.assertEqual(contract.renewal_count, 1)

    def test_renew_increments_renewal_count(self):
        contract = self._create_contract(state='pending_renewal')
        contract.action_renew()
        contract.action_set_pending_renewal()
        contract.action_renew()
        self.assertEqual(contract.renewal_count, 2)

    def test_suspend_from_active(self):
        contract = self._create_contract(state='active')
        contract.action_suspend()
        self.assertEqual(contract.state, 'suspended')
        self.assertEqual(contract.date_suspended, date.today())

    def test_renew_from_suspended(self):
        contract = self._create_contract(state='suspended')
        contract.action_renew()
        self.assertEqual(contract.state, 'active')
        self.assertFalse(contract.date_suspended)

    def test_cancel_from_active(self):
        contract = self._create_contract(state='active')
        contract.action_cancel()
        self.assertEqual(contract.state, 'cancelled')
        self.assertEqual(contract.date_cancelled, date.today())

    def test_reset_to_draft_from_cancelled(self):
        contract = self._create_contract(state='cancelled')
        contract.action_reset_to_draft()
        self.assertEqual(contract.state, 'draft')
        self.assertFalse(contract.date_cancelled)

    # ── State machine: invalid transitions ───────────────────
    def test_activate_non_draft_raises(self):
        contract = self._create_contract(state='active')
        with self.assertRaises(UserError):
            contract.action_activate()

    def test_pending_renewal_from_non_active_raises(self):
        contract = self._create_contract(state='suspended')
        with self.assertRaises(UserError):
            contract.action_set_pending_renewal()

    def test_cancel_already_cancelled_raises(self):
        contract = self._create_contract(state='cancelled')
        with self.assertRaises(UserError):
            contract.action_cancel()

    def test_reset_non_cancelled_raises(self):
        contract = self._create_contract(state='active')
        with self.assertRaises(UserError):
            contract.action_reset_to_draft()

    def test_renew_from_draft_raises(self):
        contract = self._create_contract()
        with self.assertRaises(UserError):
            contract.action_renew()

    # ── Plan change restriction ───────────────────────────────
    def test_cannot_change_plan_on_active_contract(self):
        contract = self._create_contract(state='active')
        new_plan = self.env['subscription.plan'].create({
            'name': 'Another Plan',
            'code': 'ANOTHER',
            'price_monthly': 500.0,
            'product_id': self.product.id,
        })
        with self.assertRaises(UserError):
            contract.write({'plan_id': new_plan.id})

    # ── Date constraints ──────────────────────────────────────
    def test_end_date_before_start_raises(self):
        today = date.today()
        with self.assertRaises(ValidationError):
            self.env['subscription.contract'].create({
                'name': 'Bad Dates',
                'partner_id': self.partner.id,
                'plan_id': self.plan.id,
                'date_start': today,
                'date_end': today - relativedelta(days=1),
            })

    def test_discount_out_of_range_raises(self):
        with self.assertRaises(ValidationError):
            self._create_contract(discount=101.0)

    # ── Invoice generation ────────────────────────────────────
    def test_generate_renewal_invoice_creates_move(self):
        contract = self._create_contract(state='active')
        invoice = contract._generate_renewal_invoice()
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertEqual(invoice.subscription_contract_id, contract)

    def test_invoice_amount_matches_final_amount(self):
        contract = self._create_contract(state='active', discount=10.0)
        invoice = contract._generate_renewal_invoice()
        line = invoice.invoice_line_ids[0]
        self.assertAlmostEqual(line.price_unit, contract.final_amount, places=2)

    def test_manual_invoice_action_returns_form(self):
        contract = self._create_contract(state='active')
        action = contract.action_generate_invoice_now()
        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(action['view_mode'], 'form')

    # ── Billing cycle date extension ──────────────────────────
    def test_extend_monthly(self):
        contract = self._create_contract(billing_cycle='monthly',
                                         date_end=date(2027, 1, 31))

    def test_extend_annual(self):
        contract = self._create_contract(billing_cycle='annual',
                                         date_end=date(2027, 6, 15))
        new_end = contract._extend_contract_dates()
        self.assertEqual(new_end, date(2028, 6, 15))
    # ── Prorated amount ───────────────────────────────────────
    def test_prorated_amount(self):
        contract = self._create_contract()
        # 15 days used out of 30 = 50% of final_amount
        prorated = contract._prorated_amount(15, 30)
        self.assertAlmostEqual(prorated, contract.final_amount * 0.5, places=2)

    def test_prorated_amount_zero_total_days(self):
        contract = self._create_contract()
        self.assertEqual(contract._prorated_amount(10, 0), 0.0)

    # ── Cron: check renewals ──────────────────────────────────
    def test_cron_check_renewals_sets_pending(self):
        """Contracts expiring within 30 days should become pending_renewal."""
        contract = self._create_contract(
            state='active',
            date_end=date.today() + relativedelta(days=10),
        )
        self.env['subscription.contract']._cron_check_renewals()
        self.assertEqual(contract.state, 'pending_renewal')

    def test_cron_check_renewals_ignores_far_future(self):
        """Contracts expiring far in the future should stay active."""
        contract = self._create_contract(
            state='active',
            date_end=date.today() + relativedelta(months=6),
        )
        self.env['subscription.contract']._cron_check_renewals()
        self.assertEqual(contract.state, 'active')
