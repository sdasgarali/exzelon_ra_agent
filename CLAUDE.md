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
1. **Lead Sourcing** -- fetch jobs from boards, normalize, 3-layer deduplicate (external_job_id → employer_linkedin → company+title+state+city), sub-source tracking (LinkedIn/Indeed/Glassdoor), store
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

- **LeadDetails** -- job postings with status tracking (open/hunting/closed), enhanced dedup fields (external_job_id, city, employer_linkedin_url, employer_website)
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

## Production Deployment (VPS)

### Server Details

| Item | Value |
|------|-------|
| **Host** | `187.124.74.175` (Hostinger, Ubuntu 24.04, 4 vCPU, 16GB RAM, 193GB disk) |
| **Domain** | `ra.partnerwithus.tech` |
| **SSL** | Let's Encrypt (auto-renews via `certbot.timer`) |
| **SSH** | `root@187.124.74.175` (password auth — see `~/.ssh/habib-hostinger/secrets.txt`) |
| **Linux user** | `ra-user` (runs app services) |
| **App directory** | `/opt/exzelon-ra-agent/` |
| **Git branch** | `master` (single branch) |
| **GitHub repo** | `sdasgarali/exzelon_ra_agent` |

### Services

| Service | Unit Name | Port | Command | Notes |
|---------|-----------|------|---------|-------|
| Backend API | `exzelon-api` | 8000 | `systemctl restart exzelon-api` | 4 uvicorn workers, logs to journald |
| Frontend | `exzelon-web` | 3000 | `systemctl restart exzelon-web` | Next.js production, logs to journald |
| Reverse Proxy | `nginx` | 80/443 | `systemctl reload nginx` | SSL termination, security headers |
| Database | `mysql` | 3306 | `systemctl restart mysql` | User: `ra_user`, DB: `exzelon_ra_agent` |
| Cache | `redis-server` | 6379 | `systemctl restart redis-server` | Currently unused by app (reserved) |

### Directory Layout (VPS)

```
/opt/exzelon-ra-agent/
├── backend/
│   ├── .env                  # Backend config (DB creds, API keys, secrets)
│   ├── venv/                 # Python 3.11 virtual environment
│   ├── app/                  # FastAPI application
│   └── requirements.txt
├── frontend/
│   ├── .env.local            # NEXT_PUBLIC_API_URL (NOT in git — must exist)
│   ├── .next/                # Build output
│   └── node_modules/
├── data/
│   └── backups/              # Database backup .sql.gz files
├── deploy/
│   ├── deploy.sh             # Self-contained deployment script
│   ├── nginx.conf            # Nginx config template
│   ├── vps_ssh.sh            # SSH helper for non-interactive access
│   └── systemd/
│       ├── exzelon-api.service
│       └── exzelon-web.service
└── scripts/                  # Migration and utility scripts
```

### Deploy Steps (Automated)

The self-contained deploy script handles everything:

```bash
# On VPS directly:
bash /opt/exzelon-ra-agent/deploy/deploy.sh

# From local machine via SSH:
./deploy/vps_ssh.sh "bash /opt/exzelon-ra-agent/deploy/deploy.sh"
```

The script performs: git pull → pip install → npm build → restart services → health checks.

### Deploy Steps (Manual)

If the deploy script is unavailable, run these steps on the VPS:

```bash
# 1. Pull latest code
cd /opt/exzelon-ra-agent && git pull origin master

# 2. Backend: install deps
cd /opt/exzelon-ra-agent/backend && source venv/bin/activate && pip install -r requirements.txt

# 3. Frontend: rebuild
cd /opt/exzelon-ra-agent/frontend && npm run build

# 4. Restart services
systemctl restart exzelon-api exzelon-web

# 5. Verify
systemctl status exzelon-api exzelon-web
curl -s https://ra.partnerwithus.tech/health
```

### Critical: Frontend `.env.local`

