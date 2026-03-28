# NeuraLeads AI Agent - Session Context

## Project Overview
Building a complete Cold-Email Automation System for NeuraLeads AI with:
- Lead sourcing from job boards
- Contact discovery and enrichment
- Email validation
- Outreach management
- Admin Panel UI

## Current Progress

### Completed Modules
- [x] M0: Repo scaffold + docker-compose + migrations + auth/RBAC
- [x] M1: lead_details + client_info CRUD + lead sourcing adapters
- [x] M2: contact enrichment pipeline + provider adapter
- [x] M3: email validation pipeline + provider adapter
- [x] M4: outreach (mailmerge export) + business rules
- [x] M5: programmatic sending + rate limiting + event tracking
- [x] M6: dashboards + KPIs + job run monitoring
- [x] M7: hardening: security, audit logs, documentation
- [x] M8: warmup engine (peer warmup, auto-reply, DNS checks, blacklist monitor)
- [x] M9: per-mailbox email signatures with structured form + live preview

### Testing Status
- [x] Unit tests (19/19 passed)
- [x] Comprehensive API tests (53/53 passed) - **100% Pass Rate**
- [x] E2E workflow tests (8/8 passed)
- [x] UAT Testing completed
- [x] Automated test scripts created
- [x] Test Report generated

## Session State
**Last Updated**: 2026-02-12
**Current Phase**: FEATURE DEVELOPMENT - Per-Mailbox Email Signatures
**Status**: All modules implemented. Lead sourcing optimized. Email signature feature added to mailboxes.

### Latest Test Results (2026-01-24)

#### Comprehensive Test Summary
| Category | Tests | Passed | Pass Rate |
|----------|-------|--------|-----------|
| Unit Tests (Adapters) | 19 | 19 | 100% |
| Authentication | 10 | 10 | 100% |
| Leads CRUD | 9 | 9 | 100% |
| Clients CRUD | 6 | 6 | 100% |
| Contacts CRUD | 7 | 7 | 100% |
| Pipelines | 4 | 4 | 100% |
| Dashboard | 5 | 5 | 100% |
| Settings | 4 | 4 | 100% |
| E2E Workflow | 8 | 8 | 100% |
| **TOTAL** | **72** | **72** | **100%** |

### Issues Fixed During Testing (2026-01-24)
1. **Route Ordering Bug**: Fixed `/stats` endpoints being captured by `/{id}` routes
   - Files: leads.py, contacts.py, clients.py
   - Solution: Moved static routes before parameterized routes

2. **Invalid Enum Values**: Updated test scripts with valid LeadStatus values
   - Changed "contacted" -> "enriched", "qualified" -> "validated"

3. **API Response Format**: Standardized list endpoints to return paginated format
   - Format: `{items: [], total: N}`

4. **SQLite Support**: Added SQLite configuration for local development without Docker
   - Files: config.py, base.py
   - Set `DB_TYPE=sqlite` for local dev

### Previous Issues Fixed (2026-01-18)
1. **MySQL key length issue**: Changed `job_link` from VARCHAR(1000) to VARCHAR(500)
2. **bcrypt compatibility**: Switched to argon2 for password hashing
3. **Docker port conflicts**: Updated ports (MySQL: 3307, Redis: 6380, Web: 3003)

## Deliverables Created

### 1. Backend (FastAPI)
- Authentication with RBAC (argon2 password hashing)
- Leads CRUD with filtering/pagination
- Clients CRUD with category computation
- Contacts CRUD with priority levels
- Email validation pipeline (mock + real adapters)
- Outreach pipeline (mailmerge + programmatic)
- Dashboard with KPIs and trends
- Settings management
- Pipeline execution history

### 2. Frontend (Next.js)
- Login/Registration
- Dashboard with statistics
- Navigation and layout
- API client library

### 3. Infrastructure
- docker-compose.yml (MySQL, Redis, API, Web)
- Environment configuration
- Database models and auto-creation
- SQLite support for local development

