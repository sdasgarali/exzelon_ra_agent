"""End-to-end for the phase-2 tools against the real NeuraLeads API (SQLite, two workspaces).

Tests that depend on a backend fix being developed in parallel are marked xfail(strict=False);
flip them to plain tests once the fix is merged.
"""
from __future__ import annotations

import json
import uuid

import pytest
from conftest import result_json
from mcp import Client

from neuraleads_mcp.config import Settings
from neuraleads_mcp.server import build_server

pytestmark = pytest.mark.integration


def _server(backend, key, read_only=False, tenant_id=None):
    mcp, _ = build_server(Settings(api_url=backend["api_url"], api_key=key, read_only=read_only,
                                   max_retries=0, tenant_id=tenant_id))
    return mcp


async def call(mcp, tool_name, /, **args):
    async with Client(mcp) as client:
        res = await client.call_tool(tool_name, args)
    text = "".join(getattr(c, "text", "") for c in res.content)
    if res.is_error:
        return {"__error__": text}
    return result_json(res)


def _tag() -> str:
    return uuid.uuid4().hex[:8]


# ── data management ─────────────────────────────────────────────────────

async def test_contact_create_update_delete(backend):
    a = backend["A"]
    tag = _tag()
    admin = _server(backend, a["keys"]["admin"])
    created = await call(admin, "create_contact", client_name="Acme A", first_name="Dana", last_name=f"Q{tag}",
                         email=f"dana.{tag}@acme-e2e.example.com", title="HR Director", lead_ids=[a["lead_id"]])
    assert "__error__" not in created, created
    cid = created["contact_id"]
    assert created["lead_ids"] == [a["lead_id"]]

    updated = await call(admin, "update_contact", contact_id=cid, title="VP People")
    assert updated["title"] == "VP People"

    gated = await call(admin, "delete_contact", contact_id=cid)
    assert gated["status"] == "confirmation_required"
    assert (await call(admin, "get_contact", contact_id=cid))["contact_id"] == cid  # still there

    # a write key cannot delete, whatever confirm says
    denied = await call(_server(backend, a["keys"]["write"]), "delete_contact", contact_id=cid, confirm=True)
    assert "__error__" in denied and "'admin' scope" in denied["__error__"]

    done = await call(admin, "delete_contact", contact_id=cid, confirm=True)
    assert done == {"status": "archived", "contact_id": cid}
    found = await call(admin, "search_contacts", search=f"Q{tag}")
    assert found["items"] == []


async def test_contact_email_change_resets_validation(backend):
    a = backend["A"]
    mcp = _server(backend, a["keys"]["write"])
    cid = a["contact_ids"][1]
    assert (await call(mcp, "get_contact", contact_id=cid))["validation_status"] == "valid"
    out = await call(mcp, "update_contact", contact_id=cid, email=f"moved.{_tag()}@acme-e2e.example.com")
    assert out["validation_status"] is None


async def test_create_contact_refuses_other_workspace_lead(backend):
    a, b = backend["A"], backend["B"]
    out = await call(_server(backend, a["keys"]["write"]), "create_contact", client_name="Acme A",
                     first_name="X", last_name="Y", email=f"x.{_tag()}@acme-e2e.example.com",
                     lead_ids=[b["lead_id"]])
    assert "__error__" in out and "not found in this workspace" in out["__error__"]


async def test_lead_and_company_create_update(backend):
    a = backend["A"]
    tag = _tag()
    mcp = _server(backend, a["keys"]["write"])
    lead = await call(mcp, "create_lead", client_name=f"Globex {tag}", job_title="Warehouse Supervisor",
                      state="OH", job_link=f"https://jobs.example.com/{tag}", salary_min=55000)
    assert "__error__" not in lead, lead
    upd = await call(mcp, "update_lead", lead_id=lead["lead_id"], state="PA")
    assert upd["state"] == "PA"
    company = await call(mcp, "create_company", client_name=f"Globex {tag}", industry="Manufacturing")
    assert "__error__" not in company, company
    upd = await call(mcp, "update_company", company_id=company["client_id"], website="https://globex.example.com")
    assert upd["website"] == "https://globex.example.com"


async def test_export_summary_counts(backend):
    a = backend["A"]
    out = await call(_server(backend, a["keys"]["read"]), "export_summary", entity="contacts", company="Acme A")
    assert out["total"] >= 2 and out["sample"] and "dashboard/contacts" in out["full_export"]


async def test_saved_search_create_then_run(backend):
    a = backend["A"]
    mcp = _server(backend, a["keys"]["write"])
    s = await call(mcp, "create_saved_search", name=f"TX plant {_tag()}",
                   filters={"state": "TX", "job_title": "Plant Manager"})
    assert "__error__" not in s, s
    listed = await call(mcp, "list_saved_searches")
    assert s["search_id"] in {x["search_id"] for x in listed["items"]}
    ran = await call(mcp, "run_saved_search", search_id=s["search_id"])
    assert [lead["lead_id"] for lead in ran["items"]] == [a["lead_id"]]

    # Workspace B can't run A's search
    other = await call(_server(backend, backend["B"]["keys"]["read"]), "run_saved_search", search_id=s["search_id"])
    assert "__error__" in other


