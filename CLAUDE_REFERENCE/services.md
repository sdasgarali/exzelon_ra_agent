# Services — Exzelon RA Agent

> Referenced from: `CLAUDE.md` — Read this when working on any backend service or understanding system behavior.

---

## Campaign Engine (`services/campaign_engine.py`)

Multi-step email sequence processor:
- Processes campaign queue every 2 minutes (scheduler job)
- Supports email, wait, and condition (if/then branching) steps
- A/B testing with weighted variant assignment + chi-squared auto-optimize
- Spintax text variation (`{option1|option2}`) with nested pattern support
- Round-robin mailbox selection from campaign's assigned mailboxes
- Handles replies, bounces, and unsubscribes per campaign contact
- **Per-contact timezone-aware send windows**: `_is_within_send_window()` checks contact's timezone (from `ContactDetails.timezone`), falls back to campaign timezone
- **Smart send scheduling**: `_advance_to_next_step()` uses `calculate_optimal_send_time()` to schedule next email at optimal local business hours (9-11 AM = best)
- **Preview mode**: When `campaign.preview_mode=True`, generates OutreachDraft records instead of sending
- **Lead-selection creation**: `POST /campaigns/from-leads` auto-generates campaign name, 3-step sequence, assigns all active mailboxes, enrolls contacts
- **Step modal template integration**: Sequence tab step modal loads templates via `templatesApi.list()`, grouped dropdown (Outreach/Follow-up) with active templates starred. Auto-loads active template matching current tenant's industry

---

## Unified Inbox (`services/inbox_syncer.py`)

Centralized reply management:
- Syncs OutreachEvents into inbox_messages table
- Thread grouping via Message-ID chain or email+subject hash
- AI sentiment analysis on received messages (rule-based + LLM fallback)
- AI reply suggestions from conversation context
- Category labels: interested, not_interested, ooo, question, referral, do_not_contact

---

## AI Sales Agent (`services/ai_sales_agent/`)

Autonomous, policy-constrained AI layer governing all outbound sends and reply handling:

| Component | File | Purpose |
|-----------|------|---------|
| Orchestrator | `orchestrator.py` | Two entry points: `orchestrate_send()` (gates outbound), `orchestrate_reply()` (classifies inbound). Wired into campaign_engine + ai_reply_agent_service |
| Policy Engine | `policy_engine.py` | Deterministic rules: send policy (INVALID_EMAIL, UNSUBSCRIBED, INACTIVE, NEGATIVE_REPLY), reply policy (LOW_CONFIDENCE, DESTRUCTIVE_ACTION), content policy (spam score, similarity, length). 15 configurable defaults, per-tenant overrides |
| Scoring Engine | `scoring_engine.py` | Lead scoring (hiring signals, company size, industry, salary, web presence), engagement scoring (replies, clicks, opens -> cold/warm/hot/dead), composite score (40% lead + 40% engagement + 20% priority) |
| Reply Intelligence | `reply_intelligence.py` | 2-tier classification: LLM first -> keyword fallback. Intent categories: interested, objection, question, ooo, unsubscribe. Next-best-action planner (rule-based) |
| Send Decision | `send_decision.py` | Combines policy + content + scoring into structured go/no-go decision with reason codes |
| Prompt Registry | `prompt_registry.py` | Named, versioned prompt templates (reply_classification, reply_draft, next_best_action, personalization_plan) |
| Context Builder | `agent_context.py` | Aggregates contact, lead, company, campaign, history, scores into unified context dict |
| Draft Intelligence | `draft_intelligence.py` | Personalization planning per step number (angle, tone, hooks, CTA type) |
| Learning Engine | `learning_engine.py` | Records send outcomes to automation_events, queries campaign performance stats |
| Schemas | `ai_schemas.py` | `SendDecision`, `PersonalizationPlan`, `InteractionSummary` |

---

## CRM Deal Pipeline (`api/endpoints/deals.py`)

Kanban-style deal tracking:
- 7 default stages (New Lead -> Won/Lost), auto-seeded on startup
- Pipeline view grouped by stage for frontend Kanban board
- Deal stats: win rate, avg deal size, pipeline value
- Activity timeline per deal

---

## Billing & Invoicing (`services/billing/`)

Complete billing module with invoice lifecycle management:

