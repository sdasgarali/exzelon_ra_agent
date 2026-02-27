# Master Plan - Exzelon RA Cold-Email Automation System

## Vision
Fully automated cold-email outreach system for Exzelon Research Analysts targeting non-IT industries (manufacturing, logistics, healthcare, etc.). The system discovers job postings, enriches contacts, validates emails, and manages outreach campaigns with enterprise-grade mailbox warmup and deliverability management.

---

## Requirements

### Core Pipeline
| ID | Requirement | Status |
|----|-------------|--------|
| REQ-001 | Lead sourcing from job boards (JSearch, Apollo, Indeed) with dedup and filtering | Done |
| REQ-002 | Contact discovery via Apollo/Seamless with priority ranking (P1-P5) | Done |
| REQ-003 | Email validation via NeverBounce/ZeroBounce/Hunter/Clearout/Emailable/Reacher | Done |
| REQ-004 | Outreach pipeline with AI content, rate limits, cooldowns, signature injection | Done |
| REQ-005 | Mailmerge CSV export for manual sending workflows | Done |

### Mailbox & Deliverability
| ID | Requirement | Status |
|----|-------------|--------|
| REQ-006 | Sender mailbox CRUD with daily limits and health scores | Done |
| REQ-007 | Peer-to-peer warmup between mailboxes | Done |
| REQ-008 | Auto-reply to warmup emails (AI via Groq) | Done |
| REQ-009 | DNS health checks (SPF/DKIM/DMARC) | Done |
| REQ-010 | IP/domain blacklist monitoring with auto-recovery | Done |
| REQ-011 | Warmup profiles (Conservative 45d, Standard 30d, Aggressive 20d) | Done |
| REQ-012 | Per-mailbox email signatures with structured form + live preview | Done |

### Admin Panel (Frontend)
| ID | Requirement | Status |
|----|-------------|--------|
| REQ-013 | Auth (login/register) with JWT + RBAC (admin/operator/viewer) | Done |
| REQ-014 | Dashboard with KPIs, trends, charts (Recharts) | Done |
| REQ-015 | Leads management with pagination, filtering, detail view | Done |
| REQ-016 | Contacts management with validation status display | Done |
| REQ-017 | Clients management with category badges | Done |
| REQ-018 | Pipeline execution UI (run/monitor all 4 stages) | Done |
| REQ-019 | Settings page with configurable job titles, industries, exclusions | Done |
| REQ-020 | Warmup dashboard with status, config, schedule, alerts | Done |
| REQ-021 | Mailbox management with signature editor | Done |
| REQ-022 | Outreach management page | Done |
| REQ-023 | Email validation page | Done |

### Infrastructure & Quality
| ID | Requirement | Status |
|----|-------------|--------|
| REQ-024 | Docker Compose (MySQL, Redis, API, Web) | Done |
| REQ-025 | SQLite for local development (zero external deps) | Done |
| REQ-026 | Adapter pattern for all external integrations | Done |
| REQ-027 | 72/72 tests passing (unit + integration + E2E) - 100% pass rate | Done |
| REQ-028 | SOP documentation (991 lines) | Done |
| REQ-029 | APScheduler for background warmup/monitoring jobs | Done |

### Pending
| ID | Requirement | Status |
|----|-------------|--------|
| REQ-030 | Run enrichment pipeline on 612 sourced leads | Pending |
| REQ-031 | Configure real email validation provider with API keys | Pending |
| REQ-032 | Test outreach with real enriched contacts (verify signatures) | Pending |
| REQ-033 | Sync backend DEFAULT_SETTINGS with refined exclude keywords | Pending |
| REQ-034 | Email signature templates/presets for quick setup | Pending |


### Smart Enrichment & Pipeline Selection
| ID | Requirement | Status |
|----|-------------|--------|
| REQ-035 | Smart contact enrichment with per-lead selection and company-level DB caching | In Progress |
| REQ-036 | Lead selection popup for Contact Enrichment pipeline on Pipelines page | In Progress |
| REQ-037 | Lead selection popup for Outreach pipeline on Pipelines page | In Progress |
| REQ-038 | Apollo credit optimization via contact reuse across same-company leads | In Progress |

