# Plan WIP
## SESSION_CONTEXT_RETRIEVAL
> Session 17: Global Super Admin vs Tenant Super Admin implemented — GSA (SA+tenant_id=1) has cross-tenant access; TSA (SA+tenant_id!=1) scoped to own tenant. 14 files changed, 191 tests pass.

## Immediate TODO
- [x] Global Super Admin vs Tenant Super Admin: Two-tier SA model — 14 files changed, all 191 tests pass (2026-02-28)

## Completed
- [x] Session 17: GSA vs TSA — MASTER_TENANT_ID=1 constant, _is_global_super_admin ContextVar, auth.py GSA/TSA branching, query_helpers uses GSA check, tenants.py _require_global_super_admin, users.py GSA-only scoping, seed.py fixed (SA→tenant_id=1), migration SQL, frontend isGlobalSuperAdmin(), nav globalOnly flag, tenant switcher GSA-only, role display GSA/TSA labels. 191 tests pass (2026-02-28)
- [x] Session 16: Production Deployment Config — env_loader.py (APP_ENV prefix resolution), config.py refactored, hardcoded URLs/secrets/paths removed, docker-compose aligned, 191 tests pass (2026-02-28)
- [x] Session 15: Multi-Tenant Architecture — 6 phases (Foundation → Query Filtering → Pipelines → Settings → Frontend → Hardening), 191 tests pass, 0 cross-tenant leaks (2026-02-28)
- [x] Session 14: Unsubscribe Handling Enhancement — clickable unsub links, contact status tracking, audit log, outreach_status filter, frontend columns (2026-02-28)
- [x] Session 13: Full E2E testing — 170 backend tests, 16 frontend pages, browser E2E via Playwright, 6 bugs fixed (2026-02-28)
- [x] Batch 13 (new): 36 new backend tests (170 total), Locust load test, Makefile --cov-fail-under=75 (2026-02-28)
- [x] Batch 15: Testing + docs — 39 new tests (134 total), DEPLOYMENT_GUIDE.md, CHANGELOG.md (2026-02-28)
- [x] Batch 14: Dark mode (class-based Tailwind), keyboard shortcuts (Shift+?, Ctrl+D/L/O/P) (2026-02-28)
- [x] Batch 13: Lead status state machine, audit trail (audit_logs table, /audit endpoints) (2026-02-28)
- [x] Batch 12: Multi-stage Dockerfiles, docker-compose.prod.yml, GZip, CORS env, health check (2026-02-28)
- [x] Batch 11: Alembic init, Makefile, stray file cleanup, .gitignore update (2026-02-28)
- [x] Batch 10: KPI cache (60s TTL) on /dashboard/kpis (2026-02-28)
- [x] Batch 9: Mobile responsive sidebar, ARIA labels, hamburger menu (2026-02-28)
- [x] Batch 8: Pipeline name filter + pagination on pipelines page (2026-02-28)
- [x] Batch 7: Empty states with icons, ErrorBoundary component (2026-02-28)
- [x] Batch 6: Toast notification system (Radix UI), replaced alert() calls (2026-02-28)
- [x] Batch 5: Removed react-query v3 dupe, active nav indicator, Quick Actions wired (2026-02-28)
- [x] Batch 4: Pydantic schemas for pipelines, DB indexes, N+1 fix in clients (2026-02-28)
- [x] Batch 3: XSS sanitization (DOMPurify), blocking I/O fix (asyncio.to_thread) (2026-02-28)
- [x] Batch 2: Client stats crash fix (CRIT-01), login rate limiting (slowapi) (2026-02-28)
- [x] Batch 1: Fernet encryption for mailbox passwords, migration on startup (2026-02-28)
- [x] Company-level auto-enrichment for sibling leads (2026-02-28)
- [x] Auto-enrich during lead sourcing pipeline (2026-02-28)
- [x] Delete test leads 720-723 from production MySQL DB (2026-02-27)
- [x] Fix enum serialization: s.value in leads.py line 170 and dashboard.py line 198 (2026-02-27)
- [x] Add /api/v1/dashboard/stats consolidated endpoint (2026-02-27)
- [x] Expand test coverage: 4 new test files, 27 new tests (86 total, all passing) (2026-02-27)
- [x] Comprehensive system review: 60 issues across 14 sections (2026-02-27)
- [x] docs/SYSTEM_IMPROVEMENT_RECOMMENDATIONS.md created (537 lines, 4-phase roadmap) (2026-02-27)
- [x] SQLite to MySQL migration: schema + data for all 18 tables (2026-02-27)
- [x] Smart Contact Enrichment with lead selection (REQ-035 to REQ-038) (2026-02-27)

## Previous Work
- [x] DB migration: ALTER TABLE outreach_events ADD message_id + sender_mailbox_id (2026-02-26)
- [x] Backend: Enrich lead detail endpoint with contact_name, contact_email, sender_name, sender_email (2026-02-26)
- [x] Frontend: Inbox-style email thread view with HTML iframe, reply blocks, UNSUBSCRIBE badges (2026-02-26)
- [x] Reply tracker service, scheduler job, API endpoints (2026-02-26)
- [x] Email Templates feature fully implemented (2026-02-26)

## Blockers / Notes
- Write/Edit tools now work on Windows (hook issue resolved)
- SQLAlchemy create_all creates new tables with all columns; existing tables need ALTER TABLE
- Single .env in project root (backend/.env removed); env_loader resolves APP_ENV prefixes
- mysql.connector not available in env; use pymysql instead for direct DB scripts
