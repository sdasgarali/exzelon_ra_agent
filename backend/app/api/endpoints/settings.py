"""Settings management endpoints."""
import json
import structlog
from typing import List, Optional, Dict

logger = structlog.get_logger()
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role, get_current_tenant_id, get_current_active_user
from app.api.deps.auth import get_user_settings_tab_access, get_all_settings_tab_permissions
from app.core.config import settings as app_config
from app.core.settings_resolver import (
    get_tenant_setting,
    set_tenant_setting,
    delete_tenant_setting,
    get_tenant_overrides,
)
from pydantic import BaseModel as PydanticBaseModel
from app.db.models.user import User, UserRole
from app.db.models.settings import Settings
from app.db.models.tenant import Tenant
from app.schemas.settings import SettingUpdate, SettingResponse

router = APIRouter(prefix="/settings", tags=["Settings"])

# Mapping of setting keys to their settings tab
SETTINGS_TAB_MAP: Dict[str, str] = {
    # Job Filters (target states, titles, industries, company size, exclusions)
    'target_states': 'job_filters',
    'available_job_titles': 'job_filters',
    'target_job_titles': 'job_filters',
    'target_industries': 'job_filters',
    'company_size_priority_1_max': 'job_filters',
    'company_size_priority_2_min': 'job_filters',
    'company_size_priority_2_max': 'job_filters',
    'company_size_no_preference': 'job_filters',
    'exclude_it_keywords': 'job_filters',
    'exclude_staffing_keywords': 'job_filters',
    'exclude_company_keywords': 'job_filters',
    'exclude_title_keywords': 'job_filters',
    'exclude_job_types': 'job_filters',
    'exclude_match_mode': 'job_filters',
    'job_title_categories': 'job_filters',
    # Job Source APIs (provider selection, API keys, enabled sources)
    'job_source_provider': 'job_source_apis',
    'jsearch_api_key': 'job_source_apis',
    'indeed_publisher_id': 'job_source_apis',
    'lead_sources': 'job_source_apis',
    'lead_sourcing_frequency': 'job_source_apis',
    'location_diversification': 'source_tuning',
    'lead_sourcing_target_per_run': 'source_tuning',
    'lead_sourcing_max_employee_count': 'source_tuning',
    'lead_sourcing_drop_confidential': 'source_tuning',
    'lead_sourcing_excluded_industries': 'source_tuning',
    'lead_sourcing_enrich_company_at_source': 'source_tuning',
    'lead_sourcing_enrich_max_companies': 'source_tuning',
    'source_tiers': 'source_tuning',
    'source_overlap_groups': 'source_tuning',
    'enabled_sources': 'job_source_apis',
    'theirstack_api_key': 'job_source_apis',
    'serpapi_api_key': 'job_source_apis',
    'adzuna_app_id': 'job_source_apis',
    'adzuna_api_key': 'job_source_apis',
    'searchapi_api_key': 'job_source_apis',
    'usajobs_api_key': 'job_source_apis',
    'usajobs_email': 'job_source_apis',
    'jooble_api_key': 'job_source_apis',
    'jobdatafeeds_api_key': 'job_source_apis',
    'coresignal_api_key': 'job_source_apis',
    'fantastic_jobs_api_key': 'job_source_apis',
    'fantastic_jobs_host': 'job_source_apis',
    'resourcepool_api_url': 'job_source_apis',
    'resourcepool_api_key': 'job_source_apis',
    'resourcepool_auto_push_on_reply': 'job_source_apis',
    'resourcepool_webhook_secret': 'job_source_apis',
    'resourcepool_pitch_in_email': 'job_source_apis',
    # AI/LLM
    'ai_provider': 'ai_llm',
    'groq_api_key': 'ai_llm',
    'openai_api_key': 'ai_llm',
    'anthropic_api_key': 'ai_llm',
    'gemini_api_key': 'ai_llm',
    'ai_model': 'ai_llm',
    'ai_personalize_emails': 'ai_llm',
    'ai_personalization_prompt': 'ai_llm',
    # Contacts (Apollo is a contact-enrichment provider, not a lead source)
    'contact_provider': 'contacts',
    'contact_providers': 'contacts',
    'apollo_api_key': 'contacts',
    'seamless_api_key': 'contacts',
    'hunter_contact_api_key': 'contacts',
    'snovio_client_id': 'contacts',
    'snovio_client_secret': 'contacts',
    'rocketreach_api_key': 'contacts',
    'pdl_api_key': 'contacts',
    'proxycurl_api_key': 'contacts',
    'clearbit_api_key': 'contacts',
    'opencorporates_api_key': 'contacts',
    'company_enrichment_providers': 'contacts',
    # Validation
    'email_validation_provider': 'validation',
    'neverbounce_api_key': 'validation',
    'zerobounce_api_key': 'validation',
    'hunter_api_key': 'validation',
    'clearout_api_key': 'validation',
    'emailable_api_key': 'validation',
    'mailboxvalidator_api_key': 'validation',
    'reacher_api_key': 'validation',
    'reacher_base_url': 'validation',
    # Outreach
    'email_send_mode': 'outreach',
    'smtp_host': 'outreach',
    'smtp_port': 'outreach',
    'smtp_user': 'outreach',
    'smtp_password': 'outreach',
    'smtp_from_email': 'outreach',
    'smtp_from_name': 'outreach',
    'm365_admin_email': 'outreach',
    'm365_admin_password': 'outreach',
    # Business Rules
    'daily_send_limit': 'business_rules',
    'cooldown_days': 'business_rules',
    'max_contacts_per_company_job': 'business_rules',
    'min_salary_threshold': 'business_rules',
    'catch_all_policy': 'business_rules',
    'unsubscribe_footer': 'business_rules',
    'company_address': 'business_rules',
    'category_window_days': 'business_rules',
    'category_regular_threshold': 'business_rules',
    'category_occasional_threshold': 'business_rules',
    'backup_retention_days': 'business_rules',
    'data_retention_days': 'business_rules',
    'domain_daily_limit_default': 'business_rules',
    'domain_daily_limit_major_providers': 'business_rules',
    'max_contacts_per_company_all_campaigns': 'business_rules',
    'send_delay_min_sec': 'business_rules',
    'send_delay_max_sec': 'business_rules',
    # Deal Automation
    'deal_auto_create_on_interested': 'business_rules',
    'deal_auto_advance_stages': 'business_rules',
    'deal_auto_log_activities': 'business_rules',
    'deal_stale_threshold_days': 'business_rules',
    'deal_score_to_probability': 'business_rules',
    # Automation Control Center
    'automation_master_enabled': 'automation',
    'automation_chain_enrichment': 'automation',
    'automation_chain_validation': 'automation',
    'automation_daily_assessment_enabled': 'automation',
    'automation_peer_warmup_cycle_enabled': 'automation',
    'automation_auto_reply_cycle_enabled': 'automation',
    'automation_daily_count_reset_enabled': 'automation',
    'automation_dns_checks_enabled': 'automation',
    'automation_blacklist_checks_enabled': 'automation',
    'automation_daily_log_snapshot_enabled': 'automation',
    'automation_auto_recovery_check_enabled': 'automation',
    'automation_check_outreach_replies_enabled': 'automation',
    'automation_lead_sourcing_run_enabled': 'automation',
    'automation_daily_backup_enabled': 'automation',
    'automation_backup_cleanup_enabled': 'automation',
    'automation_campaign_processor_enabled': 'automation',
    'automation_inbox_sync_enabled': 'automation',
    'automation_lead_scoring_enabled': 'automation',
    'automation_imap_read_cycle_enabled': 'automation',
    'automation_crm_sync_enabled': 'automation',
    'automation_chain_enrollment': 'automation',
    'automation_auto_enrollment_enabled': 'automation',
    'automation_cost_aggregation_enabled': 'automation',
    'automation_cost_analysis_enabled': 'automation',
    # Cost Tracking Budget
    'cost_monthly_budget_total': 'business_rules',
    # Deliverability
    'complaint_rate_threshold': 'deliverability',
    'sequence_fatigue_window_days': 'deliverability',
    'sequence_fatigue_max_unanswered': 'deliverability',
    # LOB Lead Source API Keys
    'google_places_api_key': 'lob_lead_sources',
    'crunchbase_api_key': 'lob_lead_sources',
    'builtwith_api_key': 'lob_lead_sources',
    'github_token': 'lob_lead_sources',
    # Intent Signal Automation
    'automation_intent_signals_enabled': 'automation',
    # Source Tuning (adapter performance parameters)
    'job_source_tuning': 'source_tuning',
    'pipeline_adapter_limit': 'source_tuning',
    'pipeline_max_workers': 'source_tuning',
    'posted_within_days': 'source_tuning',
    'posted_within_hours': 'source_tuning',
}

