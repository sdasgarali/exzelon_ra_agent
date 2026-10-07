"""Tenant isolation, wave 2 (MCP phase 2, agent B4).

Each test is a regression for a cross-tenant gap: tenant A (the caller, ``test_tenant``)
must not be able to read, link to or write into tenant B (``other_tenant``).

1. auto_enrollment.find_matching_contacts / preview had no tenant filter.
2. POST /leads/{id}/outreach had no role check (recruiters could send).
3. POST/PUT /contacts linked foreign lead ids; PUT email change kept a stale validation.
4. POST /templates/{id}/import-to-step wrote into another tenant's campaign step.
5. Email preview broadcast used foreign template/mailbox; PUT draft took any mailbox.
6. POST /mailboxes revealed other tenants' addresses, used foreign outreach roles and
   linked mailboxes to other tenants' users.
7. POST /outreach/events wrote super-admin events into tenant 1.
8. CORS allow_headers lacked X-API-Key.

No email is sent anywhere in this module.
"""
import json

import pytest

from app.db.models.campaign import Campaign, CampaignStatus, SequenceStep, StepType
from app.db.models.contact import ContactDetails, OutreachStatus
from app.db.models.email_template import EmailTemplate, TemplateStatus
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.outreach import OutreachEvent
from app.db.models.outreach_draft import DraftSource, DraftStatus, OutreachDraft
from app.db.models.outreach_role import OutreachRole
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User
from app.services import auto_enrollment

pytestmark = pytest.mark.integration

API = "/api/v1"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _add(db, obj):
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def _contact(db, tenant_id, email, **kw):
    kw.setdefault("validation_status", "valid")
    return _add(db, ContactDetails(tenant_id=tenant_id, client_name="Acme", first_name="Pat",
                                   last_name="Lee", email=email, **kw))


def _lead(db, tenant_id, title="Nurse"):
    return _add(db, LeadDetails(tenant_id=tenant_id, client_name="Acme", job_title=title,
                                state="TX", lead_status=LeadStatus.NEW))


def _mailbox(db, tenant_id, email):
    return _add(db, SenderMailbox(
        tenant_id=tenant_id, email=email, display_name=email.split("@")[0], password="x",
        warmup_status=WarmupStatus.COLD_READY, is_active=True, daily_send_limit=30,
        emails_sent_today=0, total_emails_sent=0,
    ))


def _template(db, tenant_id, name):
    return _add(db, EmailTemplate(tenant_id=tenant_id, name=name, subject=f"{name} subject",
                                  body_html=f"<p>{name}</p>", body_text=name,
                                  status=TemplateStatus.ACTIVE, category="outreach",
                                  is_default=False))


def _campaign(db, tenant_id, **kw):
    return _add(db, Campaign(tenant_id=tenant_id, name="C1", status=CampaignStatus.DRAFT, **kw))


def _step(db, campaign_id, subject="original"):
    return _add(db, SequenceStep(campaign_id=campaign_id, step_order=0, step_type=StepType.EMAIL,
                                 subject=subject, body_html="<p>original</p>"))


@pytest.fixture
def other_tenant(db_session):
    return _add(db_session, Tenant(name="tenant-b", slug="tenant-b", plan=TenantPlan.ENTERPRISE,
                                   max_users=99, max_mailboxes=99, max_contacts=9999,
                                   max_campaigns=99, max_leads=9999))


def _as(sa_headers, tenant):
    return {**sa_headers, "X-Tenant-ID": str(tenant.tenant_id)}


# ---------------------------------------------------------------------------
# 1. Auto-enrollment
# ---------------------------------------------------------------------------

