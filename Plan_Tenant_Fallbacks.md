# Plan: remove `tenant_id or 1` fallbacks

## Problem
22 places fall back to tenant **1** when no tenant is known. That only happens when a super admin
acts without impersonating a workspace (the scheduler always passes a real tenant). The result:
data, logs or exclusion lookups silently land in / read from tenant 1, a real workspace.
A guard already exists: `ensure_tenant()` in `api/deps/auth.py` (ELR-005) raises 400 instead.

## Sites, by fix

### A. HTTP endpoints → `ensure_tenant()` (400 "Select a tenant first")
- [x] `api/endpoints/templates.py:101, 170`
- [x] `api/endpoints/campaigns.py:588`
- [x] `api/endpoints/pipelines.py:708`
- [x] `api/endpoints/analytics.py:300`
- [x] `api/endpoints/integrations.py:417, 424` (webhook ref: unknown tenant → ignore the event, never tenant 1)

### B. Pipelines / services that write rows → refuse to run without a tenant
Raise `ValueError("tenant_id is required")` at the entry point (not HTTPException: not HTTP code).
- [x] `services/pipelines/lead_sourcing.py:854, 1206, 1288, 1712, 1884, 1899`
- [x] `services/pipelines/contact_enrichment.py:358, 507, 511, 757` (`lead.tenant_id` is always set; use it)
- [x] `services/lead_eligibility.py:150` (exclusions read for the given tenant only)
- [ ] `services/integrations/resource_pool_client.py:201`

### C. Log writers (NOT NULL tenant columns) → skip + warn instead of mis-attributing
- [ ] `services/cost_tracker.py:161, 239`
- [ ] `services/automation_logger.py:34`

Not touched: `credit_costs.py:185`, `warmup/domain_reputation.py:114` (`x or 1` arithmetic, not tenants).

## Tests
- Endpoint: super admin without impersonation → 400; impersonated → works.
- Pipelines: `tenant_id=None` raises; scheduler path (real tenant) unchanged.
- Loggers: `tenant_id=None` writes nothing, no exception.
- Full backend + MCP suites, then multi-tenant-isolation review agent on the diff.

## Ship
Branch `fix/tenant-fallbacks` → PR → CI → merge → deploy → prod health + error-log check.

## Change of plan for group C (2026-11-06)
Skipping log writes would lose real data: 21 of 28 `log_automation_event` calls are system-wide
scheduler events with no tenant, and AI costs from un-impersonated super-admin use are real spend.
The right fix is a nullable `tenant_id` on `automation_events` / `cost_entries` (NULL = system),
hidden from tenants and shown to super admins. That's a schema change, so it's a separate follow-up.
Also fixed here: `lead_sourcing.py` recorded job-board costs with no tenant (so every workspace's
sourcing cost went to tenant 1); it now passes the run's tenant.
