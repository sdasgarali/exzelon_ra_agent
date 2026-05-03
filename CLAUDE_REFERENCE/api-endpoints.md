# API Endpoints — Exzelon RA Agent

> Referenced from: `CLAUDE.md` — Read this when adding/modifying API endpoints or understanding available routes.

## Core CRUD Endpoints (via `api/router.py`)

All endpoints are mounted under `/api/v1`.

| Prefix | File | Purpose |
|--------|------|---------|
| `/auth` | `auth.py` | Login, signup, verify email, resend verification, refresh token |
| `/leads` | `leads.py` | Lead CRUD, bulk operations |
| `/contacts` | `contacts.py` | Contact CRUD, bulk operations, unsubscribe, `POST /reset-test-data` (super_admin — clears outreach/enrollment/suppression for is_test contacts) |
| `/clients` | `clients.py` | Client/company CRUD, backfill-timezones |
| `/mailboxes` | `mailboxes.py` | Mailbox CRUD, health check |
| `/campaigns` | `campaigns.py` | Campaign CRUD, sequence steps, enrollment, schedules |
| `/inbox` | `inbox.py` | Unified inbox, threads, reply, mark-read |
| `/deals` | `deals.py` | Deal CRUD, pipeline view, stats |
| `/settings` | `settings.py` | App settings, role permissions |
| `/users` | `users.py` | User management, role assignment |
| `/pipelines` | `pipelines.py` | Pipeline stage execution (sourcing/enrichment/validation/outreach) |
| `/warmup` | `warmup.py` | Warmup profiles, DNS checks, blacklist monitoring |
| `/webhooks` | `webhooks.py` | Webhook subscription CRUD |
| `/api-keys` | `api_keys.py` | API key CRUD |

## Extended Endpoints

| Prefix | File | Purpose |
|--------|------|---------|
| `/auth/signup` | `auth.py` | Self-service signup (creates tenant + admin user, sends verification email) |
| `/auth/verify` | `auth.py` | Email verification via JWT token |
| `/auth/resend-verification` | `auth.py` | Resend verification email (200 always, prevents enumeration) |
| `/analytics` | `analytics.py` | Team leaderboard, campaign comparison, revenue metrics, cost tracking |
| `/icp` | `icp_wizard.py` | ICP generation + profile CRUD |
| `/leads/ai-search` | `lead_search.py` | Natural language lead search |
| `/saved-searches` | `saved_searches.py` | Saved search/smart list CRUD + execute |
| `/sequence-generator` | `sequence_generator.py` | AI email sequence generation |
| `/crm-sync` | `crm_sync.py` | Manual CRM sync trigger + history |
| `/deals/{id}/tasks` | `deal_tasks.py` | Deal task CRUD + my-tasks |
| `/spam-check` | `spam_check.py` | Email spam score checking |
| `/tracking-domains` | `tracking_domains.py` | Custom tracking domain CRUD + verify |

## Admin & Billing Endpoints

| Prefix | File | Purpose |
|--------|------|---------|
| `/admin/tenants` | `admin_tenants.py` | Super admin tenant management (list, detail, update, deactivate, impersonate). Tenant update supports `website` + `industry` fields |
| `/billing` | `billing.py` | Invoice CRUD, bulk generation, mark-paid, PDF download, Stripe checkout, webhook, stats, tenant self-service |
| `/activity` | `activity_log.py` | Login history, 24h stats, auth audit, active users, my-login-history, unlock user (Super admin except my-login-history) |

## Feature Endpoints

| Prefix | File | Purpose |
|--------|------|---------|
| `/onboarding` | `onboarding.py` | 6-step onboarding status (auto-detected), dismiss, reset |
| `/reply-macros` | `reply_macros.py` | Reply macro CRUD + usage tracking |
| `/notifications` | `notifications.py` | Notification center (list, unread-count, mark-read, mark-all-read) |
| `/calendar` | `calendar.py` | Calendar booking CRUD + stats |
| `/credits` | `credits.py` | Credit usage tracking (list, summary, balance) |
| `/goals` | `goals.py` | Goal/KPI target CRUD + progress tracking |
| `/visitors` | `visitor_tracking.py` | Website visitor tracking (pixel.js, track endpoint, stats, sessions) |
| `/sms` | `sms.py` | SMS outreach via Twilio (send, status check) |
| `/objections` | `objections.py` | AI objection template CRUD + seed + use-counter |
| `/dfy` | `dfy.py` | Done-For-You setup (domain suggestions, DNS setup, warmup estimates) |
| `/templates` | `templates.py` | Email template CRUD, activate, preview, duplicate, seed-library, import-to-step |
| `/email-preview` | `email_preview.py` | Draft generation, CRUD, approve/reject, batch send, AI rewrite, deliverability score, spam check + AI suggestions, spam fix (13 endpoints) |

## Campaign-Specific Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/campaigns/available-leads` | Leads not in active campaigns with contact counts |
| `/campaigns/from-leads` | Create campaign from selected leads (auto-name, 3-step sequence, mailbox assignment, contact enrollment) |
| `/campaigns/{id}/schedules` | Campaign schedule CRUD (GET list, POST add, PUT update, DELETE remove) |
| `/campaigns/{id}/contact-schedule` | Timezone-aware contact send schedule (East -> West) |
| `/campaigns/{id}/ai-enhance` | LLM-based campaign name/description improvement |
| `/campaigns/{id}/ai-suggest-subjects` | LLM-based subject line generation (5 A/B variants) |
