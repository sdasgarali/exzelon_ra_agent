"""Unit tests: REST client, error mapping, sanitising, auth resolution, config, gating."""
from __future__ import annotations

import httpx
import pytest
from conftest import result_json
import respx
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from neuraleads_mcp.client import NeuraLeadsClient, NeuraLeadsError, explain_error
from neuraleads_mcp.config import ConfigError, Settings
from neuraleads_mcp.runtime import Runtime, clamp_limit, pick_list, sanitize
from neuraleads_mcp.server import build_server

pytestmark = pytest.mark.unit
API = "https://api.test/api/v1"


# ── error mapping ───────────────────────────────────────────────────────

def test_explain_402_feature_gate():
    msg = explain_error(402, {"code": "feature_not_in_plan", "required_plan": "pro",
                              "message": "Warmup is available on Pro and above."})
    assert "not included in the workspace's plan" in msg and "pro" in msg


def test_explain_422_lists_fields():
    msg = explain_error(422, [{"loc": ["body", "lead_ids"], "msg": "field required"}])
    assert msg == "Invalid request. lead_ids: field required"


@pytest.mark.parametrize("status,needle", [(401, "API key"), (403, "Permission denied"),
                                           (404, "Not found"), (429, "Rate limited"), (503, "server error")])
def test_explain_statuses(status, needle):
    assert needle in explain_error(status, "x")


# ── REST client ─────────────────────────────────────────────────────────

@respx.mock
async def test_sends_api_key_and_drops_none_params():
    route = respx.get(f"{API}/leads").mock(return_value=httpx.Response(200, json={"items": []}))
    c = NeuraLeadsClient(API, max_retries=0)
    await c.request("k1", "GET", "/leads", params={"search": "x", "status": None})
    req = route.calls.last.request
    assert req.headers["X-API-Key"] == "k1"
    assert req.url.params.get("search") == "x" and "status" not in req.url.params
    await c.aclose()


@respx.mock
async def test_get_retried_on_503():
    route = respx.get(f"{API}/leads").mock(side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": 1})])
    c = NeuraLeadsClient(API, max_retries=2)
    assert await c.request("k", "GET", "/leads") == {"ok": 1}
    assert route.call_count == 2
    await c.aclose()


@respx.mock
async def test_post_never_retried():
    route = respx.post(f"{API}/campaigns/1/activate").mock(return_value=httpx.Response(503))
    c = NeuraLeadsClient(API, max_retries=3)
    with pytest.raises(NeuraLeadsError) as exc:
        await c.request("k", "POST", "/campaigns/1/activate")
    assert route.call_count == 1 and exc.value.status == 503
    await c.aclose()


@respx.mock
async def test_post_transport_error_warns_outcome_unknown():
    respx.post(f"{API}/x").mock(side_effect=httpx.ConnectTimeout("boom"))
    c = NeuraLeadsClient(API, max_retries=3)
    with pytest.raises(NeuraLeadsError, match="may or may not have run"):
        await c.request("k", "POST", "/x")
    await c.aclose()


@respx.mock
async def test_204_returns_ok():
    respx.put(f"{API}/x").mock(return_value=httpx.Response(204))
    c = NeuraLeadsClient(API)
    assert await c.request("k", "PUT", "/x") == {"ok": True}
    await c.aclose()


async def test_empty_key_rejected_without_network():
    c = NeuraLeadsClient(API)
    with pytest.raises(NeuraLeadsError) as exc:
        await c.request("", "GET", "/leads")
    assert exc.value.status == 401
    await c.aclose()


# ── output shaping ──────────────────────────────────────────────────────

def test_sanitize_strips_credentials_recursively():
    data = {"email": "a@b.c", "password": "p", "smtp_password": "p", "oauth_refresh_token": "t",
            "api_key": "k", "nested": [{"access_token": "t", "keep": 1}],
            "password_set": True, "key_prefix": "exz_ab", "oauth_connected": True}
    out = sanitize(data)
    assert out == {"email": "a@b.c", "nested": [{"keep": 1}], "password_set": True,
                   "key_prefix": "exz_ab", "oauth_connected": True}


def test_pick_list_and_clamp():
    assert pick_list({"items": [{"a": 1, "b": 2}], "total": 1}, ("a",)) == {"items": [{"a": 1}], "total": 1}
    assert pick_list([{"a": 1, "b": 2}], ("b",)) == [{"b": 2}]
    assert clamp_limit(None) == 25 and clamp_limit(0) == 1 and clamp_limit(10_000) == 100


# ── auth resolution ─────────────────────────────────────────────────────

class _Ctx:
    def __init__(self, headers):
        self.headers = headers


def test_stdio_uses_env_key_but_header_wins():
    rt = Runtime(Settings(api_key="env-key"), hosted=False)
    assert rt.api_key_for(_Ctx({})) == "env-key"
    assert rt.api_key_for(_Ctx({"Authorization": "Bearer hdr"})) == "hdr"


def test_hosted_requires_request_key():
    rt = Runtime(Settings(api_key="server-key"), hosted=True)
    assert rt.api_key_for(_Ctx({"x-api-key": "abc"})) == "abc"
    assert rt.api_key_for(_Ctx({"authorization": "bearer xyz"})) == "xyz"
    with pytest.raises(ToolError, match="Missing API key"):
        rt.api_key_for(_Ctx({}))
    with pytest.raises(ToolError):
        rt.api_key_for(_Ctx({"Authorization": "Bearer "}))


def test_stdio_without_key_explains_setup():
    with pytest.raises(ToolError, match="NEURALEADS_API_KEY"):
        Runtime(Settings(api_key=None)).api_key_for(_Ctx({}))


# ── config ──────────────────────────────────────────────────────────────

def test_config_prefixed_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "PROD")
    monkeypatch.setenv("PROD_NEURALEADS_API_URL", "https://prod.example/api/v1/")
    monkeypatch.setenv("NEURALEADS_API_URL", "https://plain.example/api/v1")
    monkeypatch.setenv("NEURALEADS_MCP_READ_ONLY", "yes")
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "neuraleads.ai, www.neuraleads.ai")
    s = Settings.from_env()
    assert s.api_url == "https://prod.example/api/v1"
    assert s.read_only is True
    assert s.allowed_hosts == ("neuraleads.ai", "www.neuraleads.ai")


