"""Campaign enroll ownership + inbox reply send-gate (MCP phase 2, agent B2).

Regressions covered:
- POST /campaigns/{id}/contacts enrolled any contact id, including another tenant's
  contacts — which then get emailed by that campaign. It now rejects (400) and lists
  up to 20 foreign or missing ids. ``enroll_contacts`` itself also refuses contacts
  outside the campaign's tenant, so the auto-enroll path cannot leak either.
- POST /inbox/reply sent immediately with no gate: suppressed / unsubscribed /
  do-not-contact recipients were emailed, and a super admin without a tenant got a
  400 only after the email had already gone out.
"""
import pytest

from app.db.models.campaign import Campaign, CampaignContact, CampaignStatus
from app.db.models.contact import ContactDetails, OutreachStatus as ContactOutreachStatus
from app.db.models.inbox_message import InboxMessage, MessageDirection
from app.db.models.suppression import SuppressionList
from app.db.models.tenant import Tenant, TenantPlan

pytestmark = pytest.mark.integration

API = "/api/v1"


@pytest.fixture
def other_tenant(db_session):
    t = Tenant(name="B", slug="tenant-b", plan=TenantPlan.ENTERPRISE, max_users=9,
               max_mailboxes=9, max_contacts=999, max_campaigns=9, max_leads=999)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


def _contact(db, tenant_id, email, **kw):
    c = ContactDetails(tenant_id=tenant_id, client_name="Acme", first_name="Pat",
                       last_name="Lee", email=email, validation_status="valid", **kw)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _campaign(db, tenant_id):
    c = Campaign(tenant_id=tenant_id, name="C1", status=CampaignStatus.DRAFT)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ---------------------------------------------------------------------------
# Enroll
# ---------------------------------------------------------------------------

def test_enroll_rejects_foreign_contacts(client, auth_headers, db_session, test_tenant,
                                         other_tenant):
    camp = _campaign(db_session, test_tenant.tenant_id)
    own = _contact(db_session, test_tenant.tenant_id, "a@client-a.com")
    foreign = _contact(db_session, other_tenant.tenant_id, "b@client-b.com")

    r = client.post(f"{API}/campaigns/{camp.campaign_id}/contacts", headers=auth_headers,
                    json={"contact_ids": [own.contact_id, foreign.contact_id]})
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert foreign.contact_id in detail["invalid_contact_ids"]
    assert own.contact_id not in detail["invalid_contact_ids"]
    assert db_session.query(CampaignContact).count() == 0


def test_enroll_rejects_missing_ids_and_caps_list_at_20(client, auth_headers, db_session,
                                                        test_tenant):
    camp = _campaign(db_session, test_tenant.tenant_id)
    missing = list(range(900000, 900030))
    r = client.post(f"{API}/campaigns/{camp.campaign_id}/contacts", headers=auth_headers,
                    json={"contact_ids": missing})
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert len(detail["invalid_contact_ids"]) == 20
    assert detail["invalid_count"] == 30


def test_enroll_own_contacts_ok(client, auth_headers, db_session, test_tenant):
    camp = _campaign(db_session, test_tenant.tenant_id)
    own = _contact(db_session, test_tenant.tenant_id, "a@client-a.com")
    r = client.post(f"{API}/campaigns/{camp.campaign_id}/contacts", headers=auth_headers,
                    json={"contact_ids": [own.contact_id]})
    assert r.status_code == 200, r.text
    assert r.json()["enrolled"] == 1


def test_enroll_service_skips_foreign_contacts(db_session, test_tenant, other_tenant):
    """Auto-enroll calls enroll_contacts directly — it must not enroll other tenants."""
    from app.services.campaign_engine import enroll_contacts
    camp = _campaign(db_session, test_tenant.tenant_id)
    own = _contact(db_session, test_tenant.tenant_id, "a@client-a.com")
    foreign = _contact(db_session, other_tenant.tenant_id, "b@client-b.com")

    result = enroll_contacts(camp.campaign_id, [own.contact_id, foreign.contact_id], db_session)
    assert result["enrolled"] == 1
    assert result["foreign"] == 1
    enrolled_ids = [cc.contact_id for cc in db_session.query(CampaignContact).all()]
    assert enrolled_ids == [own.contact_id]


def test_enroll_service_still_skips_suppressed(db_session, test_tenant):
    """The new ownership filter must not bypass the existing suppression check."""
    from app.services.campaign_engine import enroll_contacts
    camp = _campaign(db_session, test_tenant.tenant_id)
    own = _contact(db_session, test_tenant.tenant_id, "a@client-a.com")
    db_session.add(SuppressionList(tenant_id=test_tenant.tenant_id, email="a@client-a.com",
                                   reason="unsubscribe"))
    db_session.commit()
    result = enroll_contacts(camp.campaign_id, [own.contact_id], db_session)
    assert result["enrolled"] == 0
    assert result["suppressed"] == 1


# ---------------------------------------------------------------------------
# Inbox reply
# ---------------------------------------------------------------------------

@pytest.fixture
def reply_env(db_session, test_tenant, sample_mailbox, monkeypatch):
    sends = []

    def fake_send(sender_mailbox, to_email, **kw):
        sends.append(to_email)
        return {"success": True, "message_id": "<r1@x>", "error": None}

    monkeypatch.setattr("app.services.pipelines.outreach.send_outreach_email", fake_send)

    contact = _contact(db_session, test_tenant.tenant_id, "lead@client-a.com")
    msg = InboxMessage(
        tenant_id=test_tenant.tenant_id, thread_id="thr-1", contact_id=contact.contact_id,
        mailbox_id=sample_mailbox.mailbox_id, direction=MessageDirection.RECEIVED,
        from_email="lead@client-a.com", to_email=sample_mailbox.email, subject="Hello",
        raw_message_id="<in1@client-a.com>",
    )
    db_session.add(msg)
    db_session.commit()
    return {"sends": sends, "contact": contact, "msg": msg, "mailbox": sample_mailbox}


