"""AI resilience layer — retry with exponential backoff and provider fallback.

Wraps AI adapter calls with:
1. Exponential backoff retry (3 attempts, 1s → 2s → 4s)
2. Provider fallback chain (primary → secondary → rule-based)
"""
import time
import structlog
from typing import Optional, Callable, Any, List

logger = structlog.get_logger()

# Default retry configuration
MAX_RETRIES = 3
BASE_DELAY_SEC = 1.0
BACKOFF_MULTIPLIER = 2.0


def retry_with_backoff(
    func: Callable,
    *args,
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_DELAY_SEC,
    backoff_multiplier: float = BACKOFF_MULTIPLIER,
    **kwargs,
) -> Any:
    """Call func with exponential backoff retry.

    Args:
        func: Callable to invoke
        max_retries: Max number of attempts (default 3)
        base_delay: Initial delay in seconds (default 1.0)
        backoff_multiplier: Delay multiplier per retry (default 2.0)

    Returns:
        Result of successful func call

    Raises:
        Last exception if all retries exhausted
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (backoff_multiplier ** attempt)
                logger.warning(
                    "ai_call_retry",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    delay_sec=delay,
                    error=str(e),
                )
                time.sleep(delay)
    raise last_error


def call_ai_with_fallback(
    db,
    tenant_id: Optional[int],
    method_name: str,
    *args,
    fallback_result: Any = None,
    **kwargs,
) -> Any:
    """Call an AI adapter method with provider fallback.

    Tries the tenant's configured primary provider first. If it fails after
    retries, tries each remaining provider in order. If all providers fail,
    returns fallback_result.

    Args:
        db: Database session
        tenant_id: Tenant ID for settings lookup
        method_name: Name of the method to call on the adapter (e.g., "generate_email")
        fallback_result: Value to return if all providers fail (default None)

    Returns:
        AI adapter result or fallback_result
    """
    from app.services.adapters.ai_content import get_ai_adapter
    from app.core.settings_resolver import get_tenant_setting

    # Get primary provider
    primary = get_tenant_setting(db, "warmup_ai_provider", tenant_id=tenant_id, default="groq")

    # Define fallback order (primary first, then alternatives)
    all_providers = ["groq", "openai", "anthropic", "gemini"]
    provider_order = [primary] + [p for p in all_providers if p != primary]

    for provider in provider_order:
        adapter = _try_get_adapter(db, tenant_id, provider)
        if adapter is None:
            continue

        method = getattr(adapter, method_name, None)
        if method is None:
            continue

        try:
            result = retry_with_backoff(method, *args, **kwargs)
            if provider != primary:
                logger.info("ai_fallback_used", provider=provider, method=method_name)
            return result
        except Exception as e:
            logger.warning(
                "ai_provider_failed",
                provider=provider,
                method=method_name,
                error=str(e),
            )
            continue

    logger.error("ai_all_providers_failed", method=method_name, tenant_id=tenant_id)
    return fallback_result


def _try_get_adapter(db, tenant_id: Optional[int], provider: str):
    """Try to instantiate an adapter for a specific provider."""
    from app.core.settings_resolver import get_tenant_setting

    api_key_map = {
        "groq": "groq_api_key",
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "gemini": "gemini_api_key",
    }
    key_setting = api_key_map.get(provider)
    if not key_setting:
        return None

    api_key = get_tenant_setting(db, key_setting, tenant_id=tenant_id, default="")
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
        return None
    return None
