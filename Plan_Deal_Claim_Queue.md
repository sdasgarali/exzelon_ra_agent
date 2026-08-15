# Plan — Deal Claim Queue (Unclaimed → Claim/Assign, Board/List, My Deals)

> Branch: `feature/deal-claim-queue`. Date: 2026-08-15.
> Decisions (confirmed):
> 1. **Separate claim + owner** — `claimed_by` (who pulled it from the queue; drives the
>    tag) is distinct from `owner_id` (admin-assigned owner). Unclaimed = claimed_by NULL.
> 2. **Forwarding = shared queue + in-app notification + email** to every BDM/Recruiter of
>    the tenant when an interested reply creates a new unclaimed deal.
> 3. **Reps claim, admins assign** — BDM/Recruiter claim unclaimed deals (and can release
>    their own); admin/super_admin assign/reassign owner to any rep at any stage.

## Model (Deal) — existing `owner_id` reused as the assigned owner
Add:
- `claimed_by_user_id` FK(users, nullable, index) — who claimed it. NULL = **Unclaimed**.
- `claimed_at` DateTime nullable.
- Age = derived from `created_at` (no column). Tag/queue state derived from `claimed_by_user_id`.
Idempotent lifespan migration (2 columns + indexes).

## Phase 1 — Backend model + serializer
- [ ] Deal model: add `claimed_by_user_id`, `claimed_at`. Migration in main.py.
- [ ] `deals.py::_deal_to_dict`: add `claimed_by` {id,name,initials}, `claimed_at`,
      `owner` {id,name,initials}, `age_days` (int, from created_at), `is_unclaimed` (bool).
- [ ] Helper `_initials(full_name)` → "RP".

## Phase 2 — Backend endpoints (claim/assign + filters + my)
- [ ] `POST /deals/{id}/claim` — reps (base_role bdm/recruiter) claim an **unclaimed** deal
      in their tenant → set claimed_by=self, claimed_at=now + DealActivity. 400 if already claimed.
- [ ] `POST /deals/{id}/unclaim` — the claimer OR an admin clears the claim.
- [ ] `POST /deals/{id}/assign` — admin/super_admin sets `owner_id` to a chosen rep (any
      BDM/Recruiter in tenant), any stage + DealActivity. `{user_id}` or null to unassign.
- [ ] `GET /deals` filters (all tenant-scoped): `stage_id`; `value_op`/`value_val`/`value_val2`
      + `probability_op`/`probability_val`/`probability_val2` (reuse `SIZE_OPERATORS` +
      `size_operator_clause`); `created_from`/`created_to`; `claimed_by` (=user_id, or
      `unclaimed`, or `me`); `search` (name); `mine=true` (claimed_by==me OR owner_id==me).
- [ ] Perms/isolation: reps see their tenant's deals; claim limited to reps; assign to admins.
- [ ] Tests: claim/unclaim/assign perms + tenant isolation; numeric/date/claimed_by/search
      filters; mine; unclaimed→claim→tag.

## Phase 3 — Forwarding (notify + email reps) on new unclaimed deal
- [ ] `services/deal_notifications.py::forward_new_deal_to_reps(db, deal, tenant_id)`:
      find active users whose effective base_role ∈ {bdm, recruiter} in the tenant →
      (a) one `NotificationEntry` each (category 'deal', priority 'high', link to the deal),
      (b) best-effort email each (reuse the transactional sender used by email verification).
      Gated by setting `deal_notify_reps_on_new` (default true). Best-effort, never blocks the sync.
- [ ] Call it from the interested-reply path (inbox_syncer) right after auto-create, only
      when a NEW deal was created (action == "created").
- [ ] Tests: creates a notification per rep; skips when disabled; doesn't notify admins.

## Phase 4 — Frontend Deals page (`/dashboard/deals`)
- [ ] Tabs: **Board View** (default — existing Kanban) + **List View** (new sortable table).
- [ ] Shared filter bar (both views): Status (stage) · Value (numeric op + value[/2]) ·
      Probability (numeric op) · Date Created (From–To) · Claimed By (reps + "Unclaimed" + "Me")
      · Search. Reuse the numeric-filter UI pattern from Leads.
- [ ] **Claim tag** component: red filled "Unclaimed" pill, OR green filled initials avatar
      (hover → full name tooltip). On board cards + list rows.
- [ ] **Age badge**: yellow filled "N Days" (days since created), live.
- [ ] Actions: **Claim** button (reps, on unclaimed) · **Assign** control (admins → pick a rep).
- [ ] Deal detail view: add Claimed By, Claimed At, Assigned Owner, Age + existing fields.

## Phase 5 — Dashboard "My Deals" / "My Queue"
- [ ] Section on `/dashboard` for BDM/Recruiter: their claimed + assigned deals
      (`GET /deals?mine=true`), with the same claim tag + age badge, linking into the deal.

## Phase 6 — Tests + docs + deploy
- [ ] Full backend suite + frontend tsc/build/jest green.
- [ ] Update CLAUDE_REFERENCE (data-models/services/api-endpoints) + memory.
- [ ] PR → deploy (migration: 2 columns). Verify claim/assign + notifications on prod.

## Risks / notes
- **Email fan-out volume**: every interested reply emails all reps → could be noisy on busy
  tenants. Mitigate: `deal_notify_reps_on_new` setting to disable email while keeping in-app.
- **Custom roles**: reps = users whose base_role resolves to bdm/recruiter (built-ins direct;
  custom roles via role_registry). Admin/super_admin excluded from the rep queue.
- Deal automation toggles are still global settings (pre-existing) — the new
  `deal_notify_reps_on_new` follows the same convention.
