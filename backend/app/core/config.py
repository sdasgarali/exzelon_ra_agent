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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
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
    MAX_CONTACTS_PER_COMPANY_PER_JOB: int = 4
    MIN_SALARY_THRESHOLD: int = 30000
    DATA_RETENTION_DAYS: int = 180

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

    # Company Size Preference (employees)
    COMPANY_SIZE_PRIORITY_1_MAX: int = 50
    COMPANY_SIZE_PRIORITY_2_MIN: int = 51
    COMPANY_SIZE_PRIORITY_2_MAX: int = 500

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
        "employment agency", "executive search firm"
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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
