# Multi-Tenancy Architecture — Exzelon RA Agent

> Referenced from: `CLAUDE.md` — Read this when working on tenant isolation, plan limits, or multi-tenant features.

## Overview

- **All 39 data models** have `tenant_id` column (NOT NULL, FK to `tenants.tenant_id`, indexed)
- **All 29 endpoint files** use `get_current_tenant_id` dependency + `tenant_filter` query helper
- **Super admin** (`tenant_id=None`) sees all tenants' data; regular users see only their tenant

## Tenant Model

```python
class Tenant:
    tenant_id: int  # PK
    name: str
    slug: str  # unique
    plan: TenantPlan  # starter/professional/enterprise
    is_active: bool
    website: str  # URL
    industry: str  # saas/recruiting/healthcare/ecommerce/finance/general
    # Plan limits
    max_users: int
    max_mailboxes: int
    max_contacts: int
    max_campaigns: int
    max_leads: int
    # Billing columns
    monthly_price_cents: int
    billing_email: str
    billing_address_json: str
    stripe_customer_id: str
    tax_rate_percent: float
```

## Super Admin Features

- **Impersonation**: `X-Tenant-ID` header or `/admin/tenants/{id}/impersonate` endpoint
- **Admin panel**: `/admin/tenants` — list, detail, update, deactivate tenants
- **Cross-tenant visibility**: All queries return all tenants' data when `tenant_id=None`

## Plan Limits

Enforced at CREATE endpoints via `check_plan_limit()` in `api/deps/plan_limits.py`.

| Plan | Users | Mailboxes | Contacts | Campaigns | Leads |
|------|-------|-----------|----------|-----------|-------|
| Starter | 3 | 5 | 500 | 5 | 1000 |
| Professional | 10 | 25 | 5000 | 25 | 10000 |
| Enterprise | Unlimited | Unlimited | Unlimited | Unlimited | Unlimited |

## Key Dependencies

- `get_current_tenant_id()` in `api/deps/auth.py` — extracts tenant context from JWT
- `tenant_filter(query, Model)` — appends `.filter(Model.tenant_id == tenant_id)` to any query
- JWT claims include `tenant_id` + `plan` for frontend tenant-aware logic

## Demo Seeder

`services/demo_seeder.py` — seeds sample data for new starter-plan tenants on email verification:
- Sample leads, contacts, clients
- Sample mailbox, campaign with steps
- Getting started widget auto-detects seeded data

## Tenant Cleanup (Scheduler)

Runs at 3 AM UTC:
- Deactivates empty tenants (no users, no data)
- Deletes unverified users older than 72 hours

## Implementation Phases (Completed)

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1 | Tenant model, User.tenant_id, JWT context, signup/verify | COMPLETE |
| Phase 2 | LeadDetails, ContactDetails, ClientInfo, SenderMailbox + 57 routes | COMPLETE |
| Phase 3 | Campaign, OutreachEvent, InboxMessage, EmailTemplate + services | COMPLETE |
| Phase 4 | 13 remaining tables + all 27 endpoint files | COMPLETE |
| Phase 5 | plan_limits.py, demo_seeder.py, starter plan enforcement | COMPLETE |
| Phase 6 | admin_tenants.py (5 routes), tenant cleanup scheduler | COMPLETE |

## Ad-Hoc Migrations

Phase 2-4 migration blocks in `main.py` lifespan:
- ALTER TABLE to add `tenant_id` columns
- Backfill existing rows with default tenant
- Add NOT NULL constraints
- Create indexes