def test_auto_enrollment_matches_only_campaign_tenant(db_session, test_tenant, other_tenant):
    # The foreign contact is created first (lower id) so, unscoped, it would be the one
    # the limit of 1 picks.
    foreign = _contact(db_session, other_tenant.tenant_id, "b@client-b.com",
                       outreach_status=OutreachStatus.ACTIVE)
    own = _contact(db_session, test_tenant.tenant_id, "a@client-a.com",
                   outreach_status=OutreachStatus.ACTIVE)
    camp = _campaign(db_session, test_tenant.tenant_id)

    rules = {"enabled": True, "max_per_run": 1, "daily_cap": 10}
    matched = auto_enrollment.find_matching_contacts(camp, rules, db_session)
    assert matched == [own.contact_id]
    assert foreign.contact_id not in matched

    assert auto_enrollment.preview_enrollment_matches(camp.campaign_id, rules, db_session) == 1


def test_auto_enrollment_job_title_join_is_tenant_scoped(db_session, test_tenant, other_tenant):
    # Own contact points (legacy FK) at a foreign lead whose title matches: must not count.
    foreign_lead = _lead(db_session, other_tenant.tenant_id, title="Charge Nurse")
    _contact(db_session, test_tenant.tenant_id, "a@client-a.com",
             outreach_status=OutreachStatus.ACTIVE, lead_id=foreign_lead.lead_id)
    camp = _campaign(db_session, test_tenant.tenant_id)
    rules = {"enabled": True, "max_per_run": 5, "daily_cap": 10, "job_title_keywords": ["nurse"]}
    assert auto_enrollment.find_matching_contacts(camp, rules, db_session) == []


# ---------------------------------------------------------------------------
# 2. Single-lead outreach role gate
# ---------------------------------------------------------------------------

def test_single_lead_outreach_forbidden_for_recruiter(client, viewer_headers, db_session,
                                                     test_tenant, monkeypatch):
    lead = _lead(db_session, test_tenant.tenant_id)
    calls = []
    monkeypatch.setattr("app.services.pipelines.outreach.run_outreach_for_lead",
                        lambda **kw: calls.append(kw) or {"sent": 0})
    r = client.post(f"{API}/leads/{lead.lead_id}/outreach?dry_run=true", headers=viewer_headers)
    assert r.status_code == 403, r.text
    assert calls == []


def test_single_lead_outreach_allowed_for_bdm(client, operator_headers, db_session,
                                             test_tenant, monkeypatch):
    lead = _lead(db_session, test_tenant.tenant_id)
    calls = []
    monkeypatch.setattr("app.services.pipelines.outreach.run_outreach_for_lead",
                        lambda **kw: calls.append(kw) or {"sent": 0})
    r = client.post(f"{API}/leads/{lead.lead_id}/outreach?dry_run=true", headers=operator_headers)
    assert r.status_code == 200, r.text
    assert calls and calls[0]["tenant_id"] == test_tenant.tenant_id


# ---------------------------------------------------------------------------
# 3. Contacts create / update
# ---------------------------------------------------------------------------

def _contact_body(email, **kw):
    return {"client_name": "Acme", "first_name": "Pat", "last_name": "Lee", "email": email, **kw}


def test_create_contact_rejects_foreign_lead_ids(client, auth_headers, db_session,
                                                 test_tenant, other_tenant):
    foreign_lead = _lead(db_session, other_tenant.tenant_id)
    r = client.post(f"{API}/contacts", headers=auth_headers,
                    json=_contact_body("new@a.com", lead_ids=[foreign_lead.lead_id]))
    assert r.status_code == 400, r.text
    assert db_session.query(ContactDetails).filter_by(email="new@a.com").count() == 0
    assert db_session.query(LeadContactAssociation).count() == 0


def test_create_contact_rejects_foreign_or_missing_lead_id(client, auth_headers, db_session,
                                                           test_tenant, other_tenant):
    foreign_lead = _lead(db_session, other_tenant.tenant_id)
    r = client.post(f"{API}/contacts", headers=auth_headers,
                    json=_contact_body("new@a.com", lead_id=foreign_lead.lead_id))
    assert r.status_code == 400, r.text
    r = client.post(f"{API}/contacts", headers=auth_headers,
                    json=_contact_body("new@a.com", lead_ids=[999999]))
    assert r.status_code == 400, r.text


