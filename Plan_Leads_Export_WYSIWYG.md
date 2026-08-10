# Plan — Leads Export "blank CSV" fix → full WYSIWYG export

## SESSION_CONTEXT_RETRIEVAL
> Bug: `/dashboard/leads` Export CSV produced a header-only file (420 bytes, 0 rows).
> Root cause CONFIRMED: export request mirrors only 6 of the leads-list filters and
> NEVER sends `show_archived`/`lob_id` (nor industry/size/salary/employment/text
> filters). Backend export always filters `is_archived == False`. When the user views
> archived leads — or is scoped to a tenant with 0 non-archived leads (prod tenant 3
> Medeoan = 0 non-archived / 25 archived) — the export matches 0 rows and streams only
> the header. Prod check: no leads got `downloaded_at`-stamped → proves 0-row match,
> not a mid-stream failure. User chose FULL WYSIWYG fix + zero-row guard.

## Root cause (evidence)
- `frontend .../leads/page.tsx` `handleExport()` builds body from only: status, source,
  state, from_date, to_date, search. Missing: show_archived, lob_id, industry, company
  size, salary, data_type, employment_type, exclude_keywords, title, text filters,
  extracted_from/to, downloaded.
- `backend .../endpoints/leads.py` `LeadExportRequest` + POST/GET export apply the same
  small subset; always `is_archived == False` unless `show_archived` passed.
- Downloaded file = 420 bytes, header row only. Prod: 0 `downloaded_at` stamps in 6h.

## Design
Make export WYSIWYG by reusing the list endpoint's filter logic on both sides.

### Backend
1. Extract the full filter block from `list_leads` (leads.py ~L122–275) into a shared
   `_apply_lead_filters(query, db, tenant_id, *, <all filters>, text_params)` helper
   returning the filtered query. `text_params` is a Mapping used by
   `text_filter_from_params` (works with `request.query_params` OR a dict).
2. `list_leads` calls the helper (pass `text_params=request.query_params`). Keep its
   sorting/paging/counts untouched.
3. Extend `LeadExportRequest` with ALL filter fields + `model_config = extra='allow'`
   (to carry dynamic text-filter keys like `industry_op`). POST export applies
   `_apply_lead_filters(..., text_params=body.model_dump())` when `lead_ids` is absent;
   keep `lead_ids`-only fast path.
4. Keep GET export as a thin wrapper for backward compat (also route through helper).

### Frontend
5. Extract `buildLeadFilterParams()` from `fetchLeads` (page.tsx L281–307) → returns the
   filter object. `fetchLeads` spreads it + page/sort. `handleExport('all')` sends it as
   the POST body (same keys the list uses → identical result set).
6. Zero-row guard: after download, if the CSV blob has ≤1 line (header only) show an
   info toast "No leads matched your current filters — nothing to export" instead of a
   success message. (Backend still returns the header so the file is valid if saved.)

## Tasks
- [ ] 1. Backend: add `_apply_lead_filters` helper (extract from `list_leads`).
- [ ] 2. Backend: refactor `list_leads` to use the helper (no behavior change).
- [ ] 3. Backend: extend `LeadExportRequest`; route POST + GET export through helper.
- [ ] 4. Backend: unit/integration tests — export honors show_archived, lob_id,
        industry/size/salary/text filters; selected (lead_ids) still works.
- [ ] 5. Frontend: extract `buildLeadFilterParams()`; use in fetchLeads + handleExport.
- [ ] 6. Frontend: zero-row guard toast.
- [ ] 7. Run backend pytest (export + leads suites) + frontend lint/build. Zero regressions.
- [ ] 8. Commit on feature branch, PR, deploy per runbook.

## Acceptance criteria
- Viewing archived leads → Export CSV contains exactly those archived rows.
- Any active list filter (industry/size/salary/employment/text/LOB/date) → export set ==
  list set for the same filters.
- Selected-rows export unchanged.
- Exporting an empty result set warns the user (no silent blank download).

## Completed
- [x] Root-cause analysis + prod verification (2026-08-10)

## Blockers / Notes
- text_filter_from_params uses `.get()` → dict from `body.model_dump()` is compatible.
- Deploy: `git pull` → rebuild frontend → restart exzelon-api + exzelon-web.