| Component | File | Purpose |
|-----------|------|---------|
| Invoice Generator | `invoice_generator.py` | INV-YYYY-NNNN numbering, auto-generates monthly, duplicate prevention, tax calculation |
| PDF Generator | `pdf_generator.py` | Professional PDF invoices via reportlab. Stored in `data/invoices/{tenant_id}/` |
| Payment Gateway | `payment_gateway.py` | Abstract interface with StripeGateway and ManualGateway. Factory: `get_payment_gateway()` |
| Billing Mailer | `billing_mailer.py` | 3 email types: new invoice (with PDF), overdue reminder, payment acknowledgement |

Scheduler: `job_generate_monthly_invoices` (1st at 2AM), `job_check_overdue_invoices` (daily 6AM), `job_send_overdue_reminders` (daily 9AM).

Config: `BILLING_ENABLED`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY`, `BILLING_COMPANY_*`, `BILLING_TAX_RATE_DEFAULT`, `INVOICE_*`

---

## Webhook System (`services/webhook_dispatcher.py`)

Event-driven webhook delivery:
- HMAC-SHA256 signed payloads with `X-Webhook-Signature` header
- Events: email.sent, email.opened, email.clicked, email.replied, email.bounced, contact.unsubscribed, campaign.completed, lead.created
- Exponential backoff retry (3 attempts: 1min, 5min, 15min)

---

## Pipeline Pattern (`services/pipelines/`)

Four sequential data-processing stages, each independently executable via API:

1. **Lead Sourcing** — fetch jobs from boards, normalize, 3-layer deduplicate (external_job_id -> employer_linkedin -> company+title+state+city), sub-source tracking. Supports configurable per-adapter tuning (`job_source_tuning` setting), adapter result limit (`pipeline_adapter_limit`), and thread pool size (`pipeline_max_workers`) — all managed via Settings → Source Tuning tab.
2. **Contact Enrichment** — discover decision-makers via Apollo/Seamless/Hunter/Snov.io/RocketReach/PDL/Proxycurl
3. **Email Validation** — verify email addresses before sending
4. **Outreach** — AI-generate email content, enforce rate limits and cooldowns, send (supports `preview_mode`)

---

## Warmup Engine (`services/warmup/`)

Domain reputation management subsystem:
- Peer-to-peer warmup emails between mailboxes
- Auto-reply to warmup emails (AI-generated via Groq)
- DNS checking (SPF/DKIM/DMARC)
- IP/domain blacklist monitoring
- Open/click tracking via pixel and link redirect (endpoints in `main.py`: `/t/{id}/px.gif`, `/t/{id}/l`)
- APScheduler-based automation (`scheduler.py`)

---

## Additional Services (Phase 5)

| Service | File | Purpose |
|---------|------|---------|
| Mailbox Selector | `services/mailbox_selector.py` | Health-aware mailbox selection (score = health*0.4 + quota*0.3 + warmup_age*0.15 + deliverability*0.15) |
| AI Lead Search | `services/ai_lead_search.py` | NLP query parsing -> SQL filter dict |
| Spam Checker | `services/spam_checker.py` | 106 trigger words + 6 regex patterns + link/image ratio detection |
| AI ICP Wizard | `services/ai_icp_wizard.py` | AI-generated Ideal Customer Profiles with rule-based fallback |
| AI Sequence Generator | `services/ai_sequence_generator.py` | AI email sequence generation with template fallback |
| CRM Sync Engine | `services/crm_sync_engine.py` | Bidirectional HubSpot/Salesforce sync |
| CRM Auto-Forward | `services/crm_auto_forward.py` | Auto-forward interested inbox replies to CRM |
| IMAP Reader | `services/warmup/imap_reader.py` | Read emulation for warmup |
| LOB Defaults | `core/lob_defaults.py` | Shared LOB_DEFAULT_CONFIGS, LOB_TYPE_META, TENANT_PROMPT_PROFILES (used by main.py seeding, admin_tenants.py provisioning, lob.py type listing) |

---

## Roadmap Phase Services

| Service | File | Purpose |
|---------|------|---------|
| AI Reply Agent | `services/ai_reply_agent_service.py` | HITL + Autopilot auto-reply |
| Auto-Pause Monitor | `services/auto_pause_monitor.py` | Hourly campaign health check, auto-pause on threshold breach |
| Forecast Engine | `services/forecast_engine.py` | AI-powered deal pipeline forecasting |
| Visitor Tracker | `services/visitor_tracker.py` | Website visitor tracking (JS pixel, page visits, stats) |
| Intent Data | `services/intent_data.py` | Buying intent scoring — `calculate_intent_score()` (v1, flat weights) + `calculate_intent_score_v2()` (LOB-aware, 5 weight profiles, 4-tier: Cold/Warm/Hot/Burning) |
| Intent Engine | `services/intent_engine.py` | Central orchestrator — `run_intent_engine()` runs signal checks + batch LOB-aware score recalculation, stores results in `metadata_json` |
| Intent Signal Monitor | `services/intent_signal_monitor.py` | Trigger-based prospecting — 7 signal types (npi, funding, pagespeed, tech_stack, github, hiring, news), `check_intent_signals()` creates leads from signal matches |
| Objection Handler | `services/objection_handler.py` | AI objection handling library (7 system templates) |
| Lead Assigner | `services/lead_assigner.py` | Round-robin lead assignment |
| DFY Service | `services/dfy_service.py` | Done-For-You setup |
| Credit Metering | `services/credit_metering.py` | Usage tracking per tenant |
| IP Rotation | `services/ip_rotation.py` | Dedicated IP pool management |
| Email Preview | `services/email_preview_service.py` | Draft generation, AI rewriting, deliverability scoring, approval workflow |

---

## Enterprise Safety & AI Governance

| Service | File | Purpose |
|---------|------|---------|
| Security Headers | `middleware/security_headers.py` | X-Frame-Options, CSP, HSTS, X-Content-Type-Options, Referrer-Policy, Permissions-Policy |
| Domain Throttle | `services/domain_throttle.py` | Per-recipient-domain daily send caps (gmail: 30/day, general: 50/day) |
| AI Safety | `services/ai_safety.py` | Prompt injection defense — sanitize inbound email content |
| Content Fingerprint | `services/content_fingerprint.py` | Jaccard similarity on word-level 3-shingles + Shannon entropy |
| AI Schemas | `services/ai_schemas.py` | Pydantic structured output schemas for all AI tasks + JSON parsing |
| AI Audit Logger | `services/ai_audit_logger.py` | Logs every AI decision to automation_events |
| Campaign Safety | `services/campaign_safety.py` | Job idempotency, company-level contact cap, smart pause, sequence fatigue, cross-campaign dedup |
| AI Resilience | `services/ai_resilience.py` | Retry with exponential backoff + provider fallback chain |
| Rate Limiter | `core/rate_limiter.py` | Shared slowapi limiter — auth, pipelines, email-preview, billing, campaigns |
| Job Lock | `core/job_lock.py` | MySQL advisory lock — prevents duplicate job execution across workers |
| State Machine | `core/state_machine.py` | Lead + Campaign status transition validation |
| **Send Gate** | `services/send_gate.py` | Centralized send safety — `unified_send_gate()` runs 10 ordered checks. All 4 send paths wired. Checks: contact status -> suppression -> email validation -> cooldown -> per-lead limit -> company cap -> sequence fatigue -> domain throttle -> AI orchestrator. **Test contacts** (`is_test=True`) skip checks 4-8 (cooldown, fatigue, caps) like replies do. |

---

## Email Deliverability Services

| Service | File | Purpose |
|---------|------|---------|
| Bounce Handler | `services/bounce_handler.py` | SMTP 5xx auto-suppress + contact INACTIVE |
| ESP Feedback | `services/esp_feedback.py` | Complaint rate tracking, auto-pause on 0.3% threshold |
| AI Personalizer | `services/ai_personalizer.py` | Per-contact AI email rewriting at send time — `personalize_email_for_contact()` uses configured AI adapter to rewrite emails with contact profile data. Controlled by `ai_personalize_emails` and `ai_personalization_prompt` settings. Graceful fallback on failure. |
| Email Humanizer | `services/email_humanizer.py` | Anti-AI detection (burstiness, sentence variation) |
| DKIM Signer | `services/dkim_signer.py` | Optional DKIM for custom SMTP |
| Engagement Tracker | `services/engagement_tracker.py` | Multi-signal scoring (reply > click > pixel) |
| Send-Time Optimizer | `services/send_time_optimizer.py` | US state -> timezone, optimal business-hours windows |
| Rendering Checker | `services/rendering_checker.py` | Email client compatibility warnings |

---

## User Onboarding System

- **Getting Started Widget**: 6-step visual checklist (mailboxes -> leads -> contacts -> validation -> campaigns -> deals)
- **Auto-detection**: Each step checks `COUNT > 0` against tenant's data
- **Per-user dismiss**: `onboarding_dismissed_at` column on User model
- **Interactive Tour**: driver.js spotlight walkthrough (~10 steps), auto-launches on first visit
- **Help button**: Floating `?` button (bottom-right) replays tour
- **Viewer excluded**: Only shows for admin/operator/super_admin
- **Files**: `api/endpoints/onboarding.py`, `components/getting-started.tsx`, `hooks/use-tour.ts`, `lib/tour-config.ts`
