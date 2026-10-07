"""End-to-end: MCP client → NeuraLeads MCP server → real NeuraLeads API (SQLite).

Covers each area's main read path, the confirmation gate, key scopes, and
cross-workspace isolation.
"""
from __future__ import annotations

import json

import pytest
from conftest import result_json
from mcp import Client

from neuraleads_mcp.config import Settings
from neuraleads_mcp.server import build_server

pytestmark = pytest.mark.integration


def _server(backend, key, read_only=False):
    mcp, _ = build_server(Settings(api_url=backend["api_url"], api_key=key, read_only=read_only, max_retries=0))
    return mcp


async def call(mcp, name, **args):
    async with Client(mcp) as client:
        res = await client.call_tool(name, args)
    text = "".join(getattr(c, "text", "") for c in res.content)
    if res.is_error:
        return {"__error__": text}
    return result_json(res)


# ── reads, one per area ─────────────────────────────────────────────────

async def test_whoami_reports_workspace(backend):
    out = await call(_server(backend, backend["A"]["keys"]["read"]), "whoami")
    assert out["tenant_id"] == backend["A"]["tenant_id"]
    assert out["role"] == "admin"


async def test_lead_search_and_detail(backend):
    a = backend["A"]
    mcp = _server(backend, a["keys"]["read"])
    found = await call(mcp, "search_leads", search="Plant Manager")
    assert [l["lead_id"] for l in found["items"]] == [a["lead_id"]]
    detail = await call(mcp, "get_lead", lead_id=a["lead_id"])
    assert {c["contact_id"] for c in detail["contacts"]} == set(a["contact_ids"])


async def test_contacts_filter_by_validation(backend):
    a = backend["A"]
    out = await call(_server(backend, a["keys"]["read"]), "search_contacts", validation_status="valid")
    assert {c["contact_id"] for c in out["items"]} == set(a["contact_ids"][:2])


async def test_mailboxes_strip_secrets(backend):
    a = backend["A"]
    mcp = _server(backend, a["keys"]["read"])
    out = await call(mcp, "list_mailboxes")
    assert [m["mailbox_id"] for m in out["items"]] == [a["mailbox_id"]]
    assert "password" not in json.dumps(out).lower()
    one = await call(mcp, "get_mailbox", mailbox_id=a["mailbox_id"])
    assert one["mailbox"]["email"].startswith("sender-a@")


async def test_reports_and_dashboard(backend):
    mcp = _server(backend, backend["A"]["keys"]["read"])
    assert "series" in await call(mcp, "report_daily_activity", days=7)
    assert "total_leads" in await call(mcp, "get_dashboard_kpis")


# ── isolation ───────────────────────────────────────────────────────────

async def test_cannot_see_other_workspace(backend):
    a, b = backend["A"], backend["B"]
    mcp = _server(backend, a["keys"]["admin"])
    assert "__error__" in await call(mcp, "get_lead", lead_id=b["lead_id"])
    assert "__error__" in await call(mcp, "get_mailbox", mailbox_id=b["mailbox_id"])
    # warmup routes lack tenant checks server-side; the connector must refuse first
    assert "__error__" in await call(mcp, "get_mailbox_warmup_history", mailbox_id=b["mailbox_id"])
    assert "__error__" in await call(mcp, "get_mailbox_dns_status", mailbox_id=b["mailbox_id"])
    leads = await call(mcp, "search_leads")
    assert b["lead_id"] not in {l["lead_id"] for l in leads["items"]}


async def test_enroll_rejects_other_workspace_contacts(backend):
    a, b = backend["A"], backend["B"]
    mcp = _server(backend, a["keys"]["write"])
    camp = await call(mcp, "create_campaign_from_leads", lead_ids=[a["lead_id"]])
    out = await call(mcp, "enroll_contacts", campaign_id=camp["campaign_id"], contact_ids=[b["contact_ids"][0]])
    assert "__error__" in out and "not found in this workspace" in out["__error__"]


# ── scopes and confirmation ─────────────────────────────────────────────

async def test_read_key_cannot_write(backend):
    a = backend["A"]
    out = await call(_server(backend, a["keys"]["read"]), "create_campaign_from_leads", lead_ids=[a["lead_id"]])
    assert "__error__" in out and "read-only" in out["__error__"]


async def test_read_only_server_hides_write_tools(backend):
    async with Client(_server(backend, backend["A"]["keys"]["admin"], read_only=True)) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert "search_leads" in names
    assert not names & {"activate_campaign", "run_lead_sourcing", "send_inbox_reply", "enroll_contacts"}


async def test_campaign_flow_with_confirmation_gate(backend):
    a = backend["A"]
    mcp = _server(backend, a["keys"]["write"])
    camp = await call(mcp, "create_campaign_from_leads", lead_ids=[a["lead_id"]])
    cid = camp["campaign_id"]
    assert camp["status"] == "draft"
    assert camp["mailbox_ids"] == [a["mailbox_id"]]

    gated = await call(mcp, "activate_campaign", campaign_id=cid)
    assert gated["status"] == "confirmation_required"
    assert (await call(mcp, "get_campaign", campaign_id=cid))["status"] == "draft"  # nothing changed

    done = await call(mcp, "activate_campaign", campaign_id=cid, confirm=True)
    assert done["status"] == "active"
    paused = await call(mcp, "pause_campaign", campaign_id=cid)
    assert paused["status"] == "paused"


async def test_paid_actions_are_gated(backend):
    a = backend["A"]
    mcp = _server(backend, a["keys"]["write"])
    out = await call(mcp, "validate_contact_emails", contact_ids=a["contact_ids"])
    assert out["status"] == "confirmation_required"
    out = await call(mcp, "run_lead_sourcing")
    assert out["status"] == "confirmation_required"


async def test_bad_key_gives_actionable_error(backend):
    out = await call(_server(backend, "exz_not_a_real_key"), "whoami")
    assert "API key" in out["__error__"]


async def test_stdio_entry_point(backend):
    """The installed `neuraleads-mcp` command speaks MCP over stdio."""
    import os
    import sys
    from pathlib import Path

    from mcp import StdioServerParameters

    exe = Path(sys.executable).with_name("neuraleads-mcp.exe" if os.name == "nt" else "neuraleads-mcp")
    params = StdioServerParameters(command=str(exe), args=[], env={
        **os.environ, "NEURALEADS_API_URL": backend["api_url"],
        "NEURALEADS_API_KEY": backend["A"]["keys"]["read"]})
    async with Client(params) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        res = await client.call_tool("whoami", {})
    assert "search_leads" in names
    assert result_json(res)["tenant_id"] == backend["A"]["tenant_id"]
