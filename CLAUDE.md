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
- **Auth**: JWT tokens with refresh token rotation — 30-min access tokens + 7-day refresh tokens. POST `/auth/refresh` exchanges refresh token for new token pair. Frontend auto-refreshes silently on 401. Includes `tenant_id` + `plan` claims. `TenantInfo` schema in auth responses includes `industry` for tenant-aware frontend logic. Argon2 password hashing, RBAC with 4 roles: super_admin, admin, operator, viewer. Password policy: min 8 chars, 1 uppercase, 1 digit, 1 special character. Account lockout: 5 failed attempts → 15 min lockout. Super admin bypasses all role checks and can impersonate tenants via `X-Tenant-ID` header. Dependencies in `api/deps/auth.py` (`get_current_tenant_id()` extracts tenant context). Multi-tenant: each user belongs to a tenant, email verification required for new signups.
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
- **Per-contact timezone-aware send windows**: `_is_within_send_window()` checks contact's timezone (from `ContactDetails.timezone`), falls back to campaign timezone
- **Smart send scheduling**: `_advance_to_next_step()` uses `calculate_optimal_send_time()` to schedule next email at optimal local business hours (9-11 AM = best)
- **Preview mode**: When `campaign.preview_mode=True`, generates OutreachDraft records instead of sending — enables human review via Email Preview page
- **Lead-selection creation**: `POST /campaigns/from-leads` auto-generates campaign name, 3-step sequence (outreach + wait + followup), assigns all active mailboxes, enrolls contacts from selected leads
- **Step modal template integration**: Sequence tab step modal loads templates via `templatesApi.list()`, grouped dropdown (Outreach/Follow-up) with active templates starred. Auto-loads active template matching **current tenant's industry** for first email step (outreach) and subsequent steps (followup), falling back to global active template if no industry match. Inline spam check + deliverability score buttons with results panel

### Unified Inbox (`services/inbox_syncer.py`)

Centralized reply management:
- Syncs OutreachEvents into inbox_messages table
- Thread grouping via Message-ID chain or email+subject hash
- AI sentiment analysis on received messages (rule-based + LLM fallback)
- AI reply suggestions from conversation context
- Category labels: interested, not_interested, ooo, question, referral, do_not_contact

### AI Sales Agent (`services/ai_sales_agent/`)

Autonomous, policy-constrained AI layer governing all outbound sends and reply handling:
- **Orchestrator** (`orchestrator.py`) -- Two entry points: `orchestrate_send()` (gates outbound emails), `orchestrate_reply()` (classifies inbound + determines next action). Wired into `campaign_engine.py` and `ai_reply_agent_service.py`.
- **Policy Engine** (`policy_engine.py`) -- Deterministic rules: send policy (INVALID_EMAIL, UNSUBSCRIBED, INACTIVE, NEGATIVE_REPLY), reply policy (LOW_CONFIDENCE, DESTRUCTIVE_ACTION), content policy (spam score, similarity, length). 15 configurable defaults, per-tenant overrides via settings.
- **Scoring Engine** (`scoring_engine.py`) -- Lead scoring (hiring signals, company size, industry, salary, web presence), engagement scoring (replies, clicks, opens → cold/warm/hot/dead), composite score (40% lead + 40% engagement + 20% priority).
- **Reply Intelligence** (`reply_intelligence.py`) -- 2-tier classification: LLM first (via `ai_resilience.call_ai_with_fallback`) → keyword fallback. Intent categories: interested, objection, question, ooo, unsubscribe. Next-best-action planner (rule-based).
- **Send Decision** (`send_decision.py`) -- Combines policy + content + scoring into structured go/no-go decision with reason codes.
- **Prompt Registry** (`prompt_registry.py`) -- Named, versioned prompt templates (reply_classification, reply_draft, next_best_action, personalization_plan) replacing inline strings.
- **Context Builder** (`agent_context.py`) -- Aggregates contact, lead, company, campaign, history, scores into unified context dict.
- **Draft Intelligence** (`draft_intelligence.py`) -- Personalization planning per step number (angle, tone, hooks, CTA type).
- **Learning Engine** (`learning_engine.py`) -- Records send outcomes to automation_events, queries campaign performance stats. Wired into `inbox_syncer.py`.
- **Schemas** -- `SendDecision`, `PersonalizationPlan`, `InteractionSummary` in `ai_schemas.py`

### CRM Deal Pipeline (`api/endpoints/deals.py`)