The frontend **requires** `/opt/exzelon-ra-agent/frontend/.env.local` with:
```
NEXT_PUBLIC_API_URL=https://ra.partnerwithus.tech/api/v1
```
Without this, `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000/api/v1`, which works for SSR but fails for browser-side API calls. This file is **NOT in git** — the deploy script auto-creates it if missing.

### Database Migrations

Migrations are **auto-applied on app startup** via `main.py` lifespan hooks (ad-hoc `ALTER TABLE` statements at lines 214-318). No Alembic yet. After adding a new migration hook:
1. Add the migration in `backend/app/main.py` inside the `lifespan()` function
2. Deploy normally — the migration runs when `exzelon-api` restarts
3. Verify: `journalctl -u exzelon-api --since "5 min ago" | grep -i migrat`

### Systemd Service Files

Version-controlled in `deploy/systemd/`. To install or update on VPS:
```bash
cp /opt/exzelon-ra-agent/deploy/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl restart exzelon-api exzelon-web
```

### Nginx Config

Template in `deploy/nginx.conf`. To update on VPS:
```bash
cp /opt/exzelon-ra-agent/deploy/nginx.conf /etc/nginx/sites-available/ra-app
# Replace YOUR_DOMAIN with ra.partnerwithus.tech
sed -i 's/YOUR_DOMAIN/ra.partnerwithus.tech/g' /etc/nginx/sites-available/ra-app
nginx -t && systemctl reload nginx
```

### Viewing Logs

```bash
journalctl -u exzelon-api -f              # Backend logs (live)
journalctl -u exzelon-web -f              # Frontend logs (live)
journalctl -u exzelon-api --since "1h ago" # Last hour
journalctl -u nginx -f                    # Nginx access/error
```

### SSH Access from Local Machine

```bash
# Interactive SSH (requires password):
ssh -o PubkeyAuthentication=no root@187.124.74.175

# Non-interactive (from scripts — uses askpass):
DISPLAY=:0 SSH_ASKPASS=/tmp/vps_askpass.sh ssh -o PubkeyAuthentication=no root@187.124.74.175 "command" < /dev/null

# Using the helper script:
./deploy/vps_ssh.sh "command to run on VPS"
```

### Rollback

To rollback to a previous commit:
```bash
cd /opt/exzelon-ra-agent
git log --oneline -10           # Find the commit to rollback to
git checkout <commit-hash>      # Detached HEAD at that commit
# Then rebuild and restart as normal
cd frontend && npm run build
systemctl restart exzelon-api exzelon-web
```

## Mandatory Update Table

When you make changes in these categories, you **MUST** update the corresponding files:

| Change Type | Files to Update |
|-------------|----------------|
| **New DB migration / ALTER TABLE** | `backend/app/main.py` (lifespan hook), this section of CLAUDE.md |
| **New DB table / model** | `backend/app/db/models/`, `db/base.py` imports, Key Data Models section above |
| **New API endpoint** | `backend/app/api/endpoints/`, `api/router.py`, API docs auto-update |
| **New dashboard module/page** | `frontend/src/app/dashboard/`, navigation in `layout.tsx`, MODULES constant in roles page |
| **New settings tab** | `SETTINGS_TAB_MAP` in `backend/app/api/deps/auth.py`, frontend Settings page |
| **Deploy script change** | `deploy/deploy.sh`, this CLAUDE.md Deployment section |
| **New systemd service** | `deploy/systemd/`, this CLAUDE.md Services table |
| **Nginx config change** | `deploy/nginx.conf`, apply on VPS via instructions above |
| **New environment variable** | `backend/.env`, `.env.example`, `core/config.py`, document in Environment Setup |
| **New npm/pip dependency** | `requirements.txt` or `package.json`, note rationale in commit message |
| **New RBAC module** | DEFAULT_PERMISSIONS in roles page, MODULES array, backend permission checks |
| **Infrastructure change** | `deploy/` directory, CLAUDE.md Deployment section, `Plan_WIP.md` notes |
