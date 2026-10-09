"""Unit tests for the DeepSeek AI adapter, the AI factory, and the
Anthropic / Gemini message-handling fixes.

All HTTP is served by httpx.MockTransport — no network access.
"""
import json

import httpx
import pytest

from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter
from app.services.adapters.ai.deepseek import DeepSeekAdapter
from app.services.adapters.ai.gemini import GeminiAdapter
from app.services.adapters import ai_content

pytestmark = pytest.mark.unit

FAKE_KEY = "test-deepseek-key-not-real"
_REAL_CLIENT = httpx.Client


def _install_transport(monkeypatch, handler):
    """Route every httpx.Client() created by the adapters through `handler`."""
    calls = []

    def _recording_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request, len(calls))

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_recording_handler)
        return _REAL_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _client_factory)
    # Retry backoff uses time.sleep — make it instant.
    import time
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)
    return calls


def _openai_ok(content="hello from deepseek", prompt_tokens=11, completion_tokens=7):
    return httpx.Response(200, json={
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    })


def _fake_settings(values):
    def _get(db, key, tenant_id=None, default=None):
        return values.get(key, default)
    return _get


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestFactory:
    def test_returns_deepseek_adapter_when_configured(self, monkeypatch):
        monkeypatch.setattr(ai_content, "get_tenant_setting", _fake_settings({
            "ai_provider": "deepseek",
            "deepseek_api_key": FAKE_KEY,
        }))
        db = object()
        adapter = ai_content.get_ai_adapter(db, tenant_id=7)
        assert isinstance(adapter, DeepSeekAdapter)
        assert adapter.api_key == FAKE_KEY
        assert adapter.model == "deepseek-chat"
        assert adapter._cost_db is db
        assert adapter._cost_tenant_id == 7

    def test_respects_ai_model_setting(self, monkeypatch):
        monkeypatch.setattr(ai_content, "get_tenant_setting", _fake_settings({
            "ai_provider": "deepseek",
            "deepseek_api_key": FAKE_KEY,
            "ai_model": "deepseek-reasoner",
        }))
        adapter = ai_content.get_ai_adapter(object())
        assert isinstance(adapter, DeepSeekAdapter)
        assert adapter.model == "deepseek-reasoner"

    def test_returns_none_without_key(self, monkeypatch):
        monkeypatch.setattr(ai_content, "get_tenant_setting", _fake_settings({
            "ai_provider": "deepseek",
            # A key for another provider must not be used for DeepSeek.
            "groq_api_key": "some-groq-key",
        }))
        assert ai_content.get_ai_adapter(object()) is None

    def test_resolves_from_real_settings_table(self, db_session):
        from app.core.settings_resolver import set_tenant_setting
        set_tenant_setting(db_session, "ai_provider", "deepseek")
        set_tenant_setting(db_session, "deepseek_api_key", FAKE_KEY)
        db_session.commit()
        adapter = ai_content.get_ai_adapter(db_session)
        assert isinstance(adapter, DeepSeekAdapter)
        assert adapter.api_key == FAKE_KEY


class TestStandaloneFactories:
    """Warmup, company enrichment and the AI fallback chain resolve providers
    through `warmup_ai_provider` with their own factories — DeepSeek must work there too."""

    def _configure(self, db_session):
        from app.core.settings_resolver import set_tenant_setting
        set_tenant_setting(db_session, "warmup_ai_provider", "deepseek")
        set_tenant_setting(db_session, "deepseek_api_key", FAKE_KEY)
        db_session.commit()

    def test_warmup_content_generator(self, db_session):
        from app.services.warmup import content_generator
        self._configure(db_session)
        adapter = content_generator.get_ai_adapter(db_session)
        assert isinstance(adapter, DeepSeekAdapter)
        assert adapter.api_key == FAKE_KEY

    def test_company_enrichment(self, db_session):
        from app.services import company_enrichment
        self._configure(db_session)
        assert "deepseek" in company_enrichment.PAID_AI_PROVIDERS
        adapter = company_enrichment._get_ai_adapter(db_session)
        assert isinstance(adapter, DeepSeekAdapter)

    def test_ai_resilience_fallback_chain(self, db_session):
        from app.services import ai_resilience
        self._configure(db_session)
        adapter = ai_resilience._try_get_adapter(db_session, None, "deepseek")
        assert isinstance(adapter, DeepSeekAdapter)