### 4. Testing
- Unit tests for adapters (19 tests)
- Comprehensive API test suite (53 tests)
- E2E workflow tests (8 tests)
- Test runner: `python scripts/comprehensive_test.py`

### 5. Warmup Engine
- Peer-to-peer warmup email exchange
- Auto-reply system (AI content via Groq)
- DNS health checks (SPF, DKIM, DMARC)
- Blacklist monitoring and auto-recovery
- Warmup profiles (Conservative, Standard, Aggressive)

### 6. Per-Mailbox Email Signatures
- Structured signature editor (name, title, phone, email, company, website)
- Live HTML preview in mailbox add/edit modal
- Automatic injection into outreach emails
- Clean HTML rendering with inline styles for email compatibility

### 7. Documentation
- README.md
- TESTING_PLAN.md
- TEST_REPORT.md
- TEST_RESULTS_20260124.md
- TEST_AUTOMATION_GUIDE.md
- SESSION_CONTEXT.md

## Test Credentials
- Admin: admin@exzelon.com / Admin@123
- Operator: operator@exzelon.com / Operator@123
- Viewer: viewer@exzelon.com / Viewer@123
- Test Client: testclient@example.com / TestClient@123

## Architecture
- Backend: Python 3.11+ with FastAPI
- Frontend: Next.js 14 (React)
- Database: MySQL 8+ (production) / SQLite (development)
- Queue/Cache: Redis 7
- Password Hashing: Argon2

## Quick Start (Local Development)

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Frontend
cd frontend
npm install
npm run dev -- -p 3003

# Seed database
cd backend
python -c "from app.db.seed import run_seed; run_seed()"

