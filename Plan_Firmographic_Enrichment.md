# Plan — Firmographic (company size/industry) Enrichment via Apollo

## SESSION_CONTEXT_RETRIEVAL
> Problem (found via Run #1570): leads from metadata-poor sources (SearchAPI /
> google_jobs) have no industry/size and no domain. TheirStack leads are 100%
> enriched (native firmographics). Free Groq resolver fills industry for
> recognizable names but almost never company SIZE. Fix = (A) backfill domains
> for domain-less unfilled leads then Apollo-enrich by domain; (B) wire an Apollo
> firmographic step into the sourcing resolver so future runs fill size.
> KEY FINDING (2026-07-07): Apollo /organizations/enrich works by DOMAIN
> (performanceservices.com → 510 emp, industry) but returns nothing by NAME.
> So domain is a hard prerequisite for Apollo firmographics.
> Apollo is the ONLY firmographic provider keyed on prod (apollo_api_key SET in
> tenant_settings tenant 1; clearbit/coresignal/pdl/proxycurl EMPTY).

## Design — one reusable firmographic module, used by pipeline + backfill

New `backend/app/services/company_firmographics.py`:
```
apollo_enrich_by_domain(http, api_key, domain) -> {employee_count, company_size,
    industry, website, linkedin_url} | None      # thin wrapper over /organizations/enrich
enrich_firmographics_batch(db, items, tenant_id, max_lookups) -> {key: {...}}
    # items: (name, domain). For each missing employee_count AND has a domain:
    #   Apollo-by-domain (bounded by max_lookups), cache into ClientInfo,
    #   record cost via cost_tracker (category "firmographic"). Domain-less →
    #   left for the LLM/ domain-backfill path (Apollo can't help).
```
`_employee_count_to_size(count)` shared helper (bucketing → "1-50".."5000+").

### Workstream B — wire into the sourcing resolver (code)  [IMPLEMENTED, tests green]
- [x] `services/company_firmographics.py` (apollo_enrich_by_domain, enrich_firmographics_batch, employee_count_to_size, get_firmographic_provider)
- [x] Wired firmographic step into `resolve_company_metadata_batch` (cache → firmographic(domain, paid, not free_only) → LLM). settings imported.
- [x] Settings COMPANY_FIRMOGRAPHIC_PROVIDER="none", COMPANY_FIRMOGRAPHIC_MAX_LOOKUPS=100 in config.py.
- [x] free_only never triggers Apollo (guarded + tested). Cost category "firmographic".
- [x] Tests: tests/unit/test_company_firmographics.py (17) green. Ruff clean.
- [x] services.md updated.
- [ ] (superseded detail) Add firmographic step to `resolve_company_metadata_batch` (company_enrichment.py):
      after cache, BEFORE the LLM step, when `not free_only` and provider enabled,
      call `enrich_firmographics_batch` for `to_enrich` items that have a domain.
      Merge employee_count/company_size/industry; drop filled ones from LLM set.
- [ ] Setting `company_firmographic_provider` (default "none"; "apollo" enables).
      Setting `company_firmographic_max_lookups` (default 100 — cost guard).
- [ ] free_only path (pre-enrichment gate) NEVER triggers Apollo (paid). Guard it.
- [ ] Cost tracking: record Apollo org-enrich under category "firmographic".
- [ ] Tests: unit (apollo wrapper w/ mocked http; batch caps + caching; free_only
      skips Apollo; domain-less skipped), integration (resolver fills size from a
      mocked Apollo when domain present).

### Workstream A — backfill Run #1570 + existing unfilled leads (prod op)
- [ ] Domains first: for domain-less unfilled leads, resolve a domain (free Groq
      website guess via research_company, best-effort). Persist employer_website /
      ClientInfo.website+domain.
- [ ] Then Apollo firmographic by domain (reuse `enrich_firmographics_batch`);
      persist to ClientInfo + propagate size/industry to lead_details.
- [ ] Rewrite/extend `backend/scripts/backfill_company_size.py` to: (1) accept
      --tenant, --since, --limit, --dry-run; (2) domain-resolve then Apollo;
      (3) update BOTH industry and company_size on lead_details (script currently
      only backfills size). Commit the script (currently untracked).
- [ ] Run dry-run on prod first (report counts + est. Apollo credits), then execute
      scoped to tenant 1 unfilled leads. Rate-limited (~1 req/s). Verify fill rate.

### Deploy + verify
- [ ] Enable `company_firmographic_provider=apollo` (+max_lookups) in tenant-1 settings.
- [ ] Deploy code; trigger a fresh test run; confirm SearchAPI leads now get size.

## Acceptance
- New sourcing runs fill company_size for leads that have (or get) a domain, via
  Apollo, bounded + cost-tracked; free_only gate never incurs Apollo spend.
- Run #1570's unfilled leads backfilled (industry + size) where a domain is
  resolvable; report the residual (truly-unidentifiable) count.

## Blockers / Notes
- Apollo REQUIRES a domain. Domain-less + unresolvable companies stay unfilled
  (recall preserved, never dropped). Document residual honestly — no silent caps.
- Apollo org-enrich costs credits; every path is bounded by an explicit max +
  cost-tracked. Dry-run before any bulk prod backfill.
- Reuse ONE firmographic module across pipeline + backfill (no duplicate logic).
