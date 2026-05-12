# Multi-LOB Architecture Design Spec

**Date**: 2026-05-12
**Status**: Approved
**Scope**: Backend + Frontend, Phases 1-4

## Overview

Extend NeuraLeads from a staffing-only platform to support multiple Lines of Business (LOBs): Staffing, RCM (Medeoan), Software Development, AI Services, and Digital Marketing (Neuraforz). Existing functionality must not break.

## Core Principle

**Additive-only changes with backward compatibility.** Existing staffing functionality becomes "LOB #1" automatically. `lob_id=NULL` means legacy/default. No existing behavior changes.

---

## Phase 1 — Foundation

### 1.1 New Model: `LineOfBusiness`

File: `backend/app/db/models/line_of_business.py`

```python
class LOBType(str, Enum):
    STAFFING = "staffing"
    RCM = "rcm"
    SOFTWARE_DEV = "software_dev"
    AI_SERVICES = "ai_services"
    DIGITAL_MARKETING = "digital_marketing"
    CUSTOM = "custom"

class LOBStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"

class LineOfBusiness(Base):
    __tablename__ = "lines_of_business"
    lob_id: PK
    tenant_id: FK(tenants), NOT NULL
    name: String(255), NOT NULL
    slug: String(100), NOT NULL
    lob_type: Enum(LOBType), NOT NULL
    description: Text, nullable
    lead_source_config: Text (JSON), nullable  # which adapters + search queries
    icp_config: Text (JSON), nullable          # target industries, sizes, titles, geo
    business_rules: Text (JSON), nullable      # send limits, cooldowns, thresholds
    prompt_profile: Text (JSON), nullable      # AI prompt context overrides
    target_industries_json: Text, nullable     # industry list for this LOB
    target_job_titles_json: Text, nullable     # job title list for this LOB
    exclude_keywords_json: Text, nullable      # exclusion keywords for this LOB
    is_default: Boolean, default=False
    status: Enum(LOBStatus), default=ACTIVE
    color: String(7), nullable  # hex color for UI badges
    icon: String(50), nullable  # icon identifier
    Unique(tenant_id, slug)
```

### 1.2 Schema Changes (nullable FK additions)

These models get a new `lob_id` column (nullable FK → `lines_of_business.lob_id`, SET NULL on delete):

- `LeadDetails.lob_id`
- `ContactDetails.lob_id`
- `Campaign.lob_id`
- `EmailTemplate.lob_id`
- `ICPProfile.lob_id`
- `SuppressionList.lob_id`

NULL = applies to all LOBs or legacy data.

### 1.3 API Endpoints

File: `backend/app/api/endpoints/lob.py`
Prefix: `/api/v1/lob`

- `GET /` — list LOBs for current tenant
- `POST /` — create LOB
- `GET /{lob_id}` — get LOB details
- `PUT /{lob_id}` — update LOB
- `DELETE /{lob_id}` — soft-delete (archive) LOB
- `POST /{lob_id}/set-default` — set as default LOB
- `GET /types` — list available LOB types with metadata

### 1.4 Settings Resolution Enhancement

Current: `TenantSettings[key]` → `config.py`
New: `LOB.business_rules[key]` → `TenantSettings[key]` → `config.py`

Add `resolve_lob_setting(db, tenant_id, lob_id, key, default)` to settings resolver.

### 1.5 AI Prompt LOB Context

Extend `prompt_registry.py` to inject LOB context into prompts. Each LOB has a `prompt_profile` JSON with:
- `company_description`: what the company does
- `value_proposition`: core pitch
- `industry_context`: domain-specific knowledge
- `tone`: professional/casual/technical
- `compliance_notes`: industry-specific compliance reminders

### 1.6 Seed Data

On startup, for each tenant without any LOB records, auto-seed a "Staffing" LOB with `is_default=True` and current config values migrated to its JSON fields.

### 1.7 Frontend Changes

- LOB selector dropdown in dashboard sidebar (above navigation)
- LOB context stored in Zustand auth store or dedicated LOB store
- All API calls include `?lob_id=X` query param when LOB is selected
- LOB management page under Settings
- LOB badge/tag on lead cards, contact cards, campaign cards
- LOB filter dropdown on Leads, Contacts, Campaigns list pages

---

## Phase 2 — Lead Source Expansion

### 2.1 New Adapters

All follow existing `BaseLeadSourceAdapter` pattern.

| Adapter | File | LOB | API |
|---------|------|-----|-----|
| NPI Registry | `adapters/lead_sources/npi_registry.py` | RCM | NPPES (free) |
| Google Business | `adapters/lead_sources/google_business.py` | RCM, Digital Marketing | Google Places |
| Crunchbase | `adapters/lead_sources/crunchbase.py` | Software Dev, AI Services | Crunchbase API |
| BuiltWith | `adapters/lead_sources/builtwith.py` | Software Dev, Digital Marketing | BuiltWith API |
| PageSpeed | `adapters/lead_sources/pagespeed.py` | Digital Marketing | PageSpeed Insights (free) |
| GitHub Org | `adapters/lead_sources/github_org.py` | Software Dev, AI Services | GitHub API (free) |

### 2.2 Config Keys

