"""Shared AI adapter factory — single entry point for all AI-powered features."""
import json
from sqlalchemy.orm import Session
from app.db.models.settings import Settings


def _get_setting(db: Session, key: str, default=None):
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting and setting.value_json:
        try:
            return json.loads(setting.value_json)
        except Exception:
            pass
    return default


def get_ai_adapter(db: Session):
    """Load configured AI provider from settings.

    Reads `warmup_ai_provider` and the corresponding API key from the settings
    table, then returns the matching adapter instance.  Returns None when no
    API key is configured.
    """
    provider = _get_setting(db, "warmup_ai_provider", "groq")
    api_key_map = {
        "groq": "groq_api_key",
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "gemini": "gemini_api_key",
    }
    api_key = _get_setting(db, api_key_map.get(provider, "groq_api_key"), "")
    if not api_key:
        return None
    try:
        if provider == "groq":
            from app.services.adapters.ai.groq import GroqAdapter
            return GroqAdapter(api_key=api_key)
        elif provider == "openai":
            from app.services.adapters.ai.openai_adapter import OpenAIAdapter
            return OpenAIAdapter(api_key=api_key)
        elif provider == "anthropic":
            from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter
            return AnthropicAdapter(api_key=api_key)
        elif provider == "gemini":
            from app.services.adapters.ai.gemini import GeminiAdapter
            return GeminiAdapter(api_key=api_key)
    except Exception:
        pass
    return None
