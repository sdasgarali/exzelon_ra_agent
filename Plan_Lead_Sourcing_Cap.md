# Plan — Lead-sourcing cap per run + stop when credits run out

> Status: APPROVED 2026-11-09 (defaults accepted: max 5,000; blank = no cap; anyone who can run sourcing). Branch: `feature/lead-sourcing-cap`.

## Goal
1. A workspace user chooses **how many leads** a lead-sourcing run should fetch.
2. A run **stops as soon as the workspace is out of credits**, instead of finishing and
   carrying the overage into next month.

## Today (verified in code)
- `POST /pipelines/lead-sourcing/run` takes only `sources` + `lob_id`. No count.
- The run dialog (`dashboard/pipelines/page.tsx`, ConfirmDialog) has no input.
- The only volume controls are Settings → Source Tuning (`pipeline_adapter_limit`,
  `lead_sourcing_target_per_run` = a *soft* early-stop for expensive sources, not a cap).
- Pre-flight gate asks for 50 credits (`RUN_ESTIMATE_SOURCING_LEADS`), then the run
  spends freely: `spend()` never refuses, it drives the balance negative.
- A run spends credits in 3 places:
  - firmographic lookups in the company gate — 3 cr/company, up to 300 (`enrich_max_companies`);
  - applicant-count scrapes — 3 cr each, up to 50 (off by default);
  - 1 cr per lead saved (insert loop, billed every 10 leads).

## Design

### A. Per-run cap (`max_leads`)
- New optional query param `max_leads` on `/pipelines/lead-sourcing/run`
  (int, 1–5,000; omitted = use the saved default).
- New tenant setting `lead_sourcing_max_leads_per_run` (Source Tuning tab,
  default **0 = no cap**). Used when the param is omitted, so scheduled runs and the
  Run buttons on Dashboard / Campaigns also respect it.
- `run_lead_sourcing_pipeline(..., max_leads=None)`:
  - insert loop stops once `inserted == max_leads`; the rest are not saved or billed;
  - the tiered early-stop target becomes `min(target_per_run, max_leads)`, so the
    expensive tier-2 sources don't run for a small request;
  - paid pre-insert work is scaled to the request:
    firmographic lookups ≤ `max_leads × 3`, applicant scrapes ≤ `max_leads × 2`
    (still also bounded by their existing settings). Without this, asking for 10 leads
    could still spend 900 credits on company research.
- Pre-flight gate: needs `min(max_leads, 50)` credits instead of a flat 50, so a
  workspace with 10 credits can run a 10-lead job.

### B. Stop when credits run out
Only when credit enforcement is on for the workspace (it is on in prod for everyone);
super admin / internal runs are unaffected.
- Before each paid step (firmographic batch, applicant batch) read the balance and limit
  the step to what's affordable; skip it at 0.
- Before the insert loop, compute `affordable = floor(balance / cost(lead_sourced))`;
  the effective cap is `min(max_leads, affordable)`.
- At every 10-lead checkpoint (where billing already happens), re-read the balance — another
  pipeline may be spending in parallel — and stop when it can't cover the next lead.
- Result: overspend is at most one checkpoint batch from concurrent spending, not a whole run.

### C. Reporting
- Run counters gain `requested_max_leads`, `stopped_reason`
  (`max_leads_reached` | `credits_exhausted` | null), `leads_not_saved`.
- Status stays `completed` (leads saved so far are kept and billed). Pipelines page shows
  e.g. *"Stopped: out of credits — 37 of 100 leads saved. Top up to continue."*

### D. UI
- Run dialog gets a **"How many leads?"** number field, prefilled with the saved default
  (blank = no cap), plus a hint: *"You have 240 credits ≈ 240 leads (1 credit each)."*
  `ConfirmDialog` gains optional `children` to host the field.
- Source Tuning tab: "Default leads per run (0 = no limit)".

### E. MCP connector
- `run_lead_sourcing` tool gets optional `max_leads`, shown in its confirmation payload.

## Tasks
- [x] 1. Backend: `max_leads` param + setting + `SETTINGS_TAB_MAP` (`source_tuning`) + estimate change
- [x] 2. Backend: pipeline cap, scaled pre-insert spend, credit-stop checks, counters
- [x] 3. Backend tests: cap honoured; credit stop mid-loop; pre-insert steps bounded;
      enforcement-off unchanged; estimate gate with small `max_leads`; scheduler uses default
