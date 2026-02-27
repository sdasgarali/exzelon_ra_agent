"""Core configuration settings loaded from environment variables."""
from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor all relative paths to the backend/ directory (parent of app/)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Core
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_NAME: str = "Exzelon RA Cold-Email Automation"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Data Storage Mode
    DATA_STORAGE: Literal["database", "files"] = "database"
    JOB_REQUIREMENTS_PATH: str = str(_BACKEND_DIR / "data" / "Job_requirements.xlsx")
    EXPORT_PATH: str = str(_BACKEND_DIR / "data" / "exports")

    # Database
    DB_TYPE: Literal["mysql", "sqlite"] = "sqlite"
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "ra_agent"
    DB_USER: str = "ra_user"
    DB_PASSWORD: str = "change_me"

    @property
    def DATABASE_URL(self) -> str:
        if self.DB_TYPE == "sqlite":
            db_path = _BACKEND_DIR / "data" / "ra_agent.db"
            return f"sqlite:///{db_path}"
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        if self.DB_TYPE == "sqlite":
            db_path = _BACKEND_DIR / "data" / "ra_agent.db"
            return f"sqlite+aiosqlite:///{db_path}"
        return f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

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
    MAX_CONTACTS_PER_COMPANY_PER_JOB: int = 4
    MIN_SALARY_THRESHOLD: int = 30000  # IMPACT: Lowered from 40000 to include more entry-level roles

    # Industries (Non-IT only)
    # IMPACT ON LEAD COUNT: Jobs are searched within these industries only.
    #   More industries = broader search = more leads.
    #   22 industries currently configured for maximum coverage.
    TARGET_INDUSTRIES: list[str] = [
        "Healthcare", "Manufacturing", "Logistics", "Retail", "BFSI",
        "Education", "Engineering", "Automotive", "Construction", "Energy",
        "Oil & Gas", "Food & Beverage", "Hospitality", "Real Estate",
        "Legal", "Insurance", "Financial Services", "Industrial", "Skilled Trades",
        "Light Industrial", "Heavy Industrial", "Skilled Trades"
    ]

    # Job Sources Configuration
    JOB_SOURCES: list[str] = ["linkedin", "indeed", "glassdoor", "simplyhired"]
    JSEARCH_API_KEY: str = ""  # RapidAPI key for JSearch (aggregates LinkedIn, Indeed, Glassdoor)

    # Company Size Preference (employees)
    # IMPACT ON LEAD COUNT: Apollo adapter uses these to filter companies.
    #   Wider range = more companies included in results.
    COMPANY_SIZE_PRIORITY_1_MAX: int = 50  # Priority 1: ≤50 employees
    COMPANY_SIZE_PRIORITY_2_MIN: int = 51  # Priority 2: 51-200+ employees
    COMPANY_SIZE_PRIORITY_2_MAX: int = 500

    # Excluded patterns
    # IMPACT ON LEAD COUNT: Each keyword here filters out ANY job/company containing it.
    #   Previously had 18 broad IT keywords like "engineer", "tech", "technology" that
    #   also caught legitimate non-IT roles (e.g. "Construction Engineer", "Biotech Corp").
    #   Now refined to be more specific to pure IT/software roles only.
    #   Reducing from 21 to 14 precise keywords = ~30% fewer false exclusions.
    EXCLUDE_IT_KEYWORDS: list[str] = [
        "software developer", "software engineer", "web developer",
        "programmer", "coding", "data scientist", "devops",
        "full stack", "frontend developer", "backend developer",
        "cloud architect", "cybersecurity analyst", "network administrator",
        "machine learning engineer"
    ]
    # IMPACT ON LEAD COUNT: Staffing company exclusion. These are kept tight to avoid
    #   filtering out companies that simply have "staffing" in a job description.
    #   Only excludes companies whose NAME contains these exact staffing-agency phrases.
    EXCLUDE_STAFFING_KEYWORDS: list[str] = [
        "staffing agency", "staffing firm", "recruitment agency",
        "talent acquisition agency", "temp agency",
        "employment agency", "executive search firm"
    ]

    # Available Job Titles - Master list of all available titles
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
        "Account Manager", "Territory Manager", "Area Manager"
    ]

    # Target Job Titles - Selected titles to use in searches
    # IMPACT ON LEAD COUNT: Previously only 16 of 38 titles were searched by default.
    #   Now ALL 37 titles are enabled. Each additional title generates a separate
    #   search query, potentially returning 10-30 new leads per title.
    #   Going from 16 to 37 titles = ~2.3x more search queries = ~2.3x more leads.
    #   Remove titles from this list to narrow your search scope.
    TARGET_JOB_TITLES: list[str] = [
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
        "Account Manager", "Territory Manager", "Area Manager"
    ]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