# Default settings for seed data
DEFAULT_SETTINGS = {
    "data_storage": {"value": "database", "type": "string", "description": "Storage mode: database or files"},
    "daily_send_limit": {"value": 30, "type": "integer", "description": "Max emails per day per mailbox"},
    "cooldown_days": {"value": 10, "type": "integer", "description": "Days between emails to same contact"},
    "max_contacts_per_company_job": {"value": 2, "type": "integer", "description": "Max contacts per company per job"},
    "min_salary_threshold": {"value": 40000, "type": "integer", "description": "Minimum salary threshold"},
    "contact_provider": {"value": "mock", "type": "string", "description": "Contact discovery provider"},
    "email_validation_provider": {"value": "mock", "type": "string", "description": "Email validation provider"},
    "email_send_mode": {"value": "mailmerge", "type": "string", "description": "Email send mode"},
    "catch_all_policy": {"value": "exclude", "type": "string", "description": "Policy for catch-all emails"},
    "unsubscribe_footer": {"value": True, "type": "boolean", "description": "Include unsubscribe footer"},
    "company_address": {"value": "123 Business St, City, State 12345", "type": "string", "description": "Company mailing address for footer"},
    "data_retention_days": {"value": 180, "type": "integer", "description": "Days to keep archived records before permanent deletion"},
    "domain_daily_limit_default": {"value": 50, "type": "integer", "description": "Max emails per day to any single recipient domain"},
    "domain_daily_limit_major_providers": {"value": 30, "type": "integer", "description": "Max emails per day to major providers (Gmail, Outlook, Yahoo)"},
    "max_contacts_per_company_all_campaigns": {"value": 5, "type": "integer", "description": "Max contacts per company across all active campaigns"},
    "send_delay_min_sec": {"value": 45, "type": "integer", "description": "Minimum delay (seconds) between outbound emails"},
    "send_delay_max_sec": {"value": 180, "type": "integer", "description": "Maximum delay (seconds) between outbound emails"},

    # New Job Source API Keys
    "theirstack_api_key": {"value": "", "type": "string", "description": "TheirStack API key (Free: 100 req/mo | Paid: from $49/mo)"},
    "serpapi_api_key": {"value": "", "type": "string", "description": "SerpAPI key for Google Jobs (Free: 100 req/mo | Paid: from $50/mo)"},
    "adzuna_app_id": {"value": "", "type": "string", "description": "Adzuna App ID (Free: 250 req/mo | Paid: from $99/mo)"},
    "adzuna_api_key": {"value": "", "type": "string", "description": "Adzuna API Key"},
    "searchapi_api_key": {"value": "", "type": "string", "description": "SearchAPI.io API Key — Google Jobs ($40/mo for 4,000 searches)"},
    "usajobs_api_key": {"value": "", "type": "string", "description": "USAJOBS.gov API Key — Free federal job listings"},
    "usajobs_email": {"value": "", "type": "string", "description": "USAJOBS email (required as User-Agent)"},
    "jooble_api_key": {"value": "", "type": "string", "description": "Jooble API Key — Free 71-country job aggregator"},
    "jobdatafeeds_api_key": {"value": "", "type": "string", "description": "JobDataFeeds/Techmap API Key — Bulk jobs ($200-400/mo)"},
    "coresignal_api_key": {"value": "", "type": "string", "description": "Coresignal API Key — Jobs + recruiter contacts ($800-1,500/mo)"},
    "fantastic_jobs_api_key": {"value": "", "type": "string", "description": "Fantastic.jobs direct API key (Bearer) — LinkedIn feed w/ company firmographics. Trial + plans from $95/mo at fantastic.jobs/api"},
    "fantastic_jobs_host": {"value": "data.fantastic.jobs", "type": "string", "description": "Fantastic.jobs API host (direct API: data.fantastic.jobs; RapidAPI ATS feed: active-jobs-db.p.rapidapi.com)"},
    "resourcepool_api_url": {"value": "", "type": "string", "description": "Resource Pool ATS base URL (e.g. https://resourcepool.partnerwithus.tech) for pushing qualified leads (Job+Company+Contact+Opportunity)."},
    "resourcepool_api_key": {"value": "", "type": "string", "description": "Resource Pool API key with the leads:write scope (Bearer). Used by the RA→RP lead hand-off connector."},
    "resourcepool_auto_push_on_reply": {"value": True, "type": "boolean", "description": "Automatically push a lead to Resource Pool (Opportunity=QUALIFIED) when a client reply is classified 'interested'. Requires resourcepool_api_url/key."},
    "resourcepool_webhook_secret": {"value": "", "type": "string", "description": "Shared HMAC secret (whsec_...) for verifying Resource Pool outcome webhooks (offer.accepted/placement.created/invoice.paid) at /integrations/resource-pool/webhook."},
    "resourcepool_pitch_in_email": {"value": True, "type": "boolean", "description": "Weave the Resource Pool 'N candidates >=80% fit' hook into AI-personalized cold emails (and the {{candidate_pitch}} merge field). Requires resourcepool_api_url/key."},

    # New Contact Discovery API Keys
    "hunter_contact_api_key": {"value": "", "type": "string", "description": "Hunter.io API key for contact finder (Free: 25 req/mo | Paid: from $49/mo)"},
    "snovio_client_id": {"value": "", "type": "string", "description": "Snov.io OAuth Client ID (Free: 50 credits/mo | Paid: from $39/mo)"},
    "snovio_client_secret": {"value": "", "type": "string", "description": "Snov.io OAuth Client Secret"},
    "rocketreach_api_key": {"value": "", "type": "string", "description": "RocketReach API key (Free: 5 lookups/mo | Paid: from $99/mo)"},
    "pdl_api_key": {"value": "", "type": "string", "description": "People Data Labs API key (Free: 100 req/mo | Paid: $0.01/match)"},
    "proxycurl_api_key": {"value": "", "type": "string", "description": "Proxycurl API key (Free: 10 credits | Paid: $0.01/call)"},

    # Company Enrichment API Keys
    "clearbit_api_key": {"value": "", "type": "string", "description": "Clearbit API key (Free with HubSpot | API: from $99/mo)"},
    "opencorporates_api_key": {"value": "", "type": "string", "description": "OpenCorporates API key (Free: 500 req/mo | Paid: custom)"},
    "company_enrichment_providers": {"value": [], "type": "list", "description": "Enabled company enrichment providers"},

    # Job Sources Configuration
    "job_source_provider": {"value": "jsearch", "type": "string", "description": "Primary job source provider"},
    "jsearch_api_key": {"value": "", "type": "string", "description": "JSearch RapidAPI key"},
    "indeed_publisher_id": {"value": "", "type": "string", "description": "Indeed Publisher ID"},
    "enabled_sources": {"value": ["linkedin", "indeed", "glassdoor", "simplyhired"], "type": "list", "description": "Enabled job sources"},
    "target_states": {
        "value": [
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
        ],
        "type": "list",
        "description": "Target US states for location diversification"
    },

    # Target Industries (Non-IT only)
    "target_industries": {
        "value": [
            "Healthcare", "Manufacturing", "Logistics", "Retail", "BFSI",
            "Education", "Engineering", "Automotive", "Construction", "Energy",
            "Oil & Gas", "Food & Beverage", "Hospitality", "Real Estate",
            "Legal", "Insurance", "Financial Services", "Industrial",
            "Light Industrial", "Heavy Industrial", "Skilled Trades", "Agriculture"
        ],
        "type": "list",
        "description": "Target industries for leads (Non-IT only)"
    },

    # Available Job Titles (Master List)
    "available_job_titles": {
        "value": [
            # HR & Talent
            "HR Manager", "HR Director", "HR Business Partner", "HR Generalist",
            "HR Coordinator", "Recruiter", "Talent Acquisition", "Talent Acquisition Manager",
            "Staffing Coordinator", "Staffing Manager", "Talent Manager", "Workforce Manager",
            "Recruitment Manager", "People Operations Manager", "Employee Relations Manager",
            "Compensation Manager", "Benefits Manager", "Payroll Manager",
            "VP Human Resources", "Director of HR", "Chief People Officer",
            # Operations & General Management
            "Operations Manager", "Operations Director", "VP Operations",
            "Director of Operations", "COO", "Chief Operating Officer",
            "General Manager", "Assistant General Manager", "Regional Manager",
            "Area Manager", "District Manager", "Territory Manager",
            "Branch Manager", "Site Manager", "Field Manager",
            # Manufacturing & Production
            "Plant Manager", "Production Manager", "Production Supervisor",
            "Manufacturing Manager", "Manufacturing Director", "Manufacturing Supervisor",
            "Quality Manager", "Quality Control Manager", "Quality Assurance Manager",
            "Lean Manager", "Continuous Improvement Manager", "Process Improvement Manager",
            # Warehouse & Logistics
            "Warehouse Manager", "Warehouse Supervisor", "Warehouse Director",
            "Distribution Manager", "Distribution Center Manager",
            "Logistics Manager", "Logistics Director", "Logistics Coordinator",
            "Supply Chain Manager", "Supply Chain Director",
            "Inventory Manager", "Inventory Control Manager",
            "Shipping Manager", "Receiving Manager", "Freight Manager",
            "Fleet Manager", "Dispatch Manager", "Transportation Manager",
            # Facilities & Maintenance
            "Facilities Manager", "Facilities Director", "Building Manager",
            "Maintenance Manager", "Maintenance Director", "Maintenance Supervisor",
            "Property Manager", "Property Management Director",
            # Safety & Compliance
            "Safety Manager", "Safety Director", "Safety Coordinator",
            "EHS Manager", "Environmental Health Safety Manager", "HSE Manager",
            "Compliance Manager", "Compliance Director", "Compliance Officer",
            "Risk Manager", "Risk Director", "Loss Prevention Manager",
            "Claims Manager", "Regulatory Affairs Manager",
            # Construction & Engineering
            "Construction Manager", "Construction Superintendent", "Construction Director",
            "Project Manager", "Senior Project Manager", "Program Manager",
            "Engineering Manager", "Engineering Director",
            # Purchasing & Procurement
            "Purchasing Manager", "Purchasing Director",
            "Procurement Manager", "Procurement Director",
            "Buyer", "Senior Buyer", "Category Manager",
            "Vendor Manager", "Supplier Manager",
            # Hospitality & Food Service
            "Restaurant Manager", "Restaurant General Manager",
            "Hotel Manager", "Hotel General Manager", "Front Desk Manager",
            "Food Service Manager", "Food Service Director",
            "Banquet Manager", "Catering Manager",
            "Housekeeping Manager", "Housekeeping Director",
            "Executive Chef", "Kitchen Manager",
            # Retail
            "Store Manager", "Store Director", "Retail Manager",
            "Assistant Store Manager", "Retail Operations Manager",
            "Merchandise Manager", "Visual Merchandising Manager",
            # Healthcare & Social Services
            "Nurse Manager", "Nursing Director", "Director of Nursing",
            "Clinical Manager", "Practice Manager", "Office Manager",
            "Healthcare Administrator", "Hospital Administrator",
            "Social Services Director", "Case Manager",
            # Training & Development
            "Training Manager", "Training Director", "Learning and Development Manager",
            "Organizational Development Manager",
            # Finance & Accounting
            "Controller", "Accounting Manager", "Finance Manager",
            "Accounts Payable Manager", "Accounts Receivable Manager",
            "Credit Manager", "Collections Manager",
            # Sales & Business Development
            "Account Manager", "Sales Manager", "Regional Sales Manager",
            "Business Development Manager", "Service Manager",
            "Customer Service Manager", "Call Center Manager",
            # Agriculture & Trades
            "Farm Manager", "Ranch Manager", "Ag Operations Manager",
            "Shop Manager", "Foreman", "Superintendent",
        ],
        "type": "list",
        "description": "Master list of all available job titles"
    },

    # Target Job Titles (Selected for Search)
    "target_job_titles": {
        "value": [
            # HR & Talent
            "HR Manager", "HR Director", "HR Business Partner", "HR Generalist",
            "HR Coordinator", "Recruiter", "Talent Acquisition", "Talent Acquisition Manager",
            "Staffing Coordinator", "Staffing Manager", "Talent Manager", "Workforce Manager",
            "Recruitment Manager", "People Operations Manager", "Employee Relations Manager",
            "Compensation Manager", "Benefits Manager", "Payroll Manager",
            "VP Human Resources", "Director of HR", "Chief People Officer",
            # Operations & General Management
            "Operations Manager", "Operations Director", "VP Operations",
            "Director of Operations", "COO", "Chief Operating Officer",
            "General Manager", "Assistant General Manager", "Regional Manager",
            "Area Manager", "District Manager", "Territory Manager",
            "Branch Manager", "Site Manager", "Field Manager",
            # Manufacturing & Production
            "Plant Manager", "Production Manager", "Production Supervisor",
            "Manufacturing Manager", "Manufacturing Director", "Manufacturing Supervisor",
            "Quality Manager", "Quality Control Manager", "Quality Assurance Manager",
            "Lean Manager", "Continuous Improvement Manager", "Process Improvement Manager",
            # Warehouse & Logistics
            "Warehouse Manager", "Warehouse Supervisor", "Warehouse Director",
            "Distribution Manager", "Distribution Center Manager",
            "Logistics Manager", "Logistics Director", "Logistics Coordinator",
            "Supply Chain Manager", "Supply Chain Director",
            "Inventory Manager", "Inventory Control Manager",
            "Shipping Manager", "Receiving Manager", "Freight Manager",
            "Fleet Manager", "Dispatch Manager", "Transportation Manager",
            # Facilities & Maintenance
            "Facilities Manager", "Facilities Director", "Building Manager",
            "Maintenance Manager", "Maintenance Director", "Maintenance Supervisor",
            "Property Manager", "Property Management Director",
            # Safety & Compliance
            "Safety Manager", "Safety Director", "Safety Coordinator",
            "EHS Manager", "Environmental Health Safety Manager", "HSE Manager",
            "Compliance Manager", "Compliance Director", "Compliance Officer",
            "Risk Manager", "Risk Director", "Loss Prevention Manager",
            "Claims Manager", "Regulatory Affairs Manager",
            # Construction & Engineering
            "Construction Manager", "Construction Superintendent", "Construction Director",
            "Project Manager", "Senior Project Manager", "Program Manager",
            "Engineering Manager", "Engineering Director",
            # Purchasing & Procurement
            "Purchasing Manager", "Purchasing Director",
            "Procurement Manager", "Procurement Director",
            "Buyer", "Senior Buyer", "Category Manager",
            "Vendor Manager", "Supplier Manager",
            # Hospitality & Food Service
            "Restaurant Manager", "Restaurant General Manager",
            "Hotel Manager", "Hotel General Manager", "Front Desk Manager",
            "Food Service Manager", "Food Service Director",
            "Banquet Manager", "Catering Manager",
            "Housekeeping Manager", "Housekeeping Director",
            "Executive Chef", "Kitchen Manager",
            # Retail
            "Store Manager", "Store Director", "Retail Manager",
            "Assistant Store Manager", "Retail Operations Manager",
            "Merchandise Manager", "Visual Merchandising Manager",
            # Healthcare & Social Services
            "Nurse Manager", "Nursing Director", "Director of Nursing",
            "Clinical Manager", "Practice Manager", "Office Manager",
            "Healthcare Administrator", "Hospital Administrator",
            "Social Services Director", "Case Manager",
            # Training & Development
            "Training Manager", "Training Director", "Learning and Development Manager",
            "Organizational Development Manager",
            # Finance & Accounting
            "Controller", "Accounting Manager", "Finance Manager",
            "Accounts Payable Manager", "Accounts Receivable Manager",
            "Credit Manager", "Collections Manager",
            # Sales & Business Development
            "Account Manager", "Sales Manager", "Regional Sales Manager",
            "Business Development Manager", "Service Manager",
            "Customer Service Manager", "Call Center Manager",
            # Agriculture & Trades
            "Farm Manager", "Ranch Manager", "Ag Operations Manager",
            "Shop Manager", "Foreman", "Superintendent",
        ],
        "type": "list",
        "description": "Selected job titles to use in lead searches"
    },

    # Company Size Preferences
    "company_size_priority_1_max": {"value": 50, "type": "integer", "description": "Priority 1: Max employees (small companies)"},
    "company_size_priority_2_min": {"value": 51, "type": "integer", "description": "Priority 2: Min employees"},
    "company_size_priority_2_max": {"value": 500, "type": "integer", "description": "Priority 2: Max employees"},

    # IT Role Exclusion Keywords
    "exclude_it_keywords": {
        "value": [
            "software", "developer", "engineer", "IT", "technology",
            "programmer", "coding", "tech", "data scientist", "devops",
            "full stack", "frontend", "backend", "python", "java", "javascript",
            "cloud", "aws", "azure", "cybersecurity", "network admin",
            "machine learning", "AI engineer", "system administrator"
        ],
        "type": "list",
        "description": "Keywords to exclude IT-related jobs"
    },

    # Staffing Company Exclusion Keywords
    "exclude_staffing_keywords": {
        "value": [
            "staffing agency", "staffing firm", "recruitment agency",
            "talent acquisition agency", "temp agency",
            "employment agency", "executive search firm",
            "recruitment", "government", "administration",
            "medical", "non profit", "nonprofit",
            "civics", "social services",
            "computer security", "network security", "security agency",
            "telecommunication",
            "primary education", "secondary education", "university",
            "religious", "church"
        ],
        "type": "list",
        "description": "Keywords to exclude staffing/recruitment companies and irrelevant industries"
    },

    # Company-only exclusion keywords
    "exclude_company_keywords": {
        "value": [
            "staffing agency", "staffing firm", "recruitment agency",
            "talent acquisition agency", "temp agency",
            "employment agency", "executive search firm",
            "security agency"
        ],
        "type": "list",
        "description": "Exclusion keywords matched against company name only"
    },

    # Title-only exclusion keywords
    "exclude_title_keywords": {
        "value": ["intern", "entry level"],
        "type": "list",
        "description": "Exclusion keywords matched against job title only"
    },

    # Job type / employment-type exclusions
    "exclude_job_types": {
        "value": [],
        "type": "list",
        "description": "Employment types to exclude (Full-time, Part-time, Contract, Temporary, Internship, Volunteer). Matched against the lead's normalized employment_type; unknown is never dropped."
    },

    # Exclusion match mode
    "exclude_match_mode": {
        "value": "word_boundary",
        "type": "string",
        "description": "How exclusion keywords match: word_boundary (recommended) or substring"
    },

    # Lead sourcing scheduler frequency
    "lead_sourcing_frequency": {
        "value": "2x",
        "type": "string",
        "description": "Lead sourcing runs per day: 2x, 4x, or 6x"
    },

    # Location diversification
    "location_diversification": {
        "value": False,
        "type": "boolean",
        "description": "Search per-state instead of nationwide for more results (uses more API calls)"
    },

    # Job Title Categories (grouped by industry/function)
    "job_title_categories": {
        "value": None,  # Uses config.JOB_TITLE_CATEGORIES as default when None
        "type": "object",
        "description": "Job titles grouped by category — dict of category_name: [titles]"
    },

    # Warmup Engine Configuration
    "backup_retention_days": {"value": 3, "type": "integer", "description": "Auto-delete backups older than this many days"},

    "warmup_phase_1_days": {"value": 7, "type": "integer", "description": "Phase 1 (Initial) duration in days"},
    "warmup_phase_1_min_emails": {"value": 2, "type": "integer", "description": "Phase 1 minimum emails per day"},
    "warmup_phase_1_max_emails": {"value": 5, "type": "integer", "description": "Phase 1 maximum emails per day"},
    "warmup_phase_2_days": {"value": 7, "type": "integer", "description": "Phase 2 (Building Trust) duration in days"},
    "warmup_phase_2_min_emails": {"value": 5, "type": "integer", "description": "Phase 2 minimum emails per day"},
    "warmup_phase_2_max_emails": {"value": 15, "type": "integer", "description": "Phase 2 maximum emails per day"},
    "warmup_phase_3_days": {"value": 7, "type": "integer", "description": "Phase 3 (Scaling Up) duration in days"},
    "warmup_phase_3_min_emails": {"value": 15, "type": "integer", "description": "Phase 3 minimum emails per day"},
    "warmup_phase_3_max_emails": {"value": 25, "type": "integer", "description": "Phase 3 maximum emails per day"},
    "warmup_phase_4_days": {"value": 9, "type": "integer", "description": "Phase 4 (Full Ramp) duration in days"},
    "warmup_phase_4_min_emails": {"value": 25, "type": "integer", "description": "Phase 4 minimum emails per day"},
    "warmup_phase_4_max_emails": {"value": 35, "type": "integer", "description": "Phase 4 maximum emails per day"},
    "warmup_bounce_rate_good": {"value": 2.0, "type": "float", "description": "Bounce rate threshold for good score (%)"},
    "warmup_bounce_rate_bad": {"value": 5.0, "type": "float", "description": "Bounce rate threshold for bad score (%)"},
    "warmup_reply_rate_good": {"value": 10.0, "type": "float", "description": "Reply rate threshold for good score (%)"},
    "warmup_complaint_rate_bad": {"value": 0.1, "type": "float", "description": "Complaint rate threshold for bad score (%)"},
    "warmup_weight_bounce_rate": {"value": 35, "type": "integer", "description": "Health score weight for bounce rate"},
    "warmup_weight_reply_rate": {"value": 25, "type": "integer", "description": "Health score weight for reply rate"},
    "warmup_weight_complaint_rate": {"value": 25, "type": "integer", "description": "Health score weight for complaint rate"},
    "warmup_weight_age": {"value": 15, "type": "integer", "description": "Health score weight for account age"},
    "warmup_auto_pause_bounce_rate": {"value": 5.0, "type": "float", "description": "Auto-pause if bounce rate exceeds this (%)"},
    "warmup_auto_pause_complaint_rate": {"value": 0.3, "type": "float", "description": "Auto-pause if complaint rate exceeds this (%)"},
    "warmup_min_emails_for_scoring": {"value": 10, "type": "integer", "description": "Min emails sent before health scoring applies"},
    "warmup_active_health_threshold": {"value": 80, "type": "integer", "description": "Health score required for ACTIVE promotion"},
    "warmup_active_min_days": {"value": 7, "type": "integer", "description": "Min days in COLD_READY before ACTIVE"},
    "warmup_total_days": {"value": 30, "type": "integer", "description": "Total warmup duration in days"},
    "warmup_daily_increment": {"value": 1.0, "type": "float", "description": "Daily send limit increment factor"},
    # Enterprise Warmup Engine Settings
    "warmup_peer_enabled": {"value": True, "type": "boolean", "description": "Enable peer-to-peer warmup emails"},
    "warmup_peer_reply_rate": {"value": 30, "type": "integer", "description": "Peer warmup auto-reply rate (%)"},
    "warmup_peer_min_delay_minutes": {"value": 5, "type": "integer", "description": "Minimum delay between peer emails (minutes)"},
    "warmup_peer_max_delay_minutes": {"value": 30, "type": "integer", "description": "Maximum delay between peer emails (minutes)"},
    "warmup_peer_max_emails_per_pair": {"value": 3, "type": "integer", "description": "Max warmup emails per mailbox pair per cycle"},
    "warmup_ai_provider": {"value": "groq", "type": "string", "description": "AI provider for warmup content generation"},
    "warmup_ai_temperature": {"value": 0.8, "type": "float", "description": "AI content generation temperature"},
    "warmup_content_max_length": {"value": 200, "type": "integer", "description": "Max word length for AI warmup content"},
    "warmup_content_categories": {"value": ["meeting_followup", "project_update", "question", "introduction", "thank_you", "scheduling"], "type": "list", "description": "Enabled content categories for warmup emails"},
    "warmup_send_window_start": {"value": "09:00", "type": "string", "description": "Smart schedule send window start (HH:MM)"},
    "warmup_send_window_end": {"value": "17:00", "type": "string", "description": "Smart schedule send window end (HH:MM)"},
    "warmup_timezone": {"value": "US/Eastern", "type": "string", "description": "Timezone for smart scheduling"},
    "warmup_skip_weekends": {"value": True, "type": "boolean", "description": "Skip warmup emails on weekends"},
    "warmup_min_gap_minutes": {"value": 15, "type": "integer", "description": "Minimum gap between warmup sends (minutes)"},
    "warmup_max_gap_minutes": {"value": 60, "type": "integer", "description": "Maximum gap between warmup sends (minutes)"},
    "warmup_send_speed": {"value": "normal", "type": "string", "description": "Send speed: slow, normal, fast"},
    "warmup_dns_check_interval_hours": {"value": 12, "type": "integer", "description": "DNS check interval (hours)"},
    "warmup_dkim_selector": {"value": "default", "type": "string", "description": "DKIM selector for DNS checks"},
    "warmup_blacklist_check_interval_hours": {"value": 12, "type": "integer", "description": "Blacklist check interval (hours)"},
    "warmup_blacklist_providers": {"value": ["zen.spamhaus.org", "bl.spamcop.net", "b.barracudacentral.org", "dnsbl.sorbs.net", "cbl.abuseat.org"], "type": "list", "description": "DNSBL providers for blacklist checks"},
    "warmup_auto_pause_on_blacklist": {"value": True, "type": "boolean", "description": "Auto-pause mailbox if blacklisted"},
    "warmup_seed_emails_json": {"value": [], "type": "list", "description": "Seed emails for inbox placement testing"},
    "warmup_placement_test_interval_hours": {"value": 24, "type": "integer", "description": "Inbox placement test interval (hours)"},
    "warmup_auto_recovery_enabled": {"value": True, "type": "boolean", "description": "Enable auto-recovery for paused mailboxes"},
    "warmup_recovery_wait_days": {"value": 3, "type": "integer", "description": "Days to wait before auto-recovery"},
    "warmup_recovery_ramp_factor": {"value": 1.5, "type": "float", "description": "Recovery ramp-up factor for daily limit"},
    "warmup_tracking_enabled": {"value": True, "type": "boolean", "description": "Enable open/click tracking for warmup emails"},
    "warmup_tracking_base_url": {"value": app_config.EFFECTIVE_BASE_URL, "type": "string", "description": "Base URL for tracking pixel/link endpoints"},
    "warmup_google_postmaster_api_key": {"value": "", "type": "string", "description": "Google Postmaster Tools API key (optional)"},
    "warmup_scheduler_enabled": {"value": True, "type": "boolean", "description": "Enable background warmup scheduler"},
    "warmup_daily_assessment_time": {"value": "00:05", "type": "string", "description": "Daily assessment time (HH:MM UTC)"},
    "warmup_reply_check_interval_minutes": {"value": 60, "type": "integer", "description": "Reply check interval (minutes)"},
    "warmup_alerts_enabled": {"value": True, "type": "boolean", "description": "Enable warmup alerts"},
    "warmup_alert_on_status_change": {"value": True, "type": "boolean", "description": "Alert on mailbox status changes"},
    "warmup_alert_on_health_drop": {"value": True, "type": "boolean", "description": "Alert when health score drops"},
    "warmup_alert_health_drop_threshold": {"value": 20, "type": "integer", "description": "Health score drop threshold for alerts (%)"},
    "warmup_default_profile": {"value": "Standard", "type": "string", "description": "Default warmup profile name"},

    # Automation Control Center
    "automation_master_enabled": {"value": True, "type": "boolean", "description": "Master switch — disables non-warmup scheduled automation when off (Warmup Engine runs independently)"},
    "automation_chain_enrichment": {"value": False, "type": "boolean", "description": "Auto-chain: run contact enrichment after lead sourcing"},
    "automation_chain_validation": {"value": False, "type": "boolean", "description": "Auto-chain: run email validation after contact enrichment"},
    "automation_daily_assessment_enabled": {"value": True, "type": "boolean", "description": "Enable Daily Warmup Assessment job"},
    "automation_peer_warmup_cycle_enabled": {"value": True, "type": "boolean", "description": "Enable Peer Warmup Cycle job"},
    "automation_auto_reply_cycle_enabled": {"value": True, "type": "boolean", "description": "Enable Auto Reply Cycle job"},
    "automation_daily_count_reset_enabled": {"value": True, "type": "boolean", "description": "Enable Daily Count Reset job"},
    "automation_dns_checks_enabled": {"value": True, "type": "boolean", "description": "Enable DNS Health Checks job"},
    "automation_blacklist_checks_enabled": {"value": True, "type": "boolean", "description": "Enable Blacklist Checks job"},
    "automation_daily_log_snapshot_enabled": {"value": True, "type": "boolean", "description": "Enable Daily Log Snapshot job"},
    "automation_auto_recovery_check_enabled": {"value": True, "type": "boolean", "description": "Enable Auto Recovery Check job"},
    "automation_check_outreach_replies_enabled": {"value": True, "type": "boolean", "description": "Enable Check Outreach Replies job"},
    "automation_lead_sourcing_run_enabled": {"value": True, "type": "boolean", "description": "Enable Scheduled Lead Sourcing job"},
    "automation_daily_backup_enabled": {"value": True, "type": "boolean", "description": "Enable Daily Database Backup job"},
    "automation_backup_cleanup_enabled": {"value": True, "type": "boolean", "description": "Enable Backup Cleanup job"},
    "automation_campaign_processor_enabled": {"value": True, "type": "boolean", "description": "Enable Campaign Sequence Processor job"},
    "automation_inbox_sync_enabled": {"value": True, "type": "boolean", "description": "Enable Inbox Sync job"},
    "automation_lead_scoring_enabled": {"value": True, "type": "boolean", "description": "Enable Daily Lead Scoring job"},
    "automation_imap_read_cycle_enabled": {"value": True, "type": "boolean", "description": "Enable IMAP Read Emulation job"},
    "automation_crm_sync_enabled": {"value": True, "type": "boolean", "description": "Enable Nightly CRM Sync job"},
    "automation_chain_enrollment": {"value": False, "type": "boolean", "description": "Auto-chain: enroll validated contacts into campaigns"},
    "automation_auto_enrollment_enabled": {"value": True, "type": "boolean", "description": "Enable auto-enrollment scheduler job"},
    "automation_cost_aggregation_enabled": {"value": True, "type": "boolean", "description": "Enable daily cost aggregation job (23:45 UTC)"},
    "automation_cost_analysis_enabled": {"value": True, "type": "boolean", "description": "Enable monthly cost analysis job (1st of month)"},

    # LOB Lead Source API Keys
    "google_places_api_key": {
        "value": "", "type": "string",
        "description": "Google Places API key for business search (RCM, Digital Marketing). Get at console.cloud.google.com"
    },
    "crunchbase_api_key": {
        "value": "", "type": "string",
        "description": "Crunchbase API key for company intelligence (Software Dev, AI Services). Get at data.crunchbase.com"
    },
    "builtwith_api_key": {
        "value": "", "type": "string",
        "description": "BuiltWith API key for technographic data (Software Dev, Digital Marketing). Get at builtwith.com/api"
    },
    "github_token": {
        "value": "", "type": "string",
        "description": "GitHub personal access token for higher rate limits (5000/hr vs 60/hr). Get at github.com/settings/tokens"
    },

    # Intent Signal Automation
    "automation_intent_signals_enabled": {"value": True, "type": "boolean", "description": "Enable scheduled intent signal monitoring jobs"},

    # Source Tuning — per-adapter performance parameters
    "job_source_tuning": {
        "value": {
            "jsearch": {"batch_size": 4, "num_pages": 10},
            "serpapi": {"batch_size": 4, "max_pages": 3},
            "searchapi": {"batch_size": 4, "max_pages": 3},
            "adzuna": {"batch_size": 4, "max_pages": 10, "results_per_page": 50},
            "theirstack": {"batch_size": 20, "max_pages": 10},
            "usajobs": {"batch_size": 2, "max_pages": 5, "results_per_page": 100},
            "jooble": {"batch_size": 4, "max_pages": 5},
            "jobdatafeeds": {"batch_size": 4, "max_pages": 50, "results_per_page": 100},
            "coresignal": {"batch_size": 5, "max_pages": 5, "results_per_page": 100},
        },
        "type": "object",
        "description": "Per-adapter tuning parameters (batch_size, max_pages, results_per_page)"
    },
    "pipeline_adapter_limit": {"value": 1000, "type": "integer", "description": "Max results per adapter in lead sourcing pipeline"},
    "pipeline_max_workers": {"value": 6, "type": "integer", "description": "Thread pool size for parallel adapter execution"},
    "posted_within_days": {"value": 7, "type": "integer", "description": "Only fetch jobs posted within this many days (1-90). Lower = fewer duplicates."},
    "posted_within_hours": {"value": 0, "type": "integer", "description": "Fetch window in hours (0 = use posted_within_days). 1-2160. When set, takes precedence; hour-aware sources (Fantastic.jobs) honor it exactly, day-based sources use ceil(hours/24) days."},
    "lead_sourcing_max_employee_count": {"value": 200, "type": "integer", "description": "Drop companies larger than this many employees at sourcing (0 = no size limit)"},
    "lead_sourcing_drop_confidential": {"value": True, "type": "boolean", "description": "Drop confidential/blank employer postings at sourcing"},
    "lead_sourcing_excluded_industries": {"value": [], "type": "list", "description": "Industries hard-dropped at sourcing (substring match); empty = built-in IT/staffing/government defaults"},
    "lead_sourcing_enrich_company_at_source": {"value": True, "type": "boolean", "description": "Fill missing company industry/size via AI (Groq) at sourcing, cached on ClientInfo"},
    "lead_sourcing_enrich_max_companies": {"value": 300, "type": "integer", "description": "Max AI company lookups per sourcing run (cost/latency cap)"},

    # Cost Budget
    "cost_monthly_budget_total": {"value": 500, "type": "number", "description": "Total monthly budget for API costs (USD)"},

    # Deal Pipeline Automation
    "deal_auto_create_on_interested": {"value": True, "type": "boolean", "description": "Auto-create deal when inbox reply is classified as interested"},
    "deal_auto_advance_stages": {"value": True, "type": "boolean", "description": "Auto-advance deal stages on email sent/reply received signals"},
    "deal_auto_log_activities": {"value": True, "type": "boolean", "description": "Auto-log email events (sent/received/bounced) as deal activities"},
    "deal_stale_threshold_days": {"value": 7, "type": "integer", "description": "Flag deals with no activity for this many days as stale"},
    "deal_score_to_probability": {"value": True, "type": "boolean", "description": "Auto-update deal probability from contact lead score"},

}


