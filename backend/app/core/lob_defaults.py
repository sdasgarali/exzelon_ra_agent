"""Shared LOB default configurations, type metadata, and tenant prompt profiles.

Referenced from: main.py (seeding), admin_tenants.py (auto-provisioning), lob.py (type listing).
"""

# LOB_TYPE_META — keyed by string lob_type for shared access
LOB_TYPE_META = {
    "staffing": {
        "label": "Staffing & Recruiting",
        "description": "Job board lead sourcing, hiring decision-maker targeting, staffing outreach",
        "default_color": "#1A3C6E",
        "default_icon": "briefcase",
    },
    "rcm": {
        "label": "Revenue Cycle Management",
        "description": "Healthcare provider targeting, medical billing/coding services outreach",
        "default_color": "#10B981",
        "default_icon": "heart-pulse",
    },
    "software_dev": {
        "label": "Software Development",
        "description": "Tech company prospecting, CTO/VP Engineering targeting, dev services outreach",
        "default_color": "#6366F1",
        "default_icon": "code",
    },
    "ai_services": {
        "label": "AI & Agent Services",
        "description": "AI adoption signal tracking, innovation leader targeting, AI services outreach",
        "default_color": "#F59E0B",
        "default_icon": "brain",
    },
    "digital_marketing": {
        "label": "Digital Marketing",
        "description": "Website audit-based prospecting, SEO/SEM gap analysis, marketing services outreach",
        "default_color": "#EC4899",
        "default_icon": "megaphone",
    },
    "custom": {
        "label": "Custom",
        "description": "User-defined line of business with custom configuration",
        "default_color": "#8B5CF6",
        "default_icon": "settings",
    },
}

# Comprehensive default configs per LOB type
LOB_DEFAULT_CONFIGS = {
    "staffing": {
        "lead_source_config": {
            "enabled_sources": [],
            "query": "",
            "location": "United States",
        },
        "icp_config": {
            "target_company_size": {"min": 50, "max": 5000},
            "target_industries": ["Manufacturing", "Healthcare", "Logistics", "Retail", "Construction", "Energy", "Hospitality", "Food & Beverage"],
            "target_titles": ["HR Manager", "HR Director", "Talent Acquisition", "Operations Manager", "Plant Manager", "Warehouse Manager"],
            "exclude_industries": ["Staffing and Recruiting", "Government Administration"],
            "geography": "United States",
        },
        "business_rules": {
            "daily_send_limit": 30,
            "cooldown_days": 10,
            "max_contacts_per_company": 2,
            "min_salary_threshold": 40000,
        },
    },
    "rcm": {
        "lead_source_config": {
            "enabled_sources": ["npi_registry", "google_business", "hiring_signal", "news_signal"],
            "query": "medical practice",
            "location": "United States",
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
        "business_rules": {
            "daily_send_limit": 25,
            "cooldown_days": 14,
            "max_contacts_per_company": 2,
            "min_salary_threshold": 0,
        },
    },
    "software_dev": {
        "lead_source_config": {
            "enabled_sources": ["crunchbase", "builtwith", "github_org", "hiring_signal", "news_signal"],
            "query": "software saas",
            "location": "United States",
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
        "business_rules": {
            "daily_send_limit": 30,
            "cooldown_days": 10,
            "max_contacts_per_company": 2,
            "min_salary_threshold": 0,
        },
    },
    "ai_services": {
        "lead_source_config": {
            "enabled_sources": ["crunchbase", "github_org", "hiring_signal", "news_signal"],
            "query": "artificial intelligence machine learning",
            "location": "United States",
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
        "business_rules": {
            "daily_send_limit": 25,
            "cooldown_days": 10,
            "max_contacts_per_company": 2,
            "min_salary_threshold": 0,
        },
    },
    "digital_marketing": {
        "lead_source_config": {
            "enabled_sources": ["google_business", "pagespeed", "builtwith", "hiring_signal", "news_signal"],
            "query": "local business",
            "location": "United States",
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
        "business_rules": {
            "daily_send_limit": 35,
            "cooldown_days": 7,
            "max_contacts_per_company": 2,
            "min_salary_threshold": 0,
        },
    },
}

# Tenant-specific prompt profile overrides
TENANT_PROMPT_PROFILES = {
    "medeoan": {
        "rcm": {
            "company_description": "Medeoan \u2014 a healthcare revenue cycle management company powered by AI",
            "value_proposition": "We increase collections 10-20% within 90 days with less than 3% denial rates. Performance-based \u2014 we only get paid when you do. 90-day money-back guarantee.",
        },
    },
    "neuraforz": {
        "software_dev": {
            "company_description": "Neuraforz \u2014 a software development company that builds enterprise applications",
            "value_proposition": "Get your software built in 6 weeks \u2014 no delays, no excuses. Fixed pricing with daily visibility.",
        },
        "ai_services": {
            "company_description": "Neuraforz \u2014 an AI services company building custom AI agents and intelligent automation",
            "value_proposition": "Production AI in 6 weeks, not 6 months. Custom AI agents that actually work.",
        },
        "digital_marketing": {
            "company_description": "Neuraforz \u2014 a digital marketing agency delivering data-driven results",
            "value_proposition": "Data-backed digital marketing that drives revenue, not vanity metrics.",
        },
    },
}
