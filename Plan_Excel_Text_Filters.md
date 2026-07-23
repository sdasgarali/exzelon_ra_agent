# Plan — Excel-style Text Filters (Industry / Job Title / Company Name / Position Type)

## SESSION_CONTEXT_RETRIEVAL
> Add an Excel-like Text Filter (checklist + "Text Filters" operator submenu:
> Equals / Does Not Equal / Begins With / Ends With / Contains / Does Not Contain /
> Custom Filter) for Industry, Job Title, Company Name, Position Type across the
> Leads, Campaigns (Available Leads), Clients, and Contacts pages.

## Decision
- Operators = **server-side text predicate** (LIKE/equality), because the typed text
  is often NOT in the checklist (esp. unbounded Company Name). The checklist stays
  for exact multi-select; the Text-Filters condition is an independent AND'd predicate.
- Custom Filter = two conditions combined with AND/OR.

## Contract
Frontend `ExcelTextFilter` emits: `selected: string[]` (checklist) + `textCondition:
{op, val, op2?, val2?, conj?} | null`. Serialized to params `<field>_op`, `<field>_val`
(+ `_op2`, `_val2`, `_conj`). Ops: equals|not_equals|begins|ends|contains|not_contains.

Backend helper `text_filter_condition(column, op, val, op2, val2, conj)` → SQLAlchemy
clause (ilike with escaped % _). NULL-safe for not_equals / not_contains.

## Field → column map
- Industry → LeadDetails.industry / ClientInfo.industry
- Job Title → LeadDetails.job_title
- Company Name → LeadDetails.client_name (leads); ClientInfo.client_name (clients);
  ContactDetails.client_name (contacts)
- Position Type → LeadDetails.employment_type

## Tasks
- [ ] Backend: `app/utils/text_filter.py` helper + unit tests
- [ ] Backend: wire params into GET /leads (industry, title, company, employment_type)
- [ ] Frontend: `components/excel-text-filter.tsx` (checklist + Text Filters submenu + Custom Filter dialog) + `textConditionParams()` helper + tests
- [ ] Frontend: wire Leads page (Industry, Job Title, Company Name, Position Type)
- [ ] Verify Leads end-to-end (tsc, build, pytest)
- [ ] Fan out (parallel agents, one file each): Campaigns available-leads, Clients, Contacts (+ their endpoints)
- [ ] Integrator: tsc + build + full pytest; commit; PR; deploy

## Completed
(none yet)
