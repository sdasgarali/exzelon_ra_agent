# Master Plan — Enterprise Subscription Launch Remediation

> Companion to `Master_Plan.md` (product vision) and `Enterprise_Launch_Readiness_Report_2026-08-25.md` (findings).
> Scope: everything that must be true before Exzelon RA Agent (NeuraLeads) can be sold as a **commercial enterprise subscription** product.
> Ticket scheme: **ELR-NNN** (Enterprise Launch Readiness). Each ticket → maps to a finding ID from the readiness report and a REQ-XXX.

---

## Vision

Turn the current feature-complete MVP+ (enterprise readiness **6.2/10**) into a product a security-reviewed enterprise buyer can sign: **provably isolated per tenant, subscription-grade billing, legally compliant outbound email, observable & recoverable in production.** Ship in three phases — **Phase 1 clears every launch blocker before we charge a customer.**

---

## Requirements (new — continue from Master_Plan REQ-032)

| ID | Requirement | Phase | Status |
|----|-------------|-------|--------|
| REQ-039 | Guaranteed tenant data isolation — zero cross-tenant read/write on any endpoint or job | 1 | Not started |
| REQ-040 | Subscription-grade billing — idempotent webhooks, enforced plan/credit limits, invoice integrity, lifecycle | 1–2 | Not started |
| REQ-041 | Outbound email legal compliance — CAN-SPAM address, DKIM signing, auto-unsubscribe, GDPR DSAR | 1–2 | Not started |
| REQ-042 | Production observability & disaster recovery — error tracking, offsite encrypted backups, DR runbook | 1 | Not started |
| REQ-043 | Enterprise identity — SSO/SAML or OIDC with per-tenant IdP config | 2 | Not started |
| REQ-044 | Delivery hardening — CD pipeline, rollback, staging, security scanning, Alembic migrations | 2 | Not started |
| REQ-045 | Test coverage for money/auth/isolation paths + coverage gate | 1–2 | Not started |
| REQ-046 | Horizontal scale — async pipelines (Celery), Redis caching, readiness/metrics probes | 3 | Not started |

---

## Ticket Ledger

**Legend** — Priority: `P0`=launch blocker · `P1`=high · `P2`=medium. Every ticket lists a **regression test** (per the regression-per-fix hard rule). Effort in engineer-hours.

