# Data Models — Exzelon RA Agent

> Referenced from: `CLAUDE.md` — Read this when working with database models, creating migrations, or understanding data relationships.

## Core Models

- **Tenant** — multi-tenant organization with TenantPlan enum (**free/pro/max/custom** — renamed 2026-09 from starter/professional/enterprise, which remain as enum aliases; migration `0002_plan_rename_and_max_lobs`), plan limits (max_users, max_mailboxes, max_contacts, max_campaigns, max_leads, **max_lobs**). **Limit columns are `0` = "not configured, use the plan's number" and `>0` = explicit per-tenant limit — never "unlimited"**; the real numbers live in `core/plans.py` (`PLAN_MATRIX`) and resolve via `limits_for_tenant()`. Only `plan=custom` treats these columns as authoritative (floored at Max). Also: unique slug, `website` (URL), `industry` (saas/recruiting/healthcare/ecommerce/finance/general)
- **User** — users with tenant_id FK, email verification (is_verified, verification_token, verification_sent_at), account lockout (failed_login_count, locked_until), tenant relationship. `role` is a **VARCHAR(50)** (migrated from a MySQL ENUM in 2026-08) so custom, settings-backed roles can be assigned alongside the built-in `UserRole` values `super_admin/admin/bdm/recruiter` (renamed from `operator`/`viewer`). Legacy values are normalized via `LEGACY_ROLE_ALIASES`/`role_value()` in `api/deps/auth.py`. Custom roles live in the per-tenant `custom_roles` setting (see `services/role_registry.py`) and each declares a built-in `base_role`. Notification preferences: `notify_inapp_enabled` / `notify_email_enabled` (Boolean, NOT NULL, default True) — GLOBAL master toggles gating every in-app (bell) notification / notification email for the user. Edited by admins in the Users form or self-service at `/dashboard/profile` (`PATCH /auth/me/notification-preferences`).

## Lead & Contact Models

- **LeadDetails** — job postings with status tracking (open/hunting/closed), enhanced dedup fields (external_job_id, city, employer_linkedin_url, employer_website)
- **ContactDetails** — decision-makers with priority levels (P1 job poster through P5 functional manager). **Required NOT NULL fields**: `client_name`, `first_name`, `last_name`. `is_test` (Boolean, default False) — test contacts bypass send gate cooldown/fatigue checks (4-8) and allow campaign re-enrollment.
- **LeadContactAssociation** — many-to-many junction table
- **ClientInfo** — companies/organizations, `timezone` column auto-resolved from `location_state` via `timezone_resolver.py`

## Campaign & Communication Models

- **Campaign** — multi-step email campaigns with status, send window, timezone, mailbox assignment, slow ramp (enabled/increment/day), auto-pause thresholds (bounce/spam), AI auto-reply (enabled/delay/max), assignment mode (manual/round_robin/weighted), preview_mode (Boolean)
- **CampaignSchedule** — date-range-aware schedule entries per campaign (schedule_id, campaign_id, tenant_id, start_date YYYY-MM-DD, end_date nullable, send_window_start/end, send_days_json, timezone, schedule_order, label). Multiple entries per campaign; CASCADE delete
- **SequenceStep** — campaign steps (email/wait/condition/sms/linkedin/call) with delay, A/B variants, stats, optional template_id FK
- **EmailTemplate** — reusable email templates with category (outreach/followup), status (active/inactive), subject, body_html, body_text, industry/goal targeting, is_system flag; one active per category per tenant
- **CampaignContact** — contact enrollment tracking with current_step, next_send_at, status
- **SenderMailbox** — email accounts with daily limits, health scores, warmup status. `outreach_role_id` FK → `OutreachRole`; `user_id` FK → `User` (personal/non-RA mailboxes link 1:1 to a login user; RA/machine mailboxes have none).
- **OutreachRole** — tenant-scoped mailbox role (RA/BDM/Recruiter, seeded per tenant). `auto_outbound` (bool): mailboxes with an `auto_outbound` role (RA) are the ONLY ones auto-selected for automated cold outbound AND are machine senders with no login user; non-flag roles are personal mailboxes (manual send, linked to a `User`). See `services/mailbox_user_link.py` + `services/mailbox_selector.py`.
- **OutreachEvent** — email events (sent/opened/clicked/replied/bounced), with campaign_id/step_id/variant_index. **Required**: `channel` (OutreachChannel enum)
- **OutreachDraft** — email drafts for preview & approve workflow (contact_id, lead_id, campaign_id, step_id, mailbox_id, subject, body_html, status: pending/approved/rejected/sent/expired, source: campaign/pipeline/broadcast, spam_score, deliverability_score, ai_rewritten, batch_id, variant_index)

## Inbox & Reply Models

