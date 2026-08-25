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

## Immediate TODO
- [ ] Get user sign-off on `Master_Plan_Enterprise_Launch.md` ticket scope/priorities
- [ ] ELR-011 — billing/plan-limit test scaffold + conftest starter/professional fixtures
- [ ] ELR-007 — tests/security/test_tenant_isolation.py (two-tenant fixture)
- [ ] ELR-001..006 — fix 4 confirmed cross-tenant leaks + require_tenant_id on writes
- [ ] ELR-008..010 — Stripe webhook idempotency, credit enforcement, invoice seq integrity

## Blockers / Notes
- ELR-013 (DKIM signing) is blocked on publishing the 10 pending GoDaddy DKIM DNS records
  (see memory/dkim-dns-records.md) — never emit a signature for an unpublished domain.
- ELR-009 (credit enforcement) should ship behind a per-tenant `credit_enforcement_enabled`
  flag (default off) to avoid breaking live pipelines.
- Land ELR-011 test net BEFORE the billing refactors (ELR-008/009/010).
- Phase 1 (M11) is the only hard gate to charge customers; M12/M13 can follow post-launch.
