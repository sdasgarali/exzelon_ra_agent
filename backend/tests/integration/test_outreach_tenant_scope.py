"""Tenant isolation on the outreach send paths (MCP phase 2, agent B2).

Regressions covered:
- POST /outreach/send-emails and /outreach/run-mailmerge started their background
  pipelines without the caller's tenant, so the pipeline fell back to tenant 1 and
  read every tenant's contacts and mailboxes.
- run_outreach_send_pipeline / run_outreach_for_lead picked the least-loaded mailbox
  across ALL tenants and loaded contacts without a tenant filter.
- POST /leads/bulk/outreach had no role check and did not pass the tenant;
  /leads/bulk/outreach/preview listed every tenant's mailboxes.
- POST /outreach/check-replies checked every tenant's mailboxes.

No real email is sent: send_outreach_email and the IMAP checker are mocked.
"""
import pytest

from app.db.models.contact import ContactDetails
from app.db.models.email_template import EmailTemplate, TemplateStatus
from app.db.models.job_run import JobRun
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.outreach import OutreachEvent
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.tenant import Tenant, TenantPlan
from app.services.pipelines import outreach as outreach_pipeline
from app.services.send_gate import SendGateResult

pytestmark = pytest.mark.integration

API = "/api/v1"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _tenant(db, slug):
    t = Tenant(name=slug, slug=slug, plan=TenantPlan.ENTERPRISE, max_users=99,
               max_mailboxes=99, max_contacts=9999, max_campaigns=99, max_leads=9999)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _mailbox(db, tenant_id, email, sent_today=0):
    m = SenderMailbox(
        tenant_id=tenant_id, email=email, display_name=email.split("@")[0],
        password="x", warmup_status=WarmupStatus.COLD_READY, is_active=True,
        connection_status="successful", daily_send_limit=30,
        emails_sent_today=sent_today, total_emails_sent=0,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _contact(db, tenant_id, email, lead_id=None):
    c = ContactDetails(tenant_id=tenant_id, client_name="Acme", first_name="Pat",
                       last_name="Lee", email=email, validation_status="valid",
                       lead_id=lead_id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _lead(db, tenant_id, name="Acme"):
    lead = LeadDetails(tenant_id=tenant_id, client_name=name, job_title="Nurse",
                       state="TX", lead_status=LeadStatus.NEW)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def _active_template(db, tenant_id, name):
    t = EmailTemplate(tenant_id=tenant_id, name=name, subject=f"{name} subject",
                      body_html=f"<p>{name} {{{{contact_first_name}}}}</p>",
                      body_text=f"{name}", status=TemplateStatus.ACTIVE,
                      category="outreach", is_default=False)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture
def other_tenant(db_session):
    return _tenant(db_session, "tenant-b")


@pytest.fixture
def pipeline_env(db_session, monkeypatch):
    """Point the pipeline at the test session, allow the gate, and capture sends."""
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(outreach_pipeline, "SessionLocal", lambda: db_session)

    gate_calls = []

    def fake_gate(db, contact, tenant_id, **kw):
        gate_calls.append({"contact_id": contact.contact_id, "tenant_id": tenant_id})
        return SendGateResult(allowed=True)

    monkeypatch.setattr("app.services.send_gate.unified_send_gate", fake_gate)

    sends = []

    def fake_send(sender_mailbox, to_email, **kw):
        sends.append({"mailbox_id": sender_mailbox.mailbox_id, "to": to_email})
        return {"success": True, "message_id": f"<m{len(sends)}@x>", "error": None}

    monkeypatch.setattr(outreach_pipeline, "send_outreach_email", fake_send)
    # No AI drafting in tests.
    monkeypatch.setattr(outreach_pipeline, "draft_outreach_email", lambda *a, **k: None)
    return {"gate_calls": gate_calls, "sends": sends}


# ---------------------------------------------------------------------------
# Endpoints pass the caller's tenant to the background pipelines
# ---------------------------------------------------------------------------

def test_send_emails_passes_tenant(client, auth_headers, test_tenant, monkeypatch):
    captured = {}
    monkeypatch.setattr(outreach_pipeline, "run_outreach_send_pipeline",
                        lambda **kw: captured.update(kw))
    r = client.post(f"{API}/outreach/send-emails?dry_run=true&limit=5", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert captured.get("tenant_id") == test_tenant.tenant_id
    assert captured.get("dry_run") is True


def test_run_mailmerge_passes_tenant(client, auth_headers, test_tenant, monkeypatch):
    captured = {}
    monkeypatch.setattr(outreach_pipeline, "run_outreach_mailmerge_pipeline",
                        lambda **kw: captured.update(kw))
    r = client.post(f"{API}/outreach/run-mailmerge", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert captured.get("tenant_id") == test_tenant.tenant_id


def test_send_emails_super_admin_impersonating_passes_that_tenant(
    client, sa_headers, other_tenant, monkeypatch,
):
    captured = {}
    monkeypatch.setattr(outreach_pipeline, "run_outreach_send_pipeline",
                        lambda **kw: captured.update(kw))
    headers = {**sa_headers, "X-Tenant-ID": str(other_tenant.tenant_id)}
    r = client.post(f"{API}/outreach/send-emails", headers=headers)
    assert r.status_code == 200, r.text
    assert captured.get("tenant_id") == other_tenant.tenant_id


# ---------------------------------------------------------------------------
# run_outreach_send_pipeline is scoped to its tenant
# ---------------------------------------------------------------------------

def test_send_pipeline_only_uses_own_contacts_mailboxes_and_template(
    db_session, test_tenant, other_tenant, pipeline_env,
):
    a, b = test_tenant.tenant_id, other_tenant.tenant_id
    mbx_a = _mailbox(db_session, a, "a@sender-a.com", sent_today=5)
    _mailbox(db_session, b, "b@sender-b.com", sent_today=0)  # least loaded overall
    tpl_a = _active_template(db_session, a, "TplA")
    _active_template(db_session, b, "TplB")
    ca = _contact(db_session, a, "pat@client-a.com")
    _contact(db_session, b, "pat@client-b.com")

    result = outreach_pipeline.run_outreach_send_pipeline(
        dry_run=False, limit=10, triggered_by="t", tenant_id=a,
    )

    sends = pipeline_env["sends"]
    assert sends == [{"mailbox_id": mbx_a.mailbox_id, "to": ca.email}], result
    assert {g["tenant_id"] for g in pipeline_env["gate_calls"]} == {a}

    events = db_session.query(OutreachEvent).all()
    assert len(events) == 1
    assert events[0].tenant_id == a
    assert events[0].template_id == tpl_a.template_id
    assert events[0].sender_mailbox_id == mbx_a.mailbox_id

    run = db_session.query(JobRun).filter(JobRun.pipeline_name == "outreach_send").one()
    assert run.tenant_id == a


def test_send_pipeline_without_own_mailbox_never_borrows_another_tenants(
    db_session, test_tenant, other_tenant, pipeline_env,
):
    a, b = test_tenant.tenant_id, other_tenant.tenant_id
    _mailbox(db_session, b, "b@sender-b.com")
    _contact(db_session, a, "pat@client-a.com")

    outreach_pipeline.run_outreach_send_pipeline(
        dry_run=False, limit=10, triggered_by="t", tenant_id=a,
    )
    assert pipeline_env["sends"] == []
    assert db_session.query(OutreachEvent).count() == 0


def test_send_pipeline_requires_tenant(db_session, pipeline_env):
    result = outreach_pipeline.run_outreach_send_pipeline(dry_run=False, tenant_id=None)
    assert "error" in result
    assert pipeline_env["sends"] == []
    assert db_session.query(JobRun).count() == 0


def test_mailmerge_pipeline_scoped_to_tenant(
    db_session, test_tenant, other_tenant, pipeline_env, tmp_path, monkeypatch,
):
    from app.core.config import settings
    monkeypatch.setattr(settings, "EXPORT_PATH", str(tmp_path))
    a, b = test_tenant.tenant_id, other_tenant.tenant_id
    ca = _contact(db_session, a, "pat@client-a.com")
    _contact(db_session, b, "pat@client-b.com")

    counters = outreach_pipeline.run_outreach_mailmerge_pipeline(triggered_by="t", tenant_id=a)
    assert counters["exported"] == 1
    events = db_session.query(OutreachEvent).all()
    assert [e.contact_id for e in events] == [ca.contact_id]
    run = db_session.query(JobRun).filter(JobRun.pipeline_name == "outreach_mailmerge").one()
    assert run.tenant_id == a


def test_mailmerge_pipeline_requires_tenant(db_session, pipeline_env):
    result = outreach_pipeline.run_outreach_mailmerge_pipeline(triggered_by="t", tenant_id=None)
    assert "error" in result
    assert db_session.query(JobRun).count() == 0


# ---------------------------------------------------------------------------
# run_outreach_for_lead (used by /leads/bulk/outreach and /leads/{id}/outreach)
# ---------------------------------------------------------------------------

def test_outreach_for_lead_uses_own_mailbox_and_skips_foreign_contacts(
    db_session, test_tenant, other_tenant, pipeline_env,
):
    a, b = test_tenant.tenant_id, other_tenant.tenant_id
    mbx_a = _mailbox(db_session, a, "a@sender-a.com", sent_today=7)
    _mailbox(db_session, b, "b@sender-b.com", sent_today=0)
    lead = _lead(db_session, a)
    ca = _contact(db_session, a, "pat@client-a.com", lead_id=lead.lead_id)
    # A tenant-B contact linked to A's lead (bad data / tampering) must not be emailed.
    cb = _contact(db_session, b, "pat@client-b.com")
    db_session.add(LeadContactAssociation(lead_id=lead.lead_id, contact_id=cb.contact_id))
    db_session.commit()

    outreach_pipeline.run_outreach_for_lead(lead_id=lead.lead_id, dry_run=False,
                                            triggered_by="t", tenant_id=a)

    assert pipeline_env["sends"] == [{"mailbox_id": mbx_a.mailbox_id, "to": ca.email}]
    assert {g["tenant_id"] for g in pipeline_env["gate_calls"]} == {a}
    assert all(e.tenant_id == a for e in db_session.query(OutreachEvent).all())


def test_outreach_for_lead_rejects_other_tenants_lead(
    db_session, test_tenant, other_tenant, pipeline_env,
):
    a, b = test_tenant.tenant_id, other_tenant.tenant_id
    _mailbox(db_session, a, "a@sender-a.com")
    lead_b = _lead(db_session, b, "BCorp")
    _contact(db_session, b, "pat@client-b.com", lead_id=lead_b.lead_id)

    result = outreach_pipeline.run_outreach_for_lead(lead_id=lead_b.lead_id, dry_run=False,
                                                     triggered_by="t", tenant_id=a)
    assert result.get("error") == "Lead not found"
    assert pipeline_env["sends"] == []


def test_outreach_for_lead_without_tenant_uses_leads_tenant(
    db_session, test_tenant, other_tenant, pipeline_env,
):
    """Super admin (no tenant) path: everything follows the lead's own tenant."""
    a, b = test_tenant.tenant_id, other_tenant.tenant_id
    _mailbox(db_session, a, "a@sender-a.com", sent_today=0)
    mbx_b = _mailbox(db_session, b, "b@sender-b.com", sent_today=9)
    lead_b = _lead(db_session, b, "BCorp")
    cb = _contact(db_session, b, "pat@client-b.com", lead_id=lead_b.lead_id)

    outreach_pipeline.run_outreach_for_lead(lead_id=lead_b.lead_id, dry_run=False,
                                            triggered_by="t", tenant_id=None)
    assert pipeline_env["sends"] == [{"mailbox_id": mbx_b.mailbox_id, "to": cb.email}]
    assert {g["tenant_id"] for g in pipeline_env["gate_calls"]} == {b}


# ---------------------------------------------------------------------------
# /leads/bulk/outreach and /preview
# ---------------------------------------------------------------------------

def test_bulk_outreach_recruiter_forbidden(client, viewer_headers, sample_lead, monkeypatch):
    called = []
    monkeypatch.setattr(outreach_pipeline, "run_outreach_for_lead",
                        lambda **kw: called.append(kw) or {})
    r = client.post(f"{API}/leads/bulk/outreach", headers=viewer_headers,
                    json={"lead_ids": [sample_lead.lead_id], "dry_run": True})
    assert r.status_code == 403
    assert called == []


def test_bulk_outreach_passes_tenant(client, auth_headers, test_tenant, sample_lead, monkeypatch):
    captured = []
    monkeypatch.setattr(outreach_pipeline, "run_outreach_for_lead",
                        lambda **kw: captured.append(kw) or {"sent": 0, "skipped": 0, "errors": 0})
    r = client.post(f"{API}/leads/bulk/outreach", headers=auth_headers,
                    json={"lead_ids": [sample_lead.lead_id], "dry_run": True})
    assert r.status_code == 200, r.text
    assert len(captured) == 1
    assert captured[0]["tenant_id"] == test_tenant.tenant_id
    assert captured[0]["lead_id"] == sample_lead.lead_id


def test_bulk_outreach_other_tenants_lead_not_run(
    client, auth_headers, db_session, other_tenant, monkeypatch,
):
    lead_b = _lead(db_session, other_tenant.tenant_id, "BCorp")
    captured = []
    monkeypatch.setattr(outreach_pipeline, "run_outreach_for_lead",
                        lambda **kw: captured.append(kw) or {})
    r = client.post(f"{API}/leads/bulk/outreach", headers=auth_headers,
                    json={"lead_ids": [lead_b.lead_id], "dry_run": False})
    assert r.status_code == 200, r.text
    assert captured == []
    assert r.json()["results"][0]["error"] == "Lead not found"


def test_bulk_outreach_preview_lists_only_own_mailboxes(
    client, auth_headers, db_session, test_tenant, other_tenant, sample_lead,
):
    mbx_a = _mailbox(db_session, test_tenant.tenant_id, "a@sender-a.com", sent_today=3)
    _mailbox(db_session, other_tenant.tenant_id, "b@sender-b.com", sent_today=0)
    _contact(db_session, test_tenant.tenant_id, "pat@client-a.com", lead_id=sample_lead.lead_id)

    r = client.post(f"{API}/leads/bulk/outreach/preview", headers=auth_headers,
                    json={"lead_ids": [sample_lead.lead_id]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [m["mailbox_id"] for m in body["available_mailboxes"]] == [mbx_a.mailbox_id]
    sender = body["assignments"][0]["sender"]
    assert sender is None or sender["mailbox_id"] == mbx_a.mailbox_id


def test_bulk_outreach_preview_hides_foreign_contacts(
    client, auth_headers, db_session, other_tenant, sample_lead,
):
    cb = _contact(db_session, other_tenant.tenant_id, "pat@client-b.com")
    db_session.add(LeadContactAssociation(lead_id=sample_lead.lead_id, contact_id=cb.contact_id))
    db_session.commit()
    r = client.post(f"{API}/leads/bulk/outreach/preview", headers=auth_headers,
                    json={"lead_ids": [sample_lead.lead_id]})
    assert r.status_code == 200, r.text
    emails = [c["email"] for c in r.json()["assignments"][0]["contacts"]]
    assert "pat@client-b.com" not in emails


# ---------------------------------------------------------------------------
# /outreach/check-replies
# ---------------------------------------------------------------------------

def test_check_replies_only_checks_own_mailboxes(
    client, auth_headers, db_session, test_tenant, other_tenant, monkeypatch,
):
    mbx_a = _mailbox(db_session, test_tenant.tenant_id, "a@sender-a.com")
    _mailbox(db_session, other_tenant.tenant_id, "b@sender-b.com")

    checked = []

    def fake_check(mailbox, db):
        checked.append(mailbox.mailbox_id)
        return {"replies_found": 0, "unsubscribes": 0, "errors": 0}

    monkeypatch.setattr("app.services.reply_tracker.check_replies_for_mailbox", fake_check)
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr("app.db.base.SessionLocal", lambda: db_session)

    r = client.post(f"{API}/outreach/check-replies", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert checked == [mbx_a.mailbox_id]


def test_check_all_mailbox_replies_without_tenant_covers_everyone(
    db_session, test_tenant, other_tenant, monkeypatch,
):
    """The scheduler call (no tenant) must still cover every tenant's mailboxes."""
    from app.services import reply_tracker
    a = _mailbox(db_session, test_tenant.tenant_id, "a@sender-a.com")
    b = _mailbox(db_session, other_tenant.tenant_id, "b@sender-b.com")
    checked = []
    monkeypatch.setattr(reply_tracker, "check_replies_for_mailbox",
                        lambda mailbox, db: checked.append(mailbox.mailbox_id)
                        or {"replies_found": 0, "unsubscribes": 0, "errors": 0})
    reply_tracker.check_all_mailbox_replies(db_session)
    assert sorted(checked) == sorted([a.mailbox_id, b.mailbox_id])