def test_create_contact_links_own_leads(client, auth_headers, db_session, test_tenant):
    own_lead = _lead(db_session, test_tenant.tenant_id)
    r = client.post(f"{API}/contacts", headers=auth_headers,
                    json=_contact_body("new@a.com", lead_ids=[own_lead.lead_id, own_lead.lead_id]))
    assert r.status_code == 201, r.text
    assert r.json()["lead_ids"] == [own_lead.lead_id]


def test_update_contact_rejects_foreign_lead_id(client, auth_headers, db_session,
                                                test_tenant, other_tenant):
    own = _contact(db_session, test_tenant.tenant_id, "a@a.com")
    foreign_lead = _lead(db_session, other_tenant.tenant_id)
    r = client.put(f"{API}/contacts/{own.contact_id}", headers=auth_headers,
                   json={"lead_id": foreign_lead.lead_id})
    assert r.status_code == 400, r.text
    db_session.refresh(own)
    assert own.lead_id is None


def test_update_contact_email_change_resets_validation(client, auth_headers, db_session,
                                                       test_tenant):
    own = _contact(db_session, test_tenant.tenant_id, "a@a.com")
    r = client.put(f"{API}/contacts/{own.contact_id}", headers=auth_headers,
                   json={"email": "changed@a.com"})
    assert r.status_code == 200, r.text
    assert r.json()["validation_status"] is None

    # Same address (case-insensitive) keeps the existing validation.
    other = _contact(db_session, test_tenant.tenant_id, "keep@a.com")
    r = client.put(f"{API}/contacts/{other.contact_id}", headers=auth_headers,
                   json={"email": "KEEP@a.com", "first_name": "Sam"})
    assert r.status_code == 200, r.text
    assert r.json()["validation_status"] == "valid"


def test_update_contact_explicit_validation_wins(client, auth_headers, db_session, test_tenant):
    own = _contact(db_session, test_tenant.tenant_id, "a@a.com")
    r = client.put(f"{API}/contacts/{own.contact_id}", headers=auth_headers,
                   json={"email": "changed@a.com", "validation_status": "valid"})
    assert r.status_code == 200, r.text
    assert r.json()["validation_status"] == "valid"


def test_update_contact_outreach_status_still_writable(client, auth_headers, db_session,
                                                       test_tenant):
    own = _contact(db_session, test_tenant.tenant_id, "a@a.com")
    r = client.put(f"{API}/contacts/{own.contact_id}", headers=auth_headers,
                   json={"outreach_status": "unsubscribed"})
    assert r.status_code == 200, r.text
    assert r.json()["outreach_status"] == "unsubscribed"


# ---------------------------------------------------------------------------
# 4. Template import-to-step
# ---------------------------------------------------------------------------

def test_import_to_step_rejects_foreign_campaign_step(client, auth_headers, db_session,
                                                      test_tenant, other_tenant):
    tpl = _template(db_session, test_tenant.tenant_id, "Mine")
    foreign_step = _step(db_session, _campaign(db_session, other_tenant.tenant_id).campaign_id)
    r = client.post(f"{API}/templates/{tpl.template_id}/import-to-step?step_id={foreign_step.step_id}",
                    headers=auth_headers)
    assert r.status_code == 404, r.text
    db_session.refresh(foreign_step)
    assert foreign_step.subject == "original"


def test_import_to_step_super_admin_cannot_cross_tenants(client, sa_headers, db_session,
                                                         test_tenant, other_tenant):
    tpl = _template(db_session, test_tenant.tenant_id, "Mine")
    foreign_step = _step(db_session, _campaign(db_session, other_tenant.tenant_id).campaign_id)
    r = client.post(f"{API}/templates/{tpl.template_id}/import-to-step?step_id={foreign_step.step_id}",
                    headers=sa_headers)
    assert r.status_code == 404, r.text
    db_session.refresh(foreign_step)
    assert foreign_step.subject == "original"


