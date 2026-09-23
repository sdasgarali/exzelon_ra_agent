# Plan WIP

## CURRENT TASK — Migrate MySQL -> Supabase (Postgres)
Full plan: `Plan_Supabase_Migration.md` (DRAFT, awaiting approval + 4 decisions).
Waiting on: user creating a Supabase account, then credentials -> `backend/.env` only.
Scoped 2026-09-17: 64 tables / 53 models / 19 enum cols; MySQL-only SQL isolated to
main.py (114-line legacy DDL block), job_run.py (LONGTEXT), config.py (utf8mb4 URL).
Top risk = MySQL ci-collation vs Postgres cs (mixed-case validation_status proven in data).


## ONE USER, ONE WORKSPACE — DONE 2026-09-23 (plan: `Plan_Remove_Seats_LOB.md`)
User decision: anyone who signs up becomes a tenant under the platform and is its ONLY user;
they cannot add users, LOBs or tenants — super_admin only. PLAN_MATRIX max_users=1/max_lobs=1
on every tier; POST /users + /auth/register + LOB writes = super_admin; a tenant admin's
personal mailbox no longer mints a login user; LOB UI + "Add User" hidden for non-super-admin;
seat/LOB rows removed from pricing, usage panel, custom-quote, docs, terms; homepage ROI
calculator (per-seat savings pitch, stale $49 prices) removed. Nothing deleted, no migration.
Local Playwright: `e2e/pricing-credits.spec.ts` 10/10 green (run with the uncommitted
`frontend/playwright.local.config.ts` — prod baseURL otherwise!).
LEGACY Playwright suite vs local empty DB: 30 pass / 38 fail / 30 not run — mostly empty-data
assertions + strict-mode selectors that predate the duplicated mobile/desktop nav. Not triaged.
OPEN (found 2026-09-23, not fixed): (1) mid-month upgrade leaves the old plan's credit allowance
until the 1st; (2) cancelled/unpaid subscription never downgrades tenant.plan to free.

## TRANSACTIONAL MAIL — RESEND (added 2026-09-22)
System mail (verification, password reset, deal notifications, invoices) now runs through
`services/adapters/transactional/` — Resend or SMTP, chosen by `SYSTEM_MAIL_PROVIDER`
(auto | resend | smtp | none). Key lives in `.env` only (gitignored); `.env.example` has
blank placeholders. Verified live: sends return a Resend message id.
HARD RULE: Resend is TRANSACTIONAL ONLY. Cold outreach keeps going through each tenant's
own mailboxes — their domain reputation, warmup, the 30/day send-gate pacing — and Resend's
terms ban cold email outright. `test_transactional_mail.py` asserts `campaign_engine` and
`pipelines/outreach` never import the transactional package.
Sender order: tenant's own SMTP > global provider > none. Forcing `resend`/`smtp` does NOT
silently fall back — mail from an unexpected sender is harder to debug than no mail.
`billing_mailer` had its own duplicate SMTP block that skipped silently whenever SMTP_HOST
was unset (so a Resend-only deploy would have sent zero invoices); it now routes through
`send_system_email` and gained PDF attachment support via `Attachment`.
The supplied key is SEND-ONLY scoped (cannot read /domains) — correct least privilege.
`RESEND_FROM_EMAIL` is currently `onboarding@resend.dev`, which only delivers to the Resend
account owner — set it to an address on a VERIFIED domain before relying on this in prod.

