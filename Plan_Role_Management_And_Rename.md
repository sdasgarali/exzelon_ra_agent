# Plan — Role Management (custom roles) + Rename Operator→BDM, Viewer→Recruiter

> Branch: `feature/role-management-and-rename`
> Owner: Senior Dev. Date: 2026-08-13.
> Decisions (confirmed by user): **Full internal rename** of the enum values
> (operator→bdm, viewer→recruiter) everywhere; **settings-backed custom roles**
> with a dynamic registry, enforced via the existing module-permission engine,
> built-ins protected. Constraint: **no impact to existing functionality.**

---

## 0. Current state (verified)

- `UserRole(str, PyEnum)` in `backend/app/db/models/user.py`: `super_admin, admin,
  operator, viewer`. Column `users.role` is a **MySQL ENUM** (`values_callable`).
- `require_role(allowed: List[UserRole])` in `api/deps/auth.py`: super_admin
  bypasses; else `current_user.role not in allowed` → 403. `current_user.role` is a
  `UserRole` enum instance.
- Module-permission engine (`get_module_permission`, `require_module_permission`,
  `require_module_tab_permission`, settings-tab perms) reads the per-tenant
  `role_permissions` setting keyed by `user.role.value`. Custom roles work here **iff**
  they have a matrix row.
- Sizing: `UserRole.OPERATOR` ×97, `UserRole.VIEWER` ×6, `.role.value` ×11,
  `'operator'`/`'viewer'` string literals 3+5, `role: UserRole` in `schemas/user.py` ×2.
- Frontend role sites (9): `roles/page.tsx`, `layout.tsx`, `users/page.tsx`,
  `tenants/page.tsx`, `activity-log/page.tsx`, `dashboard/page.tsx`, `lib/store.ts`,
  `lib/__tests__/store.test.ts`, `types/api.ts`.
  **EXCLUDE** `excel-text-filter.tsx` + `size-filter.tsx` — "operator" there = filter
  operator, not a role.

### Core architectural decision
Custom roles must be assignable to users → `users.role` must move from **ENUM →
VARCHAR(50)**. Because `UserRole` subclasses `str`, existing comparisons
(`role == UserRole.X`, `role in [UserRole...]`) keep working when `role` is a plain
str. Only `user.role.value` (11 sites) must become `user.role` (already a str).

### Custom-role enforcement bridge (keeps risk bounded)
Every custom role declares a **`base_role`** (one of the 4 built-ins). For coarse
`require_role([...])` checks and nav, a custom role resolves to its base_role. The
fine-grained `role_permissions` matrix can further restrict per module. This makes
custom roles functional across ALL endpoints without rewriting the ~25 files that
still use `require_role` (the incomplete-matrix-adoption gap in RBAC_Enforcement_Scope.md).

---

## 1. Immediate TODO (phased)

### Phase 1 — Backend rename operator→bdm, viewer→recruiter (enum member+value)
- [ ] `UserRole`: `OPERATOR="operator"`→`BDM="bdm"`, `VIEWER="viewer"`→`RECRUITER="recruiter"`.
- [ ] Global replace `UserRole.OPERATOR`→`UserRole.BDM` (97), `UserRole.VIEWER`→`UserRole.RECRUITER` (6).
- [ ] Review 3×`'operator'` + 5×`'viewer'` string literals + any seed/demo users.
- [ ] **Legacy alias** in `get_current_user`: map a role read as `operator`→`bdm`,
      `viewer`→`recruiter` (JWT claims + DB) so old access/refresh tokens keep working
      through the 7-day refresh window. Central `LEGACY_ROLE_ALIASES` dict.
- [ ] `role_permissions` loader (backend + frontend): alias old keys operator→bdm,
      viewer→recruiter so saved per-tenant matrices don't lose their config.
- [ ] Commit.

### Phase 2 — DB column ENUM→VARCHAR + role registry (custom roles backend)
- [ ] Idempotent lifespan migration in `main.py`:
      (a) ALTER users.role ENUM to superset (add bdm,recruiter),
      (b) `UPDATE users SET role='bdm' WHERE role='operator'` and viewer→recruiter,
      (c) `MODIFY users.role VARCHAR(50) NOT NULL DEFAULT 'recruiter'`. Guarded/idempotent.
