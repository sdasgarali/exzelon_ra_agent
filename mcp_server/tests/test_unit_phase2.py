"""Unit tests for the phase-2 tools: workspace selection, content, data management, mailbox setup,
direct outreach. The REST API is mocked with respx."""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from conftest import result_json
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from neuraleads_mcp.config import ConfigError, Settings
from neuraleads_mcp.runtime import Runtime
from neuraleads_mcp.server import build_server

pytestmark = pytest.mark.unit
API = "https://api.test/api/v1"


class _Ctx:
    def __init__(self, headers):
        self.headers = headers


def _server(**kw):
    mcp, _ = build_server(Settings(api_url=API, api_key="k", max_retries=0, **kw))
    return mcp


async def _call(mcp, name, args=None):
    async with Client(mcp) as client:
        return await client.call_tool(name, args or {})


def _text(res) -> str:
    return "".join(getattr(c, "text", "") for c in res.content)


# ── workspace selection ─────────────────────────────────────────────────

def test_config_reads_tenant_id(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("NEURALEADS_TENANT_ID", "7")
    assert Settings.from_env().tenant_id == 7


@pytest.mark.parametrize("value", ["abc", "0", "-3", "1.5"])
def test_config_rejects_bad_tenant_id(monkeypatch, value):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("NEURALEADS_TENANT_ID", value)
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_tenant_resolution_rules():
    stdio = Runtime(Settings(api_key="k", tenant_id=5), hosted=False)
    assert stdio.tenant_for(_Ctx({})) == 5
    assert stdio.tenant_for(_Ctx({"X-Tenant-ID": "9"})) == 9  # request header wins
    hosted = Runtime(Settings(api_key="k", tenant_id=5), hosted=True)
    assert hosted.tenant_for(_Ctx({})) is None  # never the server's own setting
    assert hosted.tenant_for(_Ctx({"x-tenant-id": "12"})) == 12
    with pytest.raises(ToolError, match="X-Tenant-ID"):
        hosted.tenant_for(_Ctx({"X-Tenant-ID": "twelve"}))
    assert Runtime(Settings(api_key="k")).tenant_for(_Ctx({})) is None


@respx.mock
async def test_env_tenant_forwarded_upstream():
    route = respx.get(f"{API}/leads").mock(return_value=httpx.Response(200, json={"items": []}))
    await _call(_server(tenant_id=5), "search_leads")
    assert route.calls.last.request.headers["X-Tenant-ID"] == "5"


@respx.mock
async def test_no_tenant_header_by_default():
    route = respx.get(f"{API}/leads").mock(return_value=httpx.Response(200, json={"items": []}))
    await _call(_server(), "search_leads")
    assert "X-Tenant-ID" not in route.calls.last.request.headers


@respx.mock
async def test_request_header_forwarded_in_hosted_mode():
    route = respx.get(f"{API}/auth/me").mock(return_value=httpx.Response(200, json={"tenant_id": 1}))
    rt = Runtime(Settings(api_url=API, api_key="server-key", tenant_id=99, max_retries=0), hosted=True)
    await rt.get(_Ctx({"Authorization": "Bearer user-key", "X-Tenant-ID": "12"}), "/auth/me")
    req = route.calls.last.request
    assert req.headers["X-Tenant-ID"] == "12" and req.headers["X-API-Key"] == "user-key"
    await rt.get(_Ctx({"Authorization": "Bearer user-key"}), "/auth/me")
    assert "X-Tenant-ID" not in route.calls.last.request.headers  # server default never used
    await rt.client.aclose()


@respx.mock
async def test_whoami_reports_effective_workspace():
    respx.get(f"{API}/auth/me").mock(return_value=httpx.Response(200, json={
        "user_id": 1, "role": "super_admin", "tenant_id": 1}))
    out = result_json(await _call(_server(tenant_id=4), "whoami"))
    assert out["effective_workspace_id"] == 4 and out["workspace_selected_by"] == "X-Tenant-ID"
    out = result_json(await _call(_server(), "whoami"))
    assert out["effective_workspace_id"] is None and "list_workspaces" in out["workspace_note"]


@respx.mock
async def test_whoami_regular_user_ignores_selection():
    respx.get(f"{API}/auth/me").mock(return_value=httpx.Response(200, json={"role": "admin", "tenant_id": 3}))
    out = result_json(await _call(_server(tenant_id=4), "whoami"))
    assert out["effective_workspace_id"] == 3 and "ignored" in out["workspace_note"]


@respx.mock
async def test_list_workspaces_friendly_error():
    respx.get(f"{API}/admin/tenants").mock(return_value=httpx.Response(403, json={"detail": "nope"}))
    res = await _call(_server(), "list_workspaces")
    assert res.is_error and "super-admin" in _text(res)


@respx.mock
async def test_list_workspaces_trims():
    respx.get(f"{API}/admin/tenants").mock(return_value=httpx.Response(200, json=[
        {"tenant_id": 2, "name": "B", "plan": "pro", "contact_email": "x@y.z", "lead_count": 3}]))
    out = result_json(await _call(_server(), "list_workspaces"))
    assert out == {"items": [{"tenant_id": 2, "name": "B", "plan": "pro", "lead_count": 3}], "count": 1}


# ── schema-level safety ─────────────────────────────────────────────────

def _property_names(schema) -> set:
    """Every property name in a JSON schema, including nested models ($defs)."""
    names: set = set()
    if isinstance(schema, dict):
        for name, sub in (schema.get("properties") or {}).items():
            names.add(name.lower())
            names |= _property_names(sub)
        for key, value in schema.items():
            if key != "properties":
                names |= _property_names(value)
    elif isinstance(schema, list):
        for value in schema:
            names |= _property_names(value)
    return names


async def test_no_password_or_secret_parameter_anywhere():
    for ro in (False, True):
        mcp, _ = build_server(Settings(api_key="k", read_only=ro))
        for tool in await mcp.list_tools():
            bad = {n for n in _property_names(tool.input_schema)
                   if any(w in n for w in ("password", "secret", "token", "credential"))}
            assert not bad, (tool.name, bad)


async def test_destructive_and_sending_tools_take_confirm():
    mcp, _ = build_server(Settings(api_key="k"))
    for tool in await mcp.list_tools():
        if tool.annotations.destructive_hint:
            assert "confirm" in tool.input_schema.get("properties", {}), tool.name


async def test_read_only_mode_hides_new_write_tools_but_keeps_suggestions():
    mcp, _ = build_server(Settings(api_key="k", read_only=True))
    names = {t.name for t in await mcp.list_tools()}
    assert {"suggest_reply", "suggest_subject_lines", "list_workspaces", "list_email_drafts",
            "run_saved_search", "export_summary", "preview_lead_outreach", "mailbox_oauth_link"} <= names
    assert not names & {"create_mailbox", "send_lead_outreach", "delete_contact", "create_email_template",
                        "generate_email_sequence", "send_email_drafts", "import_google_sheet",
                        "assess_all_warmup", "check_replies"}
    for tool in await mcp.list_tools():
        assert tool.annotations.read_only_hint, tool.name


# ── confirmation gates make no write call ───────────────────────────────

def _fake_api(request: httpx.Request) -> httpx.Response:
    """Answers every GET with a payload that satisfies the tools' pre-checks."""
    path = request.url.path.removeprefix("/api/v1")
    if request.method != "GET":
        if path in ("/leads/bulk/outreach/preview", "/leads/import/google-sheet/preview"):
            return httpx.Response(200, json={"assignments": [], "available_mailboxes": [], "total_rows": 2,
                                             "new_count": 2, "duplicate_count": 0, "preview": []})
        return httpx.Response(200, json={"ok": True})
    if path == "/saved-searches":
        return httpx.Response(200, json=[{"search_id": 3, "name": "S", "filters_json": "{}"}])
    if path == "/email-preview/drafts":
        return httpx.Response(200, json={"drafts": [], "total": 0})
    if path.startswith("/email-preview/drafts/"):
        return httpx.Response(200, json={"draft_id": 1, "status": "approved", "subject": "Hi"})
    if path.endswith("/detail"):
        return httpx.Response(200, json={"mailbox": {"mailbox_id": 1, "email": "a@b.c"}, "campaigns": []})
    return httpx.Response(200, json={"items": [{"mailbox_id": 1}], "total": 1, "actions": [],
                                     "mailbox_id": 1, "email": "a@b.c", "client_name": "Acme",
                                     "template_id": 1, "name": "T", "status": "draft"})


GATED = [
    ("send_email_drafts", {"draft_ids": [1, 2]}),
    ("send_email_drafts", {"batch_id": "b1"}),
    ("delete_email_drafts", {"draft_ids": [1]}),
    ("archive_email_template", {"template_id": 1}),
    ("delete_objection_response", {"template_id": 1}),
    ("delete_reply_macro", {"macro_id": 1}),
    ("generate_email_sequence", {"goal": "meetings", "product": "staffing"}),
    ("delete_lead", {"lead_id": 1}),
    ("delete_contact", {"contact_id": 1}),
    ("delete_company", {"company_id": 1}),
    ("merge_contacts", {"primary_contact_id": 1, "merge_contact_ids": [2, 3]}),
    ("delete_saved_search", {"search_id": 3}),
    ("remove_company_exclusion", {"exclusion_id": 4}),
    ("import_google_sheet", {"sheet_url": "https://docs.google.com/spreadsheets/d/x"}),
    ("archive_mailbox", {"mailbox_id": 1}),
    ("restore_mailbox", {"mailbox_id": 1}),
    ("send_lead_outreach", {"lead_ids": [1, 2]}),
    ("start_warmup_recovery", {"mailbox_id": 1}),
    ("assess_all_warmup", {}),
]
_READ_ONLY_POSTS = {"/api/v1/leads/bulk/outreach/preview", "/api/v1/leads/import/google-sheet/preview"}


@pytest.mark.parametrize("tool,args", GATED, ids=[f"{t}-{i}" for i, (t, _) in enumerate(GATED)])
async def test_confirm_gate_makes_no_write_call(tool, args):
    with respx.mock(base_url=API, assert_all_called=False) as router:
        router.route().mock(side_effect=_fake_api)
        res = await _call(_server(), tool, args)
        assert not res.is_error, _text(res)
        assert result_json(res)["status"] == "confirmation_required"
        writes = [c.request for c in router.calls
                  if c.request.method != "GET" and c.request.url.path not in _READ_ONLY_POSTS]
        assert writes == [], [f"{r.method} {r.url.path}" for r in writes]


@respx.mock
async def test_confirmed_delete_calls_backend_and_maps_403():
    respx.get(f"{API}/contacts/5").mock(return_value=httpx.Response(200, json={"contact_id": 5}))
    respx.delete(f"{API}/contacts/5").mock(return_value=httpx.Response(
        403, json={"detail": "This API key has 'write' scope, which cannot delete data."}))
    res = await _call(_server(), "delete_contact", {"contact_id": 5, "confirm": True})
    assert res.is_error and "'admin' scope" in _text(res)


@respx.mock
async def test_send_lead_outreach_confirmed_sends_for_real():
    send = respx.post(f"{API}/leads/bulk/outreach").mock(return_value=httpx.Response(200, json={"summary": {}}))
    await _call(_server(), "send_lead_outreach", {"lead_ids": [1, 1, 2], "confirm": True})
    assert json.loads(send.calls.last.request.content) == {"lead_ids": [1, 2], "dry_run": False}


async def test_send_lead_outreach_caps_batch():
    res = await _call(_server(), "send_lead_outreach", {"lead_ids": list(range(1, 102)), "confirm": True})
    assert result_json(res)["status"] == "rejected"


# ── behaviour ───────────────────────────────────────────────────────────

@respx.mock
async def test_list_pipeline_runs_returns_one_object():
    respx.get(f"{API}/pipelines/runs").mock(return_value=httpx.Response(200, json=[
        {"run_id": 1, "status": "completed", "noise": 1}, {"run_id": 2, "status": "running"}]))
    res = await _call(_server(), "list_pipeline_runs")
    assert len(res.content) == 1
    assert result_json(res) == {"items": [{"run_id": 1, "status": "completed"},
                                          {"run_id": 2, "status": "running"}], "count": 2}


@respx.mock
async def test_outreach_stats_keys_normalised():
    respx.get(f"{API}/outreach/stats/summary").mock(return_value=httpx.Response(200, json={
        "total_events": 5, "by_status": {"OutreachStatus.SENT": 3, "OutreachStatus.BOUNCED": 1, "replied": 1}}))
    out = result_json(await _call(_server(), "get_outreach_stats"))
    assert out["by_status"] == {"sent": 3, "bounced": 1, "replied": 1}


@respx.mock
async def test_outreach_preview_hides_other_workspaces_mailboxes():
    respx.get(f"{API}/mailboxes").mock(return_value=httpx.Response(200, json={"items": [{"mailbox_id": 1}]}))
    respx.post(f"{API}/leads/bulk/outreach/preview").mock(return_value=httpx.Response(200, json={
        "total_leads": 1,
        "available_mailboxes": [{"mailbox_id": 1, "email": "mine@a.com"}, {"mailbox_id": 9, "email": "other@b.com"}],
        "assignments": [{"lead_id": 4, "eligible_count": 1, "sender": {"mailbox_id": 9, "email": "other@b.com"},
                         "contacts": [{"contact_id": 2, "email": "c@d.com", "eligible": True}]}]}))
    out = result_json(await _call(_server(), "preview_lead_outreach", {"lead_ids": [4]}))
    assert [m["mailbox_id"] for m in out["available_mailboxes"]] == [1]
    assert out["assignments"][0]["sender"] is None and "other@b.com" not in json.dumps(out)


@respx.mock
async def test_update_contact_email_change_clears_validation():
    respx.get(f"{API}/contacts/3").mock(return_value=httpx.Response(200, json={"email": "old@a.com"}))
    put = respx.put(f"{API}/contacts/3").mock(return_value=httpx.Response(200, json={"contact_id": 3}))
    await _call(_server(), "update_contact", {"contact_id": 3, "email": "new@a.com"})
    assert json.loads(put.calls.last.request.content) == {"email": "new@a.com", "validation_status": None}
    await _call(_server(), "update_contact", {"contact_id": 3, "title": "VP"})
    assert json.loads(put.calls.last.request.content) == {"title": "VP"}


@respx.mock
async def test_create_contact_rejects_foreign_lead_ids():
    respx.get(f"{API}/leads/1").mock(return_value=httpx.Response(200, json={"lead_id": 1}))
    respx.get(f"{API}/leads/2").mock(return_value=httpx.Response(404, json={"detail": "Lead not found"}))
    post = respx.post(f"{API}/contacts").mock(return_value=httpx.Response(201, json={}))
    res = await _call(_server(), "create_contact", {"client_name": "Acme", "first_name": "A", "last_name": "B",
                                                    "email": "a@acme.com", "lead_ids": [1, 2]})
    assert res.is_error and "[2]" in _text(res) and post.call_count == 0


@respx.mock
async def test_run_saved_search_uses_tenant_scoped_lead_list():
    respx.get(f"{API}/saved-searches").mock(return_value=httpx.Response(200, json=[
        {"search_id": 3, "name": "TX nurses", "filters_json": json.dumps(
            {"state": "tx", "job_title": "Nurse", "salary_min": 60000, "city": "Austin"})}]))
    leads = respx.get(f"{API}/leads").mock(return_value=httpx.Response(200, json={
        "items": [{"lead_id": 8, "client_name": "H"}], "total": 1, "page": 1}))
    out = result_json(await _call(_server(), "run_saved_search", {"search_id": 3}))
    params = leads.calls.last.request.url.params
    assert params["state"] == "TX" and params["job_title"] == "Nurse"
    assert params["salary_op"] == "gte" and params["salary_value"] == "60000"
    assert out["total"] == 1 and out["ignored_filters"] == ["city"]


@respx.mock
async def test_broadcast_drafts_check_ownership_first():
    respx.get(f"{API}/templates/1").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{API}/mailboxes/2").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{API}/contacts/5").mock(return_value=httpx.Response(404, json={"detail": "Contact not found"}))
    gen = respx.post(f"{API}/email-preview/generate").mock(return_value=httpx.Response(200, json={}))
    res = await _call(_server(), "generate_email_drafts", {"source": "broadcast", "template_id": 1,
                                                           "mailbox_id": 2, "contact_ids": [5]})
    assert res.is_error and gen.call_count == 0


