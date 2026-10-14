# Subscription & Contract Lifecycle Management for Odoo 17

[![Odoo Version](https://img.shields.io/badge/Odoo-17.0-875A7B?style=flat&logo=odoo)](https://www.odoo.com)
[![License: LGPL-3](https://img.shields.io/badge/License-LGPL--3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python)](https://python.org)
[![OCA Standard](https://img.shields.io/badge/Code%20Style-OCA-875A7B)](https://github.com/OCA/odoo-community.org)

Enterprise-grade B2B subscription and contract lifecycle management for Odoo 17.
Built for SaaS and service companies that need automated renewals, self-service client portals, and full audit trails.

---

## Features

### Contract Lifecycle State Machine

```
draft ──► active ──► pending_renewal ──► suspended ──► cancelled
            ▲              │
            └──────────────┘  (renew)
```

Every state transition is tracked via `mail.thread` chatter, giving a complete audit trail on each contract record.

### Subscription Plans
- Define reusable tiers (Starter / Professional / Enterprise) with monthly, quarterly, or annual pricing
- Per-plan grace periods, trial days, and feature lists
- Linked to a service product for seamless invoice generation

### Automated Cron Jobs (3 independent schedulers)
| Cron | Schedule | Action |
|---|---|---|
| Check Approaching Renewals | Daily | Moves contracts expiring ≤ 30 days to `pending_renewal`, triggers renewal reminder email |
| Suspend Overdue Contracts | Daily | Suspends `active` contracts with unpaid invoices beyond the grace period |
| Generate Recurring Invoices | Daily | Auto-creates draft invoices for contracts due today |

### B2B Client Portal
Clients access `/my/contracts` to:
- View all subscription contracts for their commercial entity
- See contract status, plan features, and renewal date at a glance
- Request renewal with a single click (sets `renewal_requested` flag + posts chatter note)
- Browse invoice history with payment status

### Security — Record Rules
| Role | Scope |
|---|---|
| Subscription User | Contracts assigned to them or their company |
| Subscription Manager | All contracts in allowed companies; full CRUD including delete |
| Portal User | **Read-only**, scoped to their `commercial_partner_id` only — cannot see other companies' contracts |

This means a portal user at "Company A" can never see or access "Company B"'s contracts, even by guessing IDs.

### Analytics Dashboard
- **Kanban** grouped by state, color-coded with overdue/renewal-requested badges
- **Graph** view: MRR by plan
- **Pivot** view: revenue breakdown by plan × billing cycle

---

## Architecture

```
subscription_contract_mgmt/
├── models/
│   ├── subscription_plan.py          # Plan tiers & feature tags
│   ├── subscription_contract.py      # Core model + state machine + cron methods
│   └── res_partner.py               # account.move & res.partner extensions
├── controllers/
│   └── portal.py                    # CustomerPortal extension — /my/contracts/* routes
├── views/
│   ├── subscription_plan_views.xml
│   ├── subscription_contract_views.xml  # list, form, kanban, search
│   ├── subscription_dashboard_views.xml # graph + pivot
│   ├── portal_templates.xml         # QWeb portal templates
│   └── menu_views.xml
├── data/
│   ├── mail_template_data.xml       # 3 email templates + ir.sequence
│   ├── ir_cron_data.xml             # 3 scheduled actions
│   └── demo_data.xml               # Installable demo plans & contracts
├── security/
│   ├── subscription_security.xml    # Groups + 4 record rules
│   └── ir.model.access.csv
└── tests/
    ├── test_subscription_plan.py     # 8 plan tests
    ├── test_subscription_contract.py # 25+ contract & cron tests
    └── test_access_rights.py        # 7 security tests
```

---

## Quick Start

### Requirements
- Odoo 17.0
- Python packages: `python-dateutil` (already in Odoo deps)
- Depends on: `base`, `mail`, `portal`, `account`, `sale`, `website`

### Installation

```bash
# Clone into your custom addons directory
cd /path/to/odoo/custom_addons
git clone https://github.com/Kamarabbas72/subscription_contract_mgmt

# Restart Odoo with the new addon path
./odoo-bin -d your_database -u subscription_contract_mgmt
```

Or via Odoo UI: **Settings → Activate developer mode → Apps → Search "Subscription" → Install**

### First Steps After Installation
1. Go to **Subscriptions → Configuration → Plans** and create your subscription tiers
2. Set an invoicing service product on each plan (required before activation)
3. Create a contract under **Subscriptions → Contracts**
4. Click **Activate** — the first invoice date is set automatically
5. Grant portal access to your client via `res.partner` → Portal Access

---

## Running Tests

```bash
./odoo-bin -d test_db \
  --test-enable \
  --stop-after-init \
  -i subscription_contract_mgmt
```

Test coverage covers:
- Plan validation (pricing, grace period constraints)
- All valid and invalid state transitions
- Invoice generation and amount correctness
- Billing cycle date extension (monthly / quarterly / annual)
- Cron behavior (renewal detection, future contracts ignored)
- Access rights (user, manager, portal scoping)

---

## Key Technical Design Decisions

**Why `commercial_partner_id` for portal scoping?**
Odoo's `commercial_partner_id` resolves to the top-level company regardless of which contact (child partner) the portal user belongs to. This means all employees of "Company A" — regardless of which contact record they log in with — see all Company A contracts. The record rule uses `child_of` to cover nested contacts.

**Why three separate cron jobs?**
Separating renewal detection, suspension, and invoicing into independent schedulers means a failure in one (e.g. email template misconfiguration causing renewal emails to fail) doesn't block invoice generation. Each has its own priority and can be independently disabled or re-run.

**Why is `plan_id` write-protected on active contracts?**
Changing the plan mid-contract would silently alter the recurring amount without creating an audit trail or prorated adjustment invoice. The ORM-level `write()` override forces operators to go through the `action_renew` flow, which explicitly extends dates and generates a new invoice.

---

## Email Templates

| Template | Trigger |
|---|---|
| Renewal Reminder | `action_set_pending_renewal()` — 30 days before expiry |
| Suspension Notice | `action_suspend()` — on suspension |
| Contract Activated | Available for manual send on activation |

All templates use QWeb and are fully editable from **Settings → Email → Templates**.

---

## Author

**Kamarabbas Momin** — Odoo Backend Developer  
3+ years across Odoo 12–17 | Python · PostgreSQL · ORM  
[GitHub](https://github.com/Kamarabbas72) · [LinkedIn](https://linkedin.com/in/kamarabbas-momin)

---

## License

This module is released under the [GNU Lesser General Public License v3.0](https://www.gnu.org/licenses/lgpl-3.0).
