"""Shared AI adapter factory — single entry point for all AI-powered features."""
from typing import Optional
from sqlalchemy.orm import Session
from app.core.settings_resolver import get_tenant_setting


def get_ai_adapter(db: Session, tenant_id: Optional[int] = None):
    """Load configured AI provider from settings.

    Reads `ai_provider` (with fallback to legacy `warmup_ai_provider`),
    the corresponding API key, and optionally `ai_model` from the settings
    table, then returns the matching adapter instance.  Returns None when
    no API key is configured.
    """
    provider = get_tenant_setting(db, "ai_provider", tenant_id=tenant_id, default=None)
    if not provider:
        provider = get_tenant_setting(db, "warmup_ai_provider", tenant_id=tenant_id, default="groq")
    model = get_tenant_setting(db, "ai_model", tenant_id=tenant_id, default="")
    api_key_map = {
        "groq": "groq_api_key",
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "gemini": "gemini_api_key",
    }
    api_key = get_tenant_setting(db, api_key_map.get(provider, "groq_api_key"), tenant_id=tenant_id, default="")
    if not api_key:
        return None
    try:
        if provider == "groq":
            from app.services.adapters.ai.groq import GroqAdapter
            return GroqAdapter(api_key=api_key, model=model or None)
        elif provider == "openai":
            from app.services.adapters.ai.openai_adapter import OpenAIAdapter
            return OpenAIAdapter(api_key=api_key, model=model or None)
        elif provider == "anthropic":
            from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter
            return AnthropicAdapter(api_key=api_key, model=model or None)
        elif provider == "gemini":
            from app.services.adapters.ai.gemini import GeminiAdapter
            return GeminiAdapter(api_key=api_key, model=model or None)
    except Exception:
        pass
    return None
