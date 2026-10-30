# -*- coding: utf-8 -*-
{
    'name': 'Subscription & Contract Lifecycle Management',
    'version': '17.0.1.0.0',
    'price': 149.99,
    'currency': 'EUR',
    'category': 'Sales/Subscriptions',
    'summary': 'B2B subscription contracts with portal self-service, automated renewals, and lifecycle management',
    'description': """
        Enterprise-grade subscription and contract lifecycle management for B2B SaaS
        and service companies. Clients manage their contracts via a self-service portal
        while automated cron jobs handle renewals, suspensions, and invoicing.
    """,
    'author': 'Kamarabbas Momin',
    'website': 'https://github.com/Kamarabbas72',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'portal',
        'account',
        'sale',
        'website',
    ],
    'data': [
        # Security
        'security/subscription_security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/mail_template_data.xml',
        'data/ir_cron_data.xml',
        'data/demo_data.xml',
        # Views
        'views/subscription_plan_views.xml',
        'views/subscription_contract_views.xml',
        'views/res_partner_views.xml',
        'views/subscription_dashboard_views.xml',
        'views/portal_templates.xml',
        'views/menu_views.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'subscription_contract_mgmt/static/src/scss/subscription.scss',
        ],
        'web.assets_frontend': [
            'subscription_contract_mgmt/static/src/scss/portal.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.png'],
}
