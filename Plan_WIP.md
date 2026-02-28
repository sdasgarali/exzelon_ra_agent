# Plan WIP
## SESSION_CONTEXT_RETRIEVAL
> SQLite to MySQL migration COMPLETE. All 18 tables, 6032 rows migrated. App running on MySQL (cold_email_ai_agent). All verification passed. Comprehensive E2E testing COMPLETE: 59/59 backend tests pass, all 11 frontend modules verified via Playwright browser testing, 12 API integration tests pass. Test report at docs/Test_Report_MySQL_Migration.md. Next: clean up test data, fix enum serialization, add dashboard stats endpoint.

## Immediate TODO
- [ ] Clean up test data: 4 test leads (IDs 720-723) and associated contacts/outreach events in production DB
- [ ] Fix enum serialization: LeadStatus.NEW -> new in API /leads/stats by_status keys
- [ ] Add /api/v1/dashboard/stats backend endpoint
- [ ] Increase test coverage: warmup engine, email templates, pipeline execution tests

## Completed
- [x] SQLite to MySQL migration: schema + data for all 18 tables (2026-02-27)
- [x] Migration script: backend/scripts/migrate_sqlite_to_mysql.py (2026-02-27)
- [x] config.py: Added ?charset=utf8mb4 to MySQL URLs (2026-02-27)
- [x] Migrations made DB-agnostic: replaced sqlite3/PRAGMA with SQLAlchemy inspect (2026-02-27)
- [x] .env updated: DB_TYPE=mysql, cold_email_ai_agent, root credentials (2026-02-27)
- [x] Backend: Smart contact reuse (_reuse_existing_contacts, _update_lead_from_contacts) (2026-02-27)
- [x] Backend: lead_ids parameter in run_contact_enrichment_pipeline (2026-02-27)
- [x] Backend: POST /leads/bulk/enrich/preview + /bulk/enrich endpoints (2026-02-27)
- [x] Backend: Contact-enrichment/run + outreach/run accept optional lead_ids body (2026-02-27)
- [x] Backend: parse_counters updated with contacts_reused + api_calls_saved (2026-02-27)
- [x] Frontend: bulkEnrichPreview + bulkEnrich added to leadsApi (2026-02-27)
- [x] Frontend: pipelinesApi.runContactEnrichment + runOutreach accept optional leadIds (2026-02-27)
- [x] Frontend: Contact Enrich button + preview modal + results modal on leads page (2026-02-27)
- [x] Frontend: Lead selector popup on pipelines page for Contact Enrichment + Outreach (2026-02-27)
- [x] Master_Plan.md updated with REQ-035 to REQ-038 (2026-02-27)
- [x] Verification: All backend imports OK, frontend builds clean (2026-02-27)
- [x] Comprehensive E2E testing: 59/59 backend tests, 11 browser modules, 12 API tests (2026-02-27)
- [x] Test infrastructure fix: conftest.py get_db import from correct module (2026-02-27)
- [x] Test report: docs/Test_Report_MySQL_Migration.md (2026-02-27)

## Previous Work
- [x] DB migration: ALTER TABLE outreach_events ADD message_id + sender_mailbox_id (2026-02-26)
- [x] Backend: Enrich lead detail endpoint with contact_name, contact_email, sender_name, sender_email (2026-02-26)
- [x] Frontend: Inbox-style email thread view with HTML iframe, reply blocks, UNSUBSCRIBE badges (2026-02-26)
- [x] Reply tracker service, scheduler job, API endpoints (2026-02-26)
- [x] Email Templates feature fully implemented (2026-02-26)

## Blockers / Notes
- Write/Edit tools have Windows path issues; used python3 -c workaround for backend, Write/Edit tools for frontend
- SQLAlchemy create_all creates new tables with all columns; existing tables need ALTER TABLE
- .env must exist in BOTH project root AND backend/ directory (config.py reads from backend/.env)
