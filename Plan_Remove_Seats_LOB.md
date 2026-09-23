# Plan — Remove team seats & Lines of Business for customers

> STATUS 2026-09-23: IMPLEMENTED per the Decision section at the bottom (role-based, no
> migration). Tasks 4, 5, 6, 16 dropped by that decision; the rest done.

Decided 2026-09-23 (user): remove the LOB feature for customers; every plan (Free/Pro/Max)
gets **1 user + 1 line of business**. Super admin can still grant more to a specific tenant.

## Design (why it is safe)
- LOBs are NOT deleted as plumbing. `lob_id` is nullable on leads/contacts/campaigns, and the
  pipelines fall back to tenant-level config when it is NULL (`lead_sourcing.py:322`). A
  customer with no visible LOB works on that tenant-level workspace = their "1 LOB".
- One switch, no new flag: the LOB UI (selector, nav item, `/dashboard/lob`) and the team UI
  ("Add user") show only when the tenant's **effective** `max_lobs` / `max_users` is > 1.
  Plans say 1, so customers never see them; super admin raises the per-tenant override
  (existing `Tenant.max_lobs` / `max_users` columns) to grant more. Enforcement stays in the
  backend (`check_plan_limit`); the UI hiding is cosmetic.
- Nothing is deleted. Tenants that already have extra users or LOBs keep them (read + use);
  they just cannot add more unless super admin grants it.

## Tasks
### Backend
- [ ] 1. `core/plans.py` PLAN_MATRIX: `max_users=1`, `max_lobs=1` for free/pro/max; Custom
      floors for users/lobs drop to 1 (Custom no longer "starts at 50 seats / 25 LOBs").
- [ ] 2. BUG FIX: `POST /users` never calls `check_plan_limit(..., "users")` (only the invite
      path at `auth.py:242` does) — add it. Super admin (tenant_id None) still bypasses.
- [ ] 3. `POST /lob` is already gated by `check_plan_limit("lobs")`, so at a limit of 1 the
      API itself blocks a second LOB. Verify only, no change.
- [ ] 4. `GET /billing/usage`: expose `lobs_enabled` / `team_enabled` booleans (effective
      limit > 1) so the frontend has one source of truth.
- [ ] 5. Alembic `0005`: for tenants that ALREADY have >1 LOB, set `max_lobs` override to their
      current count (grandfather — they keep seeing their LOB data). Same for users. Internal
      tenants (Exzelon/Neuraforz/Medeoan) already carry `max_users=999`; they get `max_lobs=25`
      via this rule when they have >1 LOB. Idempotent, downgrade = no-op.
- [ ] 6. `main.py` legacy seed inserts for the 3 internal tenants: add `max_lobs` override.

### Frontend
- [ ] 7. `dashboard/layout.tsx`: hide "Lines of Business" nav + `<LobSelector>` unless
      `lobs_enabled` (super_admin always sees them).
- [ ] 8. `lib/lob-store.ts`: when LOBs are disabled force `activeLobId = null`, so no page stays
      filtered to a LOB the user can no longer switch away from.
- [ ] 9. `/dashboard/lob` page: redirect to dashboard when disabled.
- [ ] 10. `/dashboard/users`: hide "Add user" unless `team_enabled`; show a one-line note.
- [ ] 11. `plan-usage-panel.tsx` + `usage-meters.tsx`: drop the seats and LOB rows and the
       two fields from the custom-plan configurator.
- [ ] 12. Public pages: remove "Team seats" + "Lines of business" rows from `PricingCards.tsx`;
       remove/reword LOB and multi-user claims in `features`, `FeatureShowcase`,
       `documentation` sections, `terms` plan table.
- [ ] 13. Command palette: drop the LOB entry when disabled.

### Tests
- [ ] 14. Update `test_plan_limits`, `test_pricing_page_parity`, `test_tenant_service`,
       feature/usage tests for the new numbers.
- [ ] 15. New: `POST /users` returns 403 for a customer admin at 1 user; super admin bypasses;
       tenant with override 5 can add up to 5.
- [ ] 16. New: migration 0005 grandfathers a tenant with 3 LOBs / 4 users, leaves a 1-LOB
       tenant at 0 (plan default).
- [ ] 17. Playwright: customer admin sees no LOB selector / LOB nav / Add user; super admin
       still does; pricing page has no seat/LOB rows.
- [ ] 18. Full backend suite + frontend tsc/build + Playwright green.

### Docs
- [ ] 19. `CLAUDE_REFERENCE/multi-tenancy.md`, `api-endpoints.md` (usage fields), Plan_WIP.

## Acceptance criteria
- A Free/Pro/Max admin cannot add a second user (UI hidden AND API 403).
- A Free/Pro/Max admin never sees LOB UI and all their data is visible (no stuck LOB filter).
- Super admin can raise a tenant's `max_users` / `max_lobs` and that tenant regains the UI.
- No existing user, LOB, lead, contact or campaign is deleted or orphaned.
- Pricing page, usage panel and PLAN_MATRIX agree (parity test).

## Decision (user, 2026-09-23) — supersedes the "effective limit > 1" switch above
"Only super admin has multi, else not." So the rule is by ROLE, not by limit:
- Creating a user (`POST /users`, invite) and creating a LOB (`POST /lob`) = super_admin only.
- LOB selector / LOB nav / `/dashboard/lob` / "Add user" = visible to super_admin only.
- No grandfathering and no migration (task 5 dropped, task 4 dropped): existing extra users and
  LOB rows are NOT deleted, customers just can't manage them. Customer pages run unfiltered
  (activeLobId = null) so no data is hidden behind a LOB they can't switch.