---

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backend framework | FastAPI | Async, auto OpenAPI docs, Pydantic validation |
| Frontend framework | Next.js 14 (App Router) | SSR, React ecosystem, Tailwind integration |
| ORM | SQLAlchemy 2.0 | Mature, supports SQLite + MySQL seamlessly |
| Auth | JWT (7-day expiry) + Argon2 | bcrypt had Windows compatibility issues |
| External integrations | Adapter pattern with base classes | Swap providers without changing pipeline logic |
| AI content | Multi-provider (Groq/OpenAI/Anthropic/Gemini) | Flexibility, fallback options |
| State management | Zustand + TanStack Query | Lightweight global state + server cache |
| Styling | Tailwind CSS + Radix UI + Lucide icons | Utility-first, accessible primitives |
| Charts | Recharts | React-native, composable, lightweight |
| Task scheduling | APScheduler (BackgroundScheduler) | In-process, no external deps for dev |
| Dev DB | SQLite (file-based) | Zero setup for local development |
| Prod DB | MySQL 8 (via Docker) | Robust, widely deployed |

---

## Milestones & Status

| # | Milestone | Description | Status | Date |
|---|-----------|-------------|--------|------|
| M0 | Scaffold | Repo, Docker, migrations, auth/RBAC | Complete | 2026-01-18 |
| M1 | Leads | lead_details + client_info CRUD + sourcing adapters | Complete | 2026-01-18 |
| M2 | Contacts | Contact enrichment pipeline + provider adapters | Complete | 2026-01-18 |
| M3 | Validation | Email validation pipeline + 7 provider adapters | Complete | 2026-01-18 |
| M4 | Outreach | Mailmerge export + business rules | Complete | 2026-01-18 |
| M5 | Sending | Programmatic sending + rate limiting + event tracking | Complete | 2026-01-18 |
| M6 | Dashboard | KPIs + trends + charts + job run monitoring | Complete | 2026-01-18 |
| M7 | Hardening | Security, audit logs, comprehensive documentation | Complete | 2026-01-18 |
| M8 | Warmup | Peer warmup, auto-reply, DNS checks, blacklist monitor | Complete | 2026-01-24 |
| M9 | Signatures | Per-mailbox email signatures with form + live preview | Complete | 2026-02-12 |
| M10 | Production Readiness | Enrichment run, real validation, outreach test | In Progress | - |

---

## Tech Stack & Integrations

### Backend
- Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic v2
- APScheduler (BackgroundScheduler)
- Argon2 (password hashing), python-jose (JWT)
- dnspython (DNS checks), aiosmtplib/smtplib (email)

### Frontend
- Next.js 14, React 18, TypeScript
- Tailwind CSS, Radix UI, Lucide Icons
- Recharts, React Hook Form + Zod, Zustand, TanStack Query

### External APIs
- JSearch (RapidAPI) - job board aggregation
- Apollo.io - contact discovery + job sourcing
- Seamless.ai - contact discovery
- NeverBounce / ZeroBounce / Hunter / Clearout / Emailable / MailboxValidator / Reacher - email validation
- Groq / OpenAI / Anthropic / Gemini - AI content generation
- Microsoft 365 SMTP/IMAP - email sending/monitoring

### Infrastructure
- Docker Compose (MySQL 8, Redis 7, API, Web)
- SQLite for local dev (zero external dependencies)
- Git on master branch

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Email deliverability (bounces > 2%) | Account suspension | Multi-layer validation, warmup engine, blacklist monitoring |
| API rate limits (JSearch, Apollo) | Pipeline stalls | Configurable delays, retry logic, multiple source fallback |
| Provider API changes | Broken integrations | Adapter pattern isolates each provider behind interface |
| Mailbox reputation damage | Emails go to spam | Conservative warmup profiles, DNS health checks, daily limits |
| Data quality (stale leads) | Wasted outreach | Deduplication, salary threshold, industry/role filtering |
| Single point of failure (SQLite) | Data loss | MySQL for production, regular backups recommended |

---

## Key Business Rules
- Daily send limit: 30 emails per mailbox
- Cooldown: 10 days between emails to same contact
- Max 4 contacts per company per job
- Salary threshold: 0k+ minimum
- 22 non-IT target industries; IT roles and US staffing agencies excluded
- Only contacts with "Valid" email status receive outreach
- Contact priority: P1 (job poster) > P2 (HR/TA) > P3 (HR manager) > P4 (ops leader) > P5 (functional manager)
