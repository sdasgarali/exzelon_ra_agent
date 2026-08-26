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
| `/deals` | `deals.py` | Deal CRUD, pipeline (Kanban) view, stats. **Claim queue**: `POST /{id}/claim` (BDM/Recruiter self-pull of an unclaimed deal), `/{id}/unclaim` (claimer or admin), `/{id}/assign` (admin → owner=a BDM/Recruiter). `GET /deals` filters: `stage_id`, `value_op/value_val[/2]`, `probability_op/probability_val[/2]`, `created_from/to`, `claimed_by` (id\|unclaimed\|me), `search`, `mine`. Deal dict adds `claimed_by{name,initials}`, `owner`, `is_unclaimed`, `age_days`. New unclaimed deals are forwarded to reps via `services/deal_notifications.py`; assigning a deal to a user notifies that assignee (in-app + email) via `notify_deal_assigned`, gated by the assignee's `notify_inapp_enabled` / `notify_email_enabled` toggles. **Deal detail 360**: `GET /{id}` also returns `job` (via contact→lead), `resource_pool` {external_ref, ats_url}, `candidate_count`; `GET/POST/PUT/DELETE /{id}/candidates[/{cid}]` (DealCandidate submissions: submitted→reviewed→sent_to_client→placed/rejected); `GET /{id}/messages` (mail chain: OutreachEvent+InboxMessage merged, chronological). |
| `/settings` | `settings.py` | App settings, role permissions |
| `/users` | `users.py` | User management, role assignment |
| `/roles` | `roles.py` | Role management (super admin). GET list (built-in + custom); POST/PUT/DELETE custom roles. Per-tenant; writes require an impersonated tenant. Built-ins protected. |
| `/pipelines` | `pipelines.py` | Pipeline stage execution (sourcing/enrichment/validation/outreach) |
| `/warmup` | `warmup.py` | Warmup profiles, DNS checks, blacklist monitoring |
| `/webhooks` | `webhooks.py` | Webhook subscription CRUD |
| `/api-keys` | `api_keys.py` | API key CRUD |

## Extended Endpoints

| Prefix | File | Purpose |
|--------|------|---------|
| `/auth/signup` | `auth.py` | Self-service signup (creates tenant + admin user, sends verification email) |
| `/auth/me/notification-preferences` | `auth.py` | **Self-service** (any active user) `PATCH` of own notification master toggles `notify_inapp_enabled` / `notify_email_enabled` (partial — only provided fields change). Surfaced on `/dashboard/profile`. |
| `/settings/notifications/sender` | `settings.py` | Per-tenant notification **sender** config (admin). `GET` returns email/name/host/port/user/security + `password_set` + `effective_source` (tenant\|global\|none) — never the password. `PUT` upserts (password Fernet-encrypted; blank keeps existing; requires tenant). `POST /settings/notifications/sender/test` sends a test email. Two-segment path avoids the `/settings/{key}` catch-all. Backed by `services/system_mailer.py`. Settings UI tab "11. Notifications". |
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
| `/gdpr` | `gdpr.py` | GDPR data-subject rights (admin, tenant-scoped): `GET /gdpr/export?email=` (Right-to-Access — all PII: contacts, outreach events, inbox, visits, suppression status); `POST /gdpr/erase {email}` (Right-to-Erasure — anonymises contact PII, keeps rows for FK integrity, suppresses the address, audits; requires impersonated tenant) (ELR-024) |

## Admin & Billing Endpoints

| Prefix | File | Purpose |
|--------|------|---------|
| `/admin/tenants` | `admin_tenants.py` | Super admin tenant management (list, detail, update, deactivate, impersonate, branding, features, LOB assignments). GET/PUT `/{id}/lob-assignments` for tenant LOB type control |
| `/billing` | `billing.py` | Invoice CRUD, bulk generation, mark-paid, PDF download, Stripe checkout, webhook, stats, tenant self-service. **Subscriptions (ELR-021)**: `POST /billing/subscription/checkout {plan?}` (Stripe subscription-mode Checkout for the tenant's plan → checkout_url; needs `STRIPE_PRICE_*` set — see `deploy/STRIPE_SUBSCRIPTIONS_SETUP.md`), `GET /billing/subscription` (status), `POST /billing/subscription/cancel` (cancel at period end). Webhook syncs `customer.subscription.*` + refunds/failed-payments/disputes into `subscriptions` + invoices; suspends on non-payment (ELR-023). |
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

## Reports Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /reports/client-analytics` | Per-client KPI breakdown (contacts, leads, sent, replies, bounces, placements, unsubs). Filters: search, industry, client_category, date_from/to. Pagination + export. |
| `GET /reports/campaign-performance` | Per-campaign metrics (denormalized stats + unsub count). Filters: search, status, date range. SQL sort/paginate. |
| `GET /reports/mailbox-health` | Per-mailbox deliverability stats. Filters: search, warmup_status. SQL sort/paginate. |
| `GET /reports/daily-activity` | Time-series sent/opened/replied/bounced. Params: days (7-180), granularity (daily/weekly). Returns series + totals. |
| `GET /reports/contact-engagement` | Per-contact outreach aggregate. Filters: search, client_name, min_emails, has_replied. SQL sort/paginate. |
| `GET /reports/domain-deliverability` | Recipient-domain-level stats. Params: days (7-180). MySQL `SUBSTRING_INDEX` / SQLite `SUBSTR` for domain extraction. |

All reports endpoints require `SUPER_ADMIN`, `ADMIN`, or `OPERATOR` role. All support `export=true` (skip pagination, cap at 10K rows). File: `api/endpoints/reports.py`.

## LOB Endpoints (`api/endpoints/lob.py`)

| Endpoint | Purpose |
|----------|---------|
| `GET /lob/` | List all LOBs for current tenant |
| `POST /lob/` | Create new LOB |
| `GET /lob/types` | List available LOB types with metadata |
| `GET /lob/column-config/{lob_type}` | Per-LOB column configuration for leads table UI |
| `GET /lob/{lob_id}` | Get LOB details |
| `PUT /lob/{lob_id}` | Update LOB |
| `DELETE /lob/{lob_id}` | Soft-delete (archive) LOB |
| `POST /lob/{lob_id}/set-default` | Set LOB as tenant default |
| `GET /lob/{lob_id}/intent-signals` | Returns configured + available intent signals for a LOB with status |
| `POST /lob/{lob_id}/intent-signals/run` | Manually trigger intent engine for a specific LOB, returns summary |

## Settings — LOB Lead Sources Tab

Settings key `lob_lead_sources` tab includes:
- `google_places_api_key` — Google Places API key
- `crunchbase_api_key` — Crunchbase API key
- `builtwith_api_key` — BuiltWith API key
- `github_token` — GitHub personal access token
- `automation_intent_signals_enabled` — Enable/disable scheduled intent signal jobs

Test-connection providers: `npi_registry`, `google_business`, `crunchbase`, `builtwith`, `github_org`, `pagespeed`