async def test_company_exclusion_add_and_remove(backend):
    a = backend["A"]
    name = f"Initech {_tag()}"
    write = _server(backend, a["keys"]["write"])
    added = await call(write, "add_company_exclusions", company_names=[name], category="customer")
    assert added["company_name"] == name
    listed = await call(write, "list_company_exclusions", search=name)
    assert [x["exclusion_id"] for x in listed["items"]] == [added["exclusion_id"]]

    paused = await call(write, "update_company_exclusion", exclusion_id=added["exclusion_id"], is_active=False)
    assert paused["is_active"] is False

    admin = _server(backend, a["keys"]["admin"])
    gated = await call(admin, "remove_company_exclusion", exclusion_id=added["exclusion_id"])
    assert gated["status"] == "confirmation_required"
    await call(admin, "remove_company_exclusion", exclusion_id=added["exclusion_id"], confirm=True)
    assert (await call(write, "list_company_exclusions", search=name))["items"] == []


# ── content ─────────────────────────────────────────────────────────────

async def test_template_create_then_preview(backend):
    a = backend["A"]
    mcp = _server(backend, a["keys"]["write"])
    t = await call(mcp, "create_email_template", name=f"E2E {_tag()}",
                   subject="Quick question about {{job_title}}",
                   body_html="<p>Hi {{contact_first_name}}, is {{company_name}} still hiring?</p>")
    assert "__error__" not in t, t
    assert t["status"] == "inactive"
    preview = await call(mcp, "preview_email_template", template_id=t["template_id"])
    assert preview["subject"] == "Quick question about Senior Software Engineer"
    assert "Hi John" in preview["body_html"]
    upd = await call(mcp, "update_email_template", template_id=t["template_id"], description="from e2e")
    assert upd["description"] == "from e2e"
    # other workspace can't see it
    other = await call(_server(backend, backend["B"]["keys"]["write"]), "get_email_template",
                       template_id=t["template_id"])
    assert "__error__" in other


async def test_objections_and_macros(backend):
    mcp = _server(backend, backend["A"]["keys"]["write"])
    obj = await call(mcp, "create_objection_response", objection_type="budget",
                     objection_text="No budget this quarter", response_text="Understood — we only bill on hire.")
    used = await call(mcp, "use_objection_response", template_id=obj["template_id"])
    assert used["times_used"] == 1
    macro = await call(mcp, "create_reply_macro", title=f"Calendar {_tag()}", body_text="Here is my calendar link.")
    assert (await call(mcp, "use_reply_macro", macro_id=macro["macro_id"]))["usage_count"] == 1
    listed = await call(mcp, "list_reply_macros", search="calendar link")
    assert macro["macro_id"] in {m["macro_id"] for m in listed["items"]}


async def test_spam_check_and_draft_queue(backend):
    mcp = _server(backend, backend["A"]["keys"]["read"])
    spam = await call(mcp, "check_spam_with_suggestions", subject="FREE money!!! Act now",
                      body_html="<p>Click here for a guaranteed risk-free offer</p>")
    assert spam["score"] >= 0 and "suggestions" in spam
    drafts = await call(mcp, "list_email_drafts")
    assert drafts["items"] == [] and drafts["total"] == 0


# ── outreach ────────────────────────────────────────────────────────────

async def test_outreach_log_stats_and_preview(backend):
    a = backend["A"]
    mcp = _server(backend, a["keys"]["read"])
    assert (await call(mcp, "list_outreach_events")) == {"items": [], "count": 0}
    stats = await call(mcp, "get_outreach_stats")
    assert stats["total_events"] == 0 and stats["by_status"] == {}
    preview = await call(mcp, "preview_lead_outreach", lead_ids=[a["lead_id"]])
    assert preview["assignments"][0]["lead_id"] == a["lead_id"]
    assert {m["mailbox_id"] for m in preview["available_mailboxes"]} <= {a["mailbox_id"]}


async def test_send_lead_outreach_is_gated(backend):
    a = backend["A"]
    out = await call(_server(backend, a["keys"]["write"]), "send_lead_outreach", lead_ids=[a["lead_id"]])
    assert out["status"] == "confirmation_required" and "assignments" in out["preview"]
    assert (await call(_server(backend, a["keys"]["read"]), "get_outreach_stats"))["total_events"] == 0


async def test_check_replies_runs(backend):
    out = await call(_server(backend, backend["A"]["keys"]["write"]), "check_replies")
    assert "__error__" not in out, out


async def test_warmup_recovery_refuses_other_workspace(backend):
    out = await call(_server(backend, backend["A"]["keys"]["admin"]), "start_warmup_recovery",
                     mailbox_id=backend["B"]["mailbox_id"], confirm=True)
    assert "__error__" in out


