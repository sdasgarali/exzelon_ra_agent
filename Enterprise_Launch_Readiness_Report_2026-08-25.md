# Enterprise Launch Readiness Report — Exzelon RA Agent (NeuraLeads)

**Date:** 2026-08-25 · **Branch:** master · **Context:** Go/No-Go for launch as a **commercial enterprise subscription** SaaS.
**Method:** 5 parallel read-only audits (enterprise-readiness, tenant-isolation, test-coverage, email-deliverability, billing/subscription) + live test suites.

---

## 1. Verdict

**CONDITIONAL NO-GO for a security-reviewed enterprise buyer. GO-with-fixes for SMB/mid-market.**

The product is a capable, feature-rich MVP+ (6.2/10 enterprise readiness, up from 4.5 in March). The March security/auth debt is largely retired. But launching as a **paid subscription** exposes three classes of blocker that were previously acceptable in an internal tool:

1. **Money path is not subscription-grade** — it's an invoice generator, not a subscription platform. Credit limits are decorative, the Stripe webhook isn't idempotent, invoice numbering is race-prone.
2. **Confirmed cross-tenant data leaks** — 4 confirmed paths where one paying tenant can see another's data (analytics, deals sub-resources, visitors).
3. **Legal/compliance gaps that create shared liability** — CAN-SPAM postal address is a placeholder, DKIM is never applied on custom-SMTP sends, no GDPR export/erasure, unsubscribe-by-reply not auto-actioned.

None are architecturally deep; all are fixable in a focused 3-week hardening sprint before charging customers.

---

## 2. Test Suite Status (live run, this session)

| Suite | Result |
|---|---|
| Frontend production build (`npm run build`) | ✅ PASS (exit 0) |
| Backend pytest (full) | ✅ **1420 passed, 1 error** in 6m30s · coverage **41.6%** (gate 35%) |
| Frontend Jest | 8 suites present |
| Playwright E2E | 15 specs (prod smoke) |

**Zero skipped/xfail tests** — clean discipline. But coverage has structural blind spots (§5).

---

## 3. LAUNCH BLOCKERS (must fix before charging customers)

### A. Cross-tenant data leaks (isolation) — 4 confirmed
| ID | Endpoint | Leak | Fix |
|---|---|---|---|
| CRIT-1 | `GET /analytics/team-leaderboard` | Per-user stats are actually tenant-wide totals; under super-admin-no-impersonation, cross-tenant | Add `created_by/owner_id == user.user_id` to inner queries |
| CRIT-2 | `GET /analytics/revenue` | `won/lost_stage_ids` fetched across ALL tenants → wrong/leaked revenue | Add `DealStage.tenant_id == tenant_id` |
| CRIT-3 | `GET /deals/{id}` (+ `/messages`, campaign contacts, outreach thread) | Sub-resource reads (Contact/Lead/Client/OutreachEvent/InboxMessage) fetched by bare PK, no tenant guard | Add `tenant_id == tenant_id` to every sub-resource query |
| CRIT-4 | `GET /visitors`, `/visitors/stats` | `VisitorEvent` has no `tenant_id` column → every tenant sees all visitors | Add `tenant_id` col + migration, or restrict to super-admin |

Plus **HIGH-4**: `tenant_id or 1` fallback in 35+ write endpoints silently writes super-admin data to tenant 1 — wire `require_tenant_id` onto CRUD writes, not just pipelines.

