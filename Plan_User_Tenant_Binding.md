# Plan — Bind users to tenants + Tenant dropdown in Add/Edit User

> Branch: `feature/user-tenant-binding`. Date: 2026-08-14.
> Decisions (confirmed): ONE tenant per user (single FK). Super_admin is global
> (tenant_id=NULL) and picks the target tenant when creating/editing a user;
> regular tenant admins are LOCKED to their own tenant (no dropdown, cannot move
> users). Fixes the isolation leak + the missing tenant assignment.

## Bugs being fixed (backend/app/api/endpoints/users.py)
- `create_user` never set `tenant_id` → Users-page users were orphaned (NULL tenant).
- `list_users`/`get_user`/`update_user`/`delete_user` had NO tenant filter → a tenant
  admin could see/edit/delete users of OTHER tenants (isolation leak).

## Backend
- [ ] `schemas/user.py`: add `tenant_id: Optional[int]` to `UserCreate` + `UserUpdate`.
- [ ] `create_user`: resolve target tenant —
      super_admin: role==super_admin → tenant_id NULL; else require+validate `tenant_id`.
      regular admin: force `current_user.tenant_id` (ignore body tenant_id).
- [ ] `list_users`: non-super_admin → filter `User.tenant_id == current_user.tenant_id`;
      super_admin → optional `tenant_id` query filter (see all by default).
- [ ] `get_user`/`update_user`/`delete_user`: non-super_admin can only touch users in
      their own tenant (else 404). super_admin any.
- [ ] `update_user`: super_admin may move tenant (validate); role→super_admin forces
      tenant NULL; role away from super_admin requires a tenant. Regular admin can't
      change tenant_id.
- [ ] Validate tenant exists; import Tenant model.

## Frontend (dashboard/users/page.tsx)
- [ ] Fetch tenants (super_admin only) via `tenantsApi.list()`.
- [ ] Table: add a **Tenant** column (`u.tenant?.name` or "Global").
- [ ] Form: **Tenant dropdown** shown+required for super_admin (all tenants; forced
      "Global" + disabled when role==super_admin). Hidden for regular admins.
- [ ] Send `tenant_id` in create/update (super_admin only). Clear on role→super_admin.
- [ ] Super_admin list: optional Tenant filter.

## Tests
- [ ] `tests/integration/test_users.py`: create sets tenant (SA picks / admin forced),
      list scoping, get/update/delete isolation, SA-global, non-SA can't pick tenant,
      SA move-tenant, role↔tenant coupling.
- [ ] Run `multi-tenant-isolation-auditor` on users.py.

## Verify
- [ ] Backend pytest green; frontend tsc+build+jest green. PR → (confirm) deploy.
- [ ] No prod backfill needed (0 orphaned users today), but new creates will bind.