# Run tests
python scripts/comprehensive_test.py
```

## Docker Services
| Service | Container | Host Port | Internal Port |
|---------|-----------|-----------|---------------|
| API | ra_api | 8000 | 8000 |
| Web | ra_web | 3003 | 3000 |
| MySQL | ra_mysql | 3307 | 3306 |
| Redis | ra_redis | 6380 | 6379 |

## Key Configurations
- DATA_STORAGE: database|files
- DB_TYPE: mysql|sqlite (for local dev)
- CONTACT_PROVIDER: mock|apollo|seamless
- EMAIL_VALIDATION_PROVIDER: mock|neverbounce|zerobounce|hunter|clearout
- EMAIL_SEND_MODE: mailmerge|smtp|m365|gmail|api
- DAILY_SEND_LIMIT: 30
- COOLDOWN_DAYS: 10
- MAX_CONTACTS_PER_COMPANY_PER_JOB: 4
- MIN_SALARY_THRESHOLD: 30000
- JOB_SOURCES: jsearch, apollo (configurable in Settings UI)
- TARGET_JOB_TITLES: 37 titles (all enabled by default)
- TARGET_INDUSTRIES: 22 industries
- EXCLUDE_IT_KEYWORDS: 14 specific phrases (configurable via chip UI)
- EXCLUDE_STAFFING_KEYWORDS: 7 specific phrases (configurable via chip UI)

## Database Tables
1. users - Admin users and roles
2. lead_details - Job posts and lead rows
3. client_info - Per-company lifecycle tracking
4. contact_details - Discovered contacts for outreach
5. email_validation_results - Bulk validation responses
6. outreach_events - Send attempts and results
7. suppression_list - Do-not-contact list
8. job_runs - Pipeline job execution history
9. settings - Key-value settings store
10. sender_mailboxes - Email sender accounts (includes email_signature_json)
11. warmup_emails - Warmup email exchange records
12. warmup_daily_logs - Daily warmup statistics
13. warmup_alerts - Warmup system alerts
14. warmup_profiles - Warmup configuration profiles
15. dns_check_results - DNS health check results
16. blacklist_check_results - Blacklist monitoring results

## API Endpoints

### Authentication
- POST /api/v1/auth/login
- POST /api/v1/auth/register
- GET /api/v1/auth/me
- POST /api/v1/auth/logout

### Leads
- GET /api/v1/leads
- GET /api/v1/leads/stats
- GET /api/v1/leads/{id}
- POST /api/v1/leads
- PUT /api/v1/leads/{id}
- DELETE /api/v1/leads/{id}

### Clients
- GET /api/v1/clients
- GET /api/v1/clients/stats
- GET /api/v1/clients/{id}
- POST /api/v1/clients
- PUT /api/v1/clients/{id}
- DELETE /api/v1/clients/{id}
- POST /api/v1/clients/{id}/refresh-category

### Contacts
- GET /api/v1/contacts
- GET /api/v1/contacts/stats
- GET /api/v1/contacts/{id}
- POST /api/v1/contacts
- PUT /api/v1/contacts/{id}
- DELETE /api/v1/contacts/{id}

### Pipelines
- GET /api/v1/pipelines/runs
- POST /api/v1/pipelines/lead-sourcing/run
- POST /api/v1/pipelines/lead-sourcing/upload
- POST /api/v1/pipelines/contact-enrichment/run
- POST /api/v1/pipelines/email-validation/run
- POST /api/v1/pipelines/outreach/run

### Dashboard
- GET /api/v1/dashboard/kpis
- GET /api/v1/dashboard/trends
- GET /api/v1/dashboard/leads-sourced
- GET /api/v1/dashboard/contacts-identified
- GET /api/v1/dashboard/outreach-sent
- GET /api/v1/dashboard/client-categories

### Mailboxes
- GET /api/v1/mailboxes
- GET /api/v1/mailboxes/stats
- GET /api/v1/mailboxes/{id}
- POST /api/v1/mailboxes
- PUT /api/v1/mailboxes/{id}
- DELETE /api/v1/mailboxes/{id}
- POST /api/v1/mailboxes/{id}/test-connection
- PUT /api/v1/mailboxes/{id}/status

### Warmup
- GET /api/v1/warmup/dashboard
- POST /api/v1/warmup/send-batch
- GET /api/v1/warmup/emails
- POST /api/v1/warmup/dns-check/{mailbox_id}
- POST /api/v1/warmup/blacklist-check/{mailbox_id}

### Settings
- GET /api/v1/settings
- GET /api/v1/settings/{key}
- PUT /api/v1/settings/{key}
- POST /api/v1/settings/initialize

## Valid Enum Values

### LeadStatus
- new, enriched, validated, sent, skipped

### ClientStatus
- active, inactive, paused

### ClientCategory
- prospect, occasional, regular, dormant

### PriorityLevel
- p1_job_poster, p2_hr_ta_recruiter, p3_hr_manager, p4_ops_leader, p5_functional_manager

### ValidationStatus
- pending, valid, invalid, catch_all, unknown

## Notes for Resume
- All secrets must be in .env
- Focus on <2% bounce rate
- Implement adapter pattern for providers
- RBAC: admin, operator, viewer
- Use argon2 for password hashing (bcrypt has compatibility issues)
- Check port availability before starting Docker
- Route ordering matters in FastAPI - static routes before parameterized
- SQLite available for local development without Docker

## Pending Items
- [ ] Run contact enrichment pipeline on new 612 leads
- [ ] Configure real email validation provider (NeverBounce/ZeroBounce)
- [ ] Test outreach pipeline with enriched contacts and verify signature appears in emails
- [ ] Update backend DEFAULT_SETTINGS to match refined exclude keywords
- [ ] Add email signature templates/presets for quick setup

## Files Modified in Latest Session (2026-02-12)
### Per-Mailbox Email Signature Feature
1. `backend/app/db/models/sender_mailbox.py` - Added email_signature_json column
2. `backend/app/schemas/sender_mailbox.py` - Added email_signature_json to Base, Update, Response schemas
3. `backend/app/services/pipelines/outreach.py` - Added render_signature_html() helper + signature injection into email body
4. `frontend/src/app/dashboard/mailboxes/page.tsx` - Added signature editor form (6 fields) + live HTML preview in modal
5. `backend/data/ra_agent.db` - Migrated: ALTER TABLE sender_mailboxes ADD COLUMN email_signature_json TEXT
