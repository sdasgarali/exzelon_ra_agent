"""Core configuration settings loaded from environment variables.

Uses the env_loader module to resolve APP_ENV-prefixed variables before
Pydantic reads them from os.environ. This enables TEST/DEV/PROD switching
with zero code changes — only APP_ENV needs to change in the .env file.
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor all relative paths to the backend/ directory (parent of app/)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Load environment BEFORE Settings class is instantiated.
# This resolves DEV_DB_HOST → DB_HOST etc. in os.environ.
# Skipped when DATABASE_URL is already set (e.g. test harness).
# ---------------------------------------------------------------------------
_app_env = "DEV"
if "DATABASE_URL" not in os.environ:
    from app.core.env_loader import load_env, validate_env
    _app_env = load_env()
    validate_env(_app_env)


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    The env_loader has already resolved APP_ENV-prefixed keys into canonical
    names in os.environ, so Pydantic reads them directly. No env_file is
    specified — all values come from os.environ (populated by the loader).
    """

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore"
    )

    # Core
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_NAME: str = "NeuraLeads AI Agent"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True
    SECRET_KEY: str = ""
    ENCRYPTION_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # 30 minutes (short-lived)
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    CORS_ORIGINS: str = ""  # Comma-separated allowed origins

    # Server
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    BASE_URL: str = ""  # Public-facing URL (e.g. https://yourdomain.com); used for tracking links

    # Data Storage Mode
    DATA_STORAGE: Literal["database", "files"] = "database"
    JOB_REQUIREMENTS_PATH: str = str(_BACKEND_DIR / "data" / "Job_requirements.xlsx")
    EXPORT_PATH: str = str(_BACKEND_DIR / "data" / "exports")

    # Database
    DB_TYPE: Literal["mysql", "sqlite"] = "sqlite"
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "exzelon_ra_agent"
    DB_USER: str = "ra_user"
    DB_PASSWORD: str = ""

    # Connection pool settings (MySQL only)
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: int = 30

    @property
    def DATABASE_URL(self) -> str:
        if self.DB_TYPE == "sqlite":
            db_path = _BACKEND_DIR / "data" / "ra_agent.db"
            return f"sqlite:///{db_path}"
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        if self.DB_TYPE == "sqlite":
            db_path = _BACKEND_DIR / "data" / "ra_agent.db"
            return f"sqlite+aiosqlite:///{db_path}"
        return f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    @property
    def EFFECTIVE_BASE_URL(self) -> str:
        """Resolved base URL for tracking pixels, unsubscribe links, etc."""
        if self.BASE_URL:
            return self.BASE_URL.rstrip("/")
        return f"http://{self.HOST}:{self.PORT}"

    # Microsoft 365 OAuth2
    MS365_OAUTH_CLIENT_ID: str = ""
    MS365_OAUTH_CLIENT_SECRET: str = ""
    MS365_OAUTH_TENANT_ID: str = "common"  # "common" for multi-tenant
    MS365_OAUTH_REDIRECT_URI: str = ""  # e.g. https://ra.partnerwithus.tech/dashboard/mailboxes

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Contact Discovery Providers
    CONTACT_PROVIDER: Literal["apollo", "seamless", "mock"] = "mock"
    APOLLO_API_KEY: str = ""
    SEAMLESS_API_KEY: str = ""

    # Email Validation Providers
    EMAIL_VALIDATION_PROVIDER: Literal["neverbounce", "zerobounce", "hunter", "clearout", "emailable", "mailboxvalidator", "reacher", "mock"] = "mock"
    NEVERBOUNCE_API_KEY: str = ""
    ZEROBOUNCE_API_KEY: str = ""
    HUNTER_API_KEY: str = ""
    CLEAROUT_API_KEY: str = ""
    EMAILABLE_API_KEY: str = ""
    MAILBOXVALIDATOR_API_KEY: str = ""
    REACHER_API_KEY: str = ""
    REACHER_BASE_URL: str = "https://api.reacher.email"

    # Email Sending
    EMAIL_SEND_MODE: Literal["mailmerge", "smtp", "m365", "gmail", "api"] = "mailmerge"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # Business Rules
    DAILY_SEND_LIMIT: int = 30
    COOLDOWN_DAYS: int = 10
    # Smart Throttling
    SEND_DELAY_MIN_SEC: int = 45
    SEND_DELAY_MAX_SEC: int = 180
    MAX_HOURLY_RATIO: int = 8  # daily_limit / this = max per hour
    MAX_CONTACTS_PER_COMPANY_PER_JOB: int = 2
    MIN_SALARY_THRESHOLD: int = 40000
    DATA_RETENTION_DAYS: int = 180

    # Billing & Invoicing
    BILLING_ENABLED: bool = False
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    BILLING_TAX_RATE_DEFAULT: float = 0.0
    BILLING_COMPANY_NAME: str = ""
    BILLING_COMPANY_ADDRESS: str = ""
    BILLING_COMPANY_LOGO_PATH: str = ""
    BILLING_COMPANY_EMAIL: str = ""
    BILLING_COMPANY_PHONE: str = ""
    BILLING_COMPANY_WEBSITE: str = ""
    INVOICE_REMINDER_INTERVAL_DAYS: int = 3
    INVOICE_MAX_REMINDERS: int = 5
    INVOICE_DUE_DAY: int = 5

    # Industries (Non-IT only)
    TARGET_INDUSTRIES: list[str] = [
        "Healthcare", "Manufacturing", "Logistics", "Retail", "BFSI",
        "Education", "Engineering", "Automotive", "Construction", "Energy",
        "Oil & Gas", "Food & Beverage", "Hospitality", "Real Estate",
        "Legal", "Insurance", "Financial Services", "Industrial", "Skilled Trades",
        "Light Industrial", "Heavy Industrial", "Skilled Trades"
    ]

    # Job Sources Configuration
    JOB_SOURCES: list[str] = ["linkedin", "indeed", "glassdoor", "simplyhired"]
    JSEARCH_API_KEY: str = ""
    SEARCHAPI_API_KEY: str = ""
    USAJOBS_API_KEY: str = ""
    USAJOBS_EMAIL: str = ""
    JOOBLE_API_KEY: str = ""
    JOBDATAFEEDS_API_KEY: str = ""
    CORESIGNAL_API_KEY: str = ""

    # LOB-specific Lead Source API Keys
    GOOGLE_PLACES_API_KEY: str = ""
    CRUNCHBASE_API_KEY: str = ""
    BUILTWITH_API_KEY: str = ""
    GITHUB_TOKEN: str = ""  # Optional, for higher GitHub API rate limits

    # Company Size Preference (employees)
    COMPANY_SIZE_PRIORITY_1_MAX: int = 50
    COMPANY_SIZE_PRIORITY_2_MIN: int = 51
    COMPANY_SIZE_PRIORITY_2_MAX: int = 500
    # Hard upper bound on company size for lead sourcing. Pushed server-side into
    # TheirStack's `max_employee_count` filter so >200-employee companies are never
    # fetched. Override per-tenant via job_source_tuning.theirstack.max_employee_count.
    THEIRSTACK_MAX_EMPLOYEE_COUNT: int = 200

    # Pipeline-wide company-size ceiling applied to ALL sources (not just
    # TheirStack) after fetch/enrichment. Companies with >this many employees are
    # dropped at sourcing. Override per-tenant via `lead_sourcing_max_employee_count`.
    LEAD_SOURCING_MAX_EMPLOYEE_COUNT: int = 500
    # Drop postings with a placeholder/confidential/blank employer name.
    LEAD_SOURCING_DROP_CONFIDENTIAL: bool = True
    # Fill missing industry/size at sourcing via the configured AI adapter (Groq),
    # cached on ClientInfo. Bounded per run to control cost/latency.
    LEAD_SOURCING_ENRICH_COMPANY_AT_SOURCE: bool = True
    LEAD_SOURCING_ENRICH_MAX_COMPANIES: int = 300
    # Firmographic (company size/industry) enrichment via a data provider keyed by
    # DOMAIN. Fills company SIZE, which the free LLM resolver cannot do reliably.
    # "none" disables; "apollo" enables (needs apollo_api_key). Paid — bounded per
    # run and NEVER used on the free_only pre-enrichment gate path.
    COMPANY_FIRMOGRAPHIC_PROVIDER: str = "none"
    COMPANY_FIRMOGRAPHIC_MAX_LOOKUPS: int = 100
    # Industries hard-dropped regardless of size. Empty list falls back to
    # company_filters.DEFAULT_EXCLUDED_INDUSTRY_KEYWORDS.
    EXCLUDED_INDUSTRY_KEYWORDS: list[str] = []

    # Excluded patterns
    EXCLUDE_IT_KEYWORDS: list[str] = [
        "software developer", "software engineer", "web developer",
        "programmer", "coding", "data scientist", "devops",
        "full stack", "frontend developer", "backend developer",
        "cloud architect", "cybersecurity analyst", "network administrator",
        "machine learning engineer"
    ]
    EXCLUDE_STAFFING_KEYWORDS: list[str] = [
        "staffing agency", "staffing firm", "recruitment agency",
        "talent acquisition agency", "temp agency",
        "employment agency", "executive search firm",
        "recruitment", "government", "administration",
        "medical", "non profit", "nonprofit",
        "civics", "social services",
        "computer security", "network security", "security agency",
        "telecommunication",
        "primary education", "secondary education", "university",
        "religious", "church",
    ]

    # Company-only exclusion keywords (matched only against company name)
    EXCLUDE_COMPANY_KEYWORDS: list[str] = [
        "staffing agency", "staffing firm", "recruitment agency",
        "talent acquisition agency", "temp agency",
        "employment agency", "executive search firm",
        "security agency",
    ]

    # Title-only exclusion keywords (matched only against job title)
    EXCLUDE_TITLE_KEYWORDS: list[str] = [
        "intern", "entry level",
    ]

    # Available Job Titles
    AVAILABLE_JOB_TITLES: list[str] = [
        "HR Manager", "HR Director", "Recruiter", "Talent Acquisition",
        "Operations Manager", "Plant Manager", "Warehouse Manager",
        "Production Supervisor", "Logistics Manager", "Supply Chain Manager",
        "Maintenance Manager", "Quality Manager", "Safety Manager",
        "Facilities Manager", "Branch Manager", "Regional Manager",
        "General Manager", "Site Manager", "Distribution Manager",
        "Manufacturing Manager", "Engineering Manager", "Project Manager",
        "Purchasing Manager", "Procurement Manager", "Inventory Manager",
        "Shipping Manager", "Receiving Manager", "Fleet Manager",
        "Store Manager", "Restaurant Manager", "Hotel Manager",
        "Construction Manager", "Field Manager", "Service Manager",
        "Account Manager", "Territory Manager", "Area Manager",
        "Warehouse Supervisor", "Production Manager", "VP Operations",
        "VP Human Resources", "Director of HR", "Director of Operations",
        "Staffing Coordinator", "Talent Manager", "Workforce Manager",
        "EHS Manager", "Environmental Health Safety Manager",
        "Training Manager", "Compliance Manager", "Risk Manager",
        "Claims Manager", "Dispatch Manager", "Transportation Manager",
        "Food Service Manager", "Housekeeping Manager"
    ]

    # Job Title Categories — grouped by industry/function
    # 35 categories from CSV data + 15 existing categories merged
    JOB_TITLE_CATEGORIES: dict[str, list[str]] = {
        "HR & Talent": [
            "HR Manager", "HR Director", "HR Business Partner", "HR Generalist",
            "HR Coordinator", "Recruiter", "Talent Acquisition", "Talent Acquisition Manager",
            "Staffing Coordinator", "Staffing Manager", "Talent Manager", "Workforce Manager",
            "Recruitment Manager", "People Operations Manager", "Employee Relations Manager",
            "Compensation Manager", "Benefits Manager", "Payroll Manager",
            "VP Human Resources", "Director of HR", "Chief People Officer",
        ],
        "Operations & General Management": [
            "Operations Manager", "Operations Director", "VP Operations",
            "Director of Operations", "COO", "Chief Operating Officer",
            "General Manager", "Assistant General Manager", "Regional Manager",
            "Area Manager", "District Manager", "Territory Manager",
            "Branch Manager", "Site Manager", "Field Manager",
        ],
        "Manufacturing": [
            "Manufacturing Manager", "Manufacturing Director", "Manufacturing Supervisor",
            "Manufacturing Engineer", "Manufacturing Technician",
            "Lean Manager", "Continuous Improvement Manager", "Process Improvement Manager",
        ],
        "Production": [
            "Plant Manager", "Production Manager", "Production Supervisor",
            "Production Coordinator", "Production Planner", "Production Scheduler",
            "Production Control Manager", "Production Lead",
        ],
        "Warehouse & Logistics": [
            "Warehouse Manager", "Warehouse Supervisor", "Warehouse Director",
            "Distribution Manager", "Distribution Center Manager",
            "Logistics Manager", "Logistics Director", "Logistics Coordinator",
            "Supply Chain Manager", "Supply Chain Director",
            "Inventory Manager", "Inventory Control Manager",
            "Shipping Manager", "Receiving Manager", "Freight Manager",
            "Fleet Manager", "Dispatch Manager", "Transportation Manager",
        ],
        "Facilities": [
            "Facilities Manager", "Facilities Director", "Facilities Coordinator",
            "Facilities Supervisor", "Building Manager", "Building Engineer",
            "Property Manager", "Property Management Director",
        ],
        "Maintenance": [
            "Maintenance Manager", "Maintenance Director", "Maintenance Supervisor",
            "Maintenance Coordinator", "Maintenance Technician", "Maintenance Planner",
            "Maintenance Engineer",
        ],
        "Safety & Compliance": [
            "Safety Manager", "Safety Director", "Safety Coordinator",
            "EHS Manager", "Environmental Health Safety Manager", "HSE Manager",
            "Compliance Manager", "Compliance Director", "Compliance Officer",
            "Risk Manager", "Risk Director", "Loss Prevention Manager",
            "Claims Manager", "Regulatory Affairs Manager",
        ],
        "Construction": [
            "Construction Manager", "Construction Superintendent", "Construction Director",
            "Construction Foreman", "Construction Estimator", "Construction Inspector",
            "General Contractor", "Site Superintendent",
        ],
        "Engineering": [
            "Engineering Manager", "Engineering Director", "Chief Engineer",
            "Mechanical Engineer", "Civil Engineer", "Structural Engineer",
            "Design Engineer", "Project Engineer", "Field Engineer",
        ],
        "Quality": [
            "Quality Manager", "Quality Control Manager", "Quality Assurance Manager",
            "Quality Director", "Quality Engineer", "Quality Inspector",
            "Quality Supervisor", "Quality Technician",
        ],
        "CNC": [
            "CNC Machinist", "CNC Operator", "CNC Programmer", "CNC Supervisor",
            "CNC Manager", "CNC Setup Technician", "CNC Mill Operator",
            "CNC Lathe Operator", "CNC Lead",
        ],
        "Accounting": [
            "Accountant", "CPA", "Accounting Manager", "Accounting Director",
            "Accounting Supervisor", "Accounts Payable Manager", "Accounts Receivable Manager",
            "Staff Accountant", "Senior Accountant", "Cost Accountant",
            "Tax Accountant", "Accounting Clerk",
        ],
        "Bookkeeper": [
            "Bookkeeper", "Full Charge Bookkeeper", "Senior Bookkeeper",
            "Bookkeeping Manager", "Bookkeeping Supervisor",
        ],
        "Controller": [
            "Controller", "Assistant Controller", "Corporate Controller",
            "Division Controller", "Plant Controller", "Regional Controller",
        ],
        "Financial": [
            "Finance Manager", "Finance Director", "CFO", "Chief Financial Officer",
            "Financial Analyst", "Financial Controller", "Financial Planner",
            "Credit Manager", "Collections Manager", "Treasury Manager",
        ],
        "Tax": [
            "Tax Manager", "Tax Director", "Tax Analyst", "Tax Accountant",
            "Tax Preparer", "Tax Specialist", "Tax Supervisor",
        ],
        "Insurance": [
            "Insurance Manager", "Insurance Agent", "Insurance Underwriter",
            "Insurance Adjuster", "Claims Manager", "Claims Adjuster",
            "Insurance Director", "Risk Manager",
        ],
        "Architecture": [
            "Architect", "Senior Architect", "Architecture Manager",
            "Architectural Designer", "Project Architect", "Design Manager",
            "Interior Architect", "Landscape Architect",
        ],
        "Interior Designer": [
            "Interior Designer", "Senior Interior Designer", "Interior Design Manager",
            "Interior Design Director", "Space Planner", "Design Coordinator",
        ],
        "Purchasing & Procurement": [
            "Purchasing Manager", "Purchasing Director", "Purchasing Agent",
            "Procurement Manager", "Procurement Director", "Procurement Specialist",
            "Buyer", "Senior Buyer", "Category Manager",
            "Vendor Manager", "Supplier Manager",
        ],
        "Hospitality & Food Service": [
            "Restaurant Manager", "Restaurant General Manager",
            "Hotel Manager", "Hotel General Manager", "Front Desk Manager",
            "Food Service Manager", "Food Service Director",
            "Banquet Manager", "Catering Manager",
            "Housekeeping Manager", "Housekeeping Director",
            "Executive Chef", "Kitchen Manager",
        ],
        "Food Industry": [
            "Food Production Manager", "Food Safety Manager", "Food Plant Manager",
            "Food Quality Manager", "Food Processing Supervisor",
            "Bakery Manager", "Dairy Manager", "Meat Processing Manager",
        ],
        "Retail": [
            "Store Manager", "Store Director", "Retail Manager",
            "Assistant Store Manager", "Retail Operations Manager",
            "Merchandise Manager", "Visual Merchandising Manager",
            "Retail District Manager", "Retail Regional Manager",
        ],
        "Sales": [
            "Account Manager", "Sales Manager", "Regional Sales Manager",
            "Business Development Manager", "Service Manager",
            "Customer Service Manager", "Call Center Manager",
            "Sales Director", "VP Sales", "Inside Sales Manager",
            "Outside Sales Manager", "Territory Sales Manager",
        ],
        "Healthcare & Social Services": [
            "Nurse Manager", "Nursing Director", "Director of Nursing",
            "Clinical Manager", "Practice Manager", "Office Manager",
            "Healthcare Administrator", "Hospital Administrator",
            "Social Services Director", "Case Manager",
        ],
        "Education": [
            "School Principal", "Assistant Principal", "Academic Director",
            "Education Director", "Training Manager", "Training Director",
            "Learning and Development Manager", "Organizational Development Manager",
            "Curriculum Director", "Dean",
        ],
        "HVAC": [
            "HVAC Manager", "HVAC Supervisor", "HVAC Technician",
            "HVAC Installer", "HVAC Service Manager", "HVAC Director",
            "Refrigeration Manager", "Refrigeration Technician",
        ],
        "Electrical": [
            "Electrical Manager", "Electrical Supervisor", "Electrical Engineer",
            "Electrical Foreman", "Master Electrician", "Electrical Director",
            "Electrical Contractor", "Electrical Superintendent",
        ],
        "Technicians": [
            "Service Technician", "Field Service Technician", "Maintenance Technician",
            "Industrial Technician", "Equipment Technician", "Lab Technician",
            "Technical Manager", "Technical Director",
        ],
        "Field Service": [
            "Field Service Manager", "Field Service Director", "Field Service Engineer",
            "Field Service Supervisor", "Field Service Coordinator",
            "Field Operations Manager", "Service Dispatch Manager",
        ],
        "Mining": [
            "Mine Manager", "Mine Superintendent", "Mine Engineer",
            "Mining Supervisor", "Mining Director", "Quarry Manager",
            "Drilling Manager", "Geology Manager",
        ],
        "Solar": [
            "Solar Project Manager", "Solar Installation Manager", "Solar Director",
            "Solar Operations Manager", "Solar Site Supervisor",
            "Renewable Energy Manager", "Energy Manager",
        ],
        "Industrial": [
            "Industrial Manager", "Industrial Engineer", "Industrial Supervisor",
            "Industrial Maintenance Manager", "Industrial Production Manager",
            "Plant Engineer", "Plant Superintendent",
        ],
        "Injection Molding": [
            "Injection Molding Manager", "Injection Molding Supervisor",
            "Molding Manager", "Molding Technician", "Plastics Manager",
            "Plastics Engineer", "Extrusion Manager",
        ],
        "Process Engineer": [
            "Process Engineer", "Senior Process Engineer", "Process Engineering Manager",
            "Process Improvement Engineer", "Process Development Engineer",
            "Chemical Engineer", "Process Technician",
        ],
        "Plant Management": [
            "Plant Manager", "Plant Director", "Plant Superintendent",
            "Plant Engineer", "Plant Supervisor", "Plant Operations Manager",
            "Assistant Plant Manager",
        ],
        "Supervisor": [
            "Production Supervisor", "Warehouse Supervisor", "Shift Supervisor",
            "Team Leader", "Team Supervisor", "Lead Supervisor",
            "Night Shift Supervisor", "Day Shift Supervisor",
            "Area Supervisor", "Line Supervisor",
        ],
        "Manager": [
            "Project Manager", "Senior Project Manager", "Program Manager",
            "Department Manager", "Division Manager", "Office Manager",
            "Administrative Manager", "Business Manager",
        ],
        "Attorney": [
            "Attorney", "General Counsel", "Corporate Counsel",
            "Legal Director", "Legal Manager", "Paralegal Manager",
            "Compliance Attorney", "Employment Attorney",
        ],
        "Entry Level": [
            "Administrative Assistant", "Office Coordinator", "Receptionist",
            "Data Entry Clerk", "File Clerk", "Mail Room Clerk",
            "Customer Service Representative", "Order Entry Clerk",
        ],
        "Staff Account": [
            "Staff Accountant", "Junior Accountant", "Accounting Associate",
            "Accounting Specialist", "Accounting Coordinator",
            "AP Clerk", "AR Clerk", "Billing Clerk",
        ],
        "Agriculture & Trades": [
            "Farm Manager", "Ranch Manager", "Ag Operations Manager",
            "Shop Manager", "Foreman", "Superintendent",
            "Trades Manager", "Skilled Trades Supervisor",
        ],
    }

    # Industry Categories — group industries for filter dropdown
    INDUSTRY_CATEGORIES: dict[str, list[str]] = {
        "Manufacturing & Industrial": [
            "Automotive", "Automotive Components", "Automotive Services", "Automotive, Commercial Vehicles",
            "Chemicals", "Industrial Automation", "Industrial Manufacturing", "Industrial Equipment",
            "Manufacturing", "Machinery", "Metal Fabrication", "Metals & Mining", "Mining",
            "Plastics", "Plastics & Rubber", "Packaging", "Paper & Packaging",
            "Semiconductors", "Textiles", "Glass & Ceramics",
        ],
        "Construction & Engineering": [
            "Architecture & Planning", "Architecture and Engineering", "Civil Engineering",
            "Construction", "Construction Materials", "Engineering",
            "Building Materials", "Electrical/Electronic Manufacturing",
        ],
        "Healthcare & Life Sciences": [
            "Biotechnology", "Biotechnology Research", "Healthcare", "Hospital & Health Care",
            "Medical Devices", "Pharmaceuticals", "Veterinary", "Health, Wellness and Fitness",
            "Mental Health Care",
        ],
        "Technology & Software": [
            "Computer Networking", "Computer Software", "Information Technology",
            "Internet", "Software Development", "Telecommunications",
            "Computer Hardware", "Information Services",
        ],
        "Food & Beverage": [
            "Beverage", "Beverages", "Food & Beverages", "Food Production",
            "Restaurants", "Hospitality", "Food Processing",
        ],
        "Financial Services": [
            "Accounting and Consulting", "Accounting, Consulting, Advisory",
            "Banking", "Financial Services", "Insurance", "Investment Management",
            "Real Estate", "Venture Capital & Private Equity",
        ],
        "Retail & Consumer": [
            "Apparel & Fashion", "Consumer Electronics", "Consumer Electronics / Sporting Goods",
            "Consumer Goods", "E-Commerce", "Retail", "Luxury Goods & Jewelry",
            "Sporting Goods", "Wholesale",
        ],
        "Transportation & Logistics": [
            "Airlines/Aviation", "Logistics and Supply Chain", "Maritime",
            "Railroad Manufacture", "Transportation", "Trucking", "Warehousing",
            "Import and Export", "Package/Freight Delivery",
        ],
        "Energy & Utilities": [
            "Electric Power", "Electrical", "Energy", "Oil & Energy",
            "Renewables & Environment", "Utilities", "Solar",
        ],
        "Media & Communications": [
            "Advertising", "Broadcasting", "Communication Services",
            "Entertainment", "Media Production", "Publishing",
            "Marketing and Advertising", "Public Relations",
        ],
        "Education & Government": [
            "Education", "Education Management", "Government Administration",
            "Higher Education", "Nonprofit Organization Management",
            "Research", "Think Tanks",
        ],
        "Aerospace & Defense": [
            "Aerospace", "Aerospace & Defense", "Aerospace & Defense, Software Development",
            "Aerospace and Defense", "Aviation & Aerospace", "Defense & Space",
        ],
        "Other Services": [
            "Cannabis Investment and Operations", "Casinos & Gaming",
            "Environmental Services", "Facilities Services",
            "Human Resources", "Legal Services", "Management Consulting",
            "Professional Training & Coaching", "Security and Investigations",
            "Staffing and Recruiting", "Wine and Spirits",
        ],
    }

    # Target Job Titles
    TARGET_JOB_TITLES: list[str] = [
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
        # Finance & Accounting (non-IT)
        "Controller", "Accounting Manager", "Finance Manager",
        "Accounts Payable Manager", "Accounts Receivable Manager",
        "Credit Manager", "Collections Manager",
        # Sales & Business Development (field roles)
        "Account Manager", "Sales Manager", "Regional Sales Manager",
        "Business Development Manager", "Service Manager",
        "Customer Service Manager", "Call Center Manager",
        # Agriculture & Trades
        "Farm Manager", "Ranch Manager", "Ag Operations Manager",
        "Shop Manager", "Foreman", "Superintendent",
    ]

    # Broad search queries used when "Any" is selected for job titles.
    # These generic role-level terms cast a much wider net than the specific
    # TARGET_JOB_TITLES list. Each term acts as a contains/wildcard match
    # at the API level — e.g., "Manager" matches Construction Manager,
    # Operations Manager, Plant Manager, Food Service Manager, etc.
    BROAD_SEARCH_QUERIES: list[str] = [
        "Accountant", "Administrator", "Advisor", "Agent",
        "Analyst", "Apprentice", "Architect", "Assistant",
        "Associate", "Attorney", "Auditor", "Bookkeeper",
        "Broker", "Buyer", "CAD Technician", "CFO",
        "Chef", "Chemist", "Clerk", "Comptroller",
        "Consultant", "Controller", "Coordinator", "Counsel",
        "Counselor", "Designer", "Director", "Dispatcher",
        "Drafter", "Electrician", "Engineer", "Estimator",
        "Executive", "Fabricator", "Foreman", "Inspector",
        "Installer", "Intern", "Laborer", "Lawyer",
        "Leader", "Machinist", "Manager", "Mechanic",
        "Microbiologist", "Nutritionist", "Officer", "Operator",
        "Planner", "Principal", "Programmer", "Representative",
        "Scheduler", "Scientist", "Specialist", "Superintendent",
        "Supervisor", "Surveyor", "Tax Preparer", "Technician",
        "Technologist", "Toolmaker", "Trainee", "Treasurer",
        "Underwriter", "Worker",
    ]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