# ---------------------------------------------------------------------------
# DeepSeek adapter HTTP behaviour
# ---------------------------------------------------------------------------

class TestDeepSeekCallApi:
    def test_request_shape(self, monkeypatch):
        calls = _install_transport(monkeypatch, lambda req, n: _openai_ok())
        adapter = DeepSeekAdapter(api_key=FAKE_KEY)
        out = adapter._call_api(
            [{"role": "user", "content": "hi"}], max_tokens=50, system="be brief"
        )
        assert out == "hello from deepseek"
        assert len(calls) == 1
        req = calls[0]
        assert req.method == "POST"
        assert str(req.url) == "https://api.deepseek.com/v1/chat/completions"
        assert req.headers["Authorization"] == f"Bearer {FAKE_KEY}"
        body = json.loads(req.content)
        assert body["model"] == "deepseek-chat"
        assert body["max_tokens"] == 50
        assert body["messages"][0] == {"role": "system", "content": "be brief"}
        assert body["messages"][1] == {"role": "user", "content": "hi"}
        assert adapter._last_usage == {"input_tokens": 11, "output_tokens": 7}

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_retries_transient_errors_then_succeeds(self, monkeypatch, status):
        def handler(req, n):
            return httpx.Response(status, json={"error": "busy"}) if n < 3 else _openai_ok("ok")
        calls = _install_transport(monkeypatch, handler)
        out = DeepSeekAdapter(api_key=FAKE_KEY)._call_api([{"role": "user", "content": "x"}])
        assert out == "ok"
        assert len(calls) == 3

    def test_raises_after_exhausting_retries(self, monkeypatch):
        calls = _install_transport(monkeypatch, lambda req, n: httpx.Response(429, json={}))
        with pytest.raises(httpx.HTTPStatusError):
            DeepSeekAdapter(api_key=FAKE_KEY)._call_api([{"role": "user", "content": "x"}])
        assert len(calls) == 3

    def test_no_retry_on_client_error(self, monkeypatch):
        calls = _install_transport(monkeypatch, lambda req, n: httpx.Response(401, json={}))
        with pytest.raises(httpx.HTTPStatusError):
            DeepSeekAdapter(api_key=FAKE_KEY)._call_api([{"role": "user", "content": "x"}])
        assert len(calls) == 1

    def test_missing_key_raises(self, monkeypatch):
        adapter = DeepSeekAdapter(api_key=None)
        adapter.api_key = None
        with pytest.raises(ValueError):
            adapter._call_api([{"role": "user", "content": "x"}])

    def test_test_connection(self, monkeypatch):
        calls = _install_transport(monkeypatch, lambda req, n: httpx.Response(200, json={"data": []}))
        assert DeepSeekAdapter(api_key=FAKE_KEY).test_connection() is True
        assert str(calls[0].url) == "https://api.deepseek.com/v1/models"

    def test_cost_tracked_with_deepseek_pricing(self, monkeypatch):
        from app.services import cost_tracker
        assert cost_tracker.AI_MODEL_PRICING["deepseek-chat"] == (0.27, 1.10)
        assert cost_tracker.AI_PROVIDER_FALLBACK["deepseek"] == (0.27, 1.10)

        recorded = {}
        monkeypatch.setattr(cost_tracker, "record_ai_cost", lambda db, **kw: recorded.update(kw))
        _install_transport(monkeypatch, lambda req, n: _openai_ok(prompt_tokens=1000, completion_tokens=500))
        adapter = DeepSeekAdapter(api_key=FAKE_KEY)
        adapter._cost_db = object()
        adapter._cost_tenant_id = 3
        adapter._call_api([{"role": "user", "content": "x"}])
        assert recorded["provider"] == "deepseek"
        assert recorded["model"] == "deepseek-chat"
        assert recorded["input_tokens"] == 1000
        assert recorded["output_tokens"] == 500
        assert recorded["tenant_id"] == 3


