"""Environment loader implementing the Global Environment Configuration Standard.

Resolves APP_ENV-prefixed variables from a single .env file so that switching
between TEST/DEV/PROD requires only changing APP_ENV — zero code changes.

Usage (called once at module level in config.py, before Settings instantiation):
    from app.core.env_loader import load_env, validate_env
    app_env = load_env()
    validate_env(app_env)
"""
import os
import platform
import sys
from pathlib import Path
from typing import Optional

# Project root = parent of backend/ directory
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Valid environment names (mapped from legacy values)
_VALID_ENVS = {"TEST", "DEV", "PROD"}
_ENV_ALIASES = {
    "development": "DEV",
    "staging": "PROD",
    "production": "PROD",
    "test": "TEST",
    "dev": "DEV",
    "prod": "PROD",
}

# ---------------------------------------------------------------------------
# Project-specific: canonical keys that MUST exist per environment
# ---------------------------------------------------------------------------
REQUIRED_CANONICAL_KEYS = [
    "SECRET_KEY",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
]

# Keys that MUST NOT be placeholders in PROD
_PLACEHOLDER_VALUES = {"change-me", "change_me", "change-me-in-production",
                       "change-me-use-openssl-rand-hex-32-in-production",
                       "change-me-in-production-use-openssl-rand-hex-32",
                       "rootpassword"}

PRODUCTION_SENSITIVE_KEYS = [
    "SECRET_KEY",
    "ENCRYPTION_KEY",
    "DB_PASSWORD",
]

# Global keys that are NOT prefixed (same value across all environments)
_GLOBAL_KEYS = {
    "APP_NAME", "LOG_LEVEL", "TIMEZONE",
    # Business rules — same across environments
    "DAILY_SEND_LIMIT", "COOLDOWN_DAYS", "MAX_CONTACTS_PER_COMPANY_PER_JOB",
    "MIN_SALARY_THRESHOLD", "DATA_RETENTION_DAYS",
    "TARGET_INDUSTRIES", "JOB_SOURCES", "AVAILABLE_JOB_TITLES",
    "TARGET_JOB_TITLES", "EXCLUDE_IT_KEYWORDS", "EXCLUDE_STAFFING_KEYWORDS",
    "COMPANY_SIZE_PRIORITY_1_MAX", "COMPANY_SIZE_PRIORITY_2_MIN",
    "COMPANY_SIZE_PRIORITY_2_MAX",
    "DATA_STORAGE", "API_V1_PREFIX", "ACCESS_TOKEN_EXPIRE_MINUTES",
}


def _read_dotenv(path: str) -> dict[str, str]:
    """Read a .env file into a dict. Ignores comments and blank lines."""
    values: dict[str, str] = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Remove surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            values[key] = value
    return values


def _resolve_env(app_env: str) -> str:
    """Normalize APP_ENV value to standard form (TEST/DEV/PROD)."""
    upper = app_env.upper().strip()
    if upper in _VALID_ENVS:
        return upper
    alias = _ENV_ALIASES.get(app_env.lower().strip())
    if alias:
        return alias
    return upper  # Will be caught by validation


def _find_env_file() -> str:
    """Find the .env file. Priority: project root, then backend/."""
    root_env = _PROJECT_ROOT / ".env"
    backend_env = _BACKEND_DIR / ".env"
    if root_env.exists():
        return str(root_env)
    if backend_env.exists():
        return str(backend_env)
    return str(root_env)  # Default path (will just have no file)


def load_env(env_file: Optional[str] = None) -> str:
    """Load environment-specific variables from .env file.

    1. Reads APP_ENV (default DEV)
    2. For each key prefixed with ${APP_ENV}_, strips prefix and sets canonical key
    3. For path keys, selects _WIN or _LINUX suffix based on OS
    4. Unprefixed keys that don't match another env prefix are passed through

    Returns:
        Normalized APP_ENV string (TEST/DEV/PROD)
    """
    if env_file is None:
        env_file = _find_env_file()

    raw = _read_dotenv(env_file)

    # System env vars override .env file values
    merged = {**raw, **os.environ}

    # 1. Determine APP_ENV
    app_env = _resolve_env(merged.get("APP_ENV", "DEV"))

    if app_env not in _VALID_ENVS:
        print(
            f"FATAL: APP_ENV must be one of {_VALID_ENVS}. "
            f"Got: '{merged.get('APP_ENV', 'DEV')}' (resolved to '{app_env}')",
            file=sys.stderr,
        )
        sys.exit(1)

    # Map APP_ENV back to legacy values config.py expects
    _env_to_legacy = {"DEV": "development", "PROD": "production", "TEST": "development"}
    os.environ["APP_ENV"] = _env_to_legacy.get(app_env, "development")

    # 2. Collect all env prefixes to know which keys belong to specific envs
    all_prefixes = {f"{e}_" for e in _VALID_ENVS}
    active_prefix = f"{app_env}_"

    is_windows = platform.system() == "Windows"

    for key, value in raw.items():
        if key == "APP_ENV":
            continue

        # Check if this key starts with an environment prefix
        matched_prefix = None
        for pfx in all_prefixes:
            if key.startswith(pfx):
                matched_prefix = pfx
                break

        if matched_prefix:
            # Only process keys for the ACTIVE environment
            if matched_prefix != active_prefix:
                continue

            canonical = key[len(active_prefix):]

            # Handle OS-specific path keys (_WIN / _LINUX)
            if canonical.endswith("_WIN"):
                if is_windows:
                    base_key = canonical[:-4]  # Strip _WIN
                    if base_key not in os.environ:
                        os.environ[base_key] = value
                continue
            elif canonical.endswith("_LINUX"):
                if not is_windows:
                    base_key = canonical[:-6]  # Strip _LINUX
                    if base_key not in os.environ:
                        os.environ[base_key] = value
                continue

            # Regular prefixed key → set canonical in os.environ
            if canonical not in os.environ:
                os.environ[canonical] = value

        else:
            # Unprefixed key — pass through as-is (global/shared)
            if key not in os.environ:
                os.environ[key] = value

    return app_env


def validate_env(app_env: str) -> None:
    """Validate all required keys exist for the selected environment.

    In PROD, also checks that sensitive keys are not set to placeholder values.
    Exits immediately with an error listing missing keys.
    """
    missing = []
    for key in REQUIRED_CANONICAL_KEYS:
        val = os.environ.get(key, "")
        if not val:
            missing.append(f"{app_env}_{key}")

    if missing:
        print(
            f"FATAL: Missing required config keys for APP_ENV={app_env}:\n"
            f"  {', '.join(missing)}\n"
            f"Set these in your .env file as {app_env}_<KEY>=value\n"
            f"Example: {app_env}_DB_HOST=localhost",
            file=sys.stderr,
        )
        sys.exit(1)

    # In PROD, reject placeholder values for sensitive keys
    if app_env == "PROD":
        violations = []
        for key in PRODUCTION_SENSITIVE_KEYS:
            val = os.environ.get(key, "")
            if not val or val.lower() in _PLACEHOLDER_VALUES:
                violations.append(key)

        if violations:
            print(
                f"FATAL: Production environment has placeholder/empty values for:\n"
                f"  {', '.join(violations)}\n"
                f"Generate proper values before deploying to production.\n"
                f"  SECRET_KEY:      python -c \"from secrets import token_hex; print(token_hex(32))\"\n"
                f"  ENCRYPTION_KEY:  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"",
                file=sys.stderr,
            )
            sys.exit(1)