@pytest.mark.parametrize("var,value", [("APP_ENV", "STAGING"), ("NEURALEADS_API_URL", "ftp://x"),
                                       ("MCP_HTTP_PORT", "eighty")])
def test_config_fails_fast(monkeypatch, var, value):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv(var, value)
    with pytest.raises(ConfigError):
        Settings.from_env()


# ── tool behaviour without a backend ────────────────────────────────────

async def _call(mcp, name, args):
    async with Client(mcp) as client:
        return await client.call_tool(name, args)


@respx.mock
async def test_confirmation_gate_makes_no_write_call():
    respx.get(f"{API}/credits/balance").mock(return_value=httpx.Response(200, json={"total_remaining": 900}))
    run = respx.post(f"{API}/pipelines/lead-sourcing/run").mock(return_value=httpx.Response(200, json={}))
    mcp, _ = build_server(Settings(api_url=API, api_key="k", max_retries=0))
    res = await _call(mcp, "run_lead_sourcing", {"sources": ["indeed"]})
    assert result_json(res)["status"] == "confirmation_required"
    assert result_json(res)["details"]["credits_remaining"] == 900
    assert run.call_count == 0


@respx.mock
async def test_activate_reports_not_ready_without_calling_activate():
    respx.get(f"{API}/campaigns/5").mock(return_value=httpx.Response(200, json={
        "campaign_id": 5, "status": "draft", "mailbox_ids": [], "total_contacts": 0, "steps": []}))
    act = respx.post(f"{API}/campaigns/5/activate").mock(return_value=httpx.Response(200, json={}))
    mcp, _ = build_server(Settings(api_url=API, api_key="k", max_retries=0))
    res = await _call(mcp, "activate_campaign", {"campaign_id": 5, "confirm": True})
    assert result_json(res)["status"] == "not_ready"
    assert set(result_json(res)["problems"]) >= {"no email steps", "no sender mailboxes assigned",
                                                       "no contacts enrolled"}
    assert act.call_count == 0


@respx.mock
async def test_warmup_tool_checks_mailbox_ownership_first():
    respx.get(f"{API}/mailboxes/9").mock(return_value=httpx.Response(404, json={"detail": "Mailbox not found"}))
    hist = respx.get(f"{API}/warmup/analytics").mock(return_value=httpx.Response(200, json={}))
    mcp, _ = build_server(Settings(api_url=API, api_key="k", max_retries=0))
    res = await _call(mcp, "get_mailbox_warmup_history", {"mailbox_id": 9})
    assert res.is_error and hist.call_count == 0


@respx.mock
async def test_warmup_alerts_filtered_to_own_mailboxes():
    respx.get(f"{API}/mailboxes").mock(return_value=httpx.Response(200, json={"items": [{"mailbox_id": 1}]}))
    respx.get(f"{API}/warmup/alerts").mock(return_value=httpx.Response(200, json={"items": [
        {"id": 1, "mailbox_id": 1, "is_read": False}, {"id": 2, "mailbox_id": 77, "is_read": False}]}))
    mcp, _ = build_server(Settings(api_url=API, api_key="k", max_retries=0))
    res = await _call(mcp, "list_warmup_alerts", {})
    assert [a["id"] for a in result_json(res)["items"]] == [1]


@respx.mock
async def test_send_reply_refuses_unsubscribed_contact():
    respx.get(f"{API}/inbox/threads/t1").mock(return_value=httpx.Response(200, json={
        "thread_id": "t1", "contact": {"contact_id": 3, "email": "x@y.z"},
        "messages": [{"direction": "received", "mailbox_id": 2, "subject": "Hi"}]}))
    respx.get(f"{API}/contacts/3").mock(return_value=httpx.Response(200, json={"outreach_status": "unsubscribed"}))
    send = respx.post(f"{API}/inbox/reply").mock(return_value=httpx.Response(200, json={}))
    mcp, _ = build_server(Settings(api_url=API, api_key="k", max_retries=0))
    res = await _call(mcp, "send_inbox_reply", {"thread_id": "t1", "body_text": "hello", "confirm": True})
    assert res.is_error and "unsubscribed" in res.content[0].text
    assert send.call_count == 0


async def test_every_tool_has_annotations_and_description():
    mcp, _ = build_server(Settings(api_key="k"))
    for tool in await mcp.list_tools():
        assert tool.annotations is not None, tool.name
        assert tool.description and len(tool.description) > 20, tool.name
