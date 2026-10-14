# -*- coding: utf-8 -*-
import logging
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError

_logger = logging.getLogger(__name__)


class SubscriptionPortal(CustomerPortal):
    """
    Extends the Odoo customer portal to expose subscription contracts
    to the commercial partner's portal users.

    Security: record-rule `subscription_contract_portal_rule` (defined in
    security/subscription_security.xml) ensures portal users can only
    access contracts whose `commercial_partner_id` matches their own.
    """

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'contract_count' in counters:
            values['contract_count'] = request.env['subscription.contract'].search_count(
                self._get_contract_domain()
            )
        return values

    def _get_contract_domain(self):
        partner = request.env.user.partner_id.commercial_partner_id
        return [
            ('commercial_partner_id', '=', partner.id),
            ('state', 'not in', ['cancelled']),
        ]

    # ──────────────────────────────────────────────
    # Contract list
    # ──────────────────────────────────────────────
    @http.route(['/my/contracts', '/my/contracts/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_contracts(self, page=1, sortby=None, filterby=None, **kw):
        Contract = request.env['subscription.contract']
        domain = self._get_contract_domain()

        searchbar_sortings = {
            'date': {'label': _('Renewal Date'), 'order': 'date_end asc'},
            'name': {'label': _('Reference'), 'order': 'reference asc'},
            'state': {'label': _('Status'), 'order': 'state'},
            'amount': {'label': _('Amount'), 'order': 'final_amount desc'},
        }
        searchbar_filters = {
            'all': {'label': _('All'), 'domain': []},
            'active': {'label': _('Active'), 'domain': [('state', '=', 'active')]},
            'pending': {'label': _('Pending Renewal'), 'domain': [('state', '=', 'pending_renewal')]},
            'suspended': {'label': _('Suspended'), 'domain': [('state', '=', 'suspended')]},
        }

        sortby = sortby or 'date'
        filterby = filterby or 'all'
        order = searchbar_sortings[sortby]['order']
        domain += searchbar_filters[filterby]['domain']

        contract_count = Contract.search_count(domain)
        pager = portal_pager(
            url='/my/contracts',
            url_args={'sortby': sortby, 'filterby': filterby},
            total=contract_count,
            page=page,
            step=10,
        )
        contracts = Contract.search(domain, order=order, limit=10, offset=pager['offset'])

        return request.render('subscription_contract_mgmt.portal_my_contracts', {
            'contracts': contracts,
            'page_name': 'contracts',
            'pager': pager,
            'default_url': '/my/contracts',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': searchbar_filters,
            'filterby': filterby,
        })

    # ──────────────────────────────────────────────
    # Contract detail
    # ──────────────────────────────────────────────
    @http.route('/my/contracts/<int:contract_id>', type='http', auth='user', website=True)
    def portal_contract_detail(self, contract_id, **kw):
        contract = self._get_contract_or_raise(contract_id)
        invoices = request.env['account.move'].search([
            ('subscription_contract_id', '=', contract.id),
            ('state', '=', 'posted'),
        ], order='invoice_date desc', limit=10)

        return request.render('subscription_contract_mgmt.portal_contract_detail', {
            'contract': contract,
            'invoices': invoices,
            'page_name': 'contracts',
        })

    # ──────────────────────────────────────────────
    # Request renewal (portal action)
    # ──────────────────────────────────────────────
    @http.route('/my/contracts/<int:contract_id>/request-renewal',
                type='http', auth='user', website=True, methods=['POST'])
    def portal_request_renewal(self, contract_id, **kw):
        contract = self._get_contract_or_raise(contract_id)
        if contract.state not in ('active', 'pending_renewal'):
            return request.redirect('/my/contracts/%d?error=invalid_state' % contract_id)
        contract.sudo().write({'renewal_requested': True})
        contract.sudo().message_post(
            body=_('Renewal requested by portal user: %s') % request.env.user.name,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )
        return request.redirect('/my/contracts/%d?success=renewal_requested' % contract_id)

    # ──────────────────────────────────────────────
    # Download invoice PDF stub
    # ──────────────────────────────────────────────
    @http.route('/my/contracts/<int:contract_id>/invoices',
                type='http', auth='user', website=True)
    def portal_contract_invoices(self, contract_id, **kw):
        contract = self._get_contract_or_raise(contract_id)
        invoices = request.env['account.move'].search([
            ('subscription_contract_id', '=', contract.id),
        ], order='invoice_date desc')
        return request.render('subscription_contract_mgmt.portal_contract_invoices', {
            'contract': contract,
            'invoices': invoices,
            'page_name': 'contracts',
        })

    # ──────────────────────────────────────────────
    # Helper
    # ──────────────────────────────────────────────
    def _get_contract_or_raise(self, contract_id):
        """
        Fetch contract and enforce that portal user belongs to the
        correct commercial entity. Raises 404 on mismatch.
        """
        try:
            contract = request.env['subscription.contract'].browse(contract_id)
            # sudo() read is safe here — record rule already filters at search level.
            # We verify commercial_partner match explicitly as defense-in-depth.
            my_commercial = request.env.user.partner_id.commercial_partner_id
            if contract.commercial_partner_id != my_commercial:
                raise AccessError(_('Access denied.'))
            return contract.sudo()
        except (AccessError, MissingError):
            raise MissingError(_('This contract does not exist or is not accessible.'))