> **STATUS 2026-08-25** (branch `feature/elr-phase1-launch-blockers`):
> **Epic 1A DONE** (commit f511bc1) — ELR-001,002,003,004,006 + ELR-007 (new
> `tests/security/test_tenant_isolation.py`, 5 tests) + a pre-existing test-infra gap
> (analytics/visitor imported `get_db` from a module conftest didn't override). ELR-005 DONE
> for 17 CRUD-create files via `ensure_tenant()` (28 sites); **ELR-005b DEFERRED** =
> `email_preview.py`/`integrations.py`/`leads.py` (webhook/pipeline `(ref_)tenant_id or 1`
> resolutions that must NOT hard-400 — per-site review).
>
> **Epic 1B DONE (code+tests)** — **ELR-008** idempotent+verified Stripe webhook
> (new `ProcessedStripeEvent` de-dup table + amount/tenant verification); **ELR-009** config-driven
> credit ceilings + `check_credit_budget()` 402 gate (default OFF, per-tenant opt-in), wired into
> SMS send + `/credits/balance`; **ELR-010** `InvoiceSequence` counter (gapless, row-locked, seeds
> from legacy). **ELR-011** conftest `starter_tenant`/`professional_capped_tenant` fixtures + 4 new
> test files (plan-limits, credit-enforcement, invoice-sequence, billing-webhook). New tables are
> auto-created by lifespan `create_all`. FOLLOW-UP: wire `check_credit_budget` into the remaining
> paid choke-points (AI/enrichment/validation) — ELR-009b; atomic balance-row hardening later.
> Next: Epic 1C (email compliance ELR-012/014/013) + Epic 1D (Sentry/backups ELR-017/018).

### PHASE 1 — Launch Blockers (target ~3 weeks, ~90h) — DO BEFORE CHARGING

#### Epic 1A — Tenant Isolation (REQ-039)

**ELR-001 · Fix analytics leaderboard per-user scoping** · P0 · 3h
- Finding: CRIT-1 · Files: `backend/app/api/endpoints/analytics.py:37-63`
- Root cause: inner `OutreachEvent`/`Deal` count queries lack `created_by/owner_id == user.user_id`; every row shows tenant-wide totals, and cross-tenant when super-admin is un-impersonated.
- Acceptance: leaderboard shows true per-user counts; with `tenant_id=None` the endpoint returns 400 (via ELR-005) or scopes correctly.
- Regression: `tests/security/test_tenant_isolation.py::test_leaderboard_is_per_user_and_tenant_scoped`

**ELR-002 · Scope revenue analytics stage IDs to tenant** · P0 · 2h
- Finding: CRIT-2 · Files: `analytics.py:146-167`
- Root cause: `won_stage_ids`/`lost_stage_ids` fetched across ALL tenants → wrong/leaked revenue.
- Acceptance: stage-id queries filter `DealStage.tenant_id == tenant_id`; empty list when tenant_id is None.
- Regression: `test_revenue_stage_ids_tenant_scoped`

**ELR-003 · Tenant-guard all deal/outreach sub-resource reads** · P0 · 5h
- Findings: CRIT-3, HIGH-2, HIGH-5 · Files: `deals.py:164-180,570-572,942-962`, `outreach.py:92-100`
- Root cause: Contact/Lead/Client/DealStage/OutreachEvent/InboxMessage fetched by bare PK after parent tenant check.
- Acceptance: every sub-resource query adds `tenant_id == <parent>.tenant_id`; `_user_ref` scoped to tenant.
- Regression: `test_deal_detail_rejects_cross_tenant_subresources`

**ELR-004 · Add `tenant_id` to VisitorEvent + scope visitor endpoints** · P0 · 6h
- Finding: CRIT-4 · Files: `visitor_tracking.py:43-94`, `db/models/` (VisitorEvent), `main.py` lifespan migration
- Root cause: `VisitorEvent` has no `tenant_id` → every tenant sees all visitors.
- Acceptance: column added (idempotent `ALTER` in lifespan) + backfill from tracking token; read endpoints apply `tenant_filter`; tracking-pixel POST stays unauthenticated but stamps tenant.
- Regression: `test_visitors_isolated_by_tenant`; DB-migration reviewed by `db-migration-safety-reviewer`.

**ELR-005 · Wire `require_tenant_id` onto all CRUD write endpoints** · P0 · 6h
- Finding: HIGH-4 · Files: 35+ `tenant_id or 1` sites (deals, campaigns, goals, templates, inbox, contacts, mailboxes…)
- Root cause: `tenant_id or 1` silently writes super-admin data into tenant 1.
- Acceptance: every tenant-scoped write depends on `require_tenant_id` (400 when un-impersonated); no `or 1` fallback on write paths.
- Regression: `test_super_admin_write_without_tenant_returns_400` (parametrized across write routes)

**ELR-006 · Tenant-guard campaign contact/lead enrichment batch** · P1 · 2h
- Finding: HIGH-3 · Files: `campaigns.py:1536-1545`
- Acceptance: `ContactDetails`/`LeadDetails` `.in_()` fetches add `tenant_id == campaign.tenant_id`.
- Regression: `test_campaign_contacts_tenant_scoped`

**ELR-007 · Create tenant-isolation regression suite** · P0 · 6h
- Finding: HIGH-7 (no `tests/security/test_tenant_isolation.py`) · Files: new `backend/tests/security/`
- Acceptance: two-tenant fixture; every fixed leak (ELR-001..006) has a cross-tenant assertion; runs in CI under `-m security`.
- Regression: this ticket IS the regression suite.

#### Epic 1B — Subscription-Grade Billing (REQ-040, REQ-045)

**ELR-008 · Idempotent + verified Stripe webhook** · P0 · 5h
- Findings: BILL-CRIT-1, BILL-HIGH-7 · Files: `billing.py:634-718`
- Root cause: no `event.id` dedup, no row lock, no `amount_total == invoice.total_cents` / tenant-match assertion → replay = double PaymentRecord.
- Acceptance: new `processed_stripe_events` table (unique `event_id`, insert-first); `SELECT ... FOR UPDATE` on invoice; assert amount + tenant; single transaction.
- Regression: `test_stripe_webhook_replay_is_idempotent`, `test_webhook_amount_mismatch_refused`, `test_webhook_invalid_signature_400`

**ELR-009 · Enforce credit budgets atomically** · P0 · 8h
- Finding: BILL-CRIT-2 · Files: `credits.py:129-156`, `credit_metering.py:36-45`, paid choke-points (ai_content, enrichment, validation, sms)
- Root cause: `record_usage` called in 1 place; ceilings hard-coded and never enforced → unbounded paid spend.
- Acceptance: per-tenant monthly balance row; `check_credit_budget` pre-flight with `SELECT FOR UPDATE`; ceilings moved to plan/tenant config; over-budget → 402.
- Regression: `test_credit_gate_blocks_over_budget`, `test_credit_metering_no_double_spend_under_concurrency`

**ELR-010 · Invoice-number sequence integrity** · P0 · 5h
- Finding: BILL-CRIT-3 · Files: `invoice_generator.py:11-23,191-192`
- Root cause: `MAX(string LIKE)` + no lock → collisions abort batch / illegal gaps.
- Acceptance: per-year sequence table (or DB sequence) with `SELECT FOR UPDATE`/atomic increment; numeric `seq` column, formatted on read; concurrent generation safe.
- Regression: `test_invoice_numbers_gapless_and_unique_under_concurrency`

**ELR-011 · Billing/credits/plan-limit test coverage + conftest fixtures** · P0 · 10h
- Finding: test-coverage §5 (ZERO tests on webhook/credits/plan_limits) · Files: new tests + `conftest.py`
- Root cause: `test_tenant` is always ENTERPRISE → `check_plan_limit` never exercised.
- Acceptance: add `starter_tenant` + `professional_capped_tenant` fixtures; unit+integration tests for plan-limit enforcement, credits API/metering, billing mailer/PDF, webhook, admin_tenants RBAC (~55 tests).
- Regression: this ticket IS coverage; wire into CI markers.

**ELR-019 · Fix flaky billing test isolation** · P1 · 2h
- Finding: appendix (`test_filter_by_status` errors only in full-suite run) · Files: `tests/integration/test_billing_api.py`, `conftest.py`
- Root cause: shared-state/DB leak between suites.
- Acceptance: test passes in full-suite run 5× consecutively; per-test teardown/fixture scoping fixed.
- Regression: covered by repeated full-suite green.

#### Epic 1C — Email Legal Compliance (REQ-041)

**ELR-012 · CAN-SPAM postal address required + injected** · P0 · 4h
- Findings: MAIL-1, MAIL-2 · Files: `services/pipelines/outreach.py:316-330,805,1053`, `campaign_engine.py:759`, `settings.py:205`, `main.py:2559` (unsub page)
- Root cause: footer generated without physical address; default is placeholder `"123 Business St…"`.
- Acceptance: `generate_unsub_footer()` takes resolved tenant `company_address`; **send blocked** if address unset (structured error); address on unsub confirmation page.
- Regression: `test_unsub_footer_requires_company_address`, `test_send_blocked_without_postal_address`

**ELR-013 · Wire DKIM signing into live send path** · P0 · 5h (blocked by DNS)
- Findings: MAIL-3, W3 · Files: `services/pipelines/outreach.py:194-211`, `dkim_signer.py`, `warmup/scheduler.py` (dns check)
- Root cause: `sign_email_dkim()` is dead code in the send path; custom-SMTP mail goes unsigned. 10 GoDaddy domains have keys but no DNS TXT.
- Acceptance: **publish the 10 pending DKIM DNS records first** (see `memory/dkim-dns-records.md`); sign in `send_outreach_email()` when `should_sign_dkim()`; **block send** from any mailbox whose latest DNS check shows `dkim_status != pass`.
- Regression: `test_send_signs_dkim_for_custom_smtp`, `test_send_blocked_on_unverified_dkim`
- Dependency: DNS record publication (ops/user action).

**ELR-014 · Auto-action unsubscribe-by-reply** · P0 · 3h
- Finding: MAIL-W2 · Files: `services/reply_tracker.py:86`
- Root cause: `_is_unsubscribe()` detects intent but never suppresses.
- Acceptance: on detect → synchronously write `SuppressionList` + set `contact.outreach_status=UNSUBSCRIBED` + cancel pending `CampaignContact` + `AuditLog`.
- Regression: `test_reply_unsubscribe_suppresses_immediately`

**ELR-015 · Soft-bounce enforcement + bounce-rate auto-pause** · P1 · 4h
- Finding: MAIL-4, bounce section · Files: `bounce_handler.py:25,142`, `esp_feedback.py`
- Root cause: `MAX_TEMP_FAILURES` defined but never enforced; no mailbox auto-pause on bounce rate.
- Acceptance: track `soft_bounce_count`; suppress at threshold; `SOFT_BOUNCED` status; `bounce_rate_auto_pause_threshold` (default 5%) pauses mailbox.
- Regression: `test_soft_bounce_suppresses_after_max`, `test_mailbox_autopause_on_bounce_rate`

**ELR-016 · Suppression unique index → (tenant_id, email) + global table** · P1 · 3h
- Finding: MAIL-W4 · Files: `db/models/` suppression_list, migration in `main.py`
- Root cause: `UNIQUE(email)` alone → one tenant's opt-out crashes/blocks another's writes.
- Acceptance: composite unique `(tenant_id, email)`; new `global_suppression_list` for legal do-not-contact; gate checks both.
- Regression: `test_same_email_suppressible_by_two_tenants`; migration reviewed by `db-migration-safety-reviewer`.

#### Epic 1D — Observability & DR (REQ-042)

**ELR-017 · Integrate Sentry error tracking** · P0 · 6h
- Finding: OPS-1 · Files: `main.py` (global handler), `core/config.py`, `.env.example`
- Acceptance: `sentry-sdk[fastapi]`, env-gated DSN, tied to global exception handler; PII scrubbed; frontend DSN optional.
- Regression: `test_sentry_disabled_when_dsn_unset` (no crash path).

**ELR-018 · Offsite encrypted backups + DR runbook** · P0 · 14h
- Finding: OPS-2 · Files: `services/backup_service.py:17-21`, `warmup/scheduler.py:35`, new `deploy/DR_RUNBOOK.md`
- Root cause: backups local-only on the same VPS, unencrypted, no checksum, no failure alert.
- Acceptance: S3 (or equivalent) upload + Fernet encryption + SHA256 checksum + restore-validation; alert on `job_daily_backup` failure; documented RTO/RPO.
- Regression: `test_backup_uploaded_encrypted_checksummed` (mocked S3).

---

### PHASE 2 — Enterprise Sales Enablers (target ~5 weeks, ~92h)

**ELR-020 · SSO/SAML or OIDC login + per-tenant IdP config** · P1 · 40h · REQ-043
- Acceptance: SAML2 or OIDC (Authlib/python3-saml); per-tenant IdP metadata UI; JIT user provisioning; email/password remains for non-SSO tenants.
- Regression: `test_oidc_login_provisions_user_in_correct_tenant`

**ELR-021 · Real subscription lifecycle** · P1 · 24h · REQ-040
- Finding: BILL-HIGH-4 · Acceptance: Stripe `Product`/`Price`/`Subscription`; renew/cancel/trial; proration + plan-change endpoint that syncs `monthly_price_cents` + limits.
- Regression: `test_plan_upgrade_prorates`, `test_cancel_stops_renewal`

**ELR-022 · Failed-payment / refund / chargeback handling** · P1 · 6h · REQ-040
- Finding: BILL-HIGH-5 · Files: `billing.py` webhook
- Acceptance: handle `payment_intent.payment_failed`, `charge.refunded`, `charge.dispute.created` → update invoice/payment status + trigger dunning.
- Regression: `test_refund_marks_invoice_refunded`

**ELR-023 · Suspend-on-nonpayment** · P1 · 6h · REQ-040
- Finding: BILL-HIGH-6 · Files: `warmup/scheduler.py:846-896`, `api/deps/auth.py`
- Acceptance: `billing_suspended` flag after N reminders / M days overdue; checked in auth deps → read-only/blocked with clear UX.
- Regression: `test_overdue_tenant_suspended_after_threshold`

**ELR-024 · GDPR data-subject export + erasure API** · P1 · 24h · REQ-041
- Acceptance: `/gdpr/export` (all PII for a contact/email) + `/gdpr/delete` (anonymize + suppress + audit); tenant-scoped + audited.
- Regression: `test_gdpr_erase_anonymizes_and_suppresses`

**ELR-025 · CD pipeline + rollback + staging + smoke** · P1 · 24h · REQ-044
- Files: `.github/workflows/`, `deploy/rollback.sh`
- Acceptance: deploy-on-merge to staging→prod with health gate; `rollback.sh <sha>`; post-deploy Playwright smoke.
- Regression: pipeline dry-run green.

**ELR-026 · Migrate `main.py` migrations to Alembic** · P1 · 20h · REQ-044
- Finding: readiness §4 (2,690-line ad-hoc block, silent `pass`) · Acceptance: Alembic baseline captures current schema; new changes via revisions; lifespan block retired.
- Dependency: reviewed by `db-migration-safety-reviewer` before merge.
- Regression: `alembic upgrade head` on clean DB == current schema.

**ELR-027 · Token revocation + permission cache** · P1 · 8h · REQ-043
- Finding: readiness §4 (logout no-op; Redis unused) · Acceptance: Redis JTI blacklist on logout; permission lookups cached with TTL/invalidation.
- Regression: `test_logout_revokes_token`

**ELR-028 · Security scanning + coverage gate in CI** · P1 · 4h · REQ-044/039
- Acceptance: `pip-audit`, `bandit`, `npm audit` gate PRs; coverage threshold raised (backend ≥60% money/auth paths).
- Regression: CI fails on known-vuln fixture.

**ELR-029 · Tax/currency correctness** · P2 · 6h · REQ-040
- Findings: BILL-MED-8/9, LOW-15 · Files: `invoice_generator.py:79-102`, `billing.py:276-278`
- Acceptance: `Decimal` + `ROUND_HALF_UP` for tax; currency from tenant/config; capture VAT ID; custom-plan credit map fallback fixed.
- Regression: `test_tax_rounding_half_up`, `test_invoice_currency_from_config`

**ELR-030 · Immutable issued invoices** · P2 · 4h · REQ-040
- Finding: BILL-MED-10 · Files: `billing.py:299-305`
- Acceptance: overrides on SENT/PAID invoices issue a credit note + new invoice instead of overwriting the PDF.
- Regression: `test_override_issued_invoice_creates_credit_note`

---

### PHASE 3 — Scale & Hardening (target ~6 weeks, ~70h) — REQ-046

**ELR-031 · Celery async pipelines + Celery Beat** · P2 · 32h
- Acceptance: enrichment/validation/outreach run as Celery tasks (Redis broker already a dep); scheduler → Celery Beat; API returns job id immediately.
- Regression: `test_pipeline_enqueues_and_completes_async`

**ELR-032 · Redis rate limiter + caching** · P2 · 6h
- Acceptance: SlowAPI backed by Redis (per-cluster, not per-worker); dashboard KPI + permission caching using existing `DASHBOARD_KPI_CACHE_TTL`.
- Regression: `test_rate_limit_shared_across_workers`

**ELR-033 · Readiness + metrics probes** · P2 · 10h
- Acceptance: `/ready` (DB+scheduler+Redis) + `/metrics` (prometheus-fastapi-instrumentator); external uptime monitor on `/health`.
- Regression: `test_ready_returns_503_when_db_down`

**ELR-034 · DB-enforced tenant isolation** · P2 · 20h
- Acceptance: query interceptor asserting `tenant_id` on every tenant-scoped filter (defense-in-depth), or Postgres RLS if/when DB migrates; close residual RA-QA-016 sub-resource gaps.
- Regression: extend `test_tenant_isolation.py` with interceptor assertions.

**ELR-035 · Load tests on send/outreach hot path** · P2 · 6h
- Files: `backend/tests/load/locustfile.py`
- Acceptance: Locust scenarios for `POST /outreach/send-emails`, `/run-mailmerge`, `/check-replies`, `/credits/summary`; documented p95 targets.

**ELR-036 · Frontend security hardening** · P2 · 6h
- Findings: readiness Security (CSP `unsafe-inline/eval`, CORS localhost fallback, PII in logs)
- Acceptance: nonce-based CSP; CORS fails hard when unset in prod; structlog PII-masking processor.
- Regression: `test_cors_requires_explicit_origins_in_prod`

---

## Architecture Decisions

- **AD-1 (isolation):** App-layer `tenant_filter` remains the primary control for Phase 1; add a defense-in-depth query interceptor (ELR-034) in Phase 3. Do **not** block launch on a DB migration to Postgres RLS.
- **AD-2 (billing):** Phase 1 keeps the one-off-invoice + Stripe-checkout model but makes it *safe* (idempotent, enforced, gapless). Phase 2 introduces true Stripe Subscriptions (ELR-021) — sequenced after the safety fixes so we never build lifecycle on a leaky base.
- **AD-3 (credits):** Enforcement via an atomic per-tenant monthly balance row with `SELECT FOR UPDATE` (works on current MySQL); avoid a distributed-counter design until Celery/Redis lands.
- **AD-4 (migrations):** Freeze new ad-hoc `main.py` ALTERs; all Phase-1 schema changes (VisitorEvent.tenant_id, suppression index, processed_stripe_events, invoice seq) go in as idempotent lifespan blocks **and** are captured in the Alembic baseline (ELR-026) so we don't widen the debt.
- **AD-5 (DKIM):** Never emit a DKIM-Signature header for a domain whose DNS TXT isn't published — a broken signature is worse than none. DNS publication gates ELR-013.

---

## Milestones & Status

| # | Milestone | Tickets | Status | Target |
|---|-----------|---------|--------|--------|
| M11 | Launch blockers cleared | ELR-001…019 | Not started | Phase 1 (~3 wks) |
| M12 | Enterprise enablers | ELR-020…030 | Not started | Phase 2 (~5 wks) |
| M13 | Scale & hardening | ELR-031…036 | Not started | Phase 3 (~6 wks) |

**Go-live gate:** all P0 tickets `Done` + tenant-isolation regression suite green + backend suite green (0 errors) + a clean two-tenant manual pen-test of the four fixed leaks.

---

## Traceability (ticket → finding → REQ)

| Ticket | Finding | REQ | Ticket | Finding | REQ |
|--------|---------|-----|--------|---------|-----|
| ELR-001 | CRIT-1 | 033 | ELR-019 | appendix | 039 |
| ELR-002 | CRIT-2 | 033 | ELR-020 | readiness §4 | 037 |
| ELR-003 | CRIT-3/H-2/H-5 | 033 | ELR-021 | BILL-H-4 | 034 |
| ELR-004 | CRIT-4 | 033 | ELR-022 | BILL-H-5 | 034 |
| ELR-005 | HIGH-4 | 033 | ELR-023 | BILL-H-6 | 034 |
| ELR-006 | HIGH-3 | 033 | ELR-024 | GDPR | 035 |
| ELR-007 | HIGH-7 | 033/039 | ELR-025 | CI/CD §4 | 038 |
| ELR-008 | BILL-C-1/H-7 | 034 | ELR-026 | migrations §4 | 038 |
| ELR-009 | BILL-C-2 | 034 | ELR-027 | tokens §4 | 037 |
| ELR-010 | BILL-C-3 | 034 | ELR-028 | scanning §4 | 038/039 |
| ELR-011 | coverage §5 | 039 | ELR-029 | BILL-M-8/9 | 034 |
| ELR-012 | MAIL-1/2 | 035 | ELR-030 | BILL-M-10 | 034 |
| ELR-013 | MAIL-3/W3 | 035 | ELR-031 | scale §4 | 040 |
| ELR-014 | MAIL-W2 | 035 | ELR-032 | scale §4 | 040 |
| ELR-015 | MAIL-4 | 035 | ELR-033 | observ §4 | 040 |
| ELR-016 | MAIL-W4 | 035 | ELR-034 | isolation §4 | 040 |
| ELR-017 | OPS-1 | 036 | ELR-035 | load §5 | 040 |
| ELR-018 | OPS-2 | 036 | ELR-036 | security §4 | 038 |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| DKIM DNS records not published by ops | Blocks ELR-013; broken signatures if forced | Gate signing on `dkim_status==pass`; treat DNS publish as an external dependency, chase early |
| Schema changes on live prod DB (VisitorEvent, indexes) | Downtime / partial apply | Idempotent lifespan ALTERs + `db-migration-safety-reviewer` sign-off + backup before deploy |
| Credit-enforcement gate breaks existing pipelines | Pipeline failures for paying tenants | Ship behind a per-tenant `credit_enforcement_enabled` flag, default off, enable after validation |
| Billing refactor introduces revenue bugs | Direct financial loss | ELR-011 coverage lands *before* ELR-008/009/010 changes; changes behind tests |
| Scope creep across 36 tickets | Launch slips | Phase 1 is the only hard gate to charge; Phase 2/3 can ship post-launch to early customers under a roadmap commitment |

---

## Execution Order (recommended)

1. **ELR-011** (billing/plan-limit test scaffold + fixtures) — build the safety net first.
2. **ELR-007** (isolation regression suite scaffold) — then fix leaks against it: **ELR-001→002→003→004→005→006**.
3. **ELR-008→009→010** (billing safety) behind the ELR-011 net.
4. **ELR-012→014→013** (email compliance; 013 waits on DNS) then **ELR-015→016**.
5. **ELR-017→018** (Sentry + backups/DR) — can run in parallel with the above (different files).
6. **ELR-019** cleanup. → **M11 go-live gate**.

Each ticket: feature branch `bugfix/elr-NNN-slug` → small diff → regression test → PR → squash-merge. Update `Plan_WIP.md` `SESSION_CONTEXT_RETRIEVAL` before each ticket.
