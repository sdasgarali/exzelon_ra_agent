# Plan WIP

## SESSION_CONTEXT_RETRIEVAL
> DONE + DEPLOYED (2026-08-14): RBAC role rename (operator→bdm, viewer→recruiter)
> + settings-backed CUSTOM roles + "Role Management" tab. PR #81 squash-merged to
> master (c5d3588) and deployed to prod. Migration verified: users.role
> enum→varchar(50); operator=7→bdm, viewer=3→recruiter, 0 legacy rows (15 users).
> Full detail + gotchas in `Plan_Role_Management_And_Rename.md` and memory
> `role-rename-and-custom-roles.md`. Nothing outstanding for this task.

## Completed
- [x] Phase 1 — backend rename (3dc642e)
- [x] Phase 2 — ENUM→VARCHAR + role_registry + /roles API (93e3413)
- [x] Phase 3 — frontend rename + Role Management tab (0cddad0)
- [x] Phase 4 — tests + docs (3a8c2fa); backend 1334 pass, frontend 70 pass, build OK
- [x] PR #81 merged (c5d3588) + deployed to prod + migration verified

## Blockers / Notes
- Deploy gotcha: `git add backend/` in Phase 1 swept 5 pre-existing untracked
  helper files into the commit; VPS `git pull` aborted on untracked
  backfill_lob_configs.py → moved VPS copy to /root/*.vps_untracked_bak_* + redeployed.
  Next time stage explicit paths when untracked files are present.
- Pre-migration users backup: VPS `/root/users_backup_pre_rolerename_*.sql`.
