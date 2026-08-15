# Plan — Per-tenant deal stages (seeding + automation lookup)

> Branch: `fix/deal-stages-per-tenant`. Date: 2026-08-15.

## Confirmed bug (verified on prod)
- `deal_automation._get_stage_by_name` / `_get_next_stage` are NOT tenant-scoped →
  auto-create/auto-advance can grab ANOTHER tenant's stage by name.
- Startup `_seed_deal_stages` seeds ONLY tenant 1. Other tenants get stages only via
  `demo_seeder.seed_demo_data` (startup: neuraforz/medeoan only; verify: STARTER plan only).
  A new professional/enterprise (non-demo) tenant would have NO stages → empty pipeline,
  and an interested reply would create a deal pointing at another tenant's stage.
- Live proof: prod deal_id 26 (tenant 1) references stage_id 9 (tenant 3). (E2E test junk.)

## Changes
### backend/app/services/deal_automation.py
- [ ] `_get_stage_by_name(db, name, tenant_id)` — filter by tenant_id.
- [ ] `_get_next_stage(db, current_order, tenant_id)` — filter by tenant_id.
- [ ] NEW `DEFAULT_DEAL_STAGES` constant + `ensure_deal_stages(db, tenant_id)` —
      idempotent: seed the 7 defaults if the tenant has none. Returns count seeded.
- [ ] `auto_create_deal_from_interested_reply` — compute tenant_id (already does),
      `ensure_deal_stages(db, tenant_id)`, then `_get_stage_by_name(..., tenant_id)`.
- [ ] `auto_advance_stage` — pass `deal.tenant_id` to lookups.

### Provisioning
- [ ] `tenant_service.create_tenant_for_signup` → `ensure_deal_stages`.
- [ ] `admin_tenants.create_tenant` → `ensure_deal_stages`.

### backend/app/main.py (lifespan)
- [ ] Replace tenant-1-only `_seed_deal_stages` with a loop over ALL tenants calling
      `ensure_deal_stages` (backfill existing tenants).
- [ ] Self-healing migration: repoint any deal whose stage.tenant_id != deal.tenant_id
      to the same-named stage in the deal's own tenant (fixes deal 26 + any others).

### Tests (tests/unit/test_deal_automation.py)
- [ ] `ensure_deal_stages` seeds for a stage-less tenant; idempotent (no dup on 2nd call).
- [ ] auto-create for a tenant-2 contact uses tenant-2's "New Lead" (not tenant-1's).
- [ ] auto-create on a stage-less tenant self-heals + uses that tenant's stage.
- [ ] auto_advance uses the deal's own tenant's stage.
- [ ] `_get_stage_by_name` scoped (two tenants with same-named stage → returns the right one).

## Out of scope (note as follow-up)
- `_get_deal_setting` reads GLOBAL settings (not tenant_settings) → deal automation
  toggles are global. Left as-is (separate concern from stage scoping).

## Verify
- [ ] Backend suite green; PR → deploy; confirm all tenants have 7 stages + deal 26 repointed.
