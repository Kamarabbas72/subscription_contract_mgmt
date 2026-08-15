# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError


class TestSubscriptionAccessRights(TransactionCase):
    """
    Verifies security boundaries:
    - Subscription Users can read/write but not delete
    - Subscription Managers can do everything
    - Portal users are scoped to their commercial entity
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'Access Test Product',
            'type': 'service',
        })
        cls.plan = cls.env['subscription.plan'].create({
            'name': 'Access Test Plan',
            'code': 'ACCESS_PLAN',
            'price_monthly': 100.0,
            'product_id': cls.product.id,
        })
        # Two separate companies / commercial entities
        cls.company_a = cls.env['res.partner'].create({
            'name': 'Company A',
            'is_company': True,
        })
        cls.company_b = cls.env['res.partner'].create({
            'name': 'Company B',
            'is_company': True,
        })
        # Portal user for Company A
        cls.portal_user_a = cls.env['res.users'].create({
            'name': 'Portal User A',
            'login': 'portal_a@test.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
            'partner_id': cls.company_a.id,
        })
        # Subscription user (internal)
        cls.sub_user = cls.env['res.users'].create({
            'name': 'Sub User',
            'login': 'sub_user@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('subscription_contract_mgmt.group_subscription_user').id
            ])],
        })
        # Subscription manager (internal)
        cls.sub_manager = cls.env['res.users'].create({
            'name': 'Sub Manager',
            'login': 'sub_mgr@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('subscription_contract_mgmt.group_subscription_manager').id
            ])],
        })
        # Contracts for each company
        today = date.today()
        cls.contract_a = cls.env['subscription.contract'].create({
            'name': 'Contract for A',
            'partner_id': cls.company_a.id,
            'plan_id': cls.plan.id,
            'date_start': today,
            'date_end': today + relativedelta(months=1),
        })
        cls.contract_b = cls.env['subscription.contract'].create({
            'name': 'Contract for B',
            'partner_id': cls.company_b.id,
            'plan_id': cls.plan.id,
            'date_start': today,
            'date_end': today + relativedelta(months=1),
        })

    def test_subscription_user_can_read_contract(self):
        contract = self.contract_a.with_user(self.sub_user)
        # Should not raise
        _ = contract.name

    def test_subscription_user_cannot_delete_contract(self):
        with self.assertRaises(AccessError):
            self.contract_a.with_user(self.sub_user).unlink()

    def test_subscription_manager_can_delete_contract(self):
        """Manager should be able to unlink (delete) contracts."""
        temp = self.env['subscription.contract'].create({
            'name': 'Delete Test',
            'partner_id': self.company_a.id,
            'plan_id': self.plan.id,
            'date_start': date.today(),
            'date_end': date.today() + relativedelta(months=1),
        })
        temp.with_user(self.sub_manager).unlink()
        self.assertFalse(self.env['subscription.contract'].search([('name', '=', 'Delete Test')]))

    def test_portal_user_cannot_write_contract(self):
        """Portal users should only have read access."""
        with self.assertRaises(AccessError):
            self.contract_a.with_user(self.portal_user_a).write({'name': 'Hacked'})

    def test_portal_user_cannot_create_contract(self):
        with self.assertRaises(AccessError):
            self.env['subscription.contract'].with_user(self.portal_user_a).create({
                'name': 'Unauthorized Contract',
                'partner_id': self.company_a.id,
                'plan_id': self.plan.id,
                'date_start': date.today(),
                'date_end': date.today() + relativedelta(months=1),
            })

    def test_plan_manager_can_create_plan(self):
        new_plan = self.env['subscription.plan'].with_user(self.sub_manager).create({
            'name': 'Manager Created Plan',
            'code': 'MGR_PLAN',
            'price_monthly': 150.0,
            'product_id': self.product.id,
        })
        self.assertTrue(new_plan.id)

    def test_plan_user_cannot_create_plan(self):
        with self.assertRaises(AccessError):
            self.env['subscription.plan'].with_user(self.sub_user).create({
                'name': 'User Created Plan',
                'code': 'USR_PLAN',
                'price_monthly': 150.0,
                'product_id': self.product.id,
            })
