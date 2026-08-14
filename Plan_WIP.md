# Plan WIP

## SESSION_CONTEXT_RETRIEVAL
> Branch `feature/ra-autosend-mailbox-user`. Feature: (1) only "RA" (auto_outbound)
> mailboxes auto-send cold outbound; others manual-only; (2) non-RA mailbox add asks a
> role + login password → creates/links a login User (mailbox↔user interconnected); RA =
> no login; (3) Users module → "Add as mailbox". Full plan in
> `Plan_RA_AutoSend_And_Mailbox_User_Link.md`.
>
> STATUS (2026-08-14):
> - Phase 1 (auto_outbound gating) COMMITTED 0df7bb4. Backend 1358 pass.
> - Phase 2 (SenderMailbox.user_id + create-or-link user) COMMITTED 1c9a7ed.
> - Phase 3 (frontend) IN PROGRESS: mailboxes wizard login-password (conditional on
>   non-auto_outbound role) + outreach-role auto_outbound toggle + Users "Add as mailbox"
>   deep-link (?add_email=). tsc clean, jest 70 pass. Build running → then commit.
> - Phase 4 (docs + deliverability review + PR + deploy) NOT STARTED.
>
> Earlier this session (all SHIPPED to prod): role rename+custom roles (PR #81),
> user-tenant binding (PR #82), cleaned 7 E2E prod users.

## Immediate TODO
- [x] Phase 1 — auto_outbound gating (0df7bb4)
- [x] Phase 2 — mailbox↔user link (1c9a7ed)
- [ ] Phase 3 — frontend (commit after build green)
- [ ] Phase 4 — docs + deliverability-guardian review + PR + deploy (migration: 2 cols + RA flag)

## Blockers / Notes
- Deploy migration adds outreach_roles.auto_outbound (RA=1) + sender_mailboxes.user_id.
- Gate only applies to the AUTOMATED pool; explicit campaign mailbox assignment bypasses.
