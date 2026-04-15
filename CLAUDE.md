# CLAUDE.md — Exzelon RA Agent

This file provides guidance to Claude Code. Detailed docs are in `CLAUDE_REFERENCE/`. Read them on demand.

## Quick Reference

### Backend (FastAPI)
```bash
cd backend && pip install -r requirements.txt    # Install deps
cd backend && uvicorn app.main:app --reload --port 8000  # Dev server
cd backend && pytest                             # All tests
cd backend && pytest -m unit                     # Unit tests
cd backend && pytest -m integration              # Integration tests
cd backend && pytest -m e2e                      # E2E tests
cd backend && pytest --cov=app                   # Coverage
# API docs: http://localhost:8000/api/docs
```

### Frontend (Next.js 14)
```bash
cd frontend && npm install     # Install deps
cd frontend && npm run dev     # Dev server (http://localhost:3000)
cd frontend && npm run build   # Production build
cd frontend && npm run lint    # Lint
cd frontend && npm test        # Tests
```

### Docker
```bash
docker-compose up        # MySQL:3307, Redis:6380, API:8000, Web:3003
docker-compose up api    # Backend only with dependencies
```

## Architecture (Summary)

**Two-service architecture**: FastAPI backend + Next.js 14 frontend over REST.

### Backend (`backend/app/`)
- **Entry point**: `main.py` — FastAPI app with lifespan handler (DB tables, seeds, APScheduler)
- **Config**: `core/config.py` — Pydantic Settings from `.env`
- **API routes**: `api/endpoints/` mounted under `/api/v1` via `api/router.py`
- **Auth**: JWT (30-min access + 7-day refresh), Argon2, RBAC (super_admin/admin/operator/viewer), multi-tenant, email verification. Deps in `api/deps/auth.py`
- **Database**: SQLAlchemy 2.0 ORM, MySQL (`exzelon_ra_agent` on localhost:3306). SQLite for testing.

### Frontend (`frontend/src/`)
- **App Router**: Next.js 14, dashboard pages under `app/dashboard/`
- **API client**: `lib/api.ts` — Axios with auth interceptor + silent token refresh
- **State**: Zustand (auth) + TanStack React Query (server data)
- **UI**: Tailwind CSS + Radix UI + Lucide icons + Recharts

## CLAUDE_REFERENCE (Read On Demand)

Detailed documentation lives in `CLAUDE_REFERENCE/`. **Read the relevant file before working on that area.**

| Working On | Read | Key Info |
|---|---|---|
| External integrations (job sources, contact discovery, AI, CRM, etc.) | `CLAUDE_REFERENCE/adapters.md` | 9 adapter categories, config keys, mock variants |
| Any backend service (campaign engine, inbox, AI agent, billing, safety, etc.) | `CLAUDE_REFERENCE/services.md` | All 40+ services with file paths and descriptions |
| Database models, schema, relationships | `CLAUDE_REFERENCE/data-models.md` | All 39 models, fields, relationships, NOT NULL constraints |
| API endpoints (adding/modifying routes) | `CLAUDE_REFERENCE/api-endpoints.md` | All endpoint prefixes, files, purposes |
| Deployment, VPS, SSH, nginx, systemd | `CLAUDE_REFERENCE/deployment.md` | Server details, deploy script, logs, rollback |
| Multi-tenancy, plan limits, tenant isolation | `CLAUDE_REFERENCE/multi-tenancy.md` | Tenant model, plan limits, key dependencies |

### Global Standards (in `~/.claude/CLAUDE_REFERENCE/`)

| Working On | Read |
|---|---|
| n8n workflows | `~/.claude/CLAUDE_REFERENCE/n8n-integration.md` |
| Laravel projects | `~/.claude/CLAUDE_REFERENCE/laravel-conventions.md` |
| Architecture decisions | `~/.claude/CLAUDE_REFERENCE/architecture-conventions.md` |
| Backup/restore features | `~/.claude/CLAUDE_REFERENCE/database-backup-restore.md` |
| RBAC/permissions | `~/.claude/CLAUDE_REFERENCE/roles-permissions.md` |
| Billing/invoicing | `~/.claude/CLAUDE_REFERENCE/billing-invoicing-standard.md` |

### Maintaining CLAUDE_REFERENCE (HARD RULES)
1. **New service/module** -> update `CLAUDE_REFERENCE/services.md`
2. **New data model** -> update `CLAUDE_REFERENCE/data-models.md`
3. **New API endpoint** -> update `CLAUDE_REFERENCE/api-endpoints.md`
4. **Deploy/infra change** -> update `CLAUDE_REFERENCE/deployment.md`
5. **Tenant/plan change** -> update `CLAUDE_REFERENCE/multi-tenancy.md`
6. **New adapter** -> update `CLAUDE_REFERENCE/adapters.md`
7. **NEVER duplicate** detailed content inline here — point to reference docs instead

