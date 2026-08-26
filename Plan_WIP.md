# Plan WIP

## SESSION_CONTEXT_RETRIEVAL
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
