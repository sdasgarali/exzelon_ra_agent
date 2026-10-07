"""Settings, loaded from the environment (optionally a .env file).

Follows the project-wide convention: when ``APP_ENV`` is TEST|DEV|PROD, a key
``X`` is read from ``${APP_ENV}_X`` first, then from plain ``X``. Without
``APP_ENV``, only plain names are read, which keeps a local stdio install to
two variables (``NEURALEADS_API_URL``, ``NEURALEADS_API_KEY``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

DEFAULT_API_URL = "https://neuraleads.ai/api/v1"
_VALID_ENVS = {"TEST", "DEV", "PROD"}


class ConfigError(ValueError):
    """Raised for invalid or missing configuration (fail fast at startup)."""


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    app_env = (os.getenv("APP_ENV") or "").strip().upper()
    if app_env:
        prefixed = os.getenv(f"{app_env}_{name}")
        if prefixed not in (None, ""):
            return prefixed
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _bool(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    api_url: str = DEFAULT_API_URL
    # stdio mode: the key every call uses. HTTP mode: ignored — each request brings its own.
    api_key: Optional[str] = None
    read_only: bool = False
    timeout_seconds: float = 60.0
    max_retries: int = 2
    http_host: str = "127.0.0.1"
    http_port: int = 8010
    # Host headers the HTTP transport accepts (DNS-rebinding protection).
    allowed_hosts: tuple = field(default_factory=lambda: ("127.0.0.1:*", "localhost:*"))
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "Settings":
        load_dotenv(env_file, override=False)
        app_env = (os.getenv("APP_ENV") or "").strip().upper()
        if app_env and app_env not in _VALID_ENVS:
            raise ConfigError(f"APP_ENV must be one of {sorted(_VALID_ENVS)}, got {app_env!r}")

        api_url = (_get("NEURALEADS_API_URL", DEFAULT_API_URL) or DEFAULT_API_URL).rstrip("/")
        if not api_url.startswith(("http://", "https://")):
            raise ConfigError("NEURALEADS_API_URL must start with http:// or https://")

        try:
            timeout = float(_get("NEURALEADS_TIMEOUT_SECONDS", "60"))
            retries = int(_get("NEURALEADS_MAX_RETRIES", "2"))
            port = int(_get("MCP_HTTP_PORT", "8010"))
        except ValueError as exc:
            raise ConfigError(f"Invalid numeric setting: {exc}") from exc

        hosts_raw = _get("MCP_ALLOWED_HOSTS")
        hosts = tuple(h.strip() for h in hosts_raw.split(",") if h.strip()) if hosts_raw else cls.allowed_hosts_default()

        return cls(
            api_url=api_url,
            api_key=_get("NEURALEADS_API_KEY"),
            read_only=_bool(_get("NEURALEADS_MCP_READ_ONLY")),
            timeout_seconds=timeout,
            max_retries=max(0, retries),
            http_host=_get("MCP_HTTP_HOST", "127.0.0.1"),
            http_port=port,
            allowed_hosts=hosts,
            log_level=(_get("MCP_LOG_LEVEL", "INFO") or "INFO").upper(),
        )

    @staticmethod
    def allowed_hosts_default() -> tuple:
        return ("127.0.0.1:*", "localhost:*")