### B. Billing / subscription correctness
| ID | Issue | Fix |
|---|---|---|
| BILL-CRIT-1 | Stripe webhook **not idempotent** — replay → double PaymentRecord | `processed_stripe_events` dedup table (unique `event.id`) + `SELECT FOR UPDATE` on invoice |
| BILL-CRIT-2 | **Credit limits are decorative** — `record_usage` called in 1 place; ceilings hard-coded and never enforced → unbounded paid spend | Atomic pre-flight `check_credit_budget` at every paid choke-point (AI/enrichment/validation/SMS) |
| BILL-CRIT-3 | **Invoice numbering race-prone + string-sorted** — collisions abort batch, gaps violate gapless-numbering law | Dedicated per-year sequence/`SELECT FOR UPDATE`; numeric seq column |
| BILL-HIGH-4 | **No subscription lifecycle** — no renew/cancel/trial/upgrade/downgrade/proration (one-off invoices only) | Adopt Stripe Subscriptions or implement proration + plan-change endpoint |
| BILL-HIGH-5 | **No failed-payment/refund/chargeback handling** — refunded invoice stays PAID | Handle `payment_intent.payment_failed`, `charge.refunded`, `charge.dispute.created` |
| BILL-HIGH-6 | **No access suspension on non-payment** — overdue tenants keep full access forever | `billing_suspended` flag checked in auth deps after N reminders |
| BILL-HIGH-7 | Webhook trusts Stripe amount, doesn't verify `amount_total == invoice.total_cents` or tenant match | Assert both before marking paid |

### C. Email compliance / deliverability (legal + reputation)
| ID | Issue | Fix |
|---|---|---|
| MAIL-1 | **CAN-SPAM: physical postal address is a placeholder** (`"123 Business St…"`) — statutory ~$53k/email exposure | Make per-tenant address required; block send if unset; inject into footer |
| MAIL-3 | **DKIM never applied on custom-SMTP sends** — `sign_email_dkim()` is dead code in the live path | Wire signing into `send_outreach_email()`; publish the 10 pending GoDaddy DKIM DNS records FIRST |
| MAIL-W2 | **Unsubscribe-by-reply detected but not auto-actioned** — keeps emailing until human review | On `_is_unsubscribe()`: write SuppressionList + set UNSUBSCRIBED + cancel pending, synchronously |
| GDPR | **No data-subject export/erasure API** — cold-emailing EU contacts w/o right-to-erasure = up to 4% revenue fine | `/gdpr/export` + `/gdpr/delete` (anonymize + suppress + audit) |

### D. Operations / DR
| ID | Issue | Fix |
|---|---|---|
| OPS-1 | **No error tracking/APM (Sentry)** — production failures invisible | `sentry-sdk[fastapi]`, env-gated DSN (~6h) |
| OPS-2 | **Backups local-only on the same VPS, unencrypted, no checksum** — single VPS failure = total customer-data loss | S3 offsite + Fernet encrypt + SHA256 + failure alert (~14h) |

---

## 4. HIGH-priority (fix soon after launch)

- **No SSO/SAML/OIDC** — enterprise procurement mandate. Only email/password today. (~40h)
- **No CD / rollback / staging** — manual SSH deploy, `systemctl restart` = downtime. (~24h)
- **2,690-line ad-hoc migration block in `main.py`** (Alembic installed but unused) — silent `pass` on failures can half-apply schema. (~20h)
- **No security scanning in CI** — add pip-audit/bandit/npm-audit; FastAPI 0.109 is old. (~4h)
- **No `/ready` probe or `/metrics`** — no dependency-aware readiness, no latency/error visibility. (~10h)
- **Token revocation is a no-op on logout**; Redis + Celery are dependencies but unused (pipelines run in-request). (~16h)
- **Soft-bounce retry counter (`MAX_TEMP_FAILURES`) defined but never enforced** — reputation burn. Add auto-pause on bounce-rate too.
- **Suppression list unique index is on `email` alone** — should be `(tenant_id, email)`; global suppression → separate table.

---

## 5. Test coverage gaps (blocking confidence, not runtime)

**ZERO tests** on: Stripe webhook, `credits.py`/`credit_metering.py`, `plan_limits.py` enforcement, outbound webhooks + dispatcher, billing mailer/PDF, `admin_tenants` RBAC, and ~10 endpoint routers (automation, crm_sync, dfy, visitor_tracking, sms, copilot, goals, reports, calendar, spam_check).

