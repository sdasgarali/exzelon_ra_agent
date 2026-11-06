"""Anthropic adapter on current Claude models.

The Claude 3.x ids it used were retired (every call failed), Opus 5 / Sonnet 5 reject
`temperature` with a 400, and a reply's first content block is not always text.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter
from app.services.cost_tracker import AI_MODEL_PRICING

pytestmark = pytest.mark.unit


def _fake_client(content):
    resp = MagicMock()
    resp.json.return_value = {"content": content, "usage": {"input_tokens": 10, "output_tokens": 5}}
    resp.raise_for_status.return_value = None
    client = MagicMock()
    client.post.return_value = resp
    ctx = MagicMock()
    ctx.__enter__.return_value = client
    ctx.__exit__.return_value = False
    return ctx, client


def _call(model, content=None):
    ctx, client = _fake_client(content or [{"type": "text", "text": "Hello!"}])
    adapter = AnthropicAdapter(api_key="sk-ant-test", model=model)
    with patch("app.services.adapters.ai.anthropic_adapter.httpx.Client", return_value=ctx):
        out = adapter._call_api([{"role": "user", "content": "hi"}], max_tokens=50)
    return out, client.post.call_args.kwargs["json"]


def test_default_is_a_current_model_not_a_retired_one():
    assert AnthropicAdapter(api_key="k").model == "claude-haiku-4-5"
    assert not any(m.startswith("claude-3") for m in AnthropicAdapter.MODELS)


def test_non_claude_model_falls_back_to_default():
    assert AnthropicAdapter(api_key="k", model="gpt-4.1-nano").model == "claude-haiku-4-5"


def test_haiku_sends_temperature():
    _, payload = _call("claude-haiku-4-5")
    assert payload["model"] == "claude-haiku-4-5"
    assert "temperature" in payload


@pytest.mark.parametrize("model", ["claude-opus-5", "claude-sonnet-5"])
def test_models_without_sampling_omit_temperature(model):
    _, payload = _call(model)
    assert "temperature" not in payload


def test_reply_text_skips_non_text_blocks():
    out, _ = _call("claude-opus-5", [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": "Part one. "},
        {"type": "text", "text": "Part two."},
    ])
    assert out == "Part one. Part two."


def test_current_models_are_priced():
    assert AI_MODEL_PRICING["claude-haiku-4-5"] == (1.00, 5.00)
    assert AI_MODEL_PRICING["claude-sonnet-5"] == (2.00, 10.00)
    assert AI_MODEL_PRICING["claude-opus-5"] == (5.00, 25.00)
