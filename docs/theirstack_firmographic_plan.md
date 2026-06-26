# Plan — TheirStack server-side firmographic filtering

## Goal
Push the three business-rule filters into the TheirStack `/v1/jobs/search` query so
they run server-side (instead of post-fetch via Apollo enrichment):
1. **≤200 employees** — `max_employee_count` (default 200, configurable; `min_employee_count` optional)
2. **Exclude staffing agencies** — `company_name_partial_match_not` (from existing `_exclude_company` keywords)
3. **Non-IT companies** — `industry_id_or` / `industry_id_not` (opt-in via tuning; LinkedIn V2 codes)

Bonus: `job_title_not` (exclude intern/entry-level) when push-negatives is on.

## Confirmed API params (from live TheirStack API reference)
- `max_employee_count`, `max_employee_count_or_null` (incl. unknown-size companies)
- `min_employee_count`
- `company_name_partial_match_not` — excludes companies whose name contains any substring (case-insensitive) → ideal for "staffing", "recruiting", etc.
- `job_title_not` — exclude titles
- `industry_id_or` / `industry_id_not` — LinkedIn Industry Codes V2

## Design (no behavior change unless configured, except the ≤200 default)
All new filters are read from the existing per-adapter `tuning` dict
(`job_source_tuning.theirstack.*` in settings) + adapter attributes already set by
the pipeline (`_exclude_company`, `_exclude_title`, `_push_negatives`).

- Extract payload construction into `_build_base_payload()` + `_apply_firmographic_filters()`
  so it's unit-testable without mocking httpx.
- `max_employee_count` defaults to `settings.THEIRSTACK_MAX_EMPLOYEE_COUNT` (=200).
  Set tuning `max_employee_count: null` to disable. `include_unknown_size: true`
  switches to `max_employee_count_or_null` (more volume, includes unknown-size cos).
- Industry filters only added when explicitly set in tuning (no brittle hardcoded codes).
- Company/title exclusions only pushed when `_push_negatives` is True (consistent with
  other adapters); local `filter_excluded` backstop unchanged.

## Tasks
- [ ] config.py: add `THEIRSTACK_MAX_EMPLOYEE_COUNT: int = 200`
- [ ] .env.example: document the new var
- [ ] theirstack.py: extract `_build_base_payload` + `_apply_firmographic_filters`, wire into `fetch_jobs`
- [ ] tests/unit/test_adapters.py: payload-construction tests (size default, disable, unknown-size, staffing exclusion, industry pass-through, push_negatives gating)
- [ ] Run pytest; commit on branch; PR

## Acceptance
- Default run sends `max_employee_count: 200` + `company_name_partial_match_not` (staffing).
- Tuning can disable/loosen each filter.
- All new + existing adapter tests pass.