@router.get("/my-permissions")
async def get_my_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get the current user's effective permissions for all modules."""
    from app.api.deps.auth import get_module_permission
    modules = [
        'leads', 'contacts', 'deals', 'campaigns', 'inbox', 'analytics',
        'outreach', 'templates', 'mailboxes', 'warmup', 'pipelines',
        'automation', 'settings', 'users', 'roles', 'clients',
        'icp', 'validation', 'billing',
    ]
    return {m: get_module_permission(db, current_user, m) for m in modules}


@router.get("/my-permissions/settings-tabs")
async def get_my_settings_tab_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Get the current user's settings tab permissions."""
    return get_all_settings_tab_permissions(db, current_user)


@router.get("", response_model=List[SettingResponse])
async def list_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List all settings. Returns merged global+tenant settings.

    Tenant overrides are applied on top of global defaults.
    Each item includes is_tenant_override=True if a tenant-specific value exists.
    """
    all_settings = db.query(Settings).order_by(Settings.key).all()

    # Build tenant overrides lookup
    overrides: Dict[str, object] = {}
    if tenant_id is not None:
        overrides = get_tenant_overrides(db, tenant_id)

    if current_user.role == UserRole.SUPER_ADMIN and tenant_id is None:
        return [SettingResponse.model_validate(s) for s in all_settings]

    # Filter settings based on tab permissions
    tab_perms = get_all_settings_tab_permissions(db, current_user)
    accessible_tabs = {tab for tab, access in tab_perms.items() if access != 'no_access'}

    result = []
    for s in all_settings:
        tab = SETTINGS_TAB_MAP.get(s.key)
        is_super = current_user.role == UserRole.SUPER_ADMIN
        if is_super or tab is None or tab in accessible_tabs:
            resp = SettingResponse.model_validate(s)
            # Apply tenant override if exists
            if s.key in overrides:
                resp.value_json = json.dumps(overrides[s.key])
                resp.is_tenant_override = True
            result.append(resp)
    return result


@router.get("/tenant-overrides", response_model=Dict[str, object])
async def list_tenant_overrides(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List keys that the current tenant has explicitly overridden."""
    if tenant_id is None:
        return {}
    return get_tenant_overrides(db, tenant_id)


