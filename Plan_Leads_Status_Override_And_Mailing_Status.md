# Plan — Leads: Admin Status-Override + Mailing-Status & Campaign-ID columns

## SESSION_CONTEXT_RETRIEVAL
> Building 3 leads-page enhancements: (1) admin/super-admin can override a blocked
> lead status transition after a confirm popup; (2) new "Mailing-Status" column
> (Campaign-Draft/Active/Paused/Closed, Mailed-Offline, Not-Mailed); (3) new
> "Campaign-ID" column. Exploration complete. Awaiting approval on the Status-column
> behavior decision, then implement.

## Context / Findings (verified in code)
- Transition rules: `backend/app/core/state_machine.py` — `HUNTING` only allows
  `sent, closed_hired, closed_not_hired, closed_test`. Enforced in
  `leads.py::update_lead` (line ~2456) → HTTP 400 "Cannot transition…".
- Lead↔Campaign link: `campaign_contacts.lead_id → campaigns.campaign_id`. Campaign
  has `.status` (draft/active/paused/completed/archived) + `.is_archived`.
- `list_leads` (leads.py ~422) **already** builds `campaign_status_map` per lead
  (picks highest-priority active>paused>draft>completed, archived campaigns excluded)
  and sets `lead_dict['campaign_status']`. It does NOT expose `campaign_id`.
- Download flag = `lead_details.downloaded_at` (DateTime, nullable). Yes ⟺ not null.
- **Latent bug**: `LeadResponse` schema (schemas/lead.py) has NO `campaign_status`
  field and no `extra=allow` → FastAPI `response_model` strips it. So `campaign_status`
  currently never reaches the frontend. Adding fields to the schema fixes this.
- Roles: frontend `useAuthStore().isAdmin()` = admin|super_admin. Backend
  `UserRole.ADMIN` / `UserRole.SUPER_ADMIN` on `current_user.role`.
- Frontend leads table headers ~1500-1585; Status cell ~1737-1758; `baseColCount=17`
  (leads/page.tsx:961). Status cell today shows a read-only campaign badge when
  enrolled, else the pipeline dropdown.

## Mailing-Status derivation (single source of truth)
```
campaign_status == 'active'    -> "Campaign-Active"
campaign_status == 'paused'    -> "Campaign-Paused"
campaign_status == 'draft'     -> "Campaign-Draft"
campaign_status == 'completed' -> "Campaign-Closed"
else if downloaded_at not null -> "Mailed-Offline"
else                           -> "Not-Mailed"
```

## Tasks

### Backend
- [ ] 1. `schemas/lead.py`: add to `LeadResponse` — `campaign_status: Optional[str]=None`,
      `campaign_id: Optional[int]=None`, `mailing_status: Optional[str]=None`.
- [ ] 2. `leads.py::update_lead`: add `force: bool = Query(False, ...)`. Bypass
      `validate_transition` only when `force and current_user.role in (ADMIN, SUPER_ADMIN)`.
      Record `forced_transition: true` in the audit `changes` when bypassed. Non-admin
      `force` is ignored (normal validation still applies).
- [ ] 3. `leads.py::list_leads`: extend the campaign batch query to also capture
      `campaign_id` (keep same priority pick) → `campaign_id_map`. Add module-level
      helper `mailing_status_label(campaign_status, downloaded_at)`. Set
      `lead_dict['campaign_id']` and `lead_dict['mailing_status']`.
- [ ] 4. `leads.py` single-lead `GET /{lead_id}` + `/{lead_id}/detail`: set the same
      three fields so the lead-detail page stays consistent (compute campaign map for one id).
- [ ] 5. CSV export (`export/csv`): add "Mailing Status" + "Campaign ID" columns
      (WYSIWYG parity). Build campaign maps per batch; append to `lead_row` (+2 cols;
      bump the empty-contact filler from 13 to match new header count offset). Update header row.
- [ ] 6. Unit tests: `test_state_machine`/leads — forced transition bypass (admin) +
      rejected for non-admin; `mailing_status_label` mapping table.

### Frontend (`leads/page.tsx` + `lib/api.ts`)
- [ ] 7. `lib/api.ts` `leadsApi.update`: accept optional `force` → send as
      `?force=true` query param (`api.put('/leads/${id}', data, { params: force?{force:true}:{} })`).
- [ ] 8. `Lead` interface: add `campaign_id?: number|null`, `mailing_status?: string|null`.
- [ ] 9. `updateLeadStatus`: on 400 "Cannot transition" error → if `isAdmin()` →
      `window.confirm("<server detail> — Still want to continue? (Admin override)")`;
      if confirmed retry with `force:true`; on success update local state. Non-admin:
      show the error as today.
- [ ] 10. Add "Mailing-Status" column (read-only badge, reuse STATUS_OPTIONS colors)
      and "Campaign-ID" column (shows `#<id>` linking to campaign, or `-`). Add `<th>`
      headers + `<td>` cells. Bump `baseColCount` 17 → 19.
- [x] 11. Status column: **DECISION = B (keep current behavior)** — read-only campaign
      badge when enrolled, dropdown otherwise. New columns are purely additive.
- [ ] 12. Frontend test updates if snapshot/column-count assertions exist.

## DECISION NEEDED (Status column behavior)
Now that campaign/mailing state has its own column, should the existing "Status"
column always show the editable pipeline dropdown (even for campaign-enrolled leads)?
- **A (recommended):** Yes — Status = pipeline dropdown always. Mailing state lives in
  the new column. Also lets admins change status of enrolled leads (with override).
- **B:** No — keep current behavior (read-only badge when enrolled). New columns are
  purely additive; enrolled leads still can't have pipeline status changed inline.

## Acceptance criteria
- Admin/super-admin on lead #21665 (hunting) can pick "Enriched" → sees confirm popup
  with the exact server message → on OK, status changes to Enriched. Operator/viewer:
  no override, error shown.
- Mailing-Status column shows correct label for: draft/active/paused/completed campaign
  leads, downloaded-but-no-campaign (Mailed-Offline), and everything else (Not-Mailed).
- Campaign-ID column shows the associated campaign id (or `-`).
- CSV export includes both new columns matching the on-screen values.
- `pytest -m unit` + frontend `npm test` + `npm run build` green.

## Git
- Branch: `feature/leads-status-override-mailing-status`. Small commits per task group.