- **InboxMessage** — unified inbox messages with thread_id, direction, category, sentiment
- **ReplyMacro** — quick reply templates for inbox (title, body, category, variable substitution, usage tracking)
- **AIReplyDraft** — AI Reply Agent drafts for HITL/Autopilot approval (thread_id, intent_detected, confidence_score, status: pending/approved/rejected/auto_sent)
- **ObjectionTemplate** — AI objection handling templates (objection_type, response, effectiveness_score, system vs user-created)

## CRM Models

- **Deal** — CRM deals with value, probability, stage, contact/client associations. `owner_id` = admin-ASSIGNED owner; `claimed_by_user_id`+`claimed_at` = the rep who CLAIMED it from the queue (NULL = Unclaimed). Age is derived live from `created_at`. See `services/deal_notifications.py` (forward new unclaimed deals to reps) and the `/deals` claim endpoints.
- **DealStage** — pipeline stages (New Lead, Contacted, Qualified, Proposal, Negotiation, Won, Lost)
- **DealTask** — task management within deals (assignee, due date, priority, status)
- **CRMSyncLog** — bidirectional CRM sync operation logging (direction, entity type, records synced)

## Billing Models

- **Invoice** — monthly invoices with INV-YYYY-NNNN numbering, period dates, status lifecycle (draft->sent->paid/overdue), tax, PDF path, reminder tracking
- **InvoiceLineItem** — line items (subscription/addon/credit/tax/discount) within an invoice
- **PaymentRecord** — payment records against invoices (stripe/manual/bank_transfer/check/card), with status tracking

## Infrastructure & Config Models

- **Webhook** — webhook subscriptions with URL, HMAC secret, event filter
- **ApiKey** — API key auth with SHA-256 hash, scopes, expiry
- **WarmupProfile** — warmup templates (Conservative 45d, Standard 30d, Aggressive 20d)
- **AutomationEvent** — system activity log (scheduler runs, AI classifications, campaign sends)
- **TrackingDomain** — custom tracking domains (domain, CNAME verification, default flag)
- **SavedSearch** — saved lead filter sets (smart lists) with sharing support
- **CostEntry** — cost tracking for revenue/ROI analytics (category, amount, date). `category` ∈ {lead_sourcing, contact_discovery, validation, sending, ai}; `amount` is `DECIMAL(12,6)` so sub-cent per-call AI/token costs are not truncated. Auto-recorded by `cost_tracker.record_pipeline_cost()` (job boards + contact discovery) and `record_ai_cost()` (LLM token cost).
- **ICPProfile** — AI-generated Ideal Customer Profiles (industries, job titles, states, company sizes)
- **SuppressionList** — suppressed email addresses/domains

## User Activity & Analytics Models

- **LoginHistory** — every login attempt (success/failure) with email, IP, user agent, failure reason (invalid_credentials/inactive/unverified/locked)
- **CalendarBooking** — calendar booking tracking (Calendly/Cal.com integration, scheduling, status)
- **TenantCreditBalance** — authoritative per-tenant credit counter (`tenant_credit_balances`, UQ on tenant_id; migration `0003`). Columns: `period_start`, `allowance_credits` (monthly grant, resets on the 1st, no rollover), `topup_credits` (purchased, NEVER expire, spent only after the allowance), `period_spent`, `lifetime_spent`, `lifetime_purchased`. Locked with `with_for_update()` during `spend()` — this is the ELR-009b fix for the sum-then-check race. A tenant's first row is seeded with the plan allowance MINUS the ledger's month-to-date, so shipping this doesn't grant a free refill.
- **CreditUsage** — credit/usage metering per tenant (usage_type, credits_used, reference tracking). Monthly allowance per plan comes from `PLAN_MATRIX` via `credit_metering.plan_credit_limit()`; `CREDIT_LIMIT_{FREE,PRO,MAX}_OVERRIDE` are deployment-only overrides (0 = use the matrix). NOTE: `record_usage()` is still wired at only one call site (`sms.py`) — instrumenting the rest is Phase 2.3.
- **GoalTarget** — KPI goal tracking (metric targets: leads/emails/deals/revenue, period tracking)
- **NotificationEntry** — notification center entries (category, priority, link, read status, per-user/broadcast)
- **TenantLOBAssignment** — maps which LOB types each tenant can access (`tenant_lob_assignments` table: tenant_id FK, lob_type String(50), assigned_by, UQ(tenant_id, lob_type)). Super Admin managed. Backward compatible: no records = all LOBs visible.

## Key Relationships

- All 40 models have `tenant_id` column (NOT NULL, FK to `tenants.tenant_id`, indexed)
- Lead <-> Contact is many-to-many via `LeadContactAssociation`
- Campaign -> SequenceStep -> OutreachEvent (hierarchical)
- Campaign -> CampaignContact -> ContactDetails (enrollment)
- Campaign -> CampaignSchedule (one-to-many, CASCADE)
- Deal -> DealStage (FK), Deal -> DealTask (one-to-many)
- Invoice -> InvoiceLineItem (one-to-many, CASCADE)
- Invoice -> PaymentRecord (one-to-many)
