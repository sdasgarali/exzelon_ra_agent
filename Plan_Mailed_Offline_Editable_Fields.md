# Plan — Editable Mailing-Status / Response / Campaign-ID for Mailed-Offline leads (bulk update)

## Context
The three columns are **derived/read-only**. For leads mailed manually **offline** (Mailing-Status =
`Mailed-Offline` = downloaded_at set + no non-archived campaign), RAs need to record mailing progress,
the reply outcome, and campaign membership by hand. Add editability in the existing **Bulk Update**
modal, scoped to Mailed-Offline leads.

## Decisions (confirmed)
- **Mailing-Status** → new override column; options: `Not-Mailed, Mailed-Offline, Follow-Up-Sent, Bounced, No-Valid-Email`.
- **Response** → new override column; options: `Interested, Referral, Question, Not-Interested, Do-Not-Contact, OOO, Other`.
- **Campaign-ID** → **real enrollment** (reuse `services.campaign_engine.enroll_contacts`), not an override.
- **Scope** → apply only to selected leads currently `Mailed-Offline`; skip others; report updated vs skipped.
- Override **wins** over the derived value everywhere (display, export, filter, sort). Clearing (empty) reverts to derived.

## Storage — `LeadDetails` (backend/app/db/models/lead.py) + lifespan migration (main.py)
- `mailing_status_override VARCHAR(50) NULL`
- `response_status_override VARCHAR(50) NULL`
- Idempotent `ALTER TABLE lead_details ADD COLUMN ...` blocks in `main.py` lifespan (mirror the `downloaded_at`/`data_type` blocks).
- No campaign_id override (enrollment is real).

## Constants (leads.py, near the label helpers)
- `MAILING_STATUS_OVERRIDE_OPTIONS`, `RESPONSE_STATUS_OVERRIDE_OPTIONS` (single source; also used to validate).
- `_MAILING_SORT_ORDINAL`: Campaign-Active0 Paused1 Draft2 Closed3 Mailed-Offline4 Follow-Up-Sent5 Bounced6 No-Valid-Email7 Not-Mailed8.
- Response override label → same 0–6 ordinals as the reply categories.

## Backend — endpoint (extend `PUT /leads/bulk/update`, leads.py ~2232)
Accept optional `mailing_status_override`, `response_status_override`, `enroll_campaign_id` alongside `data_type`.
- `data_type` stays global (all selected). The three new fields apply **only** to the Mailed-Offline subset.
- Eligibility per lead: `downloaded_at IS NOT NULL` AND lead has **no** non-archived campaign enrollment (batch query campaign_contacts→campaigns).
- Validate override values against the option constants (400 on invalid).
- Enrollment: gather the eligible lead's contacts (junction + legacy FK) → `campaign_engine.enroll_contacts(campaign_id, contact_ids, db)`; validate campaign belongs to tenant.
- Audit each changed lead; return `{updated_count, skipped_count, enrolled_count, message}`.
- RBAC unchanged (super_admin, matches existing endpoint).

## Backend — override-aware everywhere (WYSIWYG, matches the sort/filter we just shipped)
- **Schema** (schemas/lead.py): add `mailing_status_override`, `response_status_override` to `LeadResponse` (for prefill/UI).
- **list_leads / export**: effective value = `override or <derived label>` for both columns.
- **Filter** (`_apply_lead_filters`): for each label, match `override == L` OR (`override IS NULL` AND derived==L); override-only labels match `override == L`; Campaign-*/auto labels require `override IS NULL`. Add the 3 new mailing labels to the filter option list.
- **Sort**: prepend override cases to the mailing/response ordinal `case()` (override wins), using the ordinal maps.

## Frontend — `frontend/src/app/dashboard/leads/page.tsx`
- Extend the existing **Bulk Update** modal (`showBulkUpdateModal`) with a "Mailed-Offline fields" section:
  - Mailing-Status `<select>` (override options + blank = leave unchanged), Response `<select>`, Campaign `<select>` (tenant campaigns; blank = none).
  - Show a hint: these apply only to selected leads that are Mailed-Offline.
- `handleBulkUpdate` sends the new fields; on success show `Updated N, skipped M`.
- Badge maps: add colors for the 3 new mailing labels + filter options list.
- Fetch campaigns for the dropdown (reuse existing campaigns API if already loaded; else add a light fetch).

## Tests
- Unit: override wins in `mailing_status_label`/`response_status_label` effective helpers (or the coalescing).
- Integration (test_leads.py): bulk endpoint sets overrides only on Mailed-Offline leads + skips others; invalid value → 400; enroll_campaign_id creates campaign_contacts + flips derived; list/export/filter/sort reflect the override.
- Run `pytest tests/integration/test_leads.py`, frontend `tsc --noEmit`.

## Verify
Run app; select Mailed-Offline leads → Bulk Update → set each field → confirm the table + CSV reflect the override, filter/sort by them work, and a mixed selection reports skips.
