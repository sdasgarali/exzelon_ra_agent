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
    plan: TenantPlan  # free/pro/max/custom
    is_active: bool
    website: str  # URL
    industry: str  # saas/recruiting/healthcare/ecommerce/finance/general
    # Plan limits — 0 = "use the plan's number"; see the sentinel table below
    max_users: int
    max_mailboxes: int
    max_contacts: int
    max_campaigns: int
    max_leads: int
    max_lobs: int  # added 2026-09 (migration 0002)
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

## User ↔ Tenant Binding (`api/endpoints/users.py`)

Every user is bound to exactly ONE tenant, except `super_admin` (global, `tenant_id=NULL`).
- **Create**: super_admin picks the target tenant (required for non-super-admin roles;
  NULL for super_admin role); regular admins are forced to their own tenant (body
  `tenant_id` ignored). Super_admin-role users are always global.
- **List/get/update/delete**: tenant-scoped — regular admins only see/manage their own
  tenant's users (404 across tenants, via `_can_access_user`); super_admin sees all with
  an optional `tenant_id` filter. A non-super-admin caller with a NULL tenant is rejected
  (400) so `IS NULL`/`NULL==NULL` can never leak global users (`_caller_tenant_id`).
- **Reassign tenant**: super_admin only; role→super_admin forces NULL; leaving super_admin
  (or an explicit `tenant_id=null` on a normal role) requires a valid tenant.
- Frontend: Users page has a Tenant column + a super-admin-only tenant dropdown/filter.

## Plans & Limits

**Source of truth: `core/plans.py` (`PLAN_MATRIX`).** Limits, credit allowances, send
quotas and feature flags all live there — never hardcode them in a service or endpoint.
Enforced at CREATE endpoints via `check_plan_limit()` in `api/deps/plan_limits.py`.

Plans were renamed 2026-09 from starter/professional/enterprise to **free/pro/max**,
plus a new **custom** tier. See `Plan_Credit_System_And_Pricing.md`.

| Plan | Price/mo | Credits/mo | Sends/mo | Users | Mailboxes | Active campaigns | LOBs | Contacts | Leads |
|------|----------|-----------|----------|-------|-----------|------------------|------|----------|-------|
| Free | $0 | 300 | 500 | 1 | 1 | 2 | 1 | 1,000 | 2,000 |
| Pro | $99 | 6,000 | 25,000 | 1 | 25 | 25 | 1 | 25,000 | 50,000 |
| Max | $299 | 25,000 | 150,000 | 1 | 1,000 | 100 | 1 | 150,000 | 250,000 |
| Custom | Quoted | > Max | > Max | 1 | > Max | > Max | 1 | > Max | > Max |

**No tier is unlimited.** Every limit is a positive integer.

**Plan changes (2026-09-23).** Always via `services/billing/plan_change.change_plan()` —
credits move with the plan the moment it changes (upgrade = difference now), and a
Stripe subscription that ends (canceled/unpaid) returns the tenant to **Free**. Nothing is
deleted on downgrade: resources above Free's limits stay but can't grow, and paid features
402. Tests: `tests/integration/test_plan_change_credits.py`.

**One user, one workspace (2026-09-23).** Anyone who signs up gets their own tenant under
the platform and is its only user. Seats and lines of business are not sold on any tier.
Adding users (`POST /users`, `POST /auth/register`), managing LOBs (`POST/PUT/DELETE /lob`,
set-default, intent-signal run) and creating tenants are **super_admin only**. A tenant
admin's personal (non-RA) mailbox is created WITHOUT minting a login user. The LOB UI and
"Add User" are hidden for everyone but super_admin, and the layout clears any persisted
`activeLobId` for customers so no data stays filtered behind a LOB they cannot switch.
Customer data runs with `lob_id = NULL` (tenant-level config). Guarded by
`tests/security/test_single_user_workspace.py`.

### The `0` sentinel (changed 2026-09 — read this before touching limits)

A tenant's `max_*` column has exactly two states:

| Value | Meaning |
|-------|---------|
| `0` | Not configured for this tenant → **the plan's number applies** |
| `> 0` | Explicit per-tenant limit (support grant, trial bump, restricted account) |

It **never** means "unlimited". Previously `0` meant "unlimited" on professional and
"locked" on starter — the same value with two opposite meanings — and
`create_tenant_for_signup()` provisioned exactly those zeroes, so **every self-signup
tenant was unable to create a mailbox, lead, contact or campaign**. Such rows now fall
back to the plan. Whether a tenant may use a feature at all is a feature-gate question
(Phase 3), not a limit of zero.

### Counting rules

- **Campaigns count live state**, not lifetime: only `ACTIVE` and `PAUSED` occupy a
  slot (`LIVE_CAMPAIGN_STATUSES`). `DRAFT` is free and `COMPLETED`/`ARCHIVED` release
  their slot. Counting every row ever created made the cap a one-way ratchet.
- **Leads and contacts stay cumulative** — they are genuine storage. Their caps are set
  well above what a year of credits can produce, so credits remain the binding meter.
- **LOBs count rows in `lines_of_business`** (an instance table — several LOBs may share
  one `lob_type`). Distinct from `TenantLOBAssignment`, which gates *which* of the 6
  types a tenant may use.