Kanban-style deal tracking:
- 7 default stages (New Lead → Won/Lost), auto-seeded on startup
- Pipeline view grouped by stage for frontend Kanban board
- Deal stats: win rate, avg deal size, pipeline value
- Activity timeline per deal

### Billing & Invoicing (`services/billing/`)

Complete billing module with invoice lifecycle management:
- **Invoice Generator** (`invoice_generator.py`) -- INV-YYYY-NNNN numbering, auto-generates monthly invoices for tenants with `monthly_price_cents > 0`, duplicate prevention, tax calculation
- **PDF Generator** (`pdf_generator.py`) -- Professional PDF invoices via reportlab (company header, line items, totals). Stored in `data/invoices/{tenant_id}/`
- **Payment Gateway** (`payment_gateway.py`) -- Abstract `PaymentGateway` interface with `StripeGateway` and `ManualGateway`. Factory: `get_payment_gateway()` returns Stripe if `STRIPE_SECRET_KEY` set
- **Billing Mailer** (`billing_mailer.py`) -- 3 email types: new invoice (with PDF), overdue reminder, payment acknowledgement
- **Scheduler Jobs** -- `job_generate_monthly_invoices` (1st at 2AM), `job_check_overdue_invoices` (daily 6AM), `job_send_overdue_reminders` (daily 9AM)
- **Business rules**: Invoices generated on 1st, due on 5th (`INVOICE_DUE_DAY`), reminders every 3 days (`INVOICE_REMINDER_INTERVAL_DAYS`), max 5 reminders
- **Config**: `BILLING_ENABLED`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY`, `BILLING_COMPANY_*`, `BILLING_TAX_RATE_DEFAULT`, `INVOICE_*`

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
4. **Outreach** -- AI-generate email content, enforce rate limits and cooldowns, send (supports `preview_mode` parameter to generate drafts instead of sending)

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

- **Tenant** -- multi-tenant organization with TenantPlan enum (starter/professional/enterprise), plan limits (max_users, max_mailboxes, max_contacts, max_campaigns, max_leads), unique slug, `website` (URL), `industry` (saas/recruiting/healthcare/ecommerce/finance/general)
- **User** -- users with tenant_id FK, email verification (is_verified, verification_token, verification_sent_at), account lockout (failed_login_count, locked_until), tenant relationship
- **LeadDetails** -- job postings with status tracking (open/hunting/closed), enhanced dedup fields (external_job_id, city, employer_linkedin_url, employer_website)
- **ContactDetails** -- decision-makers with priority levels (P1 job poster through P5 functional manager)
- **LeadContactAssociation** -- many-to-many junction table
- **ClientInfo** -- companies/organizations, `timezone` column auto-resolved from `location_state` via `timezone_resolver.py`
- **SenderMailbox** -- email accounts with daily limits, health scores, warmup status
- **OutreachEvent** -- email events (sent/opened/clicked/replied/bounced), with campaign_id/step_id/variant_index
- **WarmupProfile** -- warmup templates (Conservative 45d, Standard 30d, Aggressive 20d)
- **Campaign** -- multi-step email campaigns with status, send window, timezone, mailbox assignment, slow ramp (enabled/increment/day), auto-pause thresholds (bounce/spam), AI auto-reply (enabled/delay/max), assignment mode (manual/round_robin/weighted), preview_mode (Boolean, generates drafts instead of sending)
- **SequenceStep** -- campaign steps (email/wait/condition/sms/linkedin/call) with delay, A/B variants, stats, optional template_id FK linking to source EmailTemplate
- **EmailTemplate** -- reusable email templates with category (outreach/followup), status (active/inactive), subject, body_html, body_text, industry/goal targeting, is_system flag for seeded library; one active template per category per tenant
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
- **Invoice** -- monthly invoices with INV-YYYY-NNNN numbering, period dates, status lifecycle (draft→sent→paid/overdue), tax, PDF path, reminder tracking
- **InvoiceLineItem** -- line items (subscription/addon/credit/tax/discount) within an invoice
- **PaymentRecord** -- payment records against invoices (stripe/manual/bank_transfer/check/card), with status tracking
- **LoginHistory** -- every login attempt (success/failure) with email, IP, user agent, failure reason (invalid_credentials/inactive/unverified/locked), multi-index for analytics
- **ReplyMacro** -- quick reply templates for inbox (title, body, category, variable substitution, usage tracking)
- **AIReplyDraft** -- AI Reply Agent drafts for HITL/Autopilot approval (thread_id, intent_detected, confidence_score, status: pending/approved/rejected/auto_sent)
- **ObjectionTemplate** -- AI objection handling templates (objection_type, response, effectiveness_score, system vs user-created)
- **CalendarBooking** -- calendar booking tracking (Calendly/Cal.com integration, scheduling, status tracking)
- **CreditUsage** -- credit/usage metering per tenant (usage_type, credits_used, reference tracking)
- **GoalTarget** -- KPI goal tracking (metric targets: leads/emails/deals/revenue, period tracking)
- **NotificationEntry** -- notification center entries (category, priority, link, read status, per-user/broadcast)
- **OutreachDraft** -- email drafts for preview & approve workflow (contact_id, lead_id, campaign_id, step_id, mailbox_id, subject, body_html, original_subject, original_body_html, status: pending/approved/rejected/sent/expired, source: campaign/pipeline/broadcast, spam_score, spam_grade, flagged_words_json, deliverability_score, ai_rewritten, batch_id, variant_index)

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

### Roadmap Phase Services (Instantly.ai Parity + Beyond)

| Service | File | Purpose |
|---------|------|---------|
| AI Reply Agent | `services/ai_reply_agent_service.py` | HITL + Autopilot auto-reply (intent detection, AI draft generation, auto-send queue) |
| Auto-Pause Monitor | `services/auto_pause_monitor.py` | Hourly campaign health check, auto-pause on bounce/spam threshold breach |
| Forecast Engine | `services/forecast_engine.py` | AI-powered deal pipeline forecasting (win rate, weighted pipeline, monthly projections) |
| Visitor Tracker | `services/visitor_tracker.py` | Website visitor tracking (JS pixel, page visit recording, visitor stats) |
| Intent Data | `services/intent_data.py` | Buying intent scoring (hiring signals, recency, company size, industry, salary) |
| Objection Handler | `services/objection_handler.py` | AI objection handling library (7 system templates, seed + CRUD) |
| Lead Assigner | `services/lead_assigner.py` | Round-robin lead assignment across team members |
| DFY Service | `services/dfy_service.py` | Done-For-You setup (domain suggestions, DNS instructions, warmup estimation) |
| Credit Metering | `services/credit_metering.py` | Usage tracking and credit metering per tenant |
| IP Rotation | `services/ip_rotation.py` | SISR — dedicated IP pool management and rotation for high-volume sending |
| Email Preview | `services/email_preview_service.py` | Draft generation (campaign/pipeline/broadcast), AI rewriting, composite deliverability scoring (DNS+spam+blacklist+reputation), spam word detection with AI replacement suggestions, approval workflow, batch send |

### Enterprise Safety & AI Governance Services

| Service | File | Purpose |
|---------|------|---------|
| Security Headers | `middleware/security_headers.py` | X-Frame-Options, CSP, HSTS, X-Content-Type-Options, Referrer-Policy, Permissions-Policy on all responses |
| Domain Throttle | `services/domain_throttle.py` | Per-recipient-domain daily send caps (gmail.com: 30/day, general: 50/day, configurable via settings) |
| AI Safety | `services/ai_safety.py` | Prompt injection defense — sanitize inbound email content, strip injection patterns, delimiter wrapping |
| Content Fingerprint | `services/content_fingerprint.py` | Jaccard similarity on word-level 3-shingles to detect near-identical emails, Shannon entropy scoring for content variability |
| AI Schemas | `services/ai_schemas.py` | Pydantic structured output schemas for all AI tasks (ReplyClassification, DraftEmailResponse, SpamCheckResult, NextBestAction) + JSON parsing |
| AI Audit Logger | `services/ai_audit_logger.py` | Logs every AI decision to automation_events (prompt hash, confidence, action taken, gating reason, tokens, latency) |
| Campaign Safety | `services/campaign_safety.py` | Job idempotency guard, company-level contact cap (5/company), smart pause on reply, sequence fatigue detection (5 unanswered in 90d), cross-campaign contact dedup |
| AI Resilience | `services/ai_resilience.py` | Retry with exponential backoff (3 attempts, 1s→2s→4s) + provider fallback chain (primary→secondary→rule-based) |
| Rate Limiter | `core/rate_limiter.py` | Shared slowapi limiter — auth (5/min login, 5/hr signup), pipelines (5/hr run), email-preview (10/hr generate, 20/hr rewrite), billing (3/hr bulk), campaigns (20/hr enroll) |
| Spam Checker | `services/spam_checker.py` | 106 trigger words + 6 regex patterns + link/image ratio detection (>2 links, any images, link-to-text ratio penalized) |
| Job Lock | `core/job_lock.py` | MySQL advisory lock (`GET_LOCK`/`RELEASE_LOCK`) context manager — prevents duplicate job execution across Uvicorn workers. Used by 7 scheduler jobs: campaign_processor, lead_sourcing, outreach_replies, daily_count_reset, inbox_sync, monthly_invoices, auto_enrollment |
| State Machine | `core/state_machine.py` | Lead + Campaign status transition validation. `CAMPAIGN_STATUS_TRANSITIONS`: draft→active/archived, active→paused/completed/archived, paused→active/archived/completed, completed→archived, archived=terminal |
| **Send Gate** | `services/send_gate.py` | Centralized send safety — `unified_send_gate()` runs 10 ordered checks before any email send. All 4 send paths (Campaign Engine, Pipeline Outreach, Email Preview, AI Reply Agent) call this gate. Returns structured `SendGateResult` with machine-readable `reason_code` and user-friendly `reason_message`. Checks: contact status → suppression → email validation → contact+lead cooldown (cross-channel) → contact cooldown → per-lead contact limit → company cap → sequence fatigue → domain throttle → AI orchestrator. `is_reply=True` skips cooldown/fatigue/AI. `dry_run=True` skips domain throttle/AI. Old `check_send_eligibility()` in `outreach.py` deprecated (kept for mail-merge CSV export only). |

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
| `/admin/tenants` | `api/endpoints/admin_tenants.py` | Super admin tenant management (list, detail, update, deactivate, impersonate). Tenant update supports `website` + `industry` fields |
| `/billing` | `api/endpoints/billing.py` | Invoice CRUD, bulk generation, mark-paid, PDF download, Stripe checkout, webhook, stats, tenant self-service |
| `/activity` | `api/endpoints/activity_log.py` | Login history (paginated, filterable), 24h stats, auth audit events, active users, my-login-history, unlock user. Super admin only (except my-login-history) |
| `/onboarding` | `api/endpoints/onboarding.py` | 6-step onboarding status (auto-detected from data), dismiss, reset (super admin). Per-user dismiss, tenant-filtered queries |
| `/reply-macros` | `api/endpoints/reply_macros.py` | Reply macro CRUD + usage tracking for inbox quick templates |
| `/notifications` | `api/endpoints/notifications.py` | Notification center (list, unread-count, mark-read, mark-all-read) |
| `/calendar` | `api/endpoints/calendar.py` | Calendar booking CRUD + stats |
| `/credits` | `api/endpoints/credits.py` | Credit usage tracking (usage list, summary, balance) |
| `/goals` | `api/endpoints/goals.py` | Goal/KPI target CRUD + progress tracking |
| `/visitors` | `api/endpoints/visitor_tracking.py` | Website visitor tracking (pixel.js, track endpoint, stats, sessions) |
| `/sms` | `api/endpoints/sms.py` | SMS outreach via Twilio (send, status check) |
| `/objections` | `api/endpoints/objections.py` | AI objection template CRUD + seed + use-counter |
| `/dfy` | `api/endpoints/dfy.py` | Done-For-You setup (domain suggestions, DNS setup, warmup estimates) |
| `/templates` | `api/endpoints/templates.py` | Email template CRUD, activate, preview, duplicate, seed-library, import-to-step (copies template content to campaign sequence step). List response includes `active_outreach_template_id` + `active_followup_template_id` |
| `/email-preview` | `api/endpoints/email_preview.py` | Draft generation, CRUD, approve/reject, batch send, AI rewrite, deliverability score, spam check + AI suggestions, spam fix (13 endpoints) |
| `/clients/backfill-timezones` | `api/endpoints/clients.py` | Backfill IANA timezone from location_state for all clients missing timezone (Admin+) |
| `/campaigns/available-leads` | `api/endpoints/campaigns.py` | Leads not in active campaigns (posted within N days), with contact counts for campaign creation |
| `/campaigns/from-leads` | `api/endpoints/campaigns.py` | Create campaign from selected leads: auto-name, 3-step sequence, mailbox assignment, contact enrollment |
| `/campaigns/{id}/contact-schedule` | `api/endpoints/campaigns.py` | Timezone-aware contact send schedule ordered East→West with optimal send times |
| `/campaigns/{id}/ai-enhance` | `api/endpoints/campaigns.py` | LLM-based campaign name/description improvement with rule-based fallback |
| `/campaigns/{id}/ai-suggest-subjects` | `api/endpoints/campaigns.py` | LLM-based subject line generation (5 A/B variants) with rule-based fallback |

### User Onboarding System

- **Getting Started Widget**: 6-step visual checklist shown above dashboard when setup is incomplete (mailboxes → leads → contacts → validation → campaigns → deals)
- **Auto-detection**: Each step checks `COUNT > 0` against tenant's data (no manual flags to get out of sync)
- **Per-user dismiss**: `onboarding_dismissed_at` column on User model — each user controls their own view
- **Interactive Tour**: driver.js spotlight walkthrough (~10 steps), auto-launches on first visit (localStorage `tour_completed` flag)
- **Help button**: Floating `?` button (bottom-right) replays the tour anytime
- **Viewer excluded**: Getting Started widget only shows for admin/operator/super_admin roles
- **Files**: `api/endpoints/onboarding.py`, `components/getting-started.tsx`, `hooks/use-tour.ts`, `lib/tour-config.ts`

### Multi-Tenancy Architecture

- **All 39 data models** have `tenant_id` column (NOT NULL, FK to `tenants.tenant_id`, indexed)
- **All 29 endpoint files** use `get_current_tenant_id` dependency + `tenant_filter` query helper
- **Super admin** (`tenant_id=None`) sees all tenants' data; regular users see only their tenant
- **Super admin impersonation**: `X-Tenant-ID` header or `/admin/tenants/{id}/impersonate` endpoint
- **Plan limits**: `check_plan_limit()` in `api/deps/plan_limits.py` — enforced at CREATE endpoints
- **Demo seeder**: `services/demo_seeder.py` — seeds sample data for new starter-plan tenants on email verify
- **Tenant cleanup**: Scheduler job at 3 AM UTC — deactivates empty tenants, deletes unverified users >72h old
- **Ad-hoc migrations**: Phase 2-4 migration blocks in `main.py` lifespan (ALTER TABLE + backfill + NOT NULL + INDEX)

## Auto-Invoked Skills (MANDATORY)

The following project skills MUST be automatically invoked when their trigger conditions are met. Do NOT skip these — invoke via `/sales-draft-outreach` or the Skill tool before responding.

| Skill | Trigger Conditions | File |
|-------|-------------------|------|
| `sales-draft-outreach` | Any outreach-related task (see triggers below) | `.claude/commands/sales-draft-outreach.md` |

### sales-draft-outreach — Trigger Conditions

**ALWAYS invoke this skill when ANY of the following occur:**

1. **Direct requests**: User says "draft outreach", "write cold email", "reach out to", "draft email to", "write email to", "LinkedIn message to", "contact [person]", "outreach to [company]"
2. **Pipeline outreach stage**: Working on Pipeline Stage 4 (Outreach) — AI email content generation, campaign email drafting, sequence step creation
3. **Campaign email creation**: Creating or editing email content for campaigns, sequence steps, A/B test variants, or email templates meant for prospect communication
4. **Contact follow-up**: Drafting follow-up emails, re-engagement messages, or post-event outreach for any contact
5. **AI content generation**: When `ai_content.py`, `ai_sequence_generator.py`, or `campaign_engine.py` logic is being discussed or modified for email personalization
6. **Inbox reply drafting**: Composing replies to inbound messages in the unified inbox that are outreach-oriented (not internal)
7. **Code changes to outreach modules**: When modifying `services/pipelines/outreach.py`, `services/campaign_engine.py`, `services/ai_sequence_generator.py`, `api/endpoints/sequence_generator.py`, or email template logic — use the skill's email style guidelines as the quality standard

**The skill provides**: Research-first methodology, AIDA email structure, hook prioritization, plain-text formatting rules, anti-patterns to avoid, channel selection logic, and follow-up sequence templates.

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
5. For billing: set `BILLING_ENABLED=true`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `BILLING_COMPANY_NAME`, `BILLING_COMPANY_EMAIL` in `.env`

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

Migrations are **auto-applied on app startup** via `main.py` lifespan hooks (ad-hoc `ALTER TABLE` statements). No Alembic yet. Latest migration: `preview_mode` TINYINT(1) column on `campaigns` table. `outreach_drafts` table auto-created via `create_all`. After adding a new migration hook:
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
| **Billing plan pricing change** | `backend/app/db/models/tenant.py` (monthly_price_cents), billing docs in this section |
| **Outreach email content/logic** | Follow `.claude/commands/sales-draft-outreach.md` skill guidelines (AIDA structure, plain text, no markdown in emails) |
| **Infrastructure change** | `deploy/` directory, CLAUDE.md Deployment section, `Plan_WIP.md` notes |
