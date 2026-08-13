# Data Models — Exzelon RA Agent

> Referenced from: `CLAUDE.md` — Read this when working with database models, creating migrations, or understanding data relationships.

## Core Models

- **Tenant** — multi-tenant organization with TenantPlan enum (starter/professional/enterprise), plan limits (max_users, max_mailboxes, max_contacts, max_campaigns, max_leads), unique slug, `website` (URL), `industry` (saas/recruiting/healthcare/ecommerce/finance/general)
- **User** — users with tenant_id FK, email verification (is_verified, verification_token, verification_sent_at), account lockout (failed_login_count, locked_until), tenant relationship. `role` is a **VARCHAR(50)** (migrated from a MySQL ENUM in 2026-08) so custom, settings-backed roles can be assigned alongside the built-in `UserRole` values `super_admin/admin/bdm/recruiter` (renamed from `operator`/`viewer`). Legacy values are normalized via `LEGACY_ROLE_ALIASES`/`role_value()` in `api/deps/auth.py`. Custom roles live in the per-tenant `custom_roles` setting (see `services/role_registry.py`) and each declares a built-in `base_role`.

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
- **SenderMailbox** — email accounts with daily limits, health scores, warmup status
- **OutreachEvent** — email events (sent/opened/clicked/replied/bounced), with campaign_id/step_id/variant_index. **Required**: `channel` (OutreachChannel enum)
- **OutreachDraft** — email drafts for preview & approve workflow (contact_id, lead_id, campaign_id, step_id, mailbox_id, subject, body_html, status: pending/approved/rejected/sent/expired, source: campaign/pipeline/broadcast, spam_score, deliverability_score, ai_rewritten, batch_id, variant_index)

## Inbox & Reply Models

- **InboxMessage** — unified inbox messages with thread_id, direction, category, sentiment
- **ReplyMacro** — quick reply templates for inbox (title, body, category, variable substitution, usage tracking)
- **AIReplyDraft** — AI Reply Agent drafts for HITL/Autopilot approval (thread_id, intent_detected, confidence_score, status: pending/approved/rejected/auto_sent)
- **ObjectionTemplate** — AI objection handling templates (objection_type, response, effectiveness_score, system vs user-created)

## CRM Models

- **Deal** — CRM deals with value, probability, stage, contact/client associations
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
- **CreditUsage** — credit/usage metering per tenant (usage_type, credits_used, reference tracking)
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
