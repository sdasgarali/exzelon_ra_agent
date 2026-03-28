# Changelog

All notable changes to the NeuraLeads AI Agent project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2026-02-28 (System Improvements)

### Added
- Fernet encryption for mailbox passwords at rest (CRIT-02)
- Rate limiting on login endpoint (5/min) via slowapi (SEC-01)
- XSS sanitization via DOMPurify for email HTML rendering (CRIT-05)
- Pydantic schemas for pipeline request validation (QUAL-01)
- Composite database index on (lead_status, is_archived) (PERF-03)
- Toast notification system with Radix UI
- React ErrorBoundary for graceful error handling
- Pipeline name filter and pagination on pipelines page
- Mobile-responsive sidebar with hamburger menu
- ARIA labels and keyboard navigation support (UX-02)
- 60-second in-memory cache for dashboard KPIs (PERF-04)
- Alembic migrations initialized (DB-01)
- Makefile with dev commands (INFRA-07)
- Multi-stage Dockerfiles for backend and frontend (INFRA-02)
- Production docker-compose.prod.yml (INFRA-03)
- GZip response compression middleware (PERF-08)
- CORS origins configurable via env var (SEC-04)
- Enhanced /health endpoint with DB connectivity check (INFRA-05)
- Lead status state machine with transition validation (FEAT-05)
- Audit trail logging for lead changes (FEAT-03)
- GET /api/v1/audit endpoint for admins
- GET /api/v1/leads/status-transitions endpoint
- Dark mode with class-based Tailwind (FEAT-06)
- Keyboard shortcuts: Shift+? help, Ctrl+D dashboard, etc. (FEAT-07)
- 39 new tests: state machine (19), audit (9), security (11)
- Deployment guide (DOC-01)

### Fixed
- Runtime crash in get_client_stats() (CRIT-01)
- Blocking SMTP/IMAP I/O in async endpoints (CRIT-04)
- N+1 query in client listing (PERF-01)
- Removed duplicate react-query v3 dependency (FPERF-01)
- Cleaned up stray files in project root (INFRA-08)

### Changed
- Quick Action buttons on dashboard now functional (UX-05)
- Active sidebar indicator using pathname matching (UX-06)
- Empty states now show contextual icons and descriptions (UX-09)

## [2.0.0] - 2026-02-27 (MySQL Migration + Smart Enrichment)

### Added
- SQLite to MySQL migration (18 tables, 6032 rows)
- Smart contact enrichment with lead selection (REQ-035 to REQ-038)
- Company-level auto-enrichment for sibling leads
- Auto-enrich during lead sourcing pipeline
- Bulk enrichment preview and results modals
- /dashboard/stats consolidated endpoint
- 27 new tests (59 to 86 total)

### Changed
- Database backend switched from SQLite to MySQL

## [1.0.0] - 2026-02-26 (Initial Release)

### Added
- FastAPI backend with adapter pattern
- Next.js 14 frontend with Tailwind CSS
- 4-stage pipeline (Lead Sourcing, Contact Enrichment, Email Validation, Outreach)
- Warmup engine (peer warmup, auto-reply, DNS checks, blacklist monitoring)
- Email template management
- Reply tracking
- Docker Compose setup