@respx.mock
async def test_create_mailbox_sends_no_credentials_and_starts_inactive():
    post = respx.post(f"{API}/mailboxes").mock(return_value=httpx.Response(200, json={
        "mailbox_id": 7, "email": "s@a.com", "is_active": False}))
    out = result_json(await _call(_server(), "create_mailbox", {"email": "s@a.com", "provider": "gmail"}))
    body = json.loads(post.calls.last.request.content)
    assert body["is_active"] is False and body["warmup_status"] == "inactive"
    assert not {k for k in body if "pass" in k or "token" in k or "secret" in k}
    assert "https://api.test/dashboard/mailboxes" in out["next_step"]


async def test_mailbox_oauth_link_points_at_web_app():
    out = result_json(await _call(_server(), "mailbox_oauth_link"))
    assert out["url"] == "https://api.test/dashboard/mailboxes"


@respx.mock
async def test_create_saved_search_serialises_filters():
    post = respx.post(f"{API}/saved-searches").mock(return_value=httpx.Response(200, json={
        "search_id": 1, "name": "N", "filters_json": '{"state": "TX"}'}))
    out = result_json(await _call(_server(), "create_saved_search", {"name": "N", "filters": {"state": "TX"}}))
    assert json.loads(json.loads(post.calls.last.request.content)["filters_json"]) == {"state": "TX"}
    assert out["filters"] == {"state": "TX"}