async def test_warmup_recovery_then_mailbox_still_readable(backend):
    b = backend["B"]  # workspace B's mailbox: other tests rely on A's being cold_ready
    # Recovery needs the warmup/settings "full" permission, which only super admins have by default.
    mcp = _server(backend, backend["super"]["key"], tenant_id=b["tenant_id"])
    gated = await call(mcp, "start_warmup_recovery", mailbox_id=b["mailbox_id"])
    assert gated["status"] == "confirmation_required"
    started = await call(mcp, "start_warmup_recovery", mailbox_id=b["mailbox_id"], confirm=True)
    assert "__error__" not in started, started
    listed = await call(mcp, "list_mailboxes")
    assert "__error__" not in listed, listed


async def test_list_pipeline_runs_is_one_object(backend):
    out = await call(_server(backend, backend["A"]["keys"]["read"]), "list_pipeline_runs")
    assert set(out) == {"items", "count"}


# ── mailbox setup ───────────────────────────────────────────────────────

async def test_create_mailbox_without_credentials_then_archive(backend):
    a = backend["A"]
    email = f"new-{_tag()}@mcp-e2e.example.com"
    write = _server(backend, a["keys"]["write"])
    mb = await call(write, "create_mailbox", email=email, provider="microsoft_365", display_name="New Sender")
    assert "__error__" not in mb, mb
    assert mb["is_active"] is False and "dashboard/mailboxes" in mb["next_step"]
    assert "password" not in json.dumps(mb).lower().replace("password)", "")

    admin = _server(backend, a["keys"]["admin"])
    gated = await call(admin, "archive_mailbox", mailbox_id=mb["mailbox_id"])
    assert gated["status"] == "confirmation_required" and gated["details"]["mailbox"] == email
    await call(admin, "archive_mailbox", mailbox_id=mb["mailbox_id"], confirm=True)
    archived = await call(write, "list_mailboxes", archived=True)
    assert mb["mailbox_id"] in {m["mailbox_id"] for m in archived["items"]}


async def test_mailbox_oauth_link_checks_workspace(backend):
    a, b = backend["A"], backend["B"]
    mcp = _server(backend, a["keys"]["read"])
    ok = await call(mcp, "mailbox_oauth_link", mailbox_id=a["mailbox_id"])
    assert ok["url"].endswith("/dashboard/mailboxes") and ok["mailbox"]["mailbox_id"] == a["mailbox_id"]
    assert "__error__" in await call(mcp, "mailbox_oauth_link", mailbox_id=b["mailbox_id"])


# ── read-scope allowlist (backend fix in progress) ──────────────────────

async def test_read_key_can_suggest_subject_lines(backend):
    a = backend["A"]
    camp = await call(_server(backend, a["keys"]["write"]), "create_campaign_from_leads", lead_ids=[a["lead_id"]])
    out = await call(_server(backend, a["keys"]["read"], read_only=True), "suggest_subject_lines",
                     campaign_id=camp["campaign_id"])
    assert "__error__" not in out and "read-only" not in json.dumps(out)


async def test_read_key_can_preview_template(backend):
    a = backend["A"]
    t = await call(_server(backend, a["keys"]["write"]), "create_email_template", name=f"RO {_tag()}",
                   subject="Hi", body_html="<p>Hi {{contact_first_name}}</p>")
    out = await call(_server(backend, a["keys"]["read"]), "preview_email_template", template_id=t["template_id"])
    assert "__error__" not in out, out


# ── workspace selection for super-admin keys ────────────────────────────

async def test_list_workspaces_super_admin_only(backend):
    out = await call(_server(backend, backend["super"]["key"]), "list_workspaces")
    ids = {w["tenant_id"] for w in out["items"]}
    assert {backend["A"]["tenant_id"], backend["B"]["tenant_id"]} <= ids
    denied = await call(_server(backend, backend["A"]["keys"]["admin"]), "list_workspaces")
    assert "__error__" in denied and "super-admin" in denied["__error__"]


async def test_super_admin_key_acts_in_selected_workspace(backend):
    a, b = backend["A"], backend["B"]
    mcp = _server(backend, backend["super"]["key"], tenant_id=b["tenant_id"])
    me = await call(mcp, "whoami")
    assert me["effective_workspace_id"] == b["tenant_id"]
    leads = await call(mcp, "search_leads")
    ids = {lead["lead_id"] for lead in leads["items"]}
    assert b["lead_id"] in ids and a["lead_id"] not in ids
    company = await call(mcp, "create_company", client_name=f"Selected {_tag()}")
    assert "__error__" not in company, company
    in_b = await call(_server(backend, b["keys"]["read"]), "get_company", company_id=company["client_id"])
    assert in_b["client_id"] == company["client_id"]


async def test_regular_key_cannot_switch_workspace(backend):
    a, b = backend["A"], backend["B"]
    mcp = _server(backend, a["keys"]["admin"], tenant_id=b["tenant_id"])
    leads = await call(mcp, "search_leads")
    assert b["lead_id"] not in {lead["lead_id"] for lead in leads["items"]}
    me = await call(mcp, "whoami")
    assert me["effective_workspace_id"] == a["tenant_id"]