## Business Rules (configured in `core/config.py`)

- Daily send limit: 30 emails/mailbox (`DAILY_SEND_LIMIT`)
- Cooldown: 10 days between emails to same contact (`COOLDOWN_DAYS`)
- Max 4 contacts per company per job (`MAX_CONTACTS_PER_COMPANY_PER_JOB`)
- Salary threshold: $30k+ (`MIN_SALARY_THRESHOLD`)
- 22 non-IT target industries; IT roles and US staffing agencies excluded
- Only contacts with Valid email validation status receive outreach

## Testing

Tests use in-memory SQLite (overridden in `tests/conftest.py`). Fixtures provide `client`, `db_session`, and pre-built users with tokens for each role.

**Pitfalls**:
- ContactDetails requires `client_name`, `first_name`, AND `last_name` (all NOT NULL)
- OutreachEvent requires `channel` (OutreachChannel enum)
- `jest.setup.ts` and `__tests__/` must be excluded in `frontend/tsconfig.json`
- Signup tests use `"SecurePass123!"` (password policy requires special char)

## Environment Setup

1. Copy `.env.example` to `.env`
2. Local dev: MySQL (`DB_TYPE=mysql`, `exzelon_ra_agent`), MySQL 8.x on localhost:3306
3. Frontend: `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000/api/v1`)
4. Billing: set `BILLING_ENABLED=true`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` in `.env`

## Production Deployment (Essentials)

| Item | Value |
|------|-------|
| **URL** | `https://ra.partnerwithus.tech` |
| **VPS** | `187.124.74.175` (Hostinger, Ubuntu 24.04) |
| **App dir** | `/opt/exzelon-ra-agent/` |
| **Deploy** | `./deploy/vps_ssh.sh "bash /opt/exzelon-ra-agent/deploy/deploy.sh"` |
| **Services** | `exzelon-api` (port 8000), `exzelon-web` (port 3000), nginx, mysql, redis |

For full deployment details (SSH, logs, nginx, systemd, rollback): **Read `CLAUDE_REFERENCE/deployment.md`**

## Auto-Invoked Skills (MANDATORY)

| Skill | Trigger Conditions | File |
|-------|-------------------|------|
| `sales-draft-outreach` | Any outreach-related task (see triggers below) | `.claude/commands/sales-draft-outreach.md` |

### sales-draft-outreach — Trigger Conditions

**ALWAYS invoke this skill when ANY of the following occur:**

1. **Direct requests**: "draft outreach", "write cold email", "reach out to", "draft email to", "write email to", "LinkedIn message to", "contact [person]", "outreach to [company]"
2. **Pipeline outreach stage**: Working on Pipeline Stage 4 (Outreach)
3. **Campaign email creation**: Creating/editing email content for campaigns, sequence steps, A/B test variants, email templates
4. **Contact follow-up**: Drafting follow-up, re-engagement, or post-event outreach
5. **AI content generation**: Modifying `ai_content.py`, `ai_sequence_generator.py`, or `campaign_engine.py` email personalization
6. **Inbox reply drafting**: Outreach-oriented replies to inbound messages
7. **Code changes to outreach modules**: Modifying outreach-related services — use skill's email style as quality standard

## Mandatory Update Table

| Change Type | Files to Update |
|-------------|----------------|
| **New DB migration** | `backend/app/main.py` (lifespan hook) |
| **New DB table/model** | `backend/app/db/models/`, `db/base.py`, `CLAUDE_REFERENCE/data-models.md` |
| **New API endpoint** | `backend/app/api/endpoints/`, `api/router.py`, `CLAUDE_REFERENCE/api-endpoints.md` |
| **New dashboard page** | `frontend/src/app/dashboard/`, `layout.tsx` nav, MODULES in roles page |
| **New settings tab** | `SETTINGS_TAB_MAP` in `api/deps/auth.py`, frontend Settings page |
| **New service/module** | `CLAUDE_REFERENCE/services.md` |
| **New adapter** | `CLAUDE_REFERENCE/adapters.md` |
| **Deploy/infra change** | `deploy/` directory, `CLAUDE_REFERENCE/deployment.md` |
| **New env variable** | `backend/.env`, `.env.example`, `core/config.py` |
| **New dependency** | `requirements.txt` or `package.json`, note rationale in commit |
| **New RBAC module** | DEFAULT_PERMISSIONS in roles page, MODULES array |
| **Tenant/plan change** | `CLAUDE_REFERENCE/multi-tenancy.md` |
| **Outreach email logic** | Follow `.claude/commands/sales-draft-outreach.md` guidelines |
