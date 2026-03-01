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
    APP_NAME: str = "Exzelon RA Cold-Email Automation"
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
    DB_NAME: str = "ra_agent"
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
        "Account Manager", "Territory Manager", "Area Manager"
    ]

    # Target Job Titles
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


def get_tenant_setting(db, key: str, tenant_id: int | None, default=None):
    """Get a setting value with tenant override support.

    Lookup order:
    1. Tenant-specific: settings WHERE key=X AND tenant_id=current_tenant_id
    2. Global default: settings WHERE key=X AND tenant_id IS NULL
    3. Hardcoded default from the `default` parameter
    """
    import json
    from app.db.models.settings import Settings as SettingsModel

    if tenant_id is not None:
        tenant_setting = db.query(SettingsModel).filter(
            SettingsModel.key == key,
            SettingsModel.tenant_id == tenant_id,
        ).first()
        if tenant_setting and tenant_setting.value_json is not None:
            try:
                return json.loads(tenant_setting.value_json)
            except (json.JSONDecodeError, TypeError):
                return tenant_setting.value_json

    global_setting = db.query(SettingsModel).filter(
        SettingsModel.key == key,
        SettingsModel.tenant_id.is_(None),
    ).first()
    if global_setting and global_setting.value_json is not None:
        try:
            return json.loads(global_setting.value_json)
        except (json.JSONDecodeError, TypeError):
            return global_setting.value_json

    return default