New env vars: `GOOGLE_PLACES_API_KEY`, `CRUNCHBASE_API_KEY`, `BUILTWITH_API_KEY`
Free APIs (NPI, PageSpeed, GitHub) need no keys.

### 2.3 Pipeline Enhancement

`lead_sourcing.py` reads `LOB.lead_source_config` to decide which adapters to call. If `lob_id` is specified in pipeline run, uses LOB-specific config; otherwise falls back to existing job board behavior.

### 2.4 Frontend

- Lead Source selector in pipeline run dialog shows LOB-specific sources
- New lead source result cards for non-job-board sources (NPI shows practice info, PageSpeed shows scores, etc.)

---

## Phase 3 — LOB-Specific Intelligence

### 3.1 LOB Scoring Models

Extend `scoring_engine.py` with LOB-aware weights:

```python
LOB_SCORING_WEIGHTS = {
    "staffing": {"hiring_signals": 0.4, "company_size": 0.3, "industry_match": 0.2, "web_presence": 0.1},
    "rcm": {"practice_size": 0.3, "specialty_match": 0.25, "denial_indicators": 0.25, "location": 0.2},
    "software_dev": {"funding_stage": 0.3, "hiring_velocity": 0.25, "tech_stack_age": 0.25, "growth": 0.2},
    "ai_services": {"ai_adoption": 0.3, "automation_need": 0.25, "budget_signals": 0.25, "tech_maturity": 0.2},
    "digital_marketing": {"seo_gap": 0.3, "social_presence": 0.2, "website_quality": 0.25, "review_score": 0.25},
}
```

### 3.2 Industry Knowledge Base

Directory: `backend/app/data/lob_knowledge/`
Files: `staffing.json`, `rcm.json`, `software_dev.json`, `ai_services.json`, `digital_marketing.json`

Each contains: facts, statistics, pain_points, proof_points, compliance_notes fed into AI prompts.

### 3.3 Custom Merge Fields

LOB-specific merge fields in templates:
- RCM: `{practice_specialty}`, `{provider_count}`, `{npi_number}`
- Software Dev: `{tech_stack}`, `{funding_stage}`, `{team_size}`
- AI Services: `{ai_maturity}`, `{automation_score}`
- Digital Marketing: `{domain_authority}`, `{pagespeed_score}`, `{review_count}`

### 3.4 Frontend

- LOB-specific lead score breakdown on contact cards
- Knowledge base viewer in Settings > LOB config
- Custom merge field picker in template editor

---

## Phase 4 — Advanced Automation

### 4.1 Website Audit Reports

Service: `services/website_auditor.py`
For Digital Marketing LOB: auto-generates audit report combining PageSpeed + BuiltWith data. Stored as JSON on lead, surfaced in UI.

### 4.2 Trigger-Based Prospecting

Scheduler job: `job_check_intent_signals()`
Monitors configured sources for new signals (funding rounds, job postings, tech stack changes). Creates leads automatically when signals match LOB criteria.

### 4.3 LOB-Specific Dashboards

Each LOB type gets a custom KPI widget set:
- RCM: practices contacted, specialties covered, appointment rate
- Software Dev: companies by funding stage, tech stack distribution
- AI Services: AI maturity distribution, deal pipeline
- Digital Marketing: avg domain authority of prospects, audit completion rate

### 4.4 Frontend

- Dashboard KPI widgets adapt to selected LOB
- Automation rules editor for trigger-based prospecting
- Website audit report viewer on lead detail page

---

## Regression Safeguards

1. All new columns are nullable — existing queries unaffected
2. LOB filtering is additive (`AND lob_id = X` only when LOB is selected)
3. Default "Staffing" LOB seeded on startup for existing tenants
4. Full `pytest` run after each phase
5. No modification of existing adapter interfaces
6. Existing API responses include `lob_id: null` for legacy data (no schema break)
7. Frontend gracefully handles `lob_id=null` (shows as "All" or "General")

## Files Modified Per Phase

### Phase 1
- NEW: `db/models/line_of_business.py`, `api/endpoints/lob.py`
- EDIT: `db/models/__init__.py`, `db/base.py` (imports), `api/router.py`
- EDIT: `db/models/lead.py`, `contact.py`, `campaign.py`, `email_template.py`, `icp_profile.py`, `suppression.py` (add lob_id)
- EDIT: `main.py` (seed default LOBs)
- EDIT: `services/settings_resolver.py` (LOB-aware resolution)
- EDIT: `services/ai_sales_agent/prompt_registry.py` (LOB context injection)
- NEW: frontend LOB store, LOB selector, LOB settings page, LOB filter components

### Phase 2
- NEW: 6 adapter files in `services/adapters/lead_sources/`
- EDIT: `core/config.py` (new API key settings)
- EDIT: `services/pipelines/lead_sourcing.py` (LOB-aware adapter selection)

### Phase 3
- EDIT: `services/ai_sales_agent/scoring_engine.py` (LOB weights)
- NEW: `data/lob_knowledge/*.json` files
- EDIT: `services/ai_sales_agent/prompt_registry.py` (knowledge base injection)
- EDIT: frontend template editor (merge field picker)

### Phase 4
- NEW: `services/website_auditor.py`
- NEW: scheduler job for intent signals
- EDIT: `main.py` (new scheduler jobs)
- EDIT: frontend dashboard (LOB-specific KPI widgets)
