# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

### Backend (FastAPI)
```bash
# Install dependencies
cd backend && pip install -r requirements.txt

# Run dev server (from repo root)
cd backend && uvicorn app.main:app --reload --port 8000

# Run all tests
cd backend && pytest

# Run tests by marker
cd backend && pytest -m unit
cd backend && pytest -m integration
cd backend && pytest -m e2e

# Run a single test file
cd backend && pytest tests/unit/test_adapters.py

# Run with coverage
cd backend && pytest --cov=app

# API docs available at http://localhost:8000/api/docs
```

### Frontend (Next.js 14)
```bash
# Install dependencies
cd frontend && npm install

# Run dev server
cd frontend && npm run dev    # http://localhost:3000

# Build for production
cd frontend && npm run build

# Lint
cd frontend && npm run lint

# Run tests
cd frontend && npm test
```

### Docker (full stack)
```bash
docker-compose up        # MySQL:3307, Redis:6380, API:8000, Web:3003
docker-compose up api    # Backend only with dependencies
```

## Architecture

**Two-service architecture**: FastAPI backend + Next.js 14 frontend communicating over REST.

### Backend (`backend/app/`)

- **Entry point**: `main.py` -- FastAPI app with lifespan handler that creates DB tables, seeds warmup profiles, starts APScheduler
- **Config**: `core/config.py` -- Pydantic Settings loaded from `.env`; controls DB type (sqlite/mysql), provider selection, business rules
- **API routes**: `api/endpoints/` -- all endpoints mounted under `/api/v1` via `api/router.py`
- **Auth**: JWT tokens (7-day expiry), Argon2 password hashing, RBAC with 4 roles: super_admin, admin, operator, viewer. Super admin bypasses all role checks. Dependencies in `api/deps/auth.py`. Single-tenant deployment (no multi-tenancy).
- **Database**: SQLAlchemy 2.0 ORM, models in `db/models/`, base class in `db/base.py`. Auto-creates tables on startup. MySQL (`exzelon_ra_agent` on localhost:3306) is the active database. SQLite used for testing.

### Adapter Pattern (`services/adapters/`)

All external integrations implement abstract base classes from `adapters/base.py`. Provider selection is driven by `.env` settings. Each category has a `mock` adapter for development/testing.

| Category | Adapters | Config key |
|---|---|---|
| Job Sources | Apollo, Indeed, JSearch | `JOB_SOURCES`, `JSEARCH_API_KEY` |
| Contact Discovery | Apollo, Seamless | `CONTACT_PROVIDER` |
| Email Validation | NeverBounce, ZeroBounce, Hunter, Clearout, Emailable, MailboxValidator, Reacher | `EMAIL_VALIDATION_PROVIDER` |
| Email Sending | SMTP, Mock | `EMAIL_SEND_MODE` |
| AI Content | Groq, OpenAI, Anthropic, Gemini | per-adapter API keys |

### Pipeline Pattern (`services/pipelines/`)

Four sequential data-processing stages, each independently executable via API:
1. **Lead Sourcing** -- fetch jobs from boards, normalize, deduplicate, store
2. **Contact Enrichment** -- discover decision-makers via Apollo/Seamless
3. **Email Validation** -- verify email addresses before sending
4. **Outreach** -- AI-generate email content, enforce rate limits and cooldowns, send

### Warmup Engine (`services/warmup/`)

Domain reputation management subsystem:
- Peer-to-peer warmup emails between mailboxes
- Auto-reply to warmup emails (AI-generated via Groq)
- DNS checking (SPF/DKIM/DMARC)
- IP/domain blacklist monitoring
- Open/click tracking via pixel and link redirect (endpoints in `main.py`: `/t/{id}/px.gif`, `/t/{id}/l`)
- APScheduler-based automation (`scheduler.py`)

### Frontend (`frontend/src/`)

- **App Router**: Next.js 14 app directory at `app/`. Dashboard pages under `app/dashboard/`
- **API client**: `lib/api.ts` -- Axios instance with auth interceptor (auto-attaches Bearer token, redirects to `/login` on 401)
- **State**: Zustand for auth state (`lib/store.ts`), TanStack React Query for server data
- **Forms**: React Hook Form + Zod validation
- **Styling**: Tailwind CSS + Radix UI primitives + Lucide icons
- **Charts**: Recharts for dashboard visualizations

## Key Data Models

- **LeadDetails** -- job postings with status tracking (open/hunting/closed)
- **ContactDetails** -- decision-makers with priority levels (P1 job poster through P5 functional manager)
- **LeadContactAssociation** -- many-to-many junction table
- **ClientInfo** -- companies/organizations
- **SenderMailbox** -- email accounts with daily limits, health scores, warmup status
- **OutreachEvent** -- email events (sent/opened/clicked/replied/bounced)
- **WarmupProfile** -- warmup templates (Conservative 45d, Standard 30d, Aggressive 20d)

## Business Rules (configured in `core/config.py`)

- Daily send limit: 30 emails/mailbox (`DAILY_SEND_LIMIT`)
- Cooldown: 10 days between emails to same contact (`COOLDOWN_DAYS`)
- Max 4 contacts per company per job (`MAX_CONTACTS_PER_COMPANY_PER_JOB`)
- Salary threshold: $30k+ (`MIN_SALARY_THRESHOLD`)
- 22 non-IT target industries; IT roles and US staffing agencies excluded
- Only contacts with Valid email validation status receive outreach

## Testing

Tests use in-memory SQLite (overridden in `tests/conftest.py`). Fixtures provide `client` (TestClient), `db_session`, and pre-built users with tokens for each role.

```bash
cd backend && pytest -m unit          # Unit tests (adapters, services)
cd backend && pytest -m integration   # API endpoint tests
cd backend && pytest -m e2e           # Full workflow tests
cd backend && pytest -k test_name     # Run specific test by name
```

## Environment Setup

1. Copy `.env.example` to `.env`
2. For local dev: uses MySQL (`DB_TYPE=mysql`, `exzelon_ra_agent` database). Requires MySQL 8.x on localhost:3306
3. To migrate from old `cold_email_ai_agent` DB: `python scripts/migrate_to_exzelon.py`
4. Frontend reads `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000/api/v1`)
