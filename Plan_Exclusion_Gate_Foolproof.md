# Plan — Foolproof Pre-Enrichment Exclusion Gate

## SESSION_CONTEXT_RETRIEVAL
> Goal: guarantee ZERO paid API usage (contact-discovery + LLM) on unwanted
> jobs/leads/companies. Root cause: exclusion filters run ONLY at lead sourcing
> and work by dropping-before-insert; contact enrichment trusts the DB and
> re-checks nothing before calling paid adapters. Multiple entry paths create
> leads that bypass the sourcing gate. Fix = centralized eligibility gate at the
> enrichment choke-point + seal all lead entry paths + wire salary + free
> metadata-resolve on unknowns.
> Decisions locked (2026-07-07): (1) UNKNOWN industry/size → resolve via FREE
> Groq/cache first, drop confirmed-unwanted, let still-unknown through (recall
> preserved). (2) Scope = defense-in-depth: enrichment gate + import/create gate
> + ad-hoc search gate + wire MIN_SALARY_THRESHOLD.

## Problem map (verified in code)

Paid call sites (all per-lead, NO exclusion check before them):
- `contact_enrichment.py:527` — Apollo/Seamless/Hunter/Snov/RocketReach/PDL/Proxycurl waterfall
- `lead_search.py` ad-hoc `database_search_contacts` → Apollo directly (no gate)
- `company_enrichment.resolve_company_metadata_batch` → LLM (Groq free / OpenAI paid)

Filters exist only at `lead_sourcing._apply_company_gate` (`lead_sourcing.py:1149`),
which drops jobs pre-insert. `company_filters.py` provides pure helpers:
`is_placeholder_company`, `industry_is_excluded`, `exceeds_size_ceiling`
(unknown size/industry → NOT excluded, by design).

Leaks (leads reach paid APIs without passing the gate):
1. File import `lead_sourcing.import_leads_from_file` (~1631) → status OPEN
2. `POST /leads` `leads.py:~2257` → any status
3. `POST /leads/bulk/import` `leads.py:~1249`
4. Ad-hoc `lead_search.py` Apollo call — no gate at all
5. Explicit `lead_ids` enrichment path (`contact_enrichment.py:437`) accepts ANY
   non-closed status, not just NEW
6. Unknown industry/size never dropped → paid API spent on maybe-unwanted
7. `MIN_SALARY_THRESHOLD` (config.py:136) defined but never wired

## Design — single shared gate, reused everywhere

New module `backend/app/services/lead_eligibility.py`:
```
lead_is_eligible(db, lead_like, tenant_id, *, resolve_unknowns=True)
    -> (eligible: bool, reason: str | None)
```
- Loads tenant settings once (excluded_industries, max_employee_count,
  drop_confidential, min_salary_threshold, company-exclusion list).
- Applies, in order: placeholder-name → company-exclusion-list → salary floor →
  industry → size ceiling.
- On unknown industry/size AND `resolve_unknowns=True`: call
  `resolve_company_metadata_batch` (FREE Groq/cache, bounded) to fill, then
  re-check. Still-unknown → eligible (recall preserved).
- Pure-ish + unit-testable; wraps the existing `company_filters` helpers so
  there is ONE source of truth for "unwanted".

## Tasks

### Layer 3 — Enrichment choke-point (THE guarantee)
- [ ] Create `services/lead_eligibility.py` with `lead_is_eligible`
- [ ] In `contact_enrichment.run_contact_enrichment_pipeline`, after leads are
      selected (both `lead_ids` and auto paths, ~line 455) and inside the
      per-lead loop BEFORE the adapter loop (~line 511): call `lead_is_eligible`;
      if not eligible → mark `lead.lead_status = EXCLUDED`, set `skip_reason`,
      `counters["excluded"] += 1`, `continue` (no adapter call, no LLM paid).
- [ ] Batch-resolve unknowns once per run (collect unknown companies, single
      `resolve_company_metadata_batch` call) to avoid per-lead LLM overhead.
- [ ] Tighten explicit `lead_ids` path: still gate every lead (gate already
      covers it; no status loosening).

### Layer 2 — Seal entry paths (defense in depth)
- [ ] `import_leads_from_file` (lead_sourcing.py) — run gate before insert; skip
      excluded rows, report counts.
- [ ] `POST /leads` (leads.py) — gate on create; 422 or insert-as-EXCLUDED for
      out-of-scope (decision: insert as EXCLUDED so it's auditable, never enriched).
- [ ] `POST /leads/bulk/import` (leads.py) — gate each row before insert.

### Layer 4 — Ad-hoc search
- [ ] `lead_search.py` `database_search_contacts` — gate the target company/lead
      before the Apollo call; return empty + reason if excluded.

### Salary wiring
- [ ] Add salary floor to `lead_eligibility` + to `_apply_company_gate` so it is
      enforced at sourcing too. Setting: `min_salary_threshold`.

### Status + state machine
- [ ] Add `LeadStatus.EXCLUDED = "excluded"` (string enum, no DB migration) and
      include in `CLOSED_STATUSES` + `state_machine.py` transitions so excluded
      leads are terminal and never re-enter any enrichment queue.

### Tests (unit + integration)
- [ ] `test_lead_eligibility.py` — unit: each rule, unknown-resolve path, salary.
- [ ] Integration: enrichment pipeline given an excluded lead makes ZERO adapter
      calls (assert adapter mock not called). Cover all 4 entry paths.
- [ ] Regression: eligible lead still enriches; still-unknown lead still enriches.

### Verification
- [ ] `cd backend && pytest -q` green
- [ ] Manual: seed one IT-industry + one >500-emp lead, run enrichment, confirm
      counters.excluded and no cost_entries rows created.

## Acceptance criteria
- No paid contact-discovery or paid-LLM call occurs for a lead that fails ANY
  exclusion rule, via ANY entry path.
- Unknown-data leads are resolved via FREE provider first; genuinely-unknown
  still enriched (no recall regression).
- Excluded leads are terminal (`EXCLUDED`), auditable (`skip_reason`), excluded
  from all queues.
- Full backend test suite green; new tests prove the guarantee.

## Completed
- [x] Traced pipeline, inventoried filters, mapped all paid call sites (2026-07-07)
- [x] Locked the 2 design decisions with user (2026-07-07)

## Blockers / Notes
- `resolve_unknowns` must use ONLY the free provider by default (Groq/cache) —
  never trigger paid LLM to save a cheaper contact API. Guard provider selection.
- Company-exclusion-list is tenant+LOB scoped — pass lob_id where available.
