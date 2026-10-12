# Plan — Close credit / billing / isolation loopholes

Branch: `bugfix/credit-loopholes` (from `master` a68fddb). Source: 3-agent read-only audit, 2026-10-12.
Approved by user 2026-10-12 ("yes fix all of them").

## SESSION_CONTEXT_RETRIEVAL
> DONE on branch `bugfix/credit-loopholes` (not pushed, no PR, not deployed). A/B/C merged + integrator
> fixes + credit meter/history UI. Full backend suite 2086 passed / 0 failed (baseline 1927); frontend
> 90/90; browser QA via Playwright on a scratch DB copy passed. NEXT (user decisions): push + PR,
> set prod env keys (deployment.md), decide whether to turn CREDIT_ENFORCEMENT_ENABLED on.

## Decisions
- `CREDIT_ENFORCEMENT_ENABLED` global default stays `False` in code — flipping it on prod blocks live
  tenants and is the user's call. All other gaps are closed so that turning it on actually works.
- Overspend is **carried forward** into the next period (allowance refills minus debt), not wiped.
- Copilot metering is out of scope here: copilot lives on held PR #131 (`feature/copilot-deepseek`).
- New AI actions get prices in `CREDIT_COSTS` (C owns `credit_costs.py`).

## Partition (exclusive file ownership)

### Agent A — pipelines & tenant isolation
Owns: `services/pipelines/contact_enrichment.py`, `services/pipelines/lead_sourcing.py`,
`services/pipelines/email_validation.py`, `services/intent_signal_monitor.py`,
`services/company_enrichment.py`, new `tests/unit/test_loopholes_pipelines.py`.
- [ ] A1 `_reuse_existing_contacts` + `_auto_enrich_company_siblings`: filter by `tenant_id` (CRITICAL leak)
- [ ] A2 Enrichment meters only newly discovered contacts (`contacts_found - contacts_reused`)
- [ ] A3 Per-row `begin_nested()` savepoints instead of full `db.rollback()` (lead sourcing + enrichment) so counters match stored rows
- [ ] A4 Meter incrementally at checkpoint commits so crashed/partial runs are billed for what was stored (sourcing, enrichment, validation) — no double charge
- [ ] A5 Intent scan: also meter `lead_sourced` for leads it creates
- [ ] A6 company_enrichment: meter LLM `research_company` calls; cache firmographics for dropped companies so they are not re-bought; stop re-calling forever on permanently-null fields
- [ ] A7 Scheduler-independent: pipelines accept and honour a budget check hook? → NO (C owns scheduler); A only fixes metering.

### Agent B — entry points, settings, send gate, signup
Owns: `api/endpoints/settings.py`, `api/endpoints/contacts.py`, `schemas/contact.py`,
`api/endpoints/lead_search.py`, `core/api_key_scopes.py`, `api/endpoints/leads.py`,
`services/send_gate.py`, `api/endpoints/auth.py`, `schemas/tenant.py`, `schemas/sender_mailbox.py`,
`services/pipelines/outreach.py`, rate-limiter module, new `tests/unit/test_loopholes_entrypoints.py`.
- [ ] B1 `PUT /settings/{key}`: super-admin-only denylist for feature flags, credit enforcement, AI provider/model/keys, cooldown/caps floors (validate ranges)
- [ ] B2 `is_test` / `validation_status` writable only by super admin
- [ ] B3 `/leads/database-search`: budget gate, meter `contact_enriched` per result, remove from read-only API-key list
- [ ] B4 CSV / Google-Sheet import: admin/BDM only, plan-limit check for row count, row cap
- [ ] B5 send gate: block `billing_suspended` tenants; validation-result lookup scoped to tenant
- [ ] B6 Signup: normalise email (lowercase, strip `+tag` for duplicate check), block disposable domains, rate limiter on shared Redis storage when available
- [ ] B7 Mailbox `daily_send_limit` upper bound; outreach pipeline clamps it
- [ ] B8 Notification test-send: rate limit + restrict recipient to the caller's own email

### Agent C — credit engine, scheduler, AI metering, Stripe
Owns: `services/credit_metering.py`, `core/credit_costs.py`, `api/deps/auth.py` (budget dep only),
`services/warmup/scheduler.py`, `services/ai_sequence_generator.py`, `services/ai_icp_wizard.py`,
`api/endpoints/sequence_generator.py`, `api/endpoints/icp_wizard.py`, `api/endpoints/email_preview.py`,
`services/email_preview_service.py`, `services/outreach_draft_service.py`, `api/endpoints/campaigns.py`,
`api/endpoints/inbox.py`, `services/ai_sentiment.py`, `services/ai_reply_agent*.py`,
`services/pipeline_summary.py`, `api/endpoints/billing.py`, `api/endpoints/clients.py`,
new `tests/unit/test_loopholes_credits.py`.
- [ ] C1 Charges actually persist: commit at AI endpoints (sequence, ICP, preview-personalization)
- [ ] C2 Gate on estimated cost (`credits_needed`) for pipeline runs; budget gate on sequence-generator + preview
- [ ] C3 Carry negative balance forward on monthly refill
- [ ] C4 Scheduler: per-tenant `check_credit_budget` before scheduled sourcing/enrichment/validation (skip, log)
- [ ] C5 Lock balance in refill paths (`get_balance(lock=True)`)
- [ ] C6 Meter unmetered AI: outreach drafting, AI rewrite, spam-fix suggestions, subject/name suggestions, suggest-reply, sentiment, reply-agent early returns, pipeline summary regenerate, clients bulk enrich endpoints (gate)
- [ ] C7 Stripe top-up: grant only when `payment_status == "paid"`; handle `async_payment_succeeded`
- [ ] C8 Fix `ai_icp_wizard` `get_ai_adapter()` call missing `db`

### Main session — credit meter + history (user request 2026-10-12)
Owns: `api/endpoints/credits.py`, frontend `components/credit-meter.tsx`, `lib/credit-ledger.ts`,
`app/dashboard/billing/credits/page.tsx`, `app/dashboard/layout.tsx`, `app/dashboard/billing/page.tsx`, `lib/api.ts`.
- [x] M1 `/credits/usage` + `/credits/summary` return `label`/`category`; summary excludes top-up grants (490b428)
- [x] M2 Top-bar credit meter (desktop + mobile), refreshes every 60s, popover with allowance/top-up/sends (55390ab)
- [x] M3 `/dashboard/billing/credits` history page: filters, pagination, monthly breakdown, CSV (55390ab)

## Integration (main session)
- [x] I1 Merge A, B, C branches into `bugfix/credit-loopholes`
- [x] I2 Full backend suite — zero regressions (2086 passed, 0 failed)
- [x] I3 Update `CLAUDE_REFERENCE/services.md`, `api-endpoints.md`, `multi-tenancy.md`, `deployment.md`
- [ ] I4 PR to master (no deploy until user says)

### Integrator extras (2026-10-12)
- [x] Tenant AI overrides only run on the tenant's own key (BYO key stays tenant-writable)
- [x] Preview drafts used ANY tenant's mailbox — scoped to tenant
- [x] Run-sized gates: outreach run, forced summary regenerate, scheduled intent scans
- [x] Browser QA finds: month usage netted top-ups; 402 said "out of credits" with credits left — both fixed

## Acceptance
Every item above has a test that fails on master and passes on the branch; full suite green.
