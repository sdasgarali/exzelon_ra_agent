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
- **Auth**: JWT tokens (7-day expiry, includes `tenant_id` + `plan`), Argon2 password hashing, RBAC with 4 roles: super_admin, admin, operator, viewer. Super admin bypasses all role checks and can impersonate tenants via `X-Tenant-ID` header. Dependencies in `api/deps/auth.py` (`get_current_tenant_id()` extracts tenant context). Multi-tenant: each user belongs to a tenant, email verification required for new signups.
- **Database**: SQLAlchemy 2.0 ORM, models in `db/models/`, base class in `db/base.py`. Auto-creates tables on startup. MySQL (`exzelon_ra_agent` on localhost:3306) is the active database. SQLite used for testing.

### Adapter Pattern (`services/adapters/`)

All external integrations implement abstract base classes from `adapters/base.py`. Provider selection is driven by `.env` settings. Each category has a `mock` adapter for development/testing.

| Category | Adapters | Config key |
|---|---|---|
| Job Sources | Apollo, JSearch, TheirStack, SerpAPI (Google Jobs), Adzuna, SearchAPI, USAJobs, Jooble, JobDataFeeds, Coresignal | `JOB_SOURCES`, `JSEARCH_API_KEY`, `THEIRSTACK_API_KEY`, `SERPAPI_API_KEY`, `ADZUNA_APP_ID`+`ADZUNA_API_KEY`, `SEARCHAPI_API_KEY`, `USAJOBS_API_KEY`+`USAJOBS_EMAIL`, `JOOBLE_API_KEY`, `JOBDATAFEEDS_API_KEY`, `CORESIGNAL_API_KEY` |
| Contact Discovery | Apollo, Seamless, Hunter.io, Snov.io, RocketReach, People Data Labs, Proxycurl | `CONTACT_PROVIDER`, `HUNTER_CONTACT_API_KEY`, `SNOVIO_CLIENT_ID`+`SNOVIO_CLIENT_SECRET`, `ROCKETREACH_API_KEY`, `PDL_API_KEY`, `PROXYCURL_API_KEY` |
| Company Enrichment | Clearbit (Breeze), OpenCorporates | `CLEARBIT_API_KEY`, `OPENCORPORATES_API_KEY` |
| Email Validation | NeverBounce, ZeroBounce, Hunter, Clearout, Emailable, MailboxValidator, Reacher | `EMAIL_VALIDATION_PROVIDER` |
| Email Sending | SMTP, Mock | `EMAIL_SEND_MODE` |
| AI Content | Groq, OpenAI, Anthropic, Gemini | per-adapter API keys, shared factory in `adapters/ai_content.py` |
| CRM | HubSpot, Salesforce | `HUBSPOT_API_KEY`, `SALESFORCE_CLIENT_ID` |
| Notifications | Slack, Microsoft Teams | Webhook URLs in settings |
| Communications | Twilio (SMS + Calling) | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` |

### Campaign Engine (`services/campaign_engine.py`)

Multi-step email sequence processor:
- Processes campaign queue every 2 minutes (scheduler job)
- Supports email, wait, and condition (if/then branching) steps
- A/B testing with weighted variant assignment + chi-squared auto-optimize
- Spintax text variation (`{option1|option2}`) with nested pattern support
- Round-robin mailbox selection from campaign's assigned mailboxes
- Handles replies, bounces, and unsubscribes per campaign contact
- Timezone-aware send windows using contact's US state

### Unified Inbox (`services/inbox_syncer.py`)

Centralized reply management:
- Syncs OutreachEvents into inbox_messages table
- Thread grouping via Message-ID chain or email+subject hash
- AI sentiment analysis on received messages (rule-based + LLM fallback)
- AI reply suggestions from conversation context
- Category labels: interested, not_interested, ooo, question, referral, do_not_contact

### CRM Deal Pipeline (`api/endpoints/deals.py`)

Kanban-style deal tracking:
- 7 default stages (New Lead → Won/Lost), auto-seeded on startup
- Pipeline view grouped by stage for frontend Kanban board
- Deal stats: win rate, avg deal size, pipeline value
- Activity timeline per deal

### Webhook System (`services/webhook_dispatcher.py`)

Event-driven webhook delivery:
- HMAC-SHA256 signed payloads with `X-Webhook-Signature` header
- Events: email.sent, email.opened, email.clicked, email.replied, email.bounced, contact.unsubscribed, campaign.completed, lead.created
- Exponential backoff retry (3 attempts: 1min, 5min, 15min)

### Pipeline Pattern (`services/pipelines/`)

Four sequential data-processing stages, each independently executable via API:
1. **Lead Sourcing** -- fetch jobs from boards, normalize, 3-layer deduplicate (external_job_id → employer_linkedin → company+title+state+city), sub-source tracking (LinkedIn/Indeed/Glassdoor), store
2. **Contact Enrichment** -- discover decision-makers via Apollo/Seamless/Hunter/Snov.io/RocketReach/PDL/Proxycurl
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

- **Tenant** -- multi-tenant organization with TenantPlan enum (starter/professional/enterprise), plan limits (max_users, max_mailboxes, max_contacts, max_campaigns, max_leads), unique slug
- **User** -- users with tenant_id FK, email verification (is_verified, verification_token, verification_sent_at), tenant relationship
- **LeadDetails** -- job postings with status tracking (open/hunting/closed), enhanced dedup fields (external_job_id, city, employer_linkedin_url, employer_website)
- **ContactDetails** -- decision-makers with priority levels (P1 job poster through P5 functional manager)
- **LeadContactAssociation** -- many-to-many junction table
- **ClientInfo** -- companies/organizations
- **SenderMailbox** -- email accounts with daily limits, health scores, warmup status
- **OutreachEvent** -- email events (sent/opened/clicked/replied/bounced), with campaign_id/step_id/variant_index
- **WarmupProfile** -- warmup templates (Conservative 45d, Standard 30d, Aggressive 20d)
- **Campaign** -- multi-step email campaigns with status, send window, timezone, mailbox assignment
- **SequenceStep** -- campaign steps (email/wait/condition) with delay, A/B variants, stats
- **CampaignContact** -- contact enrollment tracking with current_step, next_send_at, status
- **InboxMessage** -- unified inbox messages with thread_id, direction, category, sentiment
- **Deal** -- CRM deals with value, probability, stage, contact/client associations
- **DealStage** -- pipeline stages (New Lead, Contacted, Qualified, Proposal, Negotiation, Won, Lost)
- **Webhook** -- webhook subscriptions with URL, HMAC secret, event filter
- **ApiKey** -- API key auth with SHA-256 hash, scopes, expiry
- **AutomationEvent** -- system activity log (scheduler runs, AI classifications, campaign sends) for user transparency
- **TrackingDomain** -- custom tracking domains for email deliverability (domain, CNAME verification, default flag)
- **SavedSearch** -- saved lead filter sets (smart lists) with sharing support
- **CostEntry** -- cost tracking for revenue/ROI analytics (category, amount, date)
- **ICPProfile** -- AI-generated Ideal Customer Profiles (industries, job titles, states, company sizes)
- **DealTask** -- task management within deals (assignee, due date, priority, status)
- **CRMSyncLog** -- bidirectional CRM sync operation logging (direction, entity type, records synced)

### Additional Services (Phase 5 — "Beat Instantly" Features)

| Service | File | Purpose |
|---------|------|---------|
| Mailbox Selector | `services/mailbox_selector.py` | Health-aware mailbox selection (score = health*0.4 + quota*0.3 + warmup_age*0.15 + deliverability*0.15) |
| AI Lead Search | `services/ai_lead_search.py` | NLP query parsing → SQL filter dict for natural language lead search |
| Spam Checker | `services/spam_checker.py` | 100+ trigger words + pattern matching, score 0-100 |
| AI ICP Wizard | `services/ai_icp_wizard.py` | AI-generated Ideal Customer Profiles with rule-based fallback |
| AI Sequence Generator | `services/ai_sequence_generator.py` | AI email sequence generation with template fallback |
| CRM Sync Engine | `services/crm_sync_engine.py` | Bidirectional HubSpot/Salesforce sync (pull contacts, push deals) |
| CRM Auto-Forward | `services/crm_auto_forward.py` | Auto-forward interested inbox replies to CRM |
| IMAP Reader | `services/warmup/imap_reader.py` | Read emulation for warmup (marks peer emails as read via IMAP) |

### Additional API Endpoints

| Prefix | File | Purpose |
|--------|------|---------|
| `/auth/signup` | `api/endpoints/auth.py` | Self-service signup (creates tenant + admin user, sends verification email) |
| `/auth/verify` | `api/endpoints/auth.py` | Email verification via JWT token |
| `/auth/resend-verification` | `api/endpoints/auth.py` | Resend verification email (200 always, prevents enumeration) |
| `/analytics` | `api/endpoints/analytics.py` | Team leaderboard, campaign comparison, revenue metrics, cost tracking |
| `/icp` | `api/endpoints/icp_wizard.py` | ICP generation + profile CRUD |
| `/leads/ai-search` | `api/endpoints/lead_search.py` | Natural language lead search |
| `/saved-searches` | `api/endpoints/saved_searches.py` | Saved search/smart list CRUD + execute |
| `/sequence-generator` | `api/endpoints/sequence_generator.py` | AI email sequence generation |
| `/crm-sync` | `api/endpoints/crm_sync.py` | Manual CRM sync trigger + history |
| `/deals/{id}/tasks` | `api/endpoints/deal_tasks.py` | Deal task CRUD + my-tasks |
| `/spam-check` | `api/endpoints/spam_check.py` | Email spam score checking |
| `/tracking-domains` | `api/endpoints/tracking_domains.py` | Custom tracking domain CRUD + verify |
| `/admin/tenants` | `api/endpoints/admin_tenants.py` | Super admin tenant management (list, detail, update, deactivate, impersonate) |

### Multi-Tenancy Architecture

- **All 38 data models** have `tenant_id` column (NOT NULL, FK to `tenants.tenant_id`, indexed)
- **All 28 endpoint files** use `get_current_tenant_id` dependency + `tenant_filter` query helper
- **Super admin** (`tenant_id=None`) sees all tenants' data; regular users see only their tenant
- **Super admin impersonation**: `X-Tenant-ID` header or `/admin/tenants/{id}/impersonate` endpoint
- **Plan limits**: `check_plan_limit()` in `api/deps/plan_limits.py` — enforced at CREATE endpoints
- **Demo seeder**: `services/demo_seeder.py` — seeds sample data for new starter-plan tenants on email verify
- **Tenant cleanup**: Scheduler job at 3 AM UTC — deactivates empty tenants, deletes unverified users >72h old
- **Ad-hoc migrations**: Phase 2-4 migration blocks in `main.py` lifespan (ALTER TABLE + backfill + NOT NULL + INDEX)

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
