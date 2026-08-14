"""One-time script: backfill LOB default configs for existing LOBs missing them."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import SessionLocal
from app.db.models.line_of_business import LineOfBusiness

LOB_DEFAULT_CONFIGS = {
    "staffing": {
        "lead_source_config": {"enabled_sources": [], "query": "", "location": "United States"},
        "icp_config": {
            "target_company_size": {"min": 50, "max": 5000},
            "target_industries": ["Manufacturing", "Healthcare", "Logistics", "Retail", "Construction", "Energy", "Hospitality", "Food & Beverage"],
            "target_titles": ["HR Manager", "HR Director", "Talent Acquisition", "Operations Manager", "Plant Manager", "Warehouse Manager"],
            "exclude_industries": ["Staffing and Recruiting", "Government Administration"],
            "geography": "United States",
        },
        "business_rules": {"daily_send_limit": 30, "cooldown_days": 10, "max_contacts_per_company": 2, "min_salary_threshold": 40000},
    },
    "rcm": {
        "lead_source_config": {
            "enabled_sources": ["npi_registry", "google_business", "hiring_signal", "news_signal"],
            "query": "medical practice", "location": "United States",
            "intent_signals": {
                "new_npi_registration": {"taxonomy": "Internal Medicine", "state": "", "limit": 50},
                "hiring_signal": {"lob_type": "rcm", "days_back": 30, "limit": 50},
                "news_event": {"lob_type": "rcm", "limit": 20},
            },
            "npi_registry": {"taxonomy": "Internal Medicine", "limit": 100},
            "google_business": {"business_type": "doctor", "limit": 20},
        },
        "icp_config": {
            "target_company_size": {"min": 2, "max": 200},
            "target_industries": ["Healthcare", "Medical Practice", "Dental", "Behavioral Health", "Urgent Care", "Specialty Clinic"],
            "target_titles": ["Practice Manager", "Office Manager", "Billing Manager", "Revenue Cycle Director", "CFO", "Administrator"],
            "target_specialties": ["Internal Medicine", "Family Medicine", "Cardiology", "Orthopedics", "Dermatology", "Gastroenterology", "Urology", "Neurology", "Oncology", "Pediatrics"],
            "geography": "United States",
        },
        "business_rules": {"daily_send_limit": 25, "cooldown_days": 14, "max_contacts_per_company": 2, "min_salary_threshold": 0},
    },
    "software_dev": {
        "lead_source_config": {
            "enabled_sources": ["crunchbase", "builtwith", "github_org", "hiring_signal", "news_signal"],
            "query": "software saas", "location": "United States",
            "intent_signals": {
                "funding_round": {"categories": ["software", "saas", "enterprise-software", "developer-tools"], "funding_stage": "series_a", "limit": 25},
                "tech_stack_change": {"technology": "WordPress", "limit": 20},
                "github_activity": {"query": "software", "min_repos": 20, "limit": 30},
                "hiring_signal": {"lob_type": "software_dev", "days_back": 30, "limit": 50},
                "news_event": {"lob_type": "software_dev", "limit": 20},
            },
            "crunchbase": {"categories": ["software", "saas"], "funding_stage": "series_a", "min_employees": 20, "limit": 25},
            "builtwith": {"technology": "WordPress", "limit": 30},
            "github_org": {"query": "software", "min_repos": 20, "limit": 30},
        },
        "icp_config": {
            "target_company_size": {"min": 20, "max": 500},
            "target_industries": ["Software", "SaaS", "Fintech", "Healthtech", "Edtech", "E-Commerce", "Cybersecurity"],
            "target_titles": ["CTO", "VP Engineering", "Director of Engineering", "Head of Product", "Chief Technology Officer", "VP Product"],
            "target_funding_stages": ["seed", "series_a", "series_b", "series_c"],
            "geography": "United States",
        },
        "business_rules": {"daily_send_limit": 30, "cooldown_days": 10, "max_contacts_per_company": 2, "min_salary_threshold": 0},
    },
    "ai_services": {
        "lead_source_config": {
            "enabled_sources": ["crunchbase", "github_org", "hiring_signal", "news_signal"],
            "query": "artificial intelligence machine learning", "location": "United States",
            "intent_signals": {
                "funding_round": {"categories": ["artificial-intelligence", "machine-learning", "deep-learning"], "limit": 25},
                "github_activity": {"query": "ai machine-learning", "min_repos": 10, "limit": 30},
                "hiring_signal": {"lob_type": "ai_services", "days_back": 30, "limit": 50},
                "news_event": {"lob_type": "ai_services", "limit": 20},
            },
            "crunchbase": {"categories": ["artificial-intelligence", "machine-learning"], "limit": 25},
            "github_org": {"query": "ai machine-learning", "min_repos": 10, "limit": 30},
        },
        "icp_config": {
            "target_company_size": {"min": 50, "max": 2000},
            "target_industries": ["Technology", "Financial Services", "Healthcare", "Manufacturing", "Retail", "Logistics", "Insurance"],
            "target_titles": ["CTO", "Chief AI Officer", "VP Data Science", "Head of AI", "Director of ML", "VP Engineering", "Chief Innovation Officer"],
            "geography": "United States",
        },
        "business_rules": {"daily_send_limit": 25, "cooldown_days": 10, "max_contacts_per_company": 2, "min_salary_threshold": 0},
    },
    "digital_marketing": {
        "lead_source_config": {
            "enabled_sources": ["google_business", "pagespeed", "builtwith", "hiring_signal", "news_signal"],
            "query": "local business", "location": "United States",
            "intent_signals": {
                "poor_pagespeed": {"max_score": 0.4, "limit": 20},
                "tech_stack_change": {"technology": "WordPress", "limit": 20},
                "hiring_signal": {"lob_type": "digital_marketing", "days_back": 30, "limit": 50},
                "news_event": {"lob_type": "digital_marketing", "limit": 20},
            },
            "google_business": {"business_type": "", "limit": 20},
            "pagespeed": {"max_score": 0.5, "limit": 20},
            "builtwith": {"technology": "WordPress", "limit": 30},
        },
        "icp_config": {
            "target_company_size": {"min": 5, "max": 200},
            "target_industries": ["Local Business", "Retail", "Hospitality", "Food & Beverage", "Health & Wellness", "Professional Services", "Automotive", "Real Estate"],
            "target_titles": ["Owner", "CEO", "Marketing Director", "Marketing Manager", "VP Marketing", "General Manager", "COO"],
            "geography": "United States",
        },
        "business_rules": {"daily_send_limit": 35, "cooldown_days": 7, "max_contacts_per_company": 2, "min_salary_threshold": 0},
    },
}


def main():
    db = SessionLocal()
    try:
        lobs = db.query(LineOfBusiness).filter(LineOfBusiness.is_archived == False).all()
        updated = 0
        for lob in lobs:
            lob_type = lob.lob_type.value if hasattr(lob.lob_type, "value") else str(lob.lob_type)
            defaults = LOB_DEFAULT_CONFIGS.get(lob_type, {})
            if not defaults:
                continue
            changed = False
            if not lob.lead_source_config and defaults.get("lead_source_config"):
                lob.lead_source_config = json.dumps(defaults["lead_source_config"])
                changed = True
            if not lob.icp_config and defaults.get("icp_config"):
                lob.icp_config = json.dumps(defaults["icp_config"])
                changed = True
            if not lob.business_rules and defaults.get("business_rules"):
                lob.business_rules = json.dumps(defaults["business_rules"])
                changed = True
            if changed:
                updated += 1
                print(f"Updated lob_id={lob.lob_id} ({lob.name}) tenant={lob.tenant_id} type={lob_type}")
        db.commit()
        print(f"\nBackfilled {updated} LOBs with default configs")
    finally:
        db.close()


if __name__ == "__main__":
    main()