class CompanyProfileUpdate(PydanticBaseModel):
    name: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    company_address: Optional[str] = None


@router.get("/company-profile")
async def get_company_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get the current tenant's company profile."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "name": tenant.name,
        "website": tenant.website,
        "industry": tenant.industry,
        "company_address": tenant.company_address,
    }


@router.put("/company-profile")
async def update_company_profile(
    data: CompanyProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update the current tenant's company profile (admin+)."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if data.name is not None:
        tenant.name = data.name
    if data.website is not None:
        tenant.website = data.website
    if data.industry is not None:
        tenant.industry = data.industry
    if data.company_address is not None:
        tenant.company_address = data.company_address

    db.commit()
    db.refresh(tenant)

    # Update the user's in-memory tenant info for next token refresh
    return {
        "message": "Company profile updated",
        "name": tenant.name,
        "website": tenant.website,
        "industry": tenant.industry,
        "company_address": tenant.company_address,
    }


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get setting by key (resolved with tenant overrides)."""
    # Check tab-level read permission for non-super-admin
    if current_user.role != UserRole.SUPER_ADMIN:
        tab = SETTINGS_TAB_MAP.get(key)
        if tab:
            access = get_user_settings_tab_access(db, current_user, tab)
            if access == 'no_access':
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No access to this settings tab"
                )

    setting = db.query(Settings).filter(Settings.key == key).first()
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Setting not found"
        )
    resp = SettingResponse.model_validate(setting)

    # Apply tenant override if present
    if tenant_id is not None:
        overrides = get_tenant_overrides(db, tenant_id)
        if key in overrides:
            resp.value_json = json.dumps(overrides[key])
            resp.is_tenant_override = True

    return resp


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    setting_in: SettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update or create setting (Admin only).

    - Super admin without X-Tenant-ID: writes to global Settings table.
    - Regular admin / super admin with X-Tenant-ID: writes to TenantSettings.
    """
    # role_permissions is always super_admin only
    if key == 'role_permissions' and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can modify role permissions"
        )

    # Check tab-level write permission for non-super-admin
    if current_user.role != UserRole.SUPER_ADMIN:
        tab = SETTINGS_TAB_MAP.get(key)
        if tab:
            access = get_user_settings_tab_access(db, current_user, tab)
            if access in ('no_access', 'read'):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No write access to the '{tab}' settings tab"
                )

    # Validate backup_retention_days: integer, min 1, max 90
    if key == "backup_retention_days":
        raw = setting_in.value if setting_in.value is not None else (
            json.loads(setting_in.value_json) if setting_in.value_json is not None else None
        )
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="backup_retention_days must be an integer",
            )
        if val < 1 or val > 90:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="backup_retention_days must be between 1 and 90",
            )

    # Validate source tuning keys
    if key == "pipeline_max_workers":
        raw = setting_in.value if setting_in.value is not None else (
            json.loads(setting_in.value_json) if setting_in.value_json is not None else None
        )
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pipeline_max_workers must be an integer")
        if val < 1 or val > 20:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pipeline_max_workers must be between 1 and 20")

    if key == "pipeline_adapter_limit":
        raw = setting_in.value if setting_in.value is not None else (
            json.loads(setting_in.value_json) if setting_in.value_json is not None else None
        )
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pipeline_adapter_limit must be an integer")
        if val < 10 or val > 50000:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pipeline_adapter_limit must be between 10 and 50000")

    if key == "posted_within_days":
        raw = setting_in.value if setting_in.value is not None else (
            json.loads(setting_in.value_json) if setting_in.value_json is not None else None
        )
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="posted_within_days must be an integer")
        if val < 1 or val > 90:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="posted_within_days must be between 1 and 90")

    if key == "posted_within_hours":
        raw = setting_in.value if setting_in.value is not None else (
            json.loads(setting_in.value_json) if setting_in.value_json is not None else None
        )
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="posted_within_hours must be an integer")
        if val < 0 or val > 2160:  # 0 = use days; 2160h = 90 days
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="posted_within_hours must be between 0 and 2160 (0 = use days)")

    if key == "lead_sourcing_max_employee_count":
        raw = setting_in.value if setting_in.value is not None else (
            json.loads(setting_in.value_json) if setting_in.value_json is not None else None
        )
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="lead_sourcing_max_employee_count must be an integer")
        if val < 0 or val > 1_000_000:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="lead_sourcing_max_employee_count must be between 0 and 1000000 (0 disables the size limit)")

    if key == "lead_sourcing_enrich_max_companies":
        raw = setting_in.value if setting_in.value is not None else (
            json.loads(setting_in.value_json) if setting_in.value_json is not None else None
        )
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="lead_sourcing_enrich_max_companies must be an integer")
        if val < 0 or val > 5000:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="lead_sourcing_enrich_max_companies must be between 0 and 5000")

    if key == "lead_sourcing_excluded_industries":
        raw = setting_in.value if setting_in.value is not None else (
            json.loads(setting_in.value_json) if setting_in.value_json is not None else None
        )
        if raw is not None and not isinstance(raw, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="lead_sourcing_excluded_industries must be a list of strings")

    if key == "job_source_tuning":
        raw = setting_in.value if setting_in.value is not None else (
            json.loads(setting_in.value_json) if setting_in.value_json is not None else None
        )
        if not isinstance(raw, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job_source_tuning must be a JSON object")
        valid_adapters = {"jsearch", "serpapi", "searchapi", "adzuna", "theirstack", "usajobs", "jooble", "jobdatafeeds", "coresignal", "fantastic_jobs"}
        for adapter_name, params in raw.items():
            if adapter_name not in valid_adapters:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown adapter: {adapter_name}")
            if not isinstance(params, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Params for {adapter_name} must be an object")
            for pk, pv in params.items():
                # List-valued params (e.g. theirstack.industry_id_not — LinkedIn
                # industry codes to exclude) must be lists of integers.
                if isinstance(pv, list):
                    if not all(isinstance(x, int) and not isinstance(x, bool) for x in pv):
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{adapter_name}.{pk} must be a list of integers")
                    continue
                # max_employee_count may be 0 = "auto" (follow the ICP size gate).
                min_ok = 0 if pk == "max_employee_count" else 1
                if isinstance(pv, bool) or not isinstance(pv, (int, float)) or pv < min_ok:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{adapter_name}.{pk} must be >= {min_ok}")

    # Determine the value to store
    if setting_in.value_json is not None:
        value_json = setting_in.value_json
    elif setting_in.value is not None:
        value_json = json.dumps(setting_in.value)
    else:
        value_json = json.dumps(None)

    parsed_value = json.loads(value_json)

    # Write to tenant_settings if tenant context, else global
    if tenant_id is not None:
        set_tenant_setting(db, key, parsed_value, tenant_id=tenant_id, updated_by=current_user.email)
        db.commit()

        # Return the global row with override applied
        setting = db.query(Settings).filter(Settings.key == key).first()
        if setting:
            resp = SettingResponse.model_validate(setting)
            resp.value_json = value_json
            resp.is_tenant_override = True
            return resp
        # No global row — return a synthetic response
        return SettingResponse(
            key=key,
            value_json=value_json,
            type=setting_in.type or "string",
            description=setting_in.description or f"Setting: {key}",
            updated_by=current_user.email,
            updated_at=__import__("datetime").datetime.utcnow(),
            is_tenant_override=True,
        )
    else:
        # Global write (super admin without X-Tenant-ID)
        setting = db.query(Settings).filter(Settings.key == key).first()
        if not setting:
            setting = Settings(
                key=key,
                value_json=value_json,
                type=setting_in.type or "string",
                description=setting_in.description or f"Setting: {key}",
                updated_by=current_user.email,
            )
            db.add(setting)
        else:
            setting.value_json = value_json
            if setting_in.type:
                setting.type = setting_in.type
            if setting_in.description:
                setting.description = setting_in.description
            setting.updated_by = current_user.email

        # When saving role_permissions or user_permission_overrides globally,
        # clear all tenant-level overrides so the new global value takes effect
        # everywhere (prevents stale tenant overrides from shadowing the global).
        if key in ('role_permissions', 'user_permission_overrides'):
            from app.db.models.tenant_settings import TenantSettings
            deleted = db.query(TenantSettings).filter(TenantSettings.key == key).delete()
            if deleted:
                logger.info("cleared_tenant_overrides", key=key, count=deleted)

        db.commit()
        db.refresh(setting)
        return SettingResponse.model_validate(setting)


@router.post("/initialize")
async def initialize_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Initialize default settings (Admin only)."""
    created = 0
    for key, config in DEFAULT_SETTINGS.items():
        existing = db.query(Settings).filter(Settings.key == key).first()
        if not existing:
            setting = Settings(
                key=key,
                value_json=json.dumps(config["value"]),
                type=config["type"],
                description=config.get("description"),
                updated_by=current_user.email,
            )
            db.add(setting)
            created += 1

    db.commit()

    return {"message": f"Initialized {created} settings", "total": len(DEFAULT_SETTINGS)}


def get_setting_value(db: Session, key: str, default: str = "", tenant_id: Optional[int] = None) -> str:
    """Get a setting value from database (tenant-aware)."""
    return get_tenant_setting(db, key, tenant_id=tenant_id, default=default)


@router.delete("/{key}/tenant-override")
async def remove_tenant_override(
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Remove a tenant's override for a key, reverting to the global default."""
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant context — cannot delete a global setting via this endpoint",
        )
    deleted = delete_tenant_setting(db, key, tenant_id)
    db.commit()
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No tenant override found for key '{key}'",
        )
    return {"message": f"Tenant override for '{key}' removed. Reverted to global default."}


