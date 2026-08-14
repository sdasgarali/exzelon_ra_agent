# Plan — RA-only auto-send + Mailbox↔User interconnection

> Branch: `feature/ra-autosend-mailbox-user`. Date: 2026-08-14.
> Decisions (confirmed):
> 1. **Auto-send gating** via a boolean `auto_outbound` flag on `OutreachRole`
>    (RA=true by default; configurable). Only mailboxes whose role has the flag are
>    auto-selected; non-flag mailboxes are usable ONLY when explicitly assigned to a
>    campaign (manual). 
> 2. **Non-RA mailbox → login user**: create-or-link a `User` (email=mailbox email),
>    RBAC role mapped from the outreach role (BDM→bdm, Recruiter→recruiter,
>    Admin→admin, else recruiter). `SenderMailbox.user_id` FK.
> 3. **Login password separate** from SMTP/OAuth send creds. RA mailboxes = no login
>    user, send via their configured SMTP/OAuth as today.
> 4. Users module → "Add as mailbox" (prefilled email → test connectivity → warm-up).

## Conceptual model
- **Automated sender (RA)** = `auto_outbound` role → auto-selected for cold outbound,
  NO login user (machine mailbox).
- **Personal mailbox (BDM/Recruiter/Admin/…)** = non-`auto_outbound` role → NOT
  auto-selected (manual/explicit only), linked 1:1 to a login `User`.
  (auto_outbound ⟺ machine/no-login; documented coupling.)

## Current state (verified)
- `OutreachRole` (per-tenant): RA/BDM/Recruiter seeded in `main.py::_seed_outreach_roles`.
  New mailboxes already default to RA.
- Auto-selection (`services/mailbox_selector.py::select_best_mailbox` +
  `campaign_engine.py::_select_mailbox`) filters health/warmup/limits but NOT role →
  today ALL eligible mailboxes auto-send. THIS is the gap.
- `SenderMailbox` has NO user link today.

## Phase 1 — Backend: auto_outbound gating (core value, self-contained)
- [ ] `OutreachRole.auto_outbound = Column(Boolean, default=False)`. Migration in
      `main.py` lifespan (add column) + set RA rows `auto_outbound=1`. Seed new RA true.
- [ ] `mailbox_selector.select_best_mailbox`: when NOT restricted to explicit
      `campaign_mailbox_ids`, join OutreachRole + filter `auto_outbound==True`.
- [ ] `campaign_engine._select_mailbox`: same gate on the auto path; explicit campaign
      mailbox assignment bypasses (manual).
- [ ] `outreach_roles` API: expose + allow toggling `auto_outbound` (GET/POST/PUT).
- [ ] Tests: only auto_outbound mailboxes auto-picked; explicit assignment still works.

## Phase 2 — Backend: Mailbox↔User link
- [ ] `SenderMailbox.user_id = FK(users.user_id, nullable, index)`. Migration.
- [ ] Helper `map_outreach_role_to_rbac(role_name) -> UserRole`.
- [ ] `create_mailbox`: role required. If role.auto_outbound → no user. Else require
      `login_password`; create-or-link `User(email, role=mapped, password, tenant)`;
      set `mailbox.user_id`. Send creds unchanged.
- [ ] `POST /users/{id}/mailbox` (or mailbox create with user_id): add a user's email as
      a linked mailbox (role mapped from user's RBAC role → non-auto_outbound role).
- [ ] Schemas: `login_password`, `full_name`, `user_id` on mailbox create/response.
- [ ] Tests: non-RA create makes/links user + role map; RA create makes no user;
      duplicate-email handling; user "add as mailbox".

## Phase 3 — Frontend
- [ ] Add-mailbox wizard: Role as first required question; conditional Login-password
      (+ name) for non-RA with helper text; hidden for RA.
- [ ] Outreach Roles screen: `auto_outbound` toggle per role (+ "Auto cold-send" badge).
- [ ] Mailbox list: show linked user / login badge.
- [ ] Users page: "Add as mailbox" action → mailbox setup (prefilled) → test
      connectivity + manual warm-up status.

## Phase 4 — Tests + docs + deploy
- [ ] Full backend + frontend suites green; isolation + deliverability guardian review.
- [ ] Update CLAUDE_REFERENCE (services/data-models/api-endpoints) + memory.
- [ ] PR → (confirm) merge + deploy (migration: add 2 columns + RA flag backfill).

## Risks
- Deliverability: gating to RA-only reduces the auto pool — confirm enough RA mailboxes
  are warmed or automation stalls. Surface a clear "no eligible RA mailbox" reason.
- Don't break existing campaigns that rely on any-mailbox auto-select: explicit campaign
  mailbox assignment must still bypass the gate.
- User/mailbox email uniqueness: mailbox email is globally unique; a linked user shares it.