### Feature gating (Phase 3)

Limits answer "how many"; the **feature gate** answers "at all". `core/plans.py` holds
`BASE_FEATURES` / `PRO_FEATURES` / `MAX_FEATURES` (strictly cumulative — upgrading never
removes a feature), and `api/deps/features.py` enforces them three ways:

| Helper | Use when |
|---|---|
| `require_feature("warmup")` | FastAPI dependency — router-level in `api/router.py` when a WHOLE area is paid, or per-endpoint |
| `ensure_feature(db, tid, "x")` | Inside an endpoint/service, when only some routes are gated |
| `has_feature(db, tid, "x")` | Branching rather than blocking (hiding UI, dropping a beacon) |

**Returns 402, not 403** — "your plan doesn't include it yet" is a payment state, same
as the credit gate. The body is a **structured dict** so the frontend can distinguish a
feature gate from an exhausted balance (both are 402):
`{code: "feature_not_in_plan", feature, feature_label, plan, required_plan, message}`.
`required_plan` is derived from `PLAN_MATRIX` by `minimum_plan_for()`, so the upgrade
prompt can never drift from what the tiers actually grant. Super admins bypass.

Gated at mount in `api/router.py`: warmup, automation, webhooks, crm_sync, roles,
analytics, email_preview, icp_wizard, sequence_generator, backups, dfy.
Gated per-endpoint (the router also serves un-gated routes): analytics `/forecast`,
integrations `/resource-pool/attribution[/export]`, leads `/intent-scores`, lob
`/{id}/intent-signals[/run]`, visitors `""` and `/stats`.

**`POST /visitors/track` is deliberately NOT gated with a 402.** It is a public beacon
from the customer's own website; a 402 there would surface as a console error on their
site and read as our bug. Unentitled plans get a 200 with `tracked: false` and the event
is dropped. `/visitors/pixel.js` stays fully public.

### SQLite and the credit race (dev/test only)

Credit spending is a read-then-write transaction (SELECT the balance, UPDATE it), and
SQLite has no row locks — `with_for_update()` compiles away. Two connections each take
a SHARED lock on the read, both try to escalate, and SQLite returns SQLITE_BUSY
**immediately** rather than waiting, because waiting could never resolve it. That is
why `busy_timeout` does not help.

The app engine gets **WAL + busy_timeout only** (`configure_sqlite_pragmas`). It
deliberately does NOT get `BEGIN IMMEDIATE`: that fixes the race but serialises
read-only transactions too, so one long-lived scheduler session blocks every request —
measured, not theorised; it hung the dev server. `configure_sqlite_write_locking()`
adds it and is used only by
`tests/security/test_credit_concurrency.py`, where serialisation is the point.

Production runs MySQL or PostgreSQL and needs none of this — they have real row locks,
and that test asserts `FOR UPDATE` is genuinely emitted for those dialects, since a
behavioural test on SQLite would pass whether the code asked for the lock or not.

### Test isolation: `DATABASE_URL` must be honoured

`Settings.DATABASE_URL` is a **property**, so an env var of the same name used to be
ignored — meaning every test run built `app.db.base.engine` against the developer's
real `data/ra_agent.db` and seeded it at app startup. It now returns an explicit
`DATABASE_URL` when one is set, which is what `tests/conftest.py` and
`migrations/env.py` always assumed.

### Send quota — the second meter

`services/send_quota.py`. Sends are **not** credits: marginal cost is ~$0 because
tenants bring their own mailboxes, and metering them in credits would make people
ration the one action the product exists to perform.

Counted from `OutreachEvent` (statuses `SENT`/`REPLIED`/`BOUNCED` — a bounce was still
a send; `SKIPPED` never left the building) rather than an incrementing counter, because
all five send paths already converge on that table and the one someone forgets to
increment becomes free sends nobody notices. Composite index
`idx_outreach_tenant_sent (tenant_id, sent_at)` (migration `0004`) keeps that count an
index range scan at Max's 150k/month. Warmup traffic is not counted — it has its own
tables.

Enforced as **check 0** of `send_gate.unified_send_gate()` — first, not last, because it
is the only tenant-level check and a failure makes every per-contact check below it
wasted work (including the AI orchestrator's LLM call). Skipped for `dry_run` and
`is_reply`. **Fails OPEN**: a counting bug must not stop a paying customer's campaign,
and the per-mailbox daily limit still bounds the damage.

### Custom tier

`plan=custom` is the only tier whose `max_*` columns are authoritative — they *are* the
contract. They are floored at Max's numbers (`custom_floor_violations()`), so a custom
plan can never be smaller than the tier it sits above. Set by a super_admin via
`PUT /admin/tenants/{id}`; quotes come in through `POST /billing/custom-quote`.

### Legacy plan names

`TenantPlan.STARTER / PROFESSIONAL / ENTERPRISE` remain as **enum aliases** of
FREE / PRO / MAX (same values, so Python binds them to the same members) and
`core.plans.normalize_plan()` maps the old strings from stale JWTs and API payloads.
Remove one release after migration `0002_plan_rename_and_max_lobs`.

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
