# Plan — Redesign Edit/Add Mailbox (3 sections)

## SESSION_CONTEXT_RETRIEVAL
> Restructure the Edit Mailbox modal (and the Add wizard's final step) into three
> sections — Sender Profile, Email Signature, Outreach Profile — per the spec below.
> File: `frontend/src/app/dashboard/mailboxes/page.tsx` (+ backend model/schema/render).

## Confirmed decisions (stakeholder)
1. **Phone** → new dedicated `phone` column on `sender_mailboxes` (US-format validated); auto-fills the signature phone.
2. **Email Signature** → view-only by default; a pencil/edit icon unlocks fields; an in-section **Save** persists immediately (own API call), then returns to view-only.
3. **Scope** → apply the new sectioned layout to **both** the Add wizard and the Edit modal.
4. **Signature "Title / Role"** → derived (read-only) from the selected Role's `description` (fallback to `role_name` if empty); updates when the Role changes.

## Target layout (both modals)
**Header:** `Email Address *` (identity; stays at top).

**Section 1 — Sender Profile**
- `First Name *`, `Last Name *`
- `Phone Number *` — US format `(555) 123-4567`, masked + validated
- `Role *` — renamed from "Outreach Role"; dropdown + "Manage Roles"
- `LinkedIn Profile URL` (optional)
- `Active` (checkbox)
- `Notes` (textarea)

**Section 2 — Email Signature** (was "Sender Profile & Email Signature")
- Default **view-only**: renders the signature as **HTML** including the **tenant website logo** (`<img>` from `tenant.logo_url`) at the top.
- Auto-populated fields (source):
  - Sender Name ← First + Last
  - Title / Role ← selected Role's `description` (read-only)
  - Phone ← Sender Profile phone
  - Email ← mailbox email
  - Company ← `tenant.name`
  - Website ← `tenant.website`
  - Address ← `tenant.company_address`
  - Logo ← `tenant.logo_url` (always shown)
- **Edit icon (top-right)** → fields become editable → **Save** (immediate PATCH of `email_signature_json` + `phone`) / **Cancel** → back to view-only.
- Preview is **always HTML** and **sanitized with DOMPurify** before injection (signature fields are user-editable → prevent XSS).

**Section 3 — Outreach Profile**
- `Provider`, `Authentication Method` (+ password / Microsoft OAuth2 / SMTP+IMAP hosts as today), `Warmup Status` (read-only, managed by engine), `Daily Send Limit`.

## Backend tasks
1. **Model** `db/models/sender_mailbox.py`: add `phone = Column(String(32), nullable=True)`.
2. **Migration**: idempotent `ALTER TABLE sender_mailboxes ADD COLUMN phone ...` in `main.py` lifespan (nullable → safe for existing rows; no backfill).
3. **Schema** `schemas/sender_mailbox.py`: add `phone: Optional[str]` to Base / Update / Response; add a US-phone normalizer/validator (accepts common inputs, stores `(NNN) NNN-NNNN`; blank allowed at API level — the **UI** enforces required).
4. **Signature render** `services/pipelines/outreach.py::render_signature_html`: emit a logo `<img>` when the signature JSON carries `logo_url`; keep element order (logo → name → title/role → company → phone|email → website → address) consistent with the UI preview.
5. Confirm the update endpoint (`api/endpoints/mailboxes.py`) passes `phone` through (schema-driven; add if it maps fields explicitly).

## Frontend tasks (`mailboxes/page.tsx`)
1. Add `phone` to `formData`; add `logo_url` to `sigData`; update `autoPopulateSigData` (title ← role description, phone ← formData.phone, logo ← tenant.logo_url).
2. Rebuild the **Edit** modal body into the 3 sections above; mirror the same into the **Add** wizard's review/step.
3. Sender Profile: mark First/Last/Phone/Role required; add a US phone mask + validation helper; block submit with a clear message if missing/invalid.
4. Email Signature: view/edit toggle with pencil icon; view mode renders sanitized HTML (logo + fields); edit mode shows inputs + inline **Save**/**Cancel**; Save calls the mailbox update API with just `{ email_signature_json, phone }`.
5. Client-side HTML signature builder that mirrors the backend `render_signature_html` (incl. logo); output is sanitized (DOMPurify) before rendering in the preview.
6. When Role changes, recompute the derived Title/Role in the signature.
7. Add `dompurify` dependency (frontend) for safe HTML rendering.

## Tests
- **Backend**: schema accepts/normalizes `phone`; `render_signature_html` includes the logo when `logo_url` present; migration is idempotent.
- **Frontend**: existing mailbox tests still green; add a focused test for required-field gating + US phone validation if the test harness allows.

## Backfill (approved — one-time, prod)
- Script `backend/scripts/backfill_mailbox_phone_role.py` (idempotent, `--dry-run`, `--commit`):
  - Blank/NULL `phone` → the mailbox's own `tenant.phone`, falling back to **Tenant 1's phone** (the default).
  - NULL `outreach_role_id` → that tenant's role named **"RA"** (create per-tenant if missing? — no; if a tenant has no "RA" role, log & skip, fall back to Tenant 1's "RA" only for tenant-1 rows).
  - Report counts; warn if Tenant 1 has no phone or no "RA" role.
- Run once after deploy (not wired into startup).

## Rollout / risk
- Column is additive + nullable → migration is safe; existing 1,000+ mailboxes keep working. Phone/Role show as empty and must be filled on the next edit (UI-required). Backend stays lenient so imports/bulk-add don't break.
- No change to send logic beyond the signature logo.

## Task checklist
- [ ] 1. Model + migration (`phone`)
- [ ] 2. Schema `phone` + US validator
- [ ] 3. `render_signature_html` logo
- [ ] 4. Frontend state + autopopulate (phone, logo, derived title)
- [ ] 5. Edit modal — 3 sections
- [ ] 6. Add wizard — 3 sections
- [ ] 7. Email Signature view/edit/inline-save + sanitized HTML preview + logo
- [ ] 8. Required-field + US-phone validation
- [ ] 9. Tests (backend + frontend) + typecheck
- [ ] 10. PR + (on approval) deploy
