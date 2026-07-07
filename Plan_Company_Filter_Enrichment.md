# Plan — Company Detail Capture + Size/Industry Exclusion Gate

## SESSION_CONTEXT_RETRIEVAL
> Goal: (a) capture Industry + Company Size at sourcing from TheirStack/Coresignal, (b) add a lightweight LLM (Groq) company-enrichment step (cached+bounded) for sources that lack it, (c) enforce exclusion so big/IT/staffing/government/confidential companies are dropped at sourcing. Driven by `neuraforz tool leads review.xlsx` (cols E/F): 48/60 leaked leads were "big size company", plus IT (Oracle/Toast), staffing (Jobot), government (City of Austin), confidential/missing-poster (Marsh, Confidential).

## Decisions (user-approved)
- Size ceiling: **≤ 500 employees** (drop 501+). Configurable.
- Hard-drop industries: **IT/Software, Staffing & Recruiting, Government/Public Admin, Confidential/unknown employer**. (Insurance/Financial stay targets — rejected for size, not industry.)
- Enrichment: **LLM (Groq) via existing `research_company`, cached on ClientInfo + bounded per run.**

## Root cause
- `base.filter_excluded` only matches keywords against job title + company NAME text → cannot detect "big"/IT/gov from a bare brand name (Oracle, HP, Kroger).
- Company size/industry are NOT captured at sourcing for JSearch/Adzuna/SearchAPI/Jooble/USAJobs. TheirStack already caps at 200 server-side (`THEIRSTACK_MAX_EMPLOYEE_COUNT`), so leaks came from the other sources.
- No size/industry gate exists anywhere in `lead_sourcing.py`.

## Tasks
- [x] 1. `services/company_filters.py` (pure, testable): `parse_employee_count`, `industry_is_excluded`, `is_placeholder_company`, `exceeds_size_ceiling`.
- [x] 2. config.py defaults: `LEAD_SOURCING_MAX_EMPLOYEE_COUNT=500`, `EXCLUDED_INDUSTRY_KEYWORDS`, enrichment bounds, drop-confidential.
- [x] 3. TheirStack adapter: map `company_object.industry` + `employee_count` → job_data.
- [x] 4. Coresignal adapter: map company `industry` + employee count → job_data.
- [x] 5. `company_enrichment.resolve_company_metadata_batch` — ClientInfo cache, else Groq `research_company`; threaded (no DB in threads), bounded.
- [x] 6. `lead_sourcing._apply_company_gate` after dedup + company-name exclusion, before insert loop. Counters wired into `counters_json`.
- [x] 7. Settings (tenant-overridable) all wired via `get_tenant_setting`.
- [x] 8. Unit tests: `tests/unit/test_company_filters.py` (37) + TheirStack industry/size capture. 144 pass; pipeline suite 90 pass.
- [x] 9. Update CLAUDE_REFERENCE (services/adapters) + memory.

## Follow-ups (optional, not done)
- Expose the 5 new gate settings in Settings → Source Tuning UI (currently defaults only).
- Deploy: frontend rebuild + `systemctl restart exzelon-api exzelon-web`.
- Verify Groq key present on prod tenant-1 (else enrichment silently skips for JSearch/Adzuna/etc.).

## Acceptance
- Companies with >500 employees, IT/software, staffing/recruiting, government, or confidential/blank names are dropped at sourcing (counted in run counters).
- Industry + size populated on new leads/clients from TheirStack/Coresignal at source, and from Groq for others (cached).
- Existing tests pass; new unit tests pass.

## Completed
- [x] Investigated pipeline, filters, adapters, config, enrichment infra (2026-07-06)
