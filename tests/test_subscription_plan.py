# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestSubscriptionPlan(TransactionCase):
    """Unit tests for subscription.plan model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Plan = cls.env['subscription.plan']
        cls.product = cls.env['product.product'].create({
            'name': 'Test Service Product',
            'type': 'service',
        })

    def _create_plan(self, **kwargs):
        defaults = {
            'name': 'Test Plan',
            'code': 'TEST_PLAN',
            'price_monthly': 100.0,
            'billing_cycle': 'monthly',
            'product_id': self.product.id,
        }
        defaults.update(kwargs)
        return self.Plan.create(defaults)

    def test_annual_price_computed_correctly(self):
        """Annual price should be 10x monthly (2 months free)."""
        plan = self._create_plan(price_monthly=100.0)
        self.assertEqual(plan.price_annual, 1000.0,
                         'Annual price should be 10x monthly.')

    def test_get_price_for_cycle_monthly(self):
        plan = self._create_plan(price_monthly=200.0)
        self.assertEqual(plan._get_price_for_cycle('monthly'), 200.0)

    def test_get_price_for_cycle_quarterly(self):
        plan = self._create_plan(price_monthly=200.0)
        self.assertEqual(plan._get_price_for_cycle('quarterly'), 600.0)

    def test_get_price_for_cycle_annual(self):
        plan = self._create_plan(price_monthly=200.0)
        self.assertEqual(plan._get_price_for_cycle('annual'), 2000.0)

    def test_negative_price_raises_validation(self):
        """Negative monthly price must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self._create_plan(price_monthly=-10.0)

    def test_grace_period_minimum_one_day(self):
        """Grace period must be >= 1 day."""
        with self.assertRaises(ValidationError):
            self._create_plan(grace_period_days=0)

    def test_plan_archive_unarchive(self):
        plan = self._create_plan(name='Archivable Plan', code='ARCHIVE_TEST')
        plan.active = False
        self.assertFalse(plan.active)
        plan.active = True
        self.assertTrue(plan.active)

    def test_contract_count_empty(self):
        """New plan with no contracts should have count = 0."""
        plan = self._create_plan(name='Empty Plan', code='EMPTY_PLAN')
        self.assertEqual(plan.contract_count, 0)
