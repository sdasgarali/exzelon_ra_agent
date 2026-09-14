# Plan — Dashboard KPI Accuracy (Valid Emails / Emails Sent)

## SESSION_CONTEXT_RETRIEVAL
> Branch `fix/dashboard-kpi-accuracy` off `master`. Reported bug: on
> https://ra.partnerwithus.tech/dashboard the "Valid Emails" and "Emails Sent" tiles
> both read 0. Diagnosed against prod MySQL (read-only) on 2026-09-14.
> DONE — all steps complete, verified against prod data, committed on this branch.
> NEXT: open PR → merge → deploy via `./deploy/vps_ssh.sh "bash /opt/exzelon-ra-agent/deploy/deploy.sh"`.

## Diagnosis (confirmed against prod DB, 2026-09-14)

KPI window = last 30 days = since 2026-08-15.

### "Valid Emails: 0" — REAL BUG
`/dashboard/kpis` counts `email_validation_results` rows with
`status='valid' AND validated_at` inside the window (`dashboard.py:64`).

| Source | Prod value |
|---|---|
| `email_validation_results` (all time) | 61 rows, 52 valid |
| newest `validated_at` | **2026-04-20** (~5 months stale) |
| → valid rows inside the 30-day window | **0** |
| `contact_details.validation_status='valid'` | **21,224** |

Two sources of truth on one page: the tile reads the near-empty results table, the
"Contacts by validation status" donut reads `contact_details` and shows 21,224.

They diverged because:
- `contact_enrichment.py:690` stamps `validation_status='valid'` whenever the source is
  apollo/seamless — no validation call, no result row written.
- `email_validation.py:129` skips the INSERT when a row for that email already exists, so
  `validated_at` never refreshes and every row eventually ages out of the window.
- `EmailValidationResult` has no `tenant_id` column, so the metric is cross-tenant anyway.

### "Emails Sent: 0" — NUMBER IS CORRECT, page is contradictory
`outreach_events` on prod:

| status | count | sent_at range |
|---|---|---|
| sent | 54 | 2026-04-14 → **2026-05-08** |
| replied | 7 | 2026-04-17 → 2026-05-08 |
| skipped | 106,110 | all 2026-08-19, **every one `skip_reason='dry_run'`** |

No real send since 2026-05-08, so 0-in-30-days is truthful. It only *looks* wrong because
the "Outreach Outcomes" chart uses `/dashboard/stats`, which is all-time AND skips
tenant filtering — it prints 54 next to a tile printing 0.

### Two further bugs found while tracing
- `page.tsx:828` "Replied" funnel pill reads `kpis?.total_replied`; the API returns
  `emails_replied`. Hardcoded 0 regardless of data (prod has 7 replies).
- `/dashboard/stats` and `/dashboard/trends` never apply `tenant_filter` to
  `outreach_events` (code comment: "no tenant_id yet — Phase 3"), while `/kpis` does.
  Tenants 2 and 3 see tenant 1's outreach numbers.

## Tasks

- [x] 1. `/kpis`: `total_valid_emails` counts `ContactDetails` with
      `lower(validation_status)='valid'`, tenant-scoped, all-time (same shape as
      `total_contacts`, matching the donut). Drop the `EmailValidationResult` read.
- [x] 2. `/stats`: apply `tenant_filter` to the 4 outreach counts.
- [x] 3. `/trends`: apply `tenant_filter` to `daily_outreach`.
- [x] 4. `page.tsx:828`: `total_replied` → `emails_replied`.
- [x] 4b. **Added mid-implementation.** The Pipeline Funnel is fed by the same payload
      and was computing step-to-step conversion from `kpis.total_leads` (30d) into
      `kpis.total_contacts` (all-time) — on prod that rendered **7,295.5%**. Funnel now
      reads `/stats` end-to-end (all-time, tenant-scoped, one source for every step).
- [x] 5. `StatCard`: optional `subtitle` prop; label each KPI tile's window so
      "last 30 days" vs "all time" is visible instead of inferred.
- [x] 6. Integration tests in `backend/tests/integration/test_dashboard.py`:
      valid-emails counts contacts + is tenant-scoped; `/stats` and `/trends` outreach
      are tenant-scoped (two-tenant regression).
- [x] 7. Full backend suite green + frontend build/lint; update
      `CLAUDE_REFERENCE/api-endpoints.md` if it describes these metrics.

## Acceptance criteria
- Dashboard "Valid Emails" equals the `valid` slice of the validation donut on the same page.
- "Emails Sent" still reports the 30-day figure, but the tile says so.
- A tenant-2 user sees only tenant-2 outreach in `/stats` and `/trends`.
- "Replied" pill shows real reply count.
- Zero regressions in `cd backend && pytest`.

## Deliberately NOT in scope
- Re-plumbing `email_validation_results` (no `tenant_id`, no refresh-on-revalidate).
  The table stays as the raw provider-response log; it is no longer a KPI source.
- Unifying the funnel's mixed windows (Leads = 30d, Contacts = all-time) beyond labelling.
- The `dry_run` outreach run itself — that was an operator choice, not a code defect.

## Blockers / Notes
- Prod `EMAIL_VALIDATION_PROVIDER=mock`, so real validation has never run there.

## Verification (2026-09-14)

Backend suite: **1495 passed, 0 failed** (`cd backend && pytest`).
Frontend: `tsc --noEmit` clean, `npm run build` clean. (`npm run lint` skipped — ESLint was
never configured in this repo; `next lint` only offers to set it up.)

New queries replayed read-only against prod MySQL, tenant 1:

| Metric | Before | After |
|---|---|---|
| Valid Emails tile | 0 | **21,196** (exactly the donut's `valid` slice) |
| Emails Sent tile | 0 | 0 — truthful, last real send 2026-05-08; now labelled "Last 30 days" |
| Replied funnel pill | 0 (dead key) | **7** |
| Funnel step 1→2 | 7,295.5% | 116.9% |
| Tenant 2 `/stats` outreach | 54 sent (tenant 1's) | 70 skipped (its own) |

Funnel now reads 18,126 → 21,198 → 21,196 → 54 → 7. Contacts still exceed leads (116.9%)
— that is real fan-out, not a bug: the business rules allow up to 4 contacts per company
per job.