def test_import_to_step_own_campaign_ok(client, auth_headers, db_session, test_tenant):
    tpl = _template(db_session, test_tenant.tenant_id, "Mine")
    step = _step(db_session, _campaign(db_session, test_tenant.tenant_id).campaign_id)
    r = client.post(f"{API}/templates/{tpl.template_id}/import-to-step?step_id={step.step_id}",
                    headers=auth_headers)
    assert r.status_code == 200, r.text
    db_session.refresh(step)
    assert step.subject == "Mine subject"


# ---------------------------------------------------------------------------
# 5. Email preview
# ---------------------------------------------------------------------------

def _broadcast(client, headers, contact_ids, template_id, mailbox_id):
    return client.post(f"{API}/email-preview/generate", headers=headers, json={
        "source": "broadcast", "contact_ids": contact_ids,
        "template_id": template_id, "mailbox_id": mailbox_id,
    })


def test_broadcast_rejects_foreign_template(client, auth_headers, db_session,
                                            test_tenant, other_tenant):
    own_c = _contact(db_session, test_tenant.tenant_id, "a@a.com")
    own_mb = _mailbox(db_session, test_tenant.tenant_id, "send@a.com")
    foreign_tpl = _template(db_session, other_tenant.tenant_id, "Theirs")
    r = _broadcast(client, auth_headers, [own_c.contact_id], foreign_tpl.template_id, own_mb.mailbox_id)
    assert r.status_code == 400, r.text
    assert db_session.query(OutreachDraft).count() == 0


def test_broadcast_rejects_foreign_mailbox(client, auth_headers, db_session,
                                           test_tenant, other_tenant):
    own_c = _contact(db_session, test_tenant.tenant_id, "a@a.com")
    own_tpl = _template(db_session, test_tenant.tenant_id, "Mine")
    foreign_mb = _mailbox(db_session, other_tenant.tenant_id, "send@b.com")
    r = _broadcast(client, auth_headers, [own_c.contact_id], own_tpl.template_id, foreign_mb.mailbox_id)
    assert r.status_code == 400, r.text
    assert db_session.query(OutreachDraft).count() == 0


def test_broadcast_own_resources_only_own_contacts(client, auth_headers, db_session,
                                                   test_tenant, other_tenant):
    own_c = _contact(db_session, test_tenant.tenant_id, "a@a.com")
    foreign_c = _contact(db_session, other_tenant.tenant_id, "b@b.com")
    own_tpl = _template(db_session, test_tenant.tenant_id, "Mine")
    own_mb = _mailbox(db_session, test_tenant.tenant_id, "send@a.com")
    r = _broadcast(client, auth_headers, [own_c.contact_id, foreign_c.contact_id],
                   own_tpl.template_id, own_mb.mailbox_id)
    assert r.status_code == 200, r.text
    assert r.json()["drafts_created"] == 1
    drafts = db_session.query(OutreachDraft).all()
    assert [d.contact_id for d in drafts] == [own_c.contact_id]


def test_update_draft_rejects_foreign_mailbox(client, auth_headers, db_session,
                                              test_tenant, other_tenant):
    own_c = _contact(db_session, test_tenant.tenant_id, "a@a.com")
    own_mb = _mailbox(db_session, test_tenant.tenant_id, "send@a.com")
    own_mb2 = _mailbox(db_session, test_tenant.tenant_id, "send2@a.com")
    foreign_mb = _mailbox(db_session, other_tenant.tenant_id, "send@b.com")
    draft = _add(db_session, OutreachDraft(
        tenant_id=test_tenant.tenant_id, contact_id=own_c.contact_id, mailbox_id=own_mb.mailbox_id,
        subject="s", body_html="<p>b</p>", status=DraftStatus.PENDING, source=DraftSource.BROADCAST,
        flagged_words_json=json.dumps([]),
    ))
    r = client.put(f"{API}/email-preview/drafts/{draft.draft_id}", headers=auth_headers,
                   json={"mailbox_id": foreign_mb.mailbox_id})
    assert r.status_code == 400, r.text
    db_session.refresh(draft)
    assert draft.mailbox_id == own_mb.mailbox_id

    r = client.put(f"{API}/email-preview/drafts/{draft.draft_id}", headers=auth_headers,
                   json={"mailbox_id": own_mb2.mailbox_id})
    assert r.status_code == 200, r.text
    assert r.json()["mailbox_id"] == own_mb2.mailbox_id


