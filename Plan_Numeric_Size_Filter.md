# Plan — Numeric Operator-Based Company-Size Filters (Leads + Clients)

## SESSION_CONTEXT_RETRIEVAL
> Convert the "Company Size" filter on /dashboard/leads and /dashboard/clients from
> band multi-select/dropdown to numeric mathematical operators (<, ≤, >, ≥, =, ≠, Between).
> Decisions (confirmed by user):
>  1. Filter on EFFECTIVE employee count = COALESCE(employee_count, parsed band).
>     Band parse: exact "120" → 120; range "51-200" → lower bound 51; empty/non-numeric → unknown(NULL).
>  2. Unknown sizes handled via a UI "Include unknown" toggle (default OFF).
> Branch: feature/numeric-size-filters

## Design
- **Backend helper** in `db/query_helpers.py`:
  - `SIZE_OPERATORS = {eq, ne, lt, lte, gt, gte, between}`
  - `effective_size_expr(size_col, emp_col=None)` → `coalesce(emp_col, nullif(cast(nullif(size_col,''), Integer), 0))` (portable MySQL+SQLite; CAST parses leading int).
  - `size_operator_clause(expr, op, v1, v2)` → SQLAlchemy boolean clause (None if invalid).
- **Clients** `GET /clients`: replace `company_size: str` with `company_size_op/value/value2/include_unknown`. Filter on `effective_size_expr(ClientInfo.company_size, ClientInfo.employee_count)`.
- **Leads** `GET /leads`: replace `company_size: List[str]` with the 4 numeric params. Lead has no employee_count → parse `LeadDetails.company_size`; fall back to client (by name) `effective_size_expr(ClientInfo.company_size, ClientInfo.employee_count)` ONLY when the lead's own size is unknown (mirrors display COALESCE precedence). Include-unknown = lead unknown AND client unknown.
- **Frontend** shared component `components/SizeFilter.tsx` (op select + number input(s) + incl-unknown checkbox) + `sizeFilterParams()` / `sizeFilterActive()` helpers. Wire into both pages; remove old band state.

## Tasks
- [x] 1. Backend helper in query_helpers.py (+ unit test test_size_filter.py)
- [x] 2. Clients list endpoint numeric filter
- [x] 3. Leads list endpoint numeric filter
- [x] 4. Frontend SizeFilter component + helpers
- [x] 5. Wire leads page
- [x] 6. Wire clients page
- [x] 7. Integration tests (leads numeric filter; clients numeric filter)
- [x] 8. Run backend pytest + frontend typecheck/tests; fix regressions

## Result (done — pending user commit approval)
- Backend: 17 new tests pass; existing test_leads.py 15/15 pass.
- Frontend: `tsc --noEmit` clean; full jest suite 57/57 pass.
- Branch: feature/numeric-size-filters (uncommitted — awaiting go-ahead).

## Acceptance
- `> 200` returns companies with effective size ≥ 201; `Between 50 and 200` inclusive; `=`, `≠`, `<`, `≤`, `≥` correct.
- Band "51-200" treated as 51 (lower bound); "120" as 120; employee_count wins when present.
- Unknown rows excluded unless "Include unknown" checked.
- Both pages: filter chip counts, clear-filters, pagination reset all work; responsive.
- Zero test regressions.
