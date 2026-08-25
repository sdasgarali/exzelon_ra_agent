# Plan WIP

## SESSION_CONTEXT_RETRIEVAL
> ENTERPRISE SUBSCRIPTION LAUNCH readiness (2026-08-25). Ran 5 parallel read-only audits
> (enterprise-readiness, tenant-isolation, test-coverage, email-deliverability, billing)
> + live test suites. Verdict: **Conditional NO-GO** for a security-reviewed enterprise
> buyer; readiness 6.2/10. Live tests: frontend build ✅; backend 1420 pass / 1 flaky
> error (billing test isolation), coverage 41.6%.
>
> DELIVERABLES WRITTEN (this session, no code changed):
> - `Enterprise_Launch_Readiness_Report_2026-08-25.md` — full findings w/ file:line.
> - `Master_Plan_Enterprise_Launch.md` — numbered ticket ledger ELR-001…036 across 3
>   phases, mapped to REQ-039…046 + traceability + execution order.
> - `Master_Plan.md` — added REQ-039…046 block + milestones M11–M13 pointing to the above.
>
> NEXT STEP: awaiting user sign-off on scope, then start Phase 1 (M11). Recommended order:
> ELR-011 (billing/plan-limit test scaffold + starter/professional fixtures) → ELR-007
> (isolation regression suite) → fix leaks ELR-001..006 → billing safety ELR-008..010 →
> email compliance ELR-012/014/013 → Sentry+DR ELR-017/018 → ELR-019 cleanup.

## Phase 1 progress (branch feature/elr-phase1-launch-blockers)
- [x] ELR-007 — tests/security/test_tenant_isolation.py (5 two-tenant tests) — commit f511bc1
- [x] ELR-001..004,006 — cross-tenant read leaks fixed + regression tests — f511bc1
- [x] ELR-005a — ensure_tenant() write-guard on 17 CRUD files (28 sites) — f511bc1
- [x] conftest dual get_db override fix; 2 tests updated for impersonation — f511bc1
- [x] Docs: readiness report + master plan — commit a95790a
- [ ] ELR-005b — email_preview/integrations/leads (webhook/pipeline `tenant_id or 1`, per-site review)
- [ ] ELR-011 — billing/plan-limit test scaffold + conftest starter/professional fixtures (do BEFORE 008-010)
- [ ] ELR-008 — Stripe webhook idempotency (processed_stripe_events table) + amount/tenant verify
- [ ] ELR-009 — atomic credit-budget enforcement at paid choke-points (behind per-tenant flag)
- [ ] ELR-010 — invoice-number sequence integrity (per-year seq + SELECT FOR UPDATE)
- [ ] ELR-012..016 (email compliance), ELR-017/018 (Sentry + backups/DR), ELR-019 cleanup

## Blockers / Notes
- ELR-013 (DKIM signing) is blocked on publishing the 10 pending GoDaddy DKIM DNS records
  (see memory/dkim-dns-records.md) — never emit a signature for an unpublished domain.
- ELR-009 (credit enforcement) should ship behind a per-tenant `credit_enforcement_enabled`
  flag (default off) to avoid breaking live pipelines.
- Land ELR-011 test net BEFORE the billing refactors (ELR-008/009/010).
- Phase 1 (M11) is the only hard gate to charge customers; M12/M13 can follow post-launch.