# ---------------------------------------------------------------------------
# 6. Mailbox create
# ---------------------------------------------------------------------------

def test_create_mailbox_duplicate_in_other_tenant_is_generic(client, auth_headers, db_session,
                                                             test_tenant, other_tenant):
    _mailbox(db_session, other_tenant.tenant_id, "taken@b.com")
    r = client.post(f"{API}/mailboxes", headers=auth_headers,
                    json={"email": "taken@b.com", "provider": "microsoft_365"})
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "taken@b.com" not in detail
    assert "already exists" not in detail
    assert detail == "This email address can't be added"


def test_create_mailbox_duplicate_in_own_tenant_is_named(client, auth_headers, db_session,
                                                         test_tenant):
    _mailbox(db_session, test_tenant.tenant_id, "mine@a.com")
    r = client.post(f"{API}/mailboxes", headers=auth_headers,
                    json={"email": "mine@a.com", "provider": "microsoft_365"})
    assert r.status_code == 400, r.text
    assert "already exists" in r.json()["detail"]


def test_create_mailbox_ignores_foreign_outreach_role(client, auth_headers, db_session,
                                                      test_tenant, other_tenant):
    own_ra = _add(db_session, OutreachRole(tenant_id=test_tenant.tenant_id, role_name="RA",
                                           auto_outbound=True))
    foreign_role = _add(db_session, OutreachRole(tenant_id=other_tenant.tenant_id,
                                                 role_name="Secret Role", auto_outbound=True))
    r = client.post(f"{API}/mailboxes", headers=auth_headers,
                    json={"email": "new@a.com", "provider": "microsoft_365",
                          "outreach_role_id": foreign_role.role_id})
    assert r.status_code == 200, r.text
    mb = db_session.query(SenderMailbox).filter_by(email="new@a.com").one()
    assert mb.outreach_role_id == own_ra.role_id
    assert mb.tenant_id == test_tenant.tenant_id


def test_create_personal_mailbox_never_links_foreign_user(client, sa_headers, db_session,
                                                          test_tenant, other_tenant):
    bdm = _add(db_session, OutreachRole(tenant_id=test_tenant.tenant_id, role_name="BDM",
                                        auto_outbound=False))
    foreign_user = _add(db_session, User(email="person@b.com", password_hash="x", full_name="B",
                                         role="bdm", tenant_id=other_tenant.tenant_id,
                                         is_active=True, is_verified=True))
    users_before = db_session.query(User).count()
    r = client.post(f"{API}/mailboxes", headers=_as(sa_headers, test_tenant),
                    json={"email": "person@b.com", "provider": "microsoft_365",
                          "outreach_role_id": bdm.role_id, "login_password": "SecurePass123!"})
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] is None
    assert db_session.query(User).count() == users_before
    db_session.refresh(foreign_user)
    assert foreign_user.tenant_id == other_tenant.tenant_id


def test_create_personal_mailbox_rejects_foreign_explicit_user(client, auth_headers, db_session,
                                                               test_tenant, other_tenant):
    bdm = _add(db_session, OutreachRole(tenant_id=test_tenant.tenant_id, role_name="BDM",
                                        auto_outbound=False))
    foreign_user = _add(db_session, User(email="person@b.com", password_hash="x", full_name="B",
                                         role="bdm", tenant_id=other_tenant.tenant_id,
                                         is_active=True, is_verified=True))
    r = client.post(f"{API}/mailboxes", headers=auth_headers,
                    json={"email": "other@a.com", "provider": "microsoft_365",
                          "outreach_role_id": bdm.role_id, "user_id": foreign_user.user_id})
    assert r.status_code == 400, r.text
    assert db_session.query(SenderMailbox).filter_by(email="other@a.com").count() == 0


# ---------------------------------------------------------------------------
# 7. Outreach events
# ---------------------------------------------------------------------------

