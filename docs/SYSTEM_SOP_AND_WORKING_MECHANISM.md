# NeuraLeads AI Agent
# Complete SOP & Internal Working Mechanism Documentation
# Version 2.0 | Last Updated: February 2026

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Module 1: Lead Sourcing Pipeline](#2-module-1-lead-sourcing-pipeline)
3. [Module 2: Contact Enrichment Pipeline](#3-module-2-contact-enrichment-pipeline)
4. [Module 3: Email Validation Pipeline](#4-module-3-email-validation-pipeline)
5. [Module 4: Outreach Pipeline](#5-module-4-outreach-pipeline)
6. [Module 5: Mailbox Management](#6-module-5-mailbox-management)
7. [Module 6: Warmup Engine](#7-module-6-warmup-engine)
8. [Module 7: Peer-to-Peer Warmup & Auto-Reply](#8-module-7-peer-to-peer-warmup--auto-reply)
9. [Module 8: DNS Health & Blacklist Monitoring](#9-module-8-dns-health--blacklist-monitoring)
10. [Module 9: AI Content Generation](#10-module-9-ai-content-generation)
11. [Module 10: Scheduler & Background Jobs](#11-module-10-scheduler--background-jobs)
12. [Module 11: Settings & Configuration](#12-module-11-settings--configuration)
13. [Module 12: Frontend Dashboard](#13-module-12-frontend-dashboard)
14. [Appendix A: Database Schema Reference](#14-appendix-a-database-schema-reference)
15. [Appendix B: API Endpoint Reference](#15-appendix-b-api-endpoint-reference)
16. [Appendix C: File Structure Map](#16-appendix-c-file-structure-map)

---

## 1. System Overview

### 1.1 Architecture

The NeuraLeads AI Agent automates the complete cold outreach pipeline for staffing/recruitment services. It targets non-IT industries (manufacturing, logistics, healthcare, etc.) by discovering job postings, enriching contacts, validating emails, and managing outreach with enterprise-grade mailbox warmup.

**Technology Stack:**
- **Backend:** FastAPI (Python 3.12+), SQLAlchemy ORM, APScheduler
- **Frontend:** Next.js 14, React, Tailwind CSS, Recharts
- **Database:** SQLite (development) / MySQL (production)
- **External APIs:** JSearch (RapidAPI), Apollo.io, Seamless.ai, Groq/OpenAI/Anthropic/Gemini AI
- **Email:** SMTP (Microsoft 365), IMAP for monitoring
- **DNS:** dnspython for SPF/DKIM/DMARC validation

**Ports:**
- Backend API: `http://localhost:8000` (prefix: `/api/v1`)
- Frontend UI: `http://localhost:3000`
- Database: `./data/ra_agent.db` (SQLite)

### 1.2 End-to-End Data Flow

```
Job Boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter)
                    |
                    v
    [1] LEAD SOURCING PIPELINE
        - Multi-source parallel fetching (JSearch, Apollo)
        - Company name normalization
        - Intelligent deduplication
        - Creates LeadDetails (status: NEW)
                    |
                    v
    [2] CONTACT ENRICHMENT PIPELINE
        - Decision-maker discovery (Apollo/Seamless)
        - Priority assignment (P1-P5)
        - Links contacts to leads (one-to-many)
        - Updates lead (status: ENRICHED)
                    |
                    v
    [3] EMAIL VALIDATION PIPELINE
        - Multi-provider validation (NeverBounce, ZeroBounce, etc.)
        - Deduplicates emails before validation
        - Stores validation results with provider details
        - Updates lead (status: VALIDATED)
                    |
                    v
    [4] OUTREACH PIPELINE
        - Eligibility checks (suppression, cooldown, validation)
        - Mail merge CSV export OR direct SMTP sending
        - Rate limiting and daily send caps
        - Records OutreachEvent for each contact
                    |
                    v
    [5] WARMUP ENGINE (parallel)
        - Progressive volume ramp-up (4 phases, 30 days)
        - Peer-to-peer email circulation
        - AI-generated content
        - Auto-reply system (~50% reply rate)
        - DNS/Blacklist monitoring
        - Health scoring and auto-pause/recovery
```

---

## 2. Module 1: Lead Sourcing Pipeline

### 2.1 SOP: Running Lead Sourcing

**Purpose:** Fetch job postings from multiple sources and create lead records for outreach.

**Prerequisites:**
- JSearch API key configured in Settings (RapidAPI)
- Target job titles configured (e.g., HR Manager, Plant Manager)
- Target US states selected
- Exclusion keywords set (IT keywords + staffing keywords)

**Step-by-Step Procedure:**

1. Navigate to **Dashboard > Pipelines**
2. Click **"Run Lead Sourcing"** button
3. The system will:
   a. Fetch jobs from all enabled sources in parallel
   b. Normalize company names (strip legal suffixes: Inc, LLC, Corp, Ltd)
   c. Deduplicate within batch and against existing database
   d. Create new LeadDetails records with status `NEW`
   e. Export results to XLSX (up to 5,000 rows)
4. Monitor progress in the Pipeline Runs table
5. View results in **Dashboard > Leads**

**Expected Output:**
- New leads appear in the Leads page with source attribution
- Pipeline run record shows: inserted count, skipped count, error count
- XLSX export saved in `data/exports/`

**Troubleshooting:**
- If 0 leads returned: Check JSearch API key is valid and has quota remaining
- If many duplicates skipped: Normal behavior - dedup is working correctly
- If API timeout: JSearch batches 4 titles per query to avoid timeouts

### 2.2 Internal Working Mechanism

**File:** `backend/app/services/pipelines/lead_sourcing.py`

**Entry Point:** `run_lead_sourcing_pipeline()`

**Step 1 - Load Configuration:**
- Reads from Settings table: target_job_titles, target_states, exclude_it_keywords, exclude_staffing_keywords, enabled_sources

**Step 2 - Parallel Fetching:**
- Uses ThreadPoolExecutor (max_workers=3)
- Each adapter runs fetch_from_source() independently
- JSearch optimization: Batches 4 titles per query = 9 queries instead of 37, fetches 3 pages per query (30 results each), 30-day posting window

**Step 3 - Company Name Normalization:**
- Remove "The " prefix
- Strip legal suffixes: Inc, LLC, Corp, Ltd, Co, LP, LLP, PC, PLLC
- Remove special characters, lowercase, strip whitespace

**Step 4 - Deduplication:**
- Dedup Key = `normalized_company_name | job_title | state`
- Quality Scoring: contact info (+10), salary (+3), job link (+2), state (+1)
- Database check: unique job_link + normalized company match within 30 days

**Step 5 - Record Creation:**
- Create LeadDetails (status=NEW)
- Pre-populate contact fields if Apollo provided them
- Create/update ClientInfo record
- Track in JobRun

**Lead Count Multipliers (cumulative ~13x):**

| Factor | Before | After | Impact |
|--------|--------|-------|--------|
| Time window | 1 day | 30 days | 3-5x |
| Pages per query | 1 (10 results) | 3 (30 results) | 3x |
| Query batching | 37 queries | 9 batched | Prevents timeouts |
| Industries | 15 | 22 | 1.47x |

---

## 3. Module 2: Contact Enrichment Pipeline

### 3.1 SOP: Running Contact Enrichment

**Purpose:** Discover decision-maker contacts for each lead (HR, Recruiters, Operations managers).

**Prerequisites:**
- Apollo.io or Seamless.ai API key configured in Settings
- Leads exist with status `NEW` (from lead sourcing)

**Step-by-Step Procedure:**

1. Navigate to **Dashboard > Pipelines**
2. Click **"Run Contact Enrichment"**
3. The system will:
   a. Select all leads with status `NEW` and no contact info
   b. Search for decision-makers at each company
   c. Assign priority levels (P1-P5)
   d. Link contacts directly to their originating lead
   e. Update lead status to `ENRICHED`
4. View results in **Dashboard > Contacts** (filter by lead_id)

**Expected Output:**
- Up to 4 contacts per lead (configurable)
- Each contact has: name, title, email, phone, priority level, source
- Lead status changes from `NEW` to `ENRICHED`

### 3.2 Internal Working Mechanism

**File:** `backend/app/services/pipelines/contact_enrichment.py`

**Priority Assignment Logic:**
```
P1 - Job Poster:     Hiring Manager, Talent Acquisition Director
P2 - HR/Recruiter:   Recruiter, HR Coordinator, TA Specialist
P3 - HR Manager:     HR Manager, HRBP, HR Director, VP HR
P4 - Ops Leader:     Operations Manager, Plant Manager, Production Manager
P5 - Functional:     Any other matching title
```

**Contact Discovery Flow:**
1. Load adapter (Apollo or Seamless) from Settings
2. For each lead with status=NEW:
   - Search company name + decision-maker titles + state via API
   - Normalize contact data (name, email, phone, title)
   - Assign priority level based on title matching
   - Check for duplicate email within same lead_id
   - Create ContactDetails linked to lead.lead_id
   - Denormalize first contact to LeadDetails fields
   - Update lead.lead_status = ENRICHED
3. Track results in JobRun

**Apollo API Integration:**
- Endpoint: `POST https://api.apollo.io/v1/mixed_people/search`
- Payload: organization name, person titles, location, per_page limit
- Returns: name, email, phone, title, company for each match

**Per-Lead Contact Linking (Current Schema):**
- ContactDetails.lead_id -> LeadDetails.lead_id (Foreign Key)
- One lead can have multiple contacts (one-to-many relationship)
- Enables per-lead tracking of outreach and validation

---

## 4. Module 3: Email Validation Pipeline

### 4.1 SOP: Running Email Validation

**Purpose:** Verify email deliverability before sending outreach emails.

**Prerequisites:**
- At least one validation provider API key configured
- Contacts exist with email addresses (from enrichment)

**Step-by-Step Procedure:**
1. Navigate to **Dashboard > Validation** or **Dashboard > Pipelines**
2. Click **"Run Validation Pipeline"**
3. System validates all contacts where `validation_status` is NULL
4. View results in **Dashboard > Validation** page

**Validation Status Meanings:**
| Status | Meaning | Action |
|--------|---------|--------|
| **Valid** | Email confirmed deliverable | Safe to send |
| **Invalid** | Email does not exist | Do NOT send |
| **Catch-All** | Server accepts all emails | Use with caution |
| **Unknown** | Could not determine | Manual verification needed |

### 4.2 Internal Working Mechanism

**File:** `backend/app/services/pipelines/email_validation.py`

**Supported Providers (7+):**

| Provider | API Base | Key Features |
|----------|----------|-------------|
| NeverBounce | api.neverbounce.com/v4 | Disposable detection |
| ZeroBounce | api.zerobounce.net/v2 | Spamtrap + abuse detection |
| Hunter | api.hunter.io/v2 | Deliverability scoring |
| Clearout | api.clearout.io/v2 | Catch-all detection |
| Emailable | api.emailable.com/v1 | Fast validation |
| MailboxValidator | api.mailboxvalidator.com/v2 | Detailed sub-status |
| Reacher | api.reacher.email/v0 | Open-source option |

**Validation Flow:**
1. Factory loads configured provider adapter
2. Fetch contacts with validation_status IS NULL
3. Deduplicate by email (case-insensitive)
4. For each unique email: call provider API, map status, store result
5. Update ContactDetails.validation_status for ALL contacts with this email
6. If valid: Update lead.lead_status = VALIDATED
7. Calculate aggregate bounce_rate
8. Track in JobRun (valid, invalid, catch_all, unknown counts)

---

## 5. Module 4: Outreach Pipeline

### 5.1 SOP: Running Outreach

**Purpose:** Send personalized cold emails or generate mail merge exports.

**Two Modes:**

#### Mode A: Mail Merge Export (Recommended for initial campaigns)
1. Navigate to **Dashboard > Outreach**
2. Select mode: **Mailmerge**
3. Click **"Run Outreach"**
4. System generates CSV + mail merge guide in `data/exports/`
5. Use CSV with your email client (Outlook, Gmail)

#### Mode B: Direct SMTP Sending
1. Select mode: **Send** (optionally enable Dry Run)
2. Click **"Run Outreach"**
3. System sends emails via SMTP with rate limiting

### 5.2 Internal Working Mechanism

**File:** `backend/app/services/pipelines/outreach.py`

**Eligibility Checks (per contact):**
1. **Suppression list:** Email not in do-not-contact list
2. **Validation:** Must be "valid" status
3. **Cooldown:** 10 days (default) since last outreach
4. **Per-lead limit:** Max 4 contacts per lead

**Mail Merge Export:**
- Generates CSV: First Name, Last Name, Email, Title, Company, State, Job Title
- Generates plain-text mail merge guide with unsubscribe instructions
- Records OutreachEvent (channel=MAILMERGE) for each contact
- Updates contact.last_outreach_date

**Direct Send:**
- Respects daily send limit (default 30)
- Rate limiting: delay = 60 / rate_limit seconds between sends
- Records OutreachEvent (channel=SMTP, status=SENT/SKIPPED)
- Tracks in JobRun

---

## 6. Module 5: Mailbox Management

### 6.1 SOP: Managing Sender Mailboxes

**Purpose:** Configure email accounts used for warmup and outreach.

**Adding a New Mailbox:**
1. Navigate to **Dashboard > Mailboxes**
2. Click **"Add Mailbox"**
3. Fill in: Email, Display Name, Password (app password), Provider, SMTP settings
4. Click **Save**, then **"Test Connection"**
5. If successful, warmup begins automatically

**Mailbox Lifecycle:**
```
INACTIVE --> [Test Connection: Success] --> WARMING_UP --> [30 days] --> COLD_READY
         --> [7+ days + health >= 80] --> ACTIVE --> [Ready for outreach]

If problems:
ACTIVE/WARMING_UP --> [bounce > 5% OR complaint > 0.3%] --> PAUSED
                  --> [3+ days wait] --> RECOVERING --> [gradual ramp] --> WARMING_UP
```

**Connection Testing:**
- Tests SMTP connectivity (STARTTLS + login)
- Microsoft 365: Requires SMTP AUTH enabled in M365 Admin Center
- Gmail: Requires App Password (2FA must be enabled first)

### 6.2 Internal Working Mechanism

**Files:** `backend/app/api/endpoints/mailboxes.py`, `backend/app/db/models/sender_mailbox.py`

**SenderMailbox Key Fields:**
- Identity: email, display_name, password, provider
- SMTP: smtp_host, smtp_port (default 587)
- Status: warmup_status (enum), is_active, connection_status
- Quotas: daily_send_limit, emails_sent_today, total_emails_sent
- Metrics: bounce_count, reply_count, complaint_count
- Warmup: warmup_started_at, warmup_days_completed, warmup_emails_sent/received/opens/replies
- DNS: dns_score (0-100), is_blacklisted

---

## 7. Module 6: Warmup Engine

### 7.1 SOP: Email Warmup Process

**Purpose:** Gradually build ISP reputation for new mailboxes by progressively increasing email volume over 30 days.

**Why Warmup is Needed:**
- New email accounts have zero reputation with ISPs (Gmail, Outlook, Yahoo)
- Sending too many emails immediately triggers spam filters
- Warmup establishes trust: consistent sending + good engagement = inbox delivery

**Warmup Phases (Default Configuration):**

| Phase | Days | Daily Emails | Purpose |
|-------|------|-------------|---------|
| Phase 1 | Days 1-7 | 2-5 | Initial reputation building |
| Phase 2 | Days 8-14 | 5-15 | Volume growth |
| Phase 3 | Days 15-21 | 15-25 | Capacity building |
| Phase 4 | Days 22-30 | 25-35 | Full ramp-up |

**Health Score Components:**

| Metric | Weight | Good | Bad |
|--------|--------|------|-----|
| Bounce Rate | 35% | <= 2% | >= 5% |
| Reply Rate | 25% | >= 10% | < 10% |
| Complaint Rate | 25% | < 0.1% | >= 0.1% |
| Account Age | 15% | 90+ days | Linear |

**Monitoring:**
1. Navigate to **Dashboard > Warmup Engine**
2. **Overview Tab:** All mailbox statuses, health scores, current phases
3. **Analytics Tab:** Daily trends (emails sent, opens, replies, bounces)
4. **Email Threads Tab:** Browse sent/received warmup emails with detail view
5. **DNS Tab:** Check SPF, DKIM, DMARC records
6. **Alerts Tab:** System alerts (auto-pause, blacklist, DNS issues)
7. **Profiles Tab:** Manage warmup phase profiles

### 7.2 Internal Working Mechanism

**File:** 

**Health Score Calculation:**


**Daily Assessment Flow (runs at 00:05 UTC):**



---

## 8. Module 7: Peer-to-Peer Warmup & Auto-Reply

### 8.1 SOP: Peer Warmup System

**Purpose:** Mailboxes email each other to generate real SMTP traffic, building ISP reputation through genuine email exchange.

**How it Works (Automated):**
- Every hour (9 AM - 5 PM UTC), scheduler triggers peer warmup sends
- 30 minutes later, auto-reply cycle generates natural-looking replies
- This creates realistic email threads that ISPs recognize as legitimate

**Manual Trigger:**
1. Go to **Warmup Engine > Overview**
2. Click **"Trigger Warmup Cycle"** to send peer emails
3. Wait 15+ minutes, then click **"Trigger Auto-Reply"** to generate replies

**Viewing Email Threads:**
1. Go to **Warmup Engine > Email Threads** tab
2. Filter by mailbox, direction (Sent/Received/All)
3. Click subject line to view full email content with HTML preview
4. Check badges: Opened (green), Replied (indigo), AI Generated / Template

### 8.2 Internal Working Mechanism

**File:** peer_warmup.py in backend/app/services/warmup/

#### Peer Warmup Send Cycle

The run_peer_warmup_cycle function:
1. Checks weekend skip setting and peer warmup enabled setting
2. Queries eligible mailboxes: WARMING_UP or RECOVERING, active, connection successful
3. For each mailbox below daily_send_limit:
   - Selects random 1-3 peers (different mailboxes, same warmup status)
   - Generates content: AI first (Groq/OpenAI), template fallback
   - Injects tracking pixel into HTML body
   - Sends via SMTP (real email delivery)
   - Creates WarmupEmail record with tracking_id
   - Increments sender counters: emails_sent_today, total_emails_sent
   - Increments receiver counter: warmup_emails_received
4. Commits all changes

#### Auto-Reply Cycle

The run_auto_reply_cycle function:
1. Checks weekend skip + auto_reply_enabled settings
2. Loads config: reply_rate_target=0.5 (50%), min_delay=15min, max_delay=90min
3. Queries candidate emails:
   - status=SENT, replied_at IS NULL
   - sent_at between (now - 24h) and (now - 15min)
4. For each candidate:
   - Random skip: if random() > 0.5 -> skip (natural rate)
   - Per-email random delay: randint(15, 90) minutes
   - Generates reply: AI or template ("Re: " + original subject, <60 words)
   - Sends reply via SMTP (receiver -> sender)
   - Updates original email: replied_at=now, status=REPLIED
   - Increments sender.reply_count + warmup_replies
   - Increments receiver.emails_sent_today + total_emails_sent
   - Creates new WarmupEmail record for the reply
5. Commits all changes

**Why 50% Reply Rate?**
- ISPs analyze engagement patterns to detect spam
- 100% reply rate looks artificial and suspicious
- Natural business email reply rates are 30-60%
- Random 50% target with per-email variation appears realistic


---

## 9. Module 8: DNS Health & Blacklist Monitoring

### 9.1 SOP: DNS and Blacklist Checks

**Purpose:** Monitor email infrastructure health to ensure deliverability.

**DNS Records Required:**
| Record | Purpose | Score Weight |
|--------|---------|-------------|
| **SPF** | Authorizes sending servers for your domain | 35% |
| **DKIM** | Cryptographic email signature for authenticity | 35% |
| **DMARC** | Policy for handling SPF/DKIM failures | 30% |
| **MX** | Mail exchange records for receiving email | Informational |

**Running DNS Checks:**
1. Go to **Warmup Engine > DNS** tab
2. Click **"Run DNS Check"** to validate all mailbox domains
3. View results: green checkmarks for passing, red X for issues
4. DNS Score = SPF (35%) + DKIM (35%) + DMARC (30%) = 0-100

**Blacklist Monitoring:**
1. Go to **Warmup Engine > Overview**, click **"Run Blacklist Check"**
2. Checks against 6 major DNSBLs:
   - zen.spamhaus.org, bl.spamcop.net, b.barracudacentral.org
   - dnsbl.sorbs.net, cbl.abuseat.org, dnsbl-1.uceprotect.net
3. If blacklisted: Mailbox auto-pauses, HIGH severity alert created

### 9.2 Internal Working Mechanism

**Files:** dns_checker.py, blacklist_monitor.py in backend/app/services/warmup/

**DNS Check Flow (run_dns_health_check):**
1. Extract domain from email address
2. Query TXT records for "v=spf1" (SPF check)
3. Query selector._domainkey.domain for "v=DKIM1" (tries: selector1, selector2, google, default)
4. Query _dmarc.domain for "v=DMARC1" and extract policy (none/quarantine/reject)
5. Query MX records and sort by priority
6. Calculate dns_score, store DNSCheckResult, update mailbox.dns_score

**Blacklist Check Flow (run_blacklist_check):**
1. Resolve domain to IP address (DNS A record)
2. Reverse IP: 1.2.3.4 -> 4.3.2.1
3. For each DNSBL: query reversed_ip.dnsbl_host
4. If resolves (127.0.0.x) -> LISTED; If NXDOMAIN -> CLEAN
5. Store BlacklistCheckResult, set is_blacklisted flag, optionally auto-pause

---

## 10. Module 9: AI Content Generation

### 10.1 SOP: Configuring AI for Warmup Content

**Purpose:** Generate varied, natural-sounding warmup email content.

**Setup:**
1. Go to **Dashboard > Settings > AI Configuration**
2. Select AI Provider: Groq (recommended - free), OpenAI, Anthropic, or Gemini
3. Enter API Key:
   - **Groq:** Free at https://console.groq.com/ (14,400 requests/day)
   - **OpenAI:** https://platform.openai.com/
   - **Anthropic:** https://console.anthropic.com/
   - **Gemini:** https://aistudio.google.com/
4. Save settings

**Content Categories (automatically rotated):**
- Meeting follow-up, Project update, Question, Introduction
- Thank you, Scheduling, Feedback request, Resource sharing

### 10.2 Internal Working Mechanism

**File:** content_generator.py in backend/app/services/warmup/

**AI Provider Loading (get_ai_adapter):**
1. Read warmup_ai_provider setting (default: "groq")
2. Read API key from settings
3. If no key -> return None (fallback to templates)
4. Instantiate adapter (GroqAdapter, OpenAIAdapter, etc.)

**AI Content Generation (generate_ai_warmup_content):**
1. Load AI adapter, pick random content category
2. Call LLM with system prompt: "Casual internal business email, under N words"
3. Parse response: extract SUBJECT line and body
4. Convert to HTML, return with ai_provider metadata

**AI Reply Generation (generate_warmup_reply):**
1. Prefix subject with "Re: "
2. Try AI: "Brief, casual reply under 60 words"
3. If AI fails: use template replies (5 variations)
4. Return {subject, body_text, body_html, ai_generated flag}

**Groq API Details:**
- Model: llama-3.3-70b-versatile (best quality)
- Fallback models: llama-3.1-8b-instant (fastest), llama-4-scout (latest)
- Free tier: 14,400 requests/day
- Temperature: 0.8 (content), 0.3 (analysis)

---

## 11. Module 10: Scheduler & Background Jobs

### 11.1 SOP: Monitoring Background Jobs

**Purpose:** APScheduler runs 8 automated background jobs that keep the warmup engine running 24/7.

**Viewing Scheduler Status:**
1. Go to **Warmup Engine > Overview**
2. Scheduler status shows: Running/Stopped + all jobs + next run times

**Job Schedule (all times UTC):**

| Job | Schedule | Purpose |
|-----|----------|---------|
| Daily Assessment | 00:05 | Advance warmup phases, check health, graduate/pause |
| Peer Warmup Cycle | Hourly 09:00-17:00 | Send warmup emails between mailboxes |
| Auto Reply Cycle | Hourly 09:30-17:30 | Reply to received warmup emails |
| Daily Count Reset | 00:00 | Reset emails_sent_today to 0 |
| DNS Health Checks | Every 12 hours | Validate SPF/DKIM/DMARC records |
| Blacklist Checks | Every 12 hours | Check IPs against 6 DNSBLs |
| Daily Log Snapshot | 23:55 | Store daily metrics for trend analysis |
| Auto Recovery Check | 06:00 | Resume paused mailboxes after cooldown |

### 11.2 Internal Working Mechanism

**File:** scheduler.py in backend/app/services/warmup/

**Initialization (at app startup):**
- BackgroundScheduler created with timezone="UTC"
- 8 jobs registered with CronTrigger or IntervalTrigger
- Scheduler starts automatically; shuts down on app exit

**Each job follows the pattern:**
1. Log "Running xxx"
2. Get fresh DB session from SessionLocal()
3. Call business logic function (e.g., run_peer_warmup_cycle)
4. Log result or error
5. Always close DB session in finally block

**Auto-Recovery Logic (job_auto_recovery_check):**
- For each PAUSED mailbox paused >= 3 days: transition to RECOVERING, set daily_limit=2
- For each RECOVERING mailbox: multiply daily_limit by 1.5x factor daily
  - Example ramp: 2 -> 3 -> 5 -> 8 -> 12 -> 18 -> 27
- When daily_limit >= 25 AND recovery_days >= 7: return to WARMING_UP

---

## 12. Module 11: Settings & Configuration

### 12.1 SOP: System Configuration

**Purpose:** Central configuration for all system behavior, API keys, and business rules.

**Accessing Settings:** Navigate to **Dashboard > Settings**

**Configuration Sections:**

#### Job Source Configuration
- JSearch API Key (RapidAPI)
- Apollo API Key (for leads and contacts)
- Enabled Sources toggle
- Target Job Titles (37 configurable, chip UI)
- Target US States (multi-select)
- Exclusion Keywords: IT keywords + staffing keywords (chip/badge UI)

#### AI Configuration
- Provider: Groq, OpenAI, Anthropic, or Gemini
- API Key, Temperature (0.8), Max Length (200 words)

#### Contact Discovery
- Provider: Apollo or Seamless
- API Key, Max Contacts Per Job (default 4)

#### Email Validation
- Provider: NeverBounce, ZeroBounce, Hunter, Clearout, Emailable, MailboxValidator, Reacher
- API Key for selected provider

#### Outreach Configuration
- Send Mode: mailmerge (export) or smtp (direct)
- SMTP Settings: Host, port, credentials
- Daily Send Limit (default 30), Cooldown Days (default 10)

#### Warmup Configuration
- Phase durations and email limits
- Health score weights (bounce, reply, complaint, age)
- Auto-pause thresholds
- Peer warmup: enabled, max per pair
- Auto-reply: enabled, reply rate (0.5), delay range (15-90 min)
- Weekend skip (configurable)

### 12.2 Internal Working Mechanism

**Storage:** Settings table with key-value pairs (key, value_json, type, description, updated_by, timestamps)

**Key Settings Reference:**

| Key | Default | Module |
|-----|---------|--------|
| jsearch_api_key | "" | Lead Sourcing |
| apollo_api_key | "" | Lead Sourcing + Contacts |
| target_job_titles | [37 titles] | Lead Sourcing |
| target_states | [all US states] | Lead Sourcing |
| exclude_it_keywords | [14 terms] | Lead Sourcing |
| contact_provider | "mock" | Contact Enrichment |
| email_validation_provider | "mock" | Email Validation |
| warmup_ai_provider | "groq" | AI Content |
| groq_api_key | "" | AI Content |
| warmup_phase_1_days | 7 | Warmup Engine |
| warmup_phase_1_min_emails | 2 | Warmup Engine |
| warmup_phase_1_max_emails | 5 | Warmup Engine |
| warmup_peer_enabled | true | Peer Warmup |
| warmup_auto_reply_enabled | true | Auto-Reply |
| warmup_auto_reply_rate | 0.5 | Auto-Reply |
| warmup_skip_weekends | true | Smart Scheduler |

---

## 13. Module 12: Frontend Dashboard

### 13.1 Page Reference

| Page | Path | Purpose |
|------|------|---------|
| Dashboard Home | /dashboard | KPIs, trends, category breakdown |
| Leads | /dashboard/leads | Job postings management, import/export |
| Clients | /dashboard/clients | Company/client management |
| Contacts | /dashboard/contacts | Contact discovery results |
| Validation | /dashboard/validation | Email validation status |
| Outreach | /dashboard/outreach | Campaign management, mail merge |
| Mailboxes | /dashboard/mailboxes | Sender account management |
| Warmup Engine | /dashboard/warmup | 7-tab warmup management |
| Pipelines | /dashboard/pipelines | Pipeline execution and history |
| Settings | /dashboard/settings | System configuration |

### 13.2 Key Frontend Features

**Leads Page:**
- Paginated table with search, status/source/state filters
- CSV import/export capability
- Sortable columns, status change via dropdown
- View linked contacts per lead in modal

**Contacts Page:**
- Filter by priority (P1-P5), validation status, source
- Priority badges with color coding
- Direct link to associated lead

**Mailboxes Page:**
- Add/edit/delete mailboxes with connection testing
- Daily quota progress bars per mailbox
- Bulk selection with bulk delete
- Filter by status, connection state, provider
- Test all connections at once

**Warmup Engine Page (7 tabs):**
- **Overview:** Mailbox statuses, health scores, phase progress, action buttons
- **Analytics:** Line/area/bar charts via Recharts (sent, opens, replies, bounces)
- **Email Threads:** Warmup email history with mailbox/direction filters, detail modal
- **DNS:** SPF/DKIM/DMARC results per domain
- **Profiles:** Create/manage warmup phase profiles
- **Alerts:** System notifications with severity indicators
- **Settings:** Phase configuration editor

**Pipelines Page:**
- One-click pipeline execution (Lead Sourcing, Contact Enrichment, Validation, Outreach)
- Pipeline run history table with status, timing, record counts
- Stats cards showing aggregated pipeline metrics

### 13.3 Common UI Patterns

- **Authentication:** JWT token, auto-redirect to /login on 401
- **Pagination:** Page size selector (10, 25, 50, 100) with page nav
- **Search:** Debounced (300ms) full-text search
- **Sorting:** Click column headers for ascending/descending
- **Filters:** Dropdown with 'All' option, clickable stat cards to filter
- **Status Badges:** Color-coded: green (good), yellow (caution), red (bad), gray (unknown)
- **Charts:** Recharts for line, area, bar charts (Warmup Analytics)

---

## 14. Appendix A: Database Schema Reference

### Core Tables

| Table | Primary Key | Purpose |
|-------|-------------|---------|
| lead_details | lead_id | Job postings / leads |
| contact_details | contact_id | Decision-maker contacts (FK: lead_id) |
| client_info | client_id | Companies tracked |
| sender_mailboxes | mailbox_id | Email accounts for sending |
| users | user_id | Authentication + roles |
| settings | key | Key-value configuration |

### Pipeline Tables

| Table | Primary Key | Purpose |
|-------|-------------|---------|
| email_validation_results | validation_id | Provider validation responses |
| outreach_events | event_id | Every email sent/skipped record |
| job_runs | run_id | Pipeline execution history |
| suppression_list | id | Do-not-contact list |

### Warmup Tables

| Table | Primary Key | Purpose |
|-------|-------------|---------|
| warmup_emails | id | Every warmup email sent/received |
| warmup_daily_logs | id | Daily metric snapshots per mailbox |
| warmup_alerts | id | System alerts and notifications |
| warmup_profiles | id | Configurable warmup phase profiles |
| dns_check_results | id | SPF/DKIM/DMARC check results |
| blacklist_check_results | id | DNSBL check results |

---

## 15. Appendix B: API Endpoint Reference

Base URL: http://localhost:8000/api/v1

### Authentication
| Method | Path | Purpose |
|--------|------|---------|
| POST | /auth/login | Login (returns JWT) |
| POST | /auth/register | Register new user |
| GET | /auth/me | Current user info |
| POST | /auth/logout | Logout |

### Leads
| Method | Path | Purpose |
|--------|------|---------|
| GET | /leads | List (paginated, filtered, sorted) |
| POST | /leads | Create single lead |
| GET | /leads/{id} | Get lead detail |
| PUT | /leads/{id} | Update lead |
| DELETE | /leads/{id} | Delete lead |
| POST | /leads/import | Import from XLSX/CSV |
| GET | /leads/export/csv | Export as CSV |

### Contacts
| Method | Path | Purpose |
|--------|------|---------|
| GET | /contacts | List (filter by lead_id, priority, validation) |
| POST | /contacts | Create contact |
| GET | /contacts/{id} | Get contact detail |
| PUT | /contacts/{id} | Update contact |
| DELETE | /contacts/{id} | Delete contact |
| GET | /contacts/stats | Validation statistics |

### Pipelines
| Method | Path | Purpose |
|--------|------|---------|
| GET | /pipelines/runs | List pipeline runs |
| POST | /pipelines/lead-sourcing/run | Run lead sourcing |
| POST | /pipelines/contact-enrichment/run | Run contact enrichment |
| POST | /pipelines/email-validation/run | Run email validation |
| POST | /pipelines/outreach/run | Run outreach |

### Mailboxes
| Method | Path | Purpose |
|--------|------|---------|
| GET | /mailboxes | List mailboxes |
| POST | /mailboxes | Add mailbox |
| GET | /mailboxes/{id} | Get mailbox detail |
| PUT | /mailboxes/{id} | Update mailbox |
| DELETE | /mailboxes/{id} | Delete mailbox |
| POST | /mailboxes/{id}/test-connection | Test SMTP connection |
| GET | /mailboxes/stats | Mailbox statistics |

### Warmup Engine (27 endpoints)
| Method | Path | Purpose |
|--------|------|---------|
| GET | /warmup/status | All mailbox warmup statuses |
| GET | /warmup/config | Warmup configuration |
| PUT | /warmup/config | Update configuration |
| POST | /warmup/assess | Assess all mailboxes |
| POST | /warmup/assess/{id} | Assess single mailbox |
| GET | /warmup/schedule | Get warmup schedule |
| GET | /warmup/health-scores | Health scores |
| POST | /warmup/peer/send | Trigger peer warmup |
| POST | /warmup/peer/auto-reply | Trigger auto-reply |
| GET | /warmup/peer/history | Warmup email history |
| GET | /warmup/peer/history/{id} | Single email detail |
| GET | /warmup/analytics | Time-series analytics |
| POST | /warmup/dns-check | Run DNS checks |
| GET | /warmup/dns/{id} | Get DNS results |
| POST | /warmup/blacklist-check | Run blacklist checks |
| GET | /warmup/blacklist/{id} | Blacklist results |
| POST | /warmup/placement-test/{id} | Inbox placement test |
| GET | /warmup/alerts | List alerts |
| PUT | /warmup/alerts/{id}/read | Mark alert read |
| PUT | /warmup/alerts/read-all | Mark all read |
| GET | /warmup/alerts/unread-count | Unread count |
| GET | /warmup/profiles | List profiles |
| POST | /warmup/profiles | Create profile |
| PUT | /warmup/profiles/{id} | Update profile |
| DELETE | /warmup/profiles/{id} | Delete profile |
| POST | /warmup/profiles/{pid}/apply/{mid} | Apply profile to mailbox |
| POST | /warmup/recovery/{id}/start | Start recovery |
| GET | /warmup/export | Export report (CSV/JSON) |
| GET | /warmup/scheduler/status | Scheduler status |

### Settings
| Method | Path | Purpose |
|--------|------|---------|
| GET | /settings | List all settings |
| GET | /settings/{key} | Get single setting |
| PUT | /settings/{key} | Update setting |
| POST | /settings/initialize | Initialize defaults |
| POST | /settings/test-connection/{provider} | Test provider |

---

## 16. Appendix C: File Structure Map

### Backend Structure

```
backend/
  app/
    main.py                               # FastAPI app, startup, CORS
    core/
      config.py                            # Environment settings
      security.py                          # JWT, password hashing
    api/
      router.py                            # Route registration
      deps.py                              # Dependency injection
      endpoints/
        auth.py                            # Login, register, logout
        leads.py                           # Lead CRUD + import/export
        contacts.py                        # Contact CRUD + stats
        clients.py                         # Client CRUD
        mailboxes.py                       # Mailbox management
        warmup.py                          # Warmup (27 endpoints)
        pipelines.py                       # Pipeline triggers
        validation.py                      # Email test endpoint
        outreach.py                        # Outreach history
        settings.py                        # Settings CRUD
        dashboard.py                       # KPIs and trends
    db/
      base.py                              # SQLAlchemy engine
      seed.py                              # Default data seeding
      models/
        lead.py, contact.py, client.py     # Core models
        sender_mailbox.py                  # Mailbox + WarmupStatus
        warmup_email.py                    # Warmup email tracking
        warmup_daily_log.py                # Daily snapshots
        warmup_alert.py, warmup_profile.py # Alerts + profiles
        dns_check_result.py                # DNS results
        blacklist_check_result.py          # Blacklist results
        email_validation.py                # Validation results
        outreach.py, job_run.py            # Pipeline records
        user.py, settings.py               # Auth + config
    services/
      pipelines/
        lead_sourcing.py                   # Multi-source job fetch
        contact_enrichment.py              # Decision-maker discovery
        email_validation.py                # Deliverability checks
        outreach.py                        # Mail merge + SMTP
        warmup_engine.py                   # Phase progression
      warmup/
        scheduler.py                       # APScheduler (8 jobs)
        peer_warmup.py                     # Peer emails + auto-reply
        content_generator.py               # AI + template content
        tracking.py                        # Open/click tracking
        dns_checker.py                     # SPF/DKIM/DMARC
        blacklist_monitor.py               # DNSBL checks
        auto_recovery.py                   # Pause recovery
        smart_scheduler.py                 # Human-like timing
      adapters/
        base.py                            # Abstract interfaces
        job_sources/jsearch.py, apollo.py, mock.py
        contact_discovery/apollo.py, seamless.py, mock.py
        email_validation/neverbounce.py, zerobounce.py, ...
        email_sending/smtp.py, mock.py
        ai/groq.py, openai_adapter.py, anthropic_adapter.py, gemini.py
```

### Frontend Structure

```
frontend/src/
  app/dashboard/
    layout.tsx                             # Sidebar + auth guard
    page.tsx                               # Dashboard home
    leads/page.tsx                         # Leads management
    clients/page.tsx                       # Client management
    contacts/page.tsx                      # Contact management
    validation/page.tsx                    # Email validation
    outreach/page.tsx                      # Outreach campaigns
    mailboxes/page.tsx                     # Mailbox management
    warmup/page.tsx                        # Warmup engine (7 tabs)
    pipelines/page.tsx                     # Pipeline execution
    settings/page.tsx                      # System configuration
  lib/
    api.ts                                 # Axios API client
```

---

*Document generated on February 12, 2026*
*System Version: 2.0*
*NeuraLeads AI Agent*