**Structural flaw:** `conftest.py` `test_tenant` is always `ENTERPRISE`, which short-circuits `check_plan_limit()` — so **plan-limit enforcement has never been exercised by any test**. Add `starter_tenant` + `professional_capped_tenant` fixtures.

**No `tests/security/test_tenant_isolation.py`** — the 4 confirmed leaks have zero regression coverage. Every fix in §3A must ship with a cross-tenant regression test.

Recommended additions before launch: ~55 backend + ~10 frontend + 1 Playwright billing spec.

---

## 6. Category Scores (enterprise rubric)

| Category | Score | Category | Score |
|---|---|---|---|
| Security | 7/10 | CI/CD | 4/10 |
| Multi-tenancy isolation | 8/10 (4 leaks to close) | Scalability | 4/10 |
| Observability | **3/10** (weakest) | Operations/Reliability | 5/10 |
| Testing | 7/10 | Data Privacy/Compliance | 4/10 |
| Billing robustness | 6/10 | **Overall** | **6.2/10** |

---

## 7. Prioritized Roadmap

### Phase 1 — Launch blockers (~3 weeks, ~90h) — DO BEFORE CHARGING
- [ ] Fix 4 cross-tenant leaks (CRIT-1..4) + wire `require_tenant_id` on CRUD writes + isolation regression tests
- [ ] Stripe webhook idempotency + amount/tenant verification
- [ ] Enforce credit limits atomically at paid choke-points
- [ ] Fix invoice-number sequence integrity
- [ ] CAN-SPAM postal address required + inject into footer
- [ ] Wire DKIM signing (after publishing pending DNS records) + block send on unverified DKIM
- [ ] Auto-action unsubscribe-by-reply
- [ ] Sentry + offsite/encrypted backups + DR runbook
- [ ] Backend test suite green (see appendix)

### Phase 2 — Enterprise sales enablers (~5 weeks, ~92h)
- [ ] SSO/SAML or OIDC with per-tenant IdP config
- [ ] Subscription lifecycle (renew/cancel/trial/proration) + failed-payment/refund handling + suspension-on-nonpayment
- [ ] GDPR export + erasure API
- [ ] CD pipeline + rollback + staging + post-deploy smoke
- [ ] Migrate `main.py` migrations to Alembic; token revocation + permission cache
- [ ] Security scanning in CI; coverage gate

### Phase 3 — Scale & hardening (~6 weeks, ~70h)
- [ ] Celery for async pipelines + Celery Beat scheduler; Redis rate-limit + caching
- [ ] `/ready` + `/metrics` + external uptime monitor
- [ ] DB-enforced isolation (RLS) or query-interceptor; close residual sub-resource gaps
- [ ] Load tests on send/outreach hot path

---

## 8. What's already strong (don't re-litigate)

Argon2 + JWT refresh + account lockout + login history + security headers/CSP/HSTS + per-endpoint rate limits + startup secret validation; `require_tenant_id` fail-closed design; 10-check send gate wired to all send paths; correct throttle caps + UTC reset; complaint auto-pause at 0.3%; unsubscribe+suppression loop; retention purge job; 1,300+ backend tests with regression-per-fix ledger; signature-verified Stripe webhook; tenant-scoped invoice access.

---

## Appendix: test-suite note
`test_billing_api.py::TestSuperAdminListInvoices::test_filter_by_status` **errors only in the full-suite run** (passes in isolation, 1 passed in 0.85s). This is a test-isolation / shared-state leak between suites — not a product bug, but it undermines CI signal on the billing path and should be fixed (proper per-test DB teardown / fixture scoping). Overall backend coverage 41.6% is above the 35% gate but low for enterprise; billing/credits/webhooks/plan-limits sit near 0% (see §5).

## Appendix: audit provenance
Five specialist sub-agents (enterprise-readiness-scorer, multi-tenant-isolation-auditor, test-coverage-gatekeeper, email-deliverability-guardian, general-purpose/billing) ran read-only against `master`. Full per-agent findings with file:line evidence are in the session transcript. No files were modified during this audit.
