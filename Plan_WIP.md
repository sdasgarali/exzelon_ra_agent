# Plan WIP

## SESSION_CONTEXT_RETRIEVAL
> Branch `feature/role-management-and-rename`. Building: (1) full internal rename
> of RBAC roles operator→bdm, viewer→recruiter; (2) settings-backed CUSTOM roles
> with a "Role Management" tab on /dashboard/roles. Full plan +checkboxes in
> `Plan_Role_Management_And_Rename.md`.
>
> STATUS (2026-08-13):
> - Phase 1 (backend rename) COMMITTED (3dc642e). 62 role tests green.
> - Phase 2 (ENUM→VARCHAR migration + role_registry.py + roles.py CRUD API +
>   auth base_role bridge) IMPLEMENTED. 13 new roles tests green; 57-test role
>   subset green. Full backend suite RUNNING to confirm zero regressions, THEN
>   commit Phase 2.
> - Phase 3 (frontend rename + Role Management UI) NOT STARTED. Frontend role
>   VALUE refs (layout nav roles:[...], user.role!=='viewer', store.ts type,
>   users/tenants/activity-log dropdowns+color maps) MUST change operator→bdm,
>   viewer→recruiter or BDM/Recruiter users lose nav access. roles/page.tsx to be
>   reworked to load roles from GET /roles + add Role Management CRUD tab.
> - Phase 4 (tests+docs+deploy) NOT STARTED.
> NOTE: do NOT touch filter-operator code (excel-text-filter.tsx, size-filter.tsx,
> query_helpers SIZE_OPERATORS) — "operator" there is a filter op, not a role.

## Immediate TODO
- [x] Phase 1 — backend rename (3dc642e)
- [x] Phase 2 — ENUM→VARCHAR + role_registry + /roles API (93e3413)
- [x] Phase 3 — frontend rename + Role Management tab (0cddad0)
- [x] Phase 4 — tests + docs (3a8c2fa). Backend 1334 pass, frontend 70 pass, build OK.
- [x] Pushed + PR #81 opened. CI pending.
- [ ] AWAITING USER: merge + deploy to prod (runs the ENUM→VARCHAR migration on live DB).

## Blockers / Notes
- Legacy JWT/DB values normalized via LEGACY_ROLE_ALIASES + role_value() in
  api/deps/auth.py. Custom roles inherit a built-in base_role for coarse
  require_role checks + matrix fallback.
