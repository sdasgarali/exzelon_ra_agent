# Plan WIP

## SESSION_CONTEXT_RETRIEVAL
> Session 27: Implemented enhanced deduplication + JSearch sub-source tracking. Added 4 new DB columns (external_job_id, city, employer_linkedin_url, employer_website), 3-layer dedup (external_job_id → employer_linkedin → company+title+state+city), title normalization with abbreviation expansion (HR→Human Resources, Mgr→Manager, etc.), per_sub_source_detail tracking (LinkedIn/Indeed/Glassdoor breakdown in pipeline reports), tree-style sub-source display in frontend report modal. 262 tests pass, frontend builds clean. Next: commit, deploy to VPS.

## Immediate TODO
- [x] VPS Production Deployment (all 8 phases complete)
- [x] Granular Settings tab permissions (per-tab view/edit control for admin role)
- [x] Pipeline improvements: confirmations, contact selector, cancel, progress tracking
- [x] Enhanced deduplication + JSearch sub-source tracking (2026-03-05)
- [ ] Deploy latest changes to VPS (dedup + sub-source + pipelines + granular settings)
- [ ] Change super_admin password from default (SA@Admin#123) to a stronger one
- [ ] Configure real email validation provider for production
- [ ] Run enrichment pipeline on sourced leads

## Completed
- [x] Session 27: Enhanced Deduplication + JSearch Sub-Source Tracking (2026-03-05)
  - 4 new DB columns: external_job_id, city, employer_linkedin_url, employer_website
  - Auto-migration in main.py lifespan for new columns + index
  - JSearch adapter captures job_id, city, employer_linkedin, employer_website, job_publisher
  - normalize_job_title() with 20 abbreviation expansions (HR→Human Resources, Mgr→Manager, etc.)
  - 3-layer dedup: external_job_id → employer_linkedin+title → company+title+state+city
  - Sub-source tracking: per_sub_source_detail in counters_json (LinkedIn, Indeed, Glassdoor, ZipRecruiter)
  - Pipeline report: tree-style sub-source rows under JSearch parent
  - Frontend: is_sub_source styling with tree connectors, correct total row (excludes sub-sources)
  - Dedup accuracy: ~75-80% → ~92-95% estimated
  - 262 tests pass, frontend builds clean
  - Plan: Dedup_SubSource_Enhancement_Plan.md
- [x] Session 23: Pipeline Confirmations, Contact Selector, Cancel & Progress (2026-03-03)
  - All 4 dashboard quick actions now require confirmation before executing
  - Lead Sourcing on Pipelines page requires confirmation
  - "Run for All" on lead/contact selectors shows warning confirmation
  - Contact Selector modal for Email Validation (search, filter by validation status, pagination)
  - Cooperative cancellation: cancel_helper.py checks is_cancel_requested in all 4 pipeline loops
  - Progress tracking (progress_pct) updated incrementally during pipeline execution
  - Cancel button in run history table with "Cancelling..." state
  - 13 new tests (3 unit + 10 integration), 213 total pass
  - Commit: d53ea47
- [x] Session 22: Granular Settings Tab Permissions (2026-03-01)
  - Roles & Permissions: Settings module now has 6 independently configurable sub-tabs (Job Sources, AI/LLM, Contacts, Validation, Outreach, Business Rules)
  - Frontend: Tab visibility, read-only mode with fieldset disabled, save button hidden for read-only, All Settings filtered
  - Backend: SETTINGS_TAB_MAP for key→tab mapping, tab-level permission checks on GET/PUT/test-connection endpoints
  - New endpoint: GET /settings/my-permissions/settings-tabs
  - 185 tests pass, frontend builds clean
- [x] Session 21: VPS Production Deployment to Hostinger (2026-03-01)
  - Phase 1: DNS A record for ra.partnerwithus.tech → 187.124.74.175
  - Phase 2: VPS base setup (Ubuntu 24.04, UFW firewall, ra-user)
  - Phase 3: Installed Python 3.11, Node.js 20, MySQL 8.0, Redis 7, Nginx 1.24
  - Phase 4: Deployed code, created venv, installed deps, built Next.js (fixed .gitignore lib/ issue)
  - Phase 5: Migrated MySQL DB (826 leads, 283 contacts, 645 clients, 14 users)
  - Phase 6: Created systemd services (exzelon-api 4 workers, exzelon-web)
  - Phase 7: Nginx reverse proxy + Let's Encrypt SSL (auto-renew)
  - Phase 8: All verification checks passed (health, API docs, login, dashboard)
  - Live at: https://ra.partnerwithus.tech
- [x] Session 20: Super Admin Role + Roles & Permissions Page + Data Migration (2026-03-01)
  - Phase 1: Added SUPER_ADMIN enum to UserRole, super_admin bypass in require_role()
  - Phase 2: Added role guards in users.py (escalation prevention, last-SA protection)
  - Phase 3: Updated store.ts (isSuperAdmin/isAdmin), layout.tsx nav, users/settings/warmup pages
  - Phase 4: Created Roles & Permissions page (/dashboard/roles) with access matrix, 13 modules, 4 roles
  - Phase 5: Updated migration script (preserves super_admin, converts tenant_admin->admin), updated test fixtures, added 13 super_admin tests
  - 185 tests pass (15 new)
  - Data migration from cold_email_ai_agent: 19 tables, 13 users, 826 leads, 645 clients migrated
  - Super admin password reset to SA@Admin#123
  - Rate limiter restored on login endpoint after debugging
- [x] Session 19: Single-tenant refactor merged to master, pushed to sdasgarali/exzelon_ra_agent (2026-03-01)
- [x] Session 18: Single-Tenant Refactor — 86 files changed, 170 tests pass (2026-02-28)
- [x] Sessions 1-17: Core features, pipelines, warmup engine, UI, testing, multi-tenant (reverted)

## Blockers / Notes
- **Production URL**: https://ra.partnerwithus.tech
- **VPS**: 187.124.74.175 (Ubuntu 24.04, 4 vCPU, 16GB RAM, 193GB disk)
- **Services**: exzelon-api (systemd, 4 uvicorn workers), exzelon-web (systemd), nginx, mysql, redis
- **SSL**: Let's Encrypt, auto-renews via certbot timer
- **DB User**: ra_user (password in /opt/exzelon-ra-agent/.env)
- **App User**: ra-user (Linux), code at /opt/exzelon-ra-agent/
- Database name: exzelon_ra_agent
- Roles: 4 levels (super_admin > admin > operator > viewer)
- GitHub repo: https://github.com/sdasgarali/exzelon_ra_agent (master branch only)