PROVIDER_TAB_MAP: Dict[str, str] = {
    'apollo': 'contacts',  # Apollo is contact-enrichment only, not a job source
    'jsearch': 'job_source_apis',
    'indeed': 'job_source_apis',
    'theirstack': 'job_source_apis',
    'serpapi': 'job_source_apis',
    'adzuna': 'job_source_apis',
    'searchapi': 'job_source_apis',
    'usajobs': 'job_source_apis',
    'jooble': 'job_source_apis',
    'jobdatafeeds': 'job_source_apis',
    'coresignal': 'job_source_apis',
    'fantastic_jobs': 'job_source_apis',
    'seamless': 'contacts',
    'hunter_contact': 'contacts',
    'snovio': 'contacts',
    'rocketreach': 'contacts',
    'pdl': 'contacts',
    'proxycurl': 'contacts',
    'clearbit': 'contacts',
    'opencorporates': 'contacts',
    'neverbounce': 'validation',
    'zerobounce': 'validation',
    'smtp': 'outreach',
    'm365': 'outreach',
    'groq': 'ai_llm',
    'openai': 'ai_llm',
    'anthropic': 'ai_llm',
    'gemini': 'ai_llm',
    # LOB Lead Source Providers
    'npi_registry': 'lob_lead_sources',
    'google_business': 'lob_lead_sources',
    'crunchbase': 'lob_lead_sources',
    'builtwith': 'lob_lead_sources',
    'github_org': 'lob_lead_sources',
    'pagespeed': 'lob_lead_sources',
}