def _reply(client, headers, mailbox_id, thread_id="thr-1"):
    return client.post(f"{API}/inbox/reply", headers=headers, json={
        "thread_id": thread_id, "mailbox_id": mailbox_id,
        "body_html": "<p>Thanks</p>", "body_text": "Thanks",
    })


def test_reply_happy_path_sends(client, auth_headers, reply_env):
    r = _reply(client, auth_headers, reply_env["mailbox"].mailbox_id)
    assert r.status_code == 200, r.text
    assert reply_env["sends"] == ["lead@client-a.com"]


def test_reply_refuses_suppressed_recipient(client, auth_headers, db_session, test_tenant,
                                            reply_env):
    db_session.add(SuppressionList(tenant_id=test_tenant.tenant_id,
                                   email="lead@client-a.com", reason="unsubscribe"))
    db_session.commit()
    r = _reply(client, auth_headers, reply_env["mailbox"].mailbox_id)
    assert r.status_code == 400, r.text
    assert reply_env["sends"] == []


def test_reply_refuses_unsubscribed_contact(client, auth_headers, db_session, reply_env):
    reply_env["contact"].outreach_status = ContactOutreachStatus.UNSUBSCRIBED
    db_session.commit()
    r = _reply(client, auth_headers, reply_env["mailbox"].mailbox_id)
    assert r.status_code == 400, r.text
    assert reply_env["sends"] == []


def test_reply_refuses_unsubscribed_contact_without_contact_link(
    client, auth_headers, db_session, reply_env,
):
    """Thread message not linked to a contact: the recipient is looked up by email."""
    reply_env["msg"].contact_id = None
    reply_env["contact"].outreach_status = ContactOutreachStatus.UNSUBSCRIBED
    db_session.commit()
    r = _reply(client, auth_headers, reply_env["mailbox"].mailbox_id)
    assert r.status_code == 400, r.text
    assert reply_env["sends"] == []


def test_reply_refuses_do_not_contact_thread(client, auth_headers, db_session, reply_env):
    reply_env["msg"].category = "do_not_contact"
    db_session.commit()
    r = _reply(client, auth_headers, reply_env["mailbox"].mailbox_id)
    assert r.status_code == 400, r.text
    assert reply_env["sends"] == []


def test_reply_super_admin_without_tenant_refused_before_send(client, sa_headers, reply_env):
    r = _reply(client, sa_headers, reply_env["mailbox"].mailbox_id)
    assert r.status_code == 400, r.text
    assert reply_env["sends"] == []


def test_reply_unvalidated_contact_still_allowed(client, auth_headers, db_session, reply_env):
    """Replies are conversations: an unvalidated address that wrote to us is fine."""
    reply_env["contact"].validation_status = None
    db_session.commit()
    r = _reply(client, auth_headers, reply_env["mailbox"].mailbox_id)
    assert r.status_code == 200, r.text
    assert reply_env["sends"] == ["lead@client-a.com"]


def test_reply_other_tenants_thread_not_found(client, auth_headers, db_session, other_tenant,
                                              reply_env):
    db_session.add(InboxMessage(
        tenant_id=other_tenant.tenant_id, thread_id="thr-b", direction=MessageDirection.RECEIVED,
        from_email="x@client-b.com", to_email="b@sender-b.com", subject="Hi",
    ))
    db_session.commit()
    r = _reply(client, auth_headers, reply_env["mailbox"].mailbox_id, thread_id="thr-b")
    assert r.status_code == 404
    assert reply_env["sends"] == []


# ---- deliverability review follow-ups (2026-10-07) -------------------------------

def test_reply_not_blocked_by_cold_domain_throttle(client, auth_headers, reply_env, monkeypatch):
    """A domain cap filled by cold outreach must not block answering an inbound email."""
    from app.services.send_gate import SendGateResult

    monkeypatch.setattr("app.services.send_gate.unified_send_gate",
                        lambda **kw: SendGateResult(allowed=False, reason_code="DOMAIN_THROTTLE"))
    r = _reply(client, auth_headers, reply_env["mailbox"].mailbox_id)
    assert r.status_code == 200, r.text
    assert reply_env["sends"] == ["lead@client-a.com"]


@pytest.mark.parametrize("change", [
    {"connection_status": "failed"}, {"is_blacklisted": True}, {"is_active": False},
    {"emails_sent_today": 30, "daily_send_limit": 30},
])
def test_reply_refuses_unhealthy_or_capped_mailbox(client, auth_headers, db_session, reply_env, change):
    mb = reply_env["mailbox"]
    for k, v in change.items():
        setattr(mb, k, v)
    db_session.commit()
    r = _reply(client, auth_headers, mb.mailbox_id)
    assert r.status_code == 400, r.text
    assert reply_env["sends"] == []


def test_sendable_mailboxes_exclude_blacklisted(db_session, test_tenant, sample_mailbox):
    from app.services.pipelines.outreach import sendable_mailboxes_query

    assert sendable_mailboxes_query(db_session, test_tenant.tenant_id).count() == 1
    sample_mailbox.is_blacklisted = True
    db_session.commit()
    assert sendable_mailboxes_query(db_session, test_tenant.tenant_id).count() == 0