- [ ] Model: `role = Column(String(50), default=UserRole.RECRUITER.value, nullable=False)`.
- [ ] Fix the 11 `.role.value` sites → `.role` (now str); add a small `role_str(user)`
      helper if any path may still hold an enum.
- [ ] `schemas/user.py`: `role: UserRole` → `role: str` with a validator that accepts
      any registered role key (built-in or custom).
- [ ] NEW `services/role_registry.py`: `list_roles(db, tenant_id)` = built-ins + custom
      (per-tenant setting `custom_roles` = `[{key,label,description,base_role}]`);
      `get_role(key)`, `resolve_base_role(key)`, `is_builtin(key)`, validation +
      lockout guards (can't delete a role in use; can't delete/rename built-ins' keys).
- [ ] `require_role` + module-permission engine: resolve custom role → base_role for
      enum checks; matrix lookups use the raw role key.
- [ ] NEW endpoints `api/endpoints/roles.py` (super_admin only): `GET /roles`,
      `POST /roles`, `PUT /roles/{key}`, `DELETE /roles/{key}`. Register in router +
      `api-endpoints.md`. On create, seed the new role's `role_permissions` row from base.
- [ ] Commit.

### Phase 3 — Frontend rename + Role Management tab
- [ ] Central role source: load roles from `GET /roles` (fallback to built-ins);
      dynamic `ROLES` in `roles/page.tsx` (matrix renders a column per role).
- [ ] Rename labels operator→**BDM**, viewer→**Recruiter** in: layout nav `roles:[...]`,
      users page (assign-role dropdown + display), tenants page, activity-log, dashboard,
      store.ts, types/api.ts. Keep internal keys = new enum values `bdm`/`recruiter`.
- [ ] Tabbed roles page: **Permissions Matrix** (existing) + **Role Management** (new):
      table of roles (Built-in/Custom badge), **Add Role** (label, description, base role),
      **Edit** (label/description; base_role for custom), **Delete** (custom only; blocked
      if users assigned). Wire to `rolesApi`.
- [ ] Responsive (mobile cards + desktop table), a11y, matches existing page styling.
- [ ] Commit.

### Phase 4 — Tests + docs + deploy
- [ ] Backend: rename regression (old refs gone), legacy-alias login, VARCHAR column,
      role CRUD (create/edit/delete, built-in protection, in-use delete block, base_role
      enforcement), matrix keyed by custom role, multi-tenant isolation of custom_roles.
- [ ] Frontend: roles page tabs + Role Management CRUD; label renders BDM/Recruiter;
      store/type tests updated.
- [ ] Full backend `pytest` + frontend `jest` green; lint + typecheck.
- [ ] Update `CLAUDE.md` business rules, `CLAUDE_REFERENCE/data-models.md`,
      `api-endpoints.md`, `roles-permissions` reference, memory index.
- [ ] PR → review → merge → deploy to VPS → verify `/health` + a login of each role.

---

## 2. Risk register / guardrails
1. **Live prod users** currently have role `operator`/`viewer` → migration UPDATE must
   run before the ENUM is narrowed/column retyped; idempotent + ordered.
2. **Active JWTs** carry old role strings → legacy alias keeps them valid until refresh.
3. **Super-admin-only modules** (users/roles/tenants/activity_log) must never be
   openable by a custom role → keep `require_role([SUPER_ADMIN])` + `superAdminOnly`.
4. **Lockout prevention**: custom role can't be granted the `roles` module; built-ins'
   keys immutable; can't delete a role assigned to any user.
5. **Per-tenant** custom_roles + role_permissions (matches today). Super-admin custom
   roles are global-default; document behavior.
6. **No drive-by**: do NOT touch filter-operator code (`excel-text-filter`, `size-filter`).

## 3. SESSION_CONTEXT_RETRIEVAL
> Phased plan written. Branch `feature/role-management-and-rename` created. Awaiting
> go-ahead to start Phase 1 (backend rename). Nothing coded yet.