# ---------------------------------------------------------------------------
# Anthropic: system messages go to the top-level `system` parameter
# ---------------------------------------------------------------------------

def _anthropic_ok(text="claude says hi"):
    return httpx.Response(200, json={
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 3, "output_tokens": 2},
    })


class TestAnthropicSystemExtraction:
    def test_system_messages_moved_to_top_level(self, monkeypatch):
        calls = _install_transport(monkeypatch, lambda req, n: _anthropic_ok())
        out = AnthropicAdapter(api_key="test-anthropic-key")._call_api([
            {"role": "system", "content": "rule one"},
            {"role": "user", "content": "hello"},
            {"role": "system", "content": "rule two"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "again"},
        ], max_tokens=20)
        assert out == "claude says hi"
        body = json.loads(calls[0].content)
        assert body["system"] == "rule one\n\nrule two"
        assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
        assert all(m["role"] != "system" for m in body["messages"])

    def test_explicit_system_merged_first(self, monkeypatch):
        calls = _install_transport(monkeypatch, lambda req, n: _anthropic_ok())
        AnthropicAdapter(api_key="test-anthropic-key")._call_api(
            [{"role": "system", "content": "inline"}, {"role": "user", "content": "q"}],
            system="explicit",
        )
        body = json.loads(calls[0].content)
        assert body["system"] == "explicit\n\ninline"
        assert body["messages"] == [{"role": "user", "content": "q"}]

    def test_no_system_key_when_absent(self, monkeypatch):
        calls = _install_transport(monkeypatch, lambda req, n: _anthropic_ok())
        AnthropicAdapter(api_key="test-anthropic-key")._call_api([{"role": "user", "content": "q"}])
        body = json.loads(calls[0].content)
        assert "system" not in body


# ---------------------------------------------------------------------------
# Gemini: accepts str prompt or list of messages
# ---------------------------------------------------------------------------

def _gemini_ok(text="gemini says hi"):
    return httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
    })


class TestGeminiMessageInput:
    def test_str_prompt_unchanged(self, monkeypatch):
        calls = _install_transport(monkeypatch, lambda req, n: _gemini_ok())
        out = GeminiAdapter(api_key="test-gemini-key")._call_api(
            prompt="write a line", system_instruction="be terse", max_tokens=30
        )
        assert out == "gemini says hi"
        body = json.loads(calls[0].content)
        assert body["contents"] == [{"parts": [{"text": "write a line"}]}]
        assert body["systemInstruction"] == {"parts": [{"text": "be terse"}]}
        assert body["generationConfig"]["maxOutputTokens"] == 30

    def test_positional_str_prompt(self, monkeypatch):
        calls = _install_transport(monkeypatch, lambda req, n: _gemini_ok())
        GeminiAdapter(api_key="test-gemini-key")._call_api("plain")
        body = json.loads(calls[0].content)
        assert body["contents"] == [{"parts": [{"text": "plain"}]}]
        assert "systemInstruction" not in body

    def test_message_list_mapped(self, monkeypatch):
        calls = _install_transport(monkeypatch, lambda req, n: _gemini_ok())
        out = GeminiAdapter(api_key="test-gemini-key")._call_api([
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
        ], max_tokens=40)
        assert out == "gemini says hi"
        body = json.loads(calls[0].content)
        assert body["systemInstruction"] == {"parts": [{"text": "sys"}]}
        assert body["contents"] == [
            {"role": "user", "parts": [{"text": "u1"}]},
            {"role": "model", "parts": [{"text": "a1"}]},
            {"role": "user", "parts": [{"text": "u2"}]},
        ]

    def test_messages_and_system_keyword_aliases(self, monkeypatch):
        calls = _install_transport(monkeypatch, lambda req, n: _gemini_ok())
        GeminiAdapter(api_key="test-gemini-key")._call_api(
            messages=[{"role": "system", "content": "inline"}, {"role": "user", "content": "q"}],
            system="explicit",
        )
        body = json.loads(calls[0].content)
        assert body["systemInstruction"] == {"parts": [{"text": "explicit\n\ninline"}]}
        assert body["contents"] == [{"role": "user", "parts": [{"text": "q"}]}]