@respx.mock
async def test_add_exclusions_single_vs_bulk():
    one = respx.post(f"{API}/company-exclusions").mock(return_value=httpx.Response(201, json={"exclusion_id": 1}))
    bulk = respx.post(f"{API}/company-exclusions/bulk").mock(return_value=httpx.Response(201, json={"created": 2}))
    await _call(_server(), "add_company_exclusions", {"company_names": ["Acme"]})
    await _call(_server(), "add_company_exclusions", {"company_names": ["Acme", "Beta", "Acme"]})
    assert one.call_count == 1 and bulk.call_count == 1
    assert len(json.loads(bulk.calls.last.request.content)["companies"]) == 2


@respx.mock
async def test_email_draft_list_omits_bodies():
    respx.get(f"{API}/email-preview/drafts").mock(return_value=httpx.Response(200, json={
        "total": 1, "pending_count": 1, "drafts": [{"draft_id": 1, "subject": "Hi", "body_html": "<p>x</p>",
                                                    "contact": {"email": "c@d.com", "first_name": "C"},
                                                    "mailbox": {"email": "m@a.com"}}]}))
    out = result_json(await _call(_server(), "list_email_drafts"))
    assert out["items"] == [{"draft_id": 1, "subject": "Hi",
                             "to": {"email": "c@d.com", "name": "C", "company": None}, "from": "m@a.com"}]


@respx.mock
async def test_single_draft_send_uses_sync_endpoint():
    one = respx.post(f"{API}/email-preview/drafts/4/send").mock(return_value=httpx.Response(200, json={"ok": 1}))
    await _call(_server(), "send_email_drafts", {"draft_ids": [4], "confirm": True})
    assert one.call_count == 1