- [x] 4. Frontend: dialog field + hint, api.ts param, Source Tuning field, run-result message; jest tests
- [x] 5. MCP tool param + test
- [x] 6. Docs: `api-endpoints.md`, `services.md`, `adapters.md` (Source Tuning)
- [ ] 7. Full backend + MCP + frontend suites, lint, tsc → PR → CI → deploy on approval

## Acceptance criteria
- Run with `max_leads=25` saves ≤ 25 leads and bills ≤ 25 lead credits.
- Workspace with 12 credits, run asks 100 → ≤ 12 leads saved, run ends
  `stopped_reason=credits_exhausted`, balance never below 0 from this run alone.
- 0 credits → run refused at start (402), as today.
- No `max_leads` and default 0 → behaviour identical to today, except the credit stop.

## Open decisions (defaults proposed)
1. Upper bound per run: **5,000**.
2. Default when left blank: **no cap** (only credits stop it).
3. Who can set the count: anyone allowed to run lead sourcing (pipelines → lead_sourcing
   read_write). The saved default stays in Source Tuning.

## Follow-up (2026-11-09): default set from the Run dialog
Source Tuning is not visible to client admins (role matrix), and it holds platform-cost knobs,
so it stays as is. Instead (user's direction):
- Run dialog gets a tick box **"Use this number for every run (default)"**. Ticked → the number is
  saved as the workspace default and prefilled next time. Unticked → this run only, and any saved
  default is cleared.
- Pipelines page shows the current default next to the Run Lead Sourcing button.
- New `PUT /pipelines/lead-sourcing/default-max-leads` (pipelines → lead_sourcing read_write,
  tenant required) writes `lead_sourcing_max_leads_per_run` (null/0 clears).
- [x] F1 backend endpoint + tests  - [x] F2 dialog tick box + page badge + tests  - [ ] F3 suites, PR, deploy

## Follow-up 2 (2026-11-09, APPROVED): strict fetch budget + pay only for saved leads
User's rule: the pop-up number is **jobs to fetch** — min **10**, max **5,000**, both shown in the
pop-up. Never fetch more than that from the APIs in total. Charge only for leads actually saved;
duplicates and filtered jobs cost nothing.

### Fetch budget (only when a run has a number)
- Sources run **one after another** in tier order with a shared budget `remaining = N`
  (uncapped runs keep today's parallel fetch). Each source gets `limit=remaining`; the pipeline
  then truncates what it returns to `remaining` (hard guarantee), subtracts, and stops at 0 —
  later/expensive sources never run once the budget is used.
- Each API is asked for no more than it may return:
  - Fantastic.jobs: per request `limit=min(100, remaining)`; pages bounded by the budget.
  - TheirStack: per page `limit=min(per_page, remaining)`.
  - Adzuna: `results_per_page=min(rpp, remaining)`.
  - JSearch (fixed ~10/page): `num_pages=floor(remaining/10)`; skipped when < 10 remain.
  - Other adapters (SerpAPI, SearchAPI, USAJobs, Jooble, JobDataFeeds, Coresignal, Indeed):
    get `limit=remaining` and are truncated by the pipeline. Not used in prod today (run #1733).
  - LOB lead sources: `limit=min(configured, remaining)` + truncation.
- Counters: `fetch_limit`, `jobs_fetched`; new `stopped_reason="fetch_limit_reached"` when the
  budget is used up before N leads were saved.

### Billing
- Lead credits already charge only stored leads (1 each) — duplicates/filtered are never charged.
- Lead-sourcing **company research and applicant scrapes stop being charged to the workspace**
  (flag on `resolve_company_metadata_batch` / `resolve_applicant_counts`), so a run costs exactly
  its saved leads. Research is still bounded (≤ N×3 lookups) and still recorded as platform cost.
- Run report / pop-up text: "Fetched 10 jobs → 4 new leads (4 credits). 6 duplicates or filtered —
  not charged."

### Limits
- `MIN_LEADS_PER_RUN = 10`: run + default endpoints `ge=10`; a saved default below 10 is raised to
  10; `run-options` returns `min_leads`. Pop-up field required, 10–5,000, label shows the range.
- Scheduled runs / Dashboard + Campaigns buttons: use the saved default (strict too); no default =
  today's uncapped behaviour.

### Tasks
- [x] S1 pipeline budget + truncation + counters   - [x] S2 adapter request sizing (4 APIs)
- [x] S3 research not billed in sourcing           - [x] S4 min 10 (backend + pop-up + Source Tuning)
- [x] S5 tests (budget never exceeded per adapter, sequential stop, billing = saved leads, min 10)
- [ ] S6 suites, PR, CI, deploy on approval