def _event_body(contact_id, **kw):
    return {"contact_id": contact_id, "channel": "smtp", "status": "sent", "subject": "hi", **kw}


def test_create_event_super_admin_without_tenant_is_400(client, sa_headers, db_session,
                                                        test_tenant):
    own_c = _contact(db_session, test_tenant.tenant_id, "a@a.com")
    r = client.post(f"{API}/outreach/events", headers=sa_headers, json=_event_body(own_c.contact_id))
    assert r.status_code == 400, r.text
    assert db_session.query(OutreachEvent).count() == 0


def test_create_event_rejects_foreign_references(client, auth_headers, db_session,
                                                 test_tenant, other_tenant):
    own_c = _contact(db_session, test_tenant.tenant_id, "a@a.com")
    foreign_c = _contact(db_session, other_tenant.tenant_id, "b@b.com")
    foreign_lead = _lead(db_session, other_tenant.tenant_id)
    foreign_tpl = _template(db_session, other_tenant.tenant_id, "Theirs")

    for body in (
        _event_body(foreign_c.contact_id),
        _event_body(own_c.contact_id, lead_id=foreign_lead.lead_id),
        _event_body(own_c.contact_id, template_id=foreign_tpl.template_id),
    ):
        r = client.post(f"{API}/outreach/events", headers=auth_headers, json=body)
        assert r.status_code == 400, (body, r.text)
    assert db_session.query(OutreachEvent).count() == 0


def test_create_event_writes_callers_tenant(client, sa_headers, db_session, test_tenant,
                                            other_tenant):
    their_c = _contact(db_session, other_tenant.tenant_id, "b@b.com")
    r = client.post(f"{API}/outreach/events", headers=_as(sa_headers, other_tenant),
                    json=_event_body(their_c.contact_id))
    assert r.status_code == 201, r.text
    ev = db_session.query(OutreachEvent).one()
    assert ev.tenant_id == other_tenant.tenant_id


# ---------------------------------------------------------------------------
# 8. CORS
# ---------------------------------------------------------------------------

def test_cors_allows_api_key_and_tenant_headers():
    from starlette.middleware.cors import CORSMiddleware

    from app.main import app

    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors, "CORSMiddleware not installed"
    allowed = {h.lower() for h in cors[0].kwargs["allow_headers"]}
    assert {"x-api-key", "x-tenant-id", "authorization", "content-type"} <= allowed


def test_bulk_update_rejects_foreign_lead_link(client, db_session, sa_headers, test_tenant):
    """PUT /contacts/bulk/update must not link contacts to another tenant's lead."""
    from datetime import date as _date

    from app.db.models.contact import ContactDetails as _C
    from app.db.models.lead import LeadDetails as _L, LeadStatus as _S
    from app.db.models.tenant import Tenant as _T, TenantPlan as _P

    other = _T(name="Other BU", slug="other-bulk-upd", plan=_P.ENTERPRISE)
    db_session.add(other)
    db_session.flush()
    foreign = _L(tenant_id=other.tenant_id, client_name="X", job_title="Y", state="TX",
                 posting_date=_date.today(), source="manual", lead_status=_S.NEW)
    mine = _L(tenant_id=test_tenant.tenant_id, client_name="X", job_title="Y", state="TX",
              posting_date=_date.today(), source="manual", lead_status=_S.NEW)
    c = _C(tenant_id=test_tenant.tenant_id, client_name="X", first_name="A", last_name="B",
           email="bulk.upd@x.example.com")
    db_session.add_all([foreign, mine, c])
    db_session.commit()

    bad = client.put("/api/v1/contacts/bulk/update", headers=sa_headers,
                     json={"contact_ids": [c.contact_id], "updates": {"lead_id": foreign.lead_id}})
    assert bad.status_code == 400
    ok = client.put("/api/v1/contacts/bulk/update", headers=sa_headers,
                    json={"contact_ids": [c.contact_id], "updates": {"lead_id": mine.lead_id}})
    assert ok.status_code == 200, ok.text