## PRICING / CREDIT SYSTEM — PHASES 0 + 1 IMPLEMENTED 2026-09-22 (1,504 tests green)
Done: `core/plans.py` PLAN_MATRIX (single source of truth), TenantPlan free/pro/max/custom with
legacy enum aliases + `normalize_plan()`, Alembic `0002_plan_rename_and_max_lobs`, signup-blocker
fix, `0`=use-plan-default sentinel, live-state campaign counting, LOB metering (`max_lobs` +
counter + gate on LOB create), custom-tier floor guard in admin_tenants, annual Stripe price ids,
`POST /billing/custom-quote`. Docs updated: multi-tenancy / data-models / api-endpoints /
STRIPE_SUBSCRIPTIONS_SETUP / .env.example.
PHASE 2 DONE 2026-09-22 (1,526 tests green): `core/credit_costs.py` price registry (6 credits =
one contact end-to-end), `TenantCreditBalance` + migration `0003` with `SELECT..FOR UPDATE`
(closes ELR-009b's sum-then-check race), metering wired at ALL 10 choke-points, monthly
`credit_refill` scheduler job (1st, 00:05), top-up flow (`POST /billing/credits/topup` +
`create_one_time_checkout` + webhook grant guarded by ProcessedStripeEvent),
`GET /credits/balance` + `/credits/price-list`.
Key semantics to preserve: GATE (`check_credit_budget`, raises 402, runs BEFORE work) vs METER
(`meter()`/`spend()`, never raises, runs AFTER). Allowance spent before top-ups; overage goes
NEGATIVE not clamped; no rollover; top-ups never expire. AI actions are charged only when the AI
path actually succeeds — the template/rule-based fallbacks are free.
PHASE 3 DONE 2026-09-22 (1,557 tests green): `api/deps/features.py` (require_feature dependency /
ensure_feature / has_feature) returning **402 with a STRUCTURED body** so the frontend can tell a
feature gate from an exhausted credit balance (both are 402); 11 routers gated at mount in
`api/router.py`, 6 partial gates in endpoint bodies; `services/send_quota.py` as the second meter,
wired as CHECK 0 of `unified_send_gate()` + composite index `idx_outreach_tenant_sent`
(migration `0004`); `GET /credits/balance` now returns both meters.
Two deliberate choices to preserve: `POST /visitors/track` and `/visitors/pixel.js` are PUBLIC and
must never 402 (unentitled plans get 200 + `tracked:false`, event dropped) — a 402 there shows up
as a console error on the CUSTOMER's website. And the send-quota check FAILS OPEN: a counting bug
must not stop a paying customer's campaign; the per-mailbox daily limit still bounds it.
PHASE 4 DONE 2026-09-22 (1,585 tests green; frontend tsc + build clean): `GET /billing/usage`
(one call = plan + both meters + resource counts + `features` + near_limit flags),
`components/usage-meters.tsx` on the dashboard, `components/plan-usage-panel.tsx` on billing
(upgrade w/ annual toggle, credit top-up blocks, and the deferred 1.6 custom-plan configurator),
`hooks/use-plan-features.ts`, feature-aware sidebar nav, and a full rewrite of the public
pricing page + documentation/terms plan tables (they still advertised a $49 Starter tier,
"self-hosted" and a 14-day trial that no longer exist).
`tests/unit/test_pricing_page_parity.py` parses PricingCards.tsx and FAILS if any advertised
number or price drifts from PLAN_MATRIX — that page is the one place a mismatch costs money
in both directions.
Two frontend rules to preserve: `usePlanFeatures().has()` FAILS OPEN while loading (a flash of
a nav item beats hiding a paid feature), so anything that STARTS work on a feature — pollers,
sockets — must wait on `.ready` or it fires one gated 402 on mount. And the gate is cosmetic:
`api/deps/features.py` is the enforcement.
BUG FIXED during Phase 4: migration 0002 backfilled `max_lobs=1`, and since a positive value is
an explicit override that capped every existing MAX tenant at 1 LOB instead of 25. New limit
columns must default to 0 ("use the plan"). Regression test added.
PHASE 5 DONE (verified 2026-09-23: full suite 1,642 passed): `security/test_credit_concurrency.py`
(parallel spends cannot overdraw), `security/test_credit_tenant_isolation.py`,
`security/test_feature_gate_coverage.py`, `integration/test_feature_gate_routes.py` (402/200 matrix),
`integration/test_plan_rename_migration.py`. The 1.6 custom-plan configurator shipped in Phase 4
(`plan-usage-panel.tsx`).
COMMITTED 2026-09-23 on branch `feature/credit-system-pricing` (local only, not pushed, no PR yet).
NEXT: push + PR to master, then resume the Supabase migration (still blocked on credentials).
Full plan: `Plan_Credit_System_And_Pricing.md`. Shareable version:
https://claude.ai/code/artifact/6a4d0abf-596b-481c-a5b1-e4dab9634ce4
Free $0 / 300 cr · Pro $99 / 6,000 cr · Max $299 / 25,000 cr · Custom (quoted). Credits meter
data+AI only; email sends are a separate flat quota. 1 credit ≈ $0.01 retail, 6 credits = one
contact end-to-end. 4 open decisions in §10 of the plan.
NO tier is unlimited on ANY axis (user decision 2026-09-22). Max = 1,000 mailboxes / 50 seats /
25 LOBs; above any of those is the Custom tier, floored at Max's numbers. Custom limits read from
the existing per-tenant `Tenant` limit columns, not the plan matrix.
Because every limit is now a positive integer, the sentinel fix SIMPLIFIES: `0` means only
"not included", the `0 == unlimited` branch in plan_limits.py is deleted, and the
`plan == ENTERPRISE: return` early-exit goes too. No -1 sentinel, no nullable migration.
NEW PLUMBING: LOBs are not a metered resource today — no `Tenant.max_lobs` column and no `lobs`
key in RESOURCE_COUNTERS/RESOURCE_LIMITS. Count rows in `lines_of_business` (an instance table —
many LOBs may share one lob_type), distinct from TenantLOBAssignment which gates the 6 types.
BLOCKER found: `tenant_service.create_tenant_for_signup()` assigns max_mailboxes/contacts/
campaigns/leads = 0, and `plan_limits.py` reads 0-on-starter as a hard 403 — so self-signup
tenants cannot create anything today. Must be fixed before any Free tier ships.
Also: `credit_metering.record_usage()` is wired at exactly ONE call site (`sms.py:64`) —
the ledger exists but nothing writes to it.


## LOCAL OFFLINE RUN (set up 2026-09-22) — works with no network, no DB server
Start backend:  `cd backend && venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
Start frontend: `cd frontend && npm run dev`   ->  http://localhost:3000
Login: `admin@example.com` / `LocalDev#2026` (super_admin, local only)

- `.env` (root, gitignored) — `APP_ENV=DEV`, `DEV_DB_TYPE=sqlite`, all providers on `mock`,
  no SMTP / Stripe / Sentry keys. DB = `backend/data/ra_agent.db` (backup: `.bak-20260922`).
- Tenant #1 (Exzelon) had to be seeded by hand: the legacy `main.py` DDL block inserts it with
  `NOW()`, which SQLite has no function for, so the insert silently warned and skipped. Postgres
  DOES have `NOW()`, so this does not block the Supabase migration — but the same block's
  `SHOW COLUMNS` / `INFORMATION_SCHEMA` / backtick-quoted `` `key` `` statements are MySQL-only
  and will warn on Postgres too. Relevant to ELR-026b (retire that block into Alembic).
- `frontend/next.config.js` — CSP `connect-src 'self' https:` blocked the http://localhost:8000
  API from the :3000 page (prod is same-origin behind nginx, so it never showed there). Added a
  dev-only widening gated on `NODE_ENV !== 'production'`; shipped policy unchanged. UNCOMMITTED.
- KNOWN BUG (pre-existing, blocks offline lead sourcing): `lead_sourcing.py:505,516` calls
  `adapter.fetch_jobs(..., limit=, tuning=)`, but `MockJobSourceAdapter.fetch_jobs` (and the
  `base.py` abstract signature, and several other adapters) accept neither -> `TypeError` on
  every scheduled run. Only real adapters like TheirStack have the newer signature.


## PHASE 2 progress (branch feature/elr-phase2-enterprise, stacked on phase1)
- [x] ELR-029 — tax Decimal HALF_UP (compute_tax_cents) + BILLING_DEFAULT_CURRENCY config
- [x] ELR-022 — webhook handles charge.refunded (→REFUNDED + negative PaymentRecord), payment_failed (→OVERDUE), dispute (→note). New InvoiceStatus.REFUNDED + enum migration
- [x] ELR-023 — tenants.billing_suspended flag + migration; require_tenant_id 402s suspended tenants; scheduler suspends after BILLING_SUSPEND_AFTER_DAYS_OVERDUE (14) grace + un-suspends when settled; immediate clear on payment
- [x] ELR-028 — CI security-scan job (pip-audit + bandit + npm audit, report-only)
- [x] ELR-024 — GDPR /gdpr/export (Right-to-Access) + /gdpr/erase (Right-to-Erasure: anonymise PII, keep rows, suppress, audit); tenant-scoped, admin-gated; api-endpoints.md updated
- [ ] ELR-030 — immutable issued invoices (credit-note flow) — deferred, needs design
- [x] ELR-027 — access-token jti + logout revocation (token_blacklist Redis/memory); get_current_user rejects revoked. (permission cache = perf follow-up)
- [x] ELR-030 — issued invoices immutable (override draft-only)
- [x] ELR-021 — full Stripe Subscriptions: SubscriptionRecord model, StripeGateway sub methods, /billing/subscription/{checkout,cancel} + GET, webhook customer.subscription.* sync + tenant plan sync, deploy/STRIPE_SUBSCRIPTIONS_SETUP.md (inert until STRIPE_PRICE_* set)
- [x] ELR-026 — Alembic backbone: fixed env.py (imports ALL models via app.db.models; honors DATABASE_URL env), migrations/versions/0001_baseline.py (create_all-based, matches models), deploy/MIGRATIONS.md, CLAUDE.md updated. Fresh DB=upgrade head, existing prod=stamp 0001_baseline. Legacy main.py block kept as safety net (ELR-026b = retire it later)
- [ ] ELR-020 — SSO — DEFERRED per user ("remind me later")
- [ ] ELR-026b — retire legacy main.py migration block into discrete Alembic revisions (careful follow-up)
- [ ] ELR-025 — CD pipeline (needs VPS/secrets access)

## SESSION_CONTEXT_RETRIEVAL
> Phase 2 STARTED on branch feature/elr-phase2-enterprise (stacked on phase1). Billing-lifecycle
> batch done: ELR-029/022/023/028. NEXT: ELR-024 (GDPR export/erasure). DECISIONS NEEDED before
> ELR-021 (Stripe Subscriptions) + ELR-020 (SSO provider). Phase 1 branch still not PR'd.
>
> Executing Phase 1 of the enterprise-launch remediation on branch
> `feature/elr-phase1-launch-blockers`. Epic 1A (tenant isolation, commit f511bc1) and
> Epic 1B (billing safety, commit 72597c8) DONE + full suite green (1446 passed).
> NEXT: Epic 1C email compliance (ELR-012 CAN-SPAM address → ELR-014 auto-unsubscribe →
> ELR-013 DKIM [blocked on DNS]) then Epic 1D (ELR-017 Sentry, ELR-018 backups/DR).
> Ledger + statuses in Master_Plan_Enterprise_Launch.md. NOTE: `pip install stripe` was
> needed locally (declared dep, CI has it).

## Phase 1 progress (branch feature/elr-phase1-launch-blockers)
- [x] ELR-007 — tests/security/test_tenant_isolation.py (5 two-tenant tests) — commit f511bc1
- [x] ELR-001..004,006 — cross-tenant read leaks fixed + regression tests — f511bc1
- [x] ELR-005a — ensure_tenant() write-guard on 17 CRUD files (28 sites) — f511bc1
- [x] conftest dual get_db override fix; 2 tests updated for impersonation — f511bc1
- [x] Docs: readiness report + master plan — commit a95790a
- [x] ELR-011 — conftest starter/professional fixtures + plan-limit tests — commit 72597c8
- [x] ELR-008 — Stripe webhook idempotency (ProcessedStripeEvent) + amount/tenant verify — 72597c8
- [x] ELR-009 — credit-budget 402 gate (default OFF) + config ceilings; wired SMS + balance — 72597c8
- [x] ELR-010 — InvoiceSequence counter (gapless, row-locked, seeds legacy) — 72597c8
- [ ] ELR-005b — email_preview/integrations/leads (webhook/pipeline `tenant_id or 1`, per-site review)
- [ ] ELR-009b — wire check_credit_budget into AI/enrichment/validation choke-points + atomic balance row
- [x] ELR-012 — CAN-SPAM address injected into footer (per-tenant + global fallback) at all send sites
- [x] ELR-014 — auto-action unsubscribe: extracted apply_unsubscribe() (suppress+status+CANCEL pending enrollments+audit); fixed autoflush=False double-insert
- [x] ELR-015 — soft-bounce tracker (SoftBounceTracker) escalates after MAX_TEMP_FAILURES + mailbox bounce-rate auto-pause (>5%)
- [x] ELR-016 — suppression uniqueness → (tenant_id,email) composite + best-effort MySQL migration
- [x] ELR-017 — Sentry init in main.py, inert unless SENTRY_DSN set (PII off)
- [x] ELR-018 — backup SHA256 + offsite S3 (Fernet-encrypted) upload behind env vars + deploy/DR_RUNBOOK.md; adds sentry-sdk+boto3
- [x] ELR-005b — email_preview (15) + integrations (4 writes, webhook ref preserved) + leads (create/bulk/import-helper) now use ensure_tenant; also fixed unscoped DealStage lookup in Zapier deal create
- [x] ELR-009b — require_tenant_with_budget dep wired into 5 pipelines + 2 validation + leads enrichment (pre-flight 402 gate, no-op unless enforcement on)
- [ ] ELR-013 — DKIM signing DEFERRED (user publishes 10 GoDaddy DNS records first)
- [ ] ELR-019 — verify/close the (already-green) flaky billing test
- [ ] PHASE 1 nearly complete → open PR after final green (per user: hold PR for now)

## Blockers / Notes
- ELR-013 (DKIM signing) is blocked on publishing the 10 pending GoDaddy DKIM DNS records
  (see memory/dkim-dns-records.md) — never emit a signature for an unpublished domain.
- ELR-009 (credit enforcement) should ship behind a per-tenant `credit_enforcement_enabled`
  flag (default off) to avoid breaking live pipelines.
- Land ELR-011 test net BEFORE the billing refactors (ELR-008/009/010).
- Phase 1 (M11) is the only hard gate to charge customers; M12/M13 can follow post-launch.