@router.post("/test-connection/{provider}")
async def test_provider_connection(
    provider: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Test connection to a provider (uses tenant-specific API keys if set)."""
    # Check tab-level permission for the provider
    if current_user.role != UserRole.SUPER_ADMIN:
        tab = PROVIDER_TAB_MAP.get(provider)
        if tab:
            access = get_user_settings_tab_access(db, current_user, tab)
            if access == 'no_access':
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No access to the '{tab}' settings tab"
                )

    # Tenant-aware setting getter (uses tenant's API keys if overridden)
    def _gs(key: str, default: str = "") -> str:
        return get_setting_value(db, key, default, tenant_id=tenant_id)

    try:
        if provider == "apollo":
            api_key = _gs("apollo_api_key")
            if not api_key:
                return {"status": "error", "message": "Apollo API key not configured", "provider": provider}
            from app.services.adapters.contact_discovery.apollo import ApolloAdapter
            adapter = ApolloAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed", "provider": provider}

        elif provider == "seamless":
            api_key = _gs("seamless_api_key")
            if not api_key:
                return {"status": "error", "message": "Seamless API key not configured", "provider": provider}
            from app.services.adapters.contact_discovery.seamless import SeamlessAdapter
            adapter = SeamlessAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed", "provider": provider}

        elif provider == "neverbounce":
            api_key = _gs("neverbounce_api_key")
            if not api_key:
                return {"status": "error", "message": "NeverBounce API key not configured", "provider": provider}
            from app.services.adapters.email_validation.neverbounce import NeverBounceAdapter
            adapter = NeverBounceAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed", "provider": provider}

        elif provider == "zerobounce":
            api_key = _gs("zerobounce_api_key")
            if not api_key:
                return {"status": "error", "message": "ZeroBounce API key not configured", "provider": provider}
            from app.services.adapters.email_validation.zerobounce import ZeroBounceAdapter
            adapter = ZeroBounceAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed", "provider": provider}

        elif provider == "smtp":
            smtp_host = _gs("smtp_host")
            smtp_port = _gs("smtp_port", "587")
            smtp_user = _gs("smtp_user")
            smtp_password = _gs("smtp_password")

            if not smtp_host:
                return {"status": "error", "message": "SMTP host not configured", "provider": provider}

            # Test SMTP connection
            import smtplib
            try:
                server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=10)
                server.starttls()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.quit()
                return {"status": "success", "message": "SMTP connection successful!", "provider": provider}
            except smtplib.SMTPAuthenticationError:
                return {"status": "error", "message": "SMTP authentication failed", "provider": provider}
            except smtplib.SMTPConnectError:
                return {"status": "error", "message": "Could not connect to SMTP server", "provider": provider}
            except Exception as e:
                return {"status": "error", "message": f"SMTP error: {str(e)}", "provider": provider}

        elif provider == "m365":
            m365_email = _gs("m365_admin_email")
            m365_password = _gs("m365_admin_password")

            if not m365_email or not m365_password:
                return {"status": "error", "message": "Microsoft 365 admin credentials not configured", "provider": provider}

            # Test Microsoft 365 SMTP connection
            import smtplib
            try:
                server = smtplib.SMTP("smtp.office365.com", 587, timeout=15)
                server.starttls()
                server.login(m365_email, m365_password)
                server.quit()
                return {"status": "success", "message": "Microsoft 365 connection successful!", "provider": provider}
            except smtplib.SMTPAuthenticationError:
                return {"status": "error", "message": "M365 authentication failed. Ensure SMTP AUTH is enabled in M365 Admin Center for this user.", "provider": provider}
            except smtplib.SMTPConnectError:
                return {"status": "error", "message": "Could not connect to Microsoft 365 SMTP server", "provider": provider}
            except Exception as e:
                return {"status": "error", "message": f"M365 connection error: {str(e)}", "provider": provider}

        # AI/LLM Providers
        elif provider == "groq":
            api_key = _gs("groq_api_key")
            if not api_key:
                return {"status": "error", "message": "Groq API key not configured", "provider": provider}
            from app.services.adapters.ai.groq import GroqAdapter
            adapter = GroqAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed", "provider": provider}

        elif provider == "openai":
            api_key = _gs("openai_api_key")
            if not api_key:
                return {"status": "error", "message": "OpenAI API key not configured", "provider": provider}
            from app.services.adapters.ai.openai_adapter import OpenAIAdapter
            adapter = OpenAIAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed", "provider": provider}

        elif provider == "anthropic":
            api_key = _gs("anthropic_api_key")
            if not api_key:
                return {"status": "error", "message": "Anthropic API key not configured", "provider": provider}
            from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter
            adapter = AnthropicAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed", "provider": provider}

        elif provider == "gemini":
            api_key = _gs("gemini_api_key")
            if not api_key:
                return {"status": "error", "message": "Gemini API key not configured", "provider": provider}
            from app.services.adapters.ai.gemini import GeminiAdapter
            adapter = GeminiAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed", "provider": provider}

        # Job Source Providers
        elif provider == "jsearch":
            api_key = _gs("jsearch_api_key")
            if not api_key:
                return {"status": "error", "message": "JSearch API key not configured. Get one at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch", "provider": provider}
            from app.services.adapters.job_sources.jsearch import JSearchAdapter
            adapter = JSearchAdapter(api_key=api_key)
            result = adapter.test_connection()
            if isinstance(result, dict):
                if result.get("ok"):
                    return {"status": "success", "message": "Connection successful!", "provider": provider}
                return {"status": "failed", "message": result.get("error", "Connection failed"), "provider": provider}
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your RapidAPI key", "provider": provider}

        elif provider == "indeed":
            publisher_id = _gs("indeed_publisher_id")
            if not publisher_id:
                return {"status": "error", "message": "Indeed Publisher ID not configured. Apply at https://www.indeed.com/publisher", "provider": provider}
            from app.services.adapters.job_sources.indeed import IndeedAdapter
            adapter = IndeedAdapter(publisher_id=publisher_id)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your Publisher ID", "provider": provider}

        # New Job Source Providers
        elif provider == "theirstack":
            api_key = _gs("theirstack_api_key")
            if not api_key:
                return {"status": "error", "message": "TheirStack API key not configured. Get one at https://theirstack.com/", "provider": provider}
            from app.services.adapters.job_sources.theirstack import TheirStackAdapter
            adapter = TheirStackAdapter(api_key=api_key)
            try:
                result = adapter.test_connection()
            except Exception as e:
                return {"status": "failed", "message": f"Connection error: {e}", "provider": provider}
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "serpapi":
            api_key = _gs("serpapi_api_key")
            if not api_key:
                return {"status": "error", "message": "SerpAPI key not configured. Get one at https://serpapi.com/", "provider": provider}
            from app.services.adapters.job_sources.serpapi import SerpAPIAdapter
            adapter = SerpAPIAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "adzuna":
            app_id = _gs("adzuna_app_id")
            api_key = _gs("adzuna_api_key")
            if not app_id or not api_key:
                return {"status": "error", "message": "Adzuna credentials not configured. Get them at https://developer.adzuna.com/", "provider": provider}
            from app.services.adapters.job_sources.adzuna import AdzunaAdapter
            adapter = AdzunaAdapter(app_id=app_id, api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your credentials", "provider": provider}

        elif provider == "searchapi":
            api_key = _gs("searchapi_api_key")
            if not api_key:
                return {"status": "error", "message": "SearchAPI.io API key not configured. Get one at https://www.searchapi.io/", "provider": provider}
            from app.services.adapters.job_sources.searchapi import SearchAPIAdapter
            adapter = SearchAPIAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "usajobs":
            api_key = _gs("usajobs_api_key")
            email = _gs("usajobs_email")
            if not api_key:
                return {"status": "error", "message": "USAJOBS API key not configured. Get one free at https://developer.usajobs.gov/", "provider": provider}
            from app.services.adapters.job_sources.usajobs import USAJobsAdapter
            adapter = USAJobsAdapter(api_key=api_key, email=email)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key and email", "provider": provider}

        elif provider == "jooble":
            api_key = _gs("jooble_api_key")
            if not api_key:
                return {"status": "error", "message": "Jooble API key not configured. Get one free at https://jooble.org/api/about", "provider": provider}
            from app.services.adapters.job_sources.jooble import JoobleAdapter
            adapter = JoobleAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "jobdatafeeds":
            api_key = _gs("jobdatafeeds_api_key")
            if not api_key:
                return {"status": "error", "message": "JobDataFeeds API key not configured. Sign up at https://jobdatafeeds.com/", "provider": provider}
            from app.services.adapters.job_sources.jobdatafeeds import JobDataFeedsAdapter
            adapter = JobDataFeedsAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "coresignal":
            api_key = _gs("coresignal_api_key")
            if not api_key:
                return {"status": "error", "message": "Coresignal API key not configured. Get one at https://coresignal.com/", "provider": provider}
            from app.services.adapters.job_sources.coresignal import CoresignalAdapter
            adapter = CoresignalAdapter(api_key=api_key)
            try:
                result = adapter.test_connection()
            except Exception as e:
                return {"status": "failed", "message": f"Connection error: {e}", "provider": provider}
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "fantastic_jobs":
            api_key = _gs("fantastic_jobs_api_key")
            if not api_key:
                return {"status": "error", "message": "Fantastic.jobs API key not configured. Get one at https://fantastic.jobs/api", "provider": provider}
            from app.services.adapters.job_sources.fantastic_jobs import FantasticJobsAdapter
            adapter = FantasticJobsAdapter(api_key=api_key, host=_gs("fantastic_jobs_host") or None)
            try:
                result = adapter.test_connection()
            except Exception as e:
                return {"status": "failed", "message": f"Connection error: {e}", "provider": provider}
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        # New Contact Discovery Providers
        elif provider == "hunter_contact":
            api_key = _gs("hunter_contact_api_key")
            if not api_key:
                return {"status": "error", "message": "Hunter.io API key not configured. Get one at https://hunter.io/", "provider": provider}
            from app.services.adapters.contact_discovery.hunter_contact import HunterContactAdapter
            adapter = HunterContactAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "snovio":
            client_id = _gs("snovio_client_id")
            client_secret = _gs("snovio_client_secret")
            if not client_id or not client_secret:
                return {"status": "error", "message": "Snov.io credentials not configured. Get them at https://snov.io/", "provider": provider}
            from app.services.adapters.contact_discovery.snovio import SnovioAdapter
            adapter = SnovioAdapter(client_id=client_id, client_secret=client_secret)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your credentials", "provider": provider}

        elif provider == "rocketreach":
            api_key = _gs("rocketreach_api_key")
            if not api_key:
                return {"status": "error", "message": "RocketReach API key not configured. Get one at https://rocketreach.co/", "provider": provider}
            from app.services.adapters.contact_discovery.rocketreach import RocketReachAdapter
            adapter = RocketReachAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "pdl":
            api_key = _gs("pdl_api_key")
            if not api_key:
                return {"status": "error", "message": "People Data Labs API key not configured. Get one at https://www.peopledatalabs.com/", "provider": provider}
            from app.services.adapters.contact_discovery.pdl import PDLAdapter
            adapter = PDLAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "proxycurl":
            api_key = _gs("proxycurl_api_key")
            if not api_key:
                return {"status": "error", "message": "Proxycurl API key not configured. Get one at https://nubela.co/proxycurl/", "provider": provider}
            from app.services.adapters.contact_discovery.proxycurl import ProxycurlAdapter
            adapter = ProxycurlAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        # Company Enrichment Providers
        elif provider == "clearbit":
            api_key = _gs("clearbit_api_key")
            if not api_key:
                return {"status": "error", "message": "Clearbit API key not configured. Get one at https://clearbit.com/", "provider": provider}
            from app.services.adapters.company.clearbit import ClearbitAdapter
            adapter = ClearbitAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "opencorporates":
            api_key = _gs("opencorporates_api_key")
            if not api_key:
                return {"status": "error", "message": "OpenCorporates API key not configured. Get one at https://opencorporates.com/", "provider": provider}
            from app.services.adapters.company.opencorporates import OpenCorporatesAdapter
            adapter = OpenCorporatesAdapter(api_key=api_key)
            result = adapter.test_connection()
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        # LOB Lead Source Providers
        elif provider == "npi_registry":
            from app.services.adapters.lead_sources.npi_registry import NPIRegistryAdapter
            adapter = NPIRegistryAdapter()
            try:
                result = adapter.test_connection()
            except Exception as e:
                return {"status": "failed", "message": f"Connection error: {e}", "provider": provider}
            return {"status": "success" if result else "failed", "message": "NPI Registry accessible (free, no key needed)" if result else "Connection failed", "provider": provider}

        elif provider == "google_business":
            api_key = _gs("google_places_api_key") or app_config.GOOGLE_PLACES_API_KEY
            if not api_key:
                return {"status": "error", "message": "Google Places API key not configured. Get one at https://console.cloud.google.com", "provider": provider}
            from app.services.adapters.lead_sources.google_business import GoogleBusinessAdapter
            adapter = GoogleBusinessAdapter(api_key=api_key)
            try:
                result = adapter.test_connection()
            except Exception as e:
                return {"status": "failed", "message": f"Connection error: {e}", "provider": provider}
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "crunchbase":
            api_key = _gs("crunchbase_api_key") or app_config.CRUNCHBASE_API_KEY
            if not api_key:
                return {"status": "error", "message": "Crunchbase API key not configured. Get one at https://data.crunchbase.com", "provider": provider}
            from app.services.adapters.lead_sources.crunchbase import CrunchbaseAdapter
            adapter = CrunchbaseAdapter(api_key=api_key)
            try:
                result = adapter.test_connection()
            except Exception as e:
                return {"status": "failed", "message": f"Connection error: {e}", "provider": provider}
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "builtwith":
            api_key = _gs("builtwith_api_key") or app_config.BUILTWITH_API_KEY
            if not api_key:
                return {"status": "error", "message": "BuiltWith API key not configured. Get one at https://builtwith.com/api", "provider": provider}
            from app.services.adapters.lead_sources.builtwith import BuiltWithAdapter
            adapter = BuiltWithAdapter(api_key=api_key)
            try:
                result = adapter.test_connection()
            except Exception as e:
                return {"status": "failed", "message": f"Connection error: {e}", "provider": provider}
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your API key", "provider": provider}

        elif provider == "github_org":
            token = _gs("github_token") or app_config.GITHUB_TOKEN
            from app.services.adapters.lead_sources.github_org import GitHubOrgAdapter
            adapter = GitHubOrgAdapter(token=token)
            try:
                result = adapter.test_connection()
            except Exception as e:
                return {"status": "failed", "message": f"Connection error: {e}", "provider": provider}
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed - check your token", "provider": provider}

        elif provider == "pagespeed":
            api_key = _gs("google_places_api_key") or app_config.GOOGLE_PLACES_API_KEY
            from app.services.adapters.lead_sources.pagespeed import PageSpeedAdapter
            adapter = PageSpeedAdapter(api_key=api_key)
            try:
                result = adapter.test_connection()
            except Exception as e:
                return {"status": "failed", "message": f"Connection error: {e}", "provider": provider}
            return {"status": "success" if result else "failed", "message": "Connection successful!" if result else "Connection failed", "provider": provider}

        else:
            return {"status": "error", "message": f"Unknown provider: {provider}", "provider": provider}

    except Exception as e:
        return {"status": "error", "message": str(e), "provider": provider}
