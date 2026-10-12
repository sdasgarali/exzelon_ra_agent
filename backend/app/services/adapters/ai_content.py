"""Shared AI adapter factory — single entry point for all AI-powered features."""
import json
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.core.settings_resolver import get_tenant_setting

API_KEY_SETTING = {
    "groq": "groq_api_key",
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini": "gemini_api_key",
}


def _tenant_only(db: Session, key: str, tenant_id: Optional[int]):
    """A tenant's own override for `key`, ignoring the global default."""
    if tenant_id is None:
        return None
    from app.db.models.tenant_settings import TenantSettings
    row = (
        db.query(TenantSettings)
        .filter(TenantSettings.tenant_id == tenant_id, TenantSettings.key == key)
        .first()
    )
    if row is None or row.value_json is None:
        return None
    try:
        return json.loads(row.value_json)
    except (json.JSONDecodeError, TypeError):
        return row.value_json


def resolve_ai_config(
    db: Session,
    tenant_id: Optional[int],
    provider_keys: Tuple[str, ...] = ("ai_provider", "warmup_ai_provider"),
    model_key: Optional[str] = "ai_model",
) -> Tuple[str, str, str]:
    """(provider, model, api_key) for a tenant, never billing a tenant's choice to us.

    A tenant may bring its own provider, model and key. What it must not do is pick a
    provider or model and have the call run on the PLATFORM's key for it — that turns
    a flat-priced credit into an uncapped bill for us (e.g. switching to the most
    expensive Anthropic model while credits stay at 1 per action).

    So: if the tenant overrides the provider or model, the key must also be the
    tenant's own. Without one, the tenant's overrides are ignored and the platform's
    configuration is used as a whole.
    """
    def first(keys, tid):
        for k in keys:
            v = (_tenant_only(db, k, tid) if tid is not None
                 else get_tenant_setting(db, k, tenant_id=None, default=None))
            if v:
                return str(v)
        return None

    platform_provider = first(provider_keys, None) or "groq"
    platform_model = (get_tenant_setting(db, model_key, tenant_id=None, default="") or "") if model_key else ""
    platform_key = get_tenant_setting(db, API_KEY_SETTING.get(platform_provider, "groq_api_key"),
                                      tenant_id=None, default="") or ""

    if tenant_id is None:
        return platform_provider, str(platform_model), str(platform_key)

    t_provider = first(provider_keys, tenant_id)
    t_model = _tenant_only(db, model_key, tenant_id) if model_key else None
    provider = t_provider or platform_provider
    t_key = _tenant_only(db, API_KEY_SETTING.get(provider, "groq_api_key"), tenant_id)

    if t_key:
        return provider, str(t_model or (platform_model if provider == platform_provider else "")), str(t_key)
    # No key of its own: a tenant override would run on our key, so drop it.
    return platform_provider, str(platform_model), str(platform_key)


def get_ai_adapter(db: Session, tenant_id: Optional[int] = None):
    """Load configured AI provider from settings.

    Reads `ai_provider` (with fallback to legacy `warmup_ai_provider`),
    the corresponding API key, and optionally `ai_model`, then returns the matching
    adapter instance. See :func:`resolve_ai_config` for how tenant overrides are
    honoured. Returns None when no API key is configured.
    """
    provider, model, api_key = resolve_ai_config(db, tenant_id)
    if not api_key:
        return None
    try:
        adapter = None
        if provider == "groq":
            from app.services.adapters.ai.groq import GroqAdapter
            adapter = GroqAdapter(api_key=api_key, model=model or None)
        elif provider == "openai":
            from app.services.adapters.ai.openai_adapter import OpenAIAdapter
            adapter = OpenAIAdapter(api_key=api_key, model=model or None)
        elif provider == "anthropic":
            from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter
            adapter = AnthropicAdapter(api_key=api_key, model=model or None)
        elif provider == "gemini":
            from app.services.adapters.ai.gemini import GeminiAdapter
            adapter = GeminiAdapter(api_key=api_key, model=model or None)
        if adapter is not None:
            # Enable automatic AI cost tracking (uses this session via SAVEPOINT).
            adapter._cost_db = db
            adapter._cost_tenant_id = tenant_id
        return adapter
    except Exception:
        pass
    return None
