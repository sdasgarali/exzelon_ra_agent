"""Tests for deal detail 360: candidates, mail chain, job details."""
import pytest

from app.db.models.deal import Deal, DealStage
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.db.models.outreach import OutreachEvent, OutreachChannel, OutreachStatus
from app.db.models.inbox_message import InboxMessage, MessageDirection

pytestmark = pytest.mark.integration


@pytest.fixture
def stage(db_session, test_tenant):
    s = DealStage(tenant_id=test_tenant.tenant_id, name="New Lead", stage_order=1, color="#111")
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _deal(db, tenant_id, stage_id, contact_id=None):
    d = Deal(tenant_id=tenant_id, name="Acme — Jane", stage_id=stage_id, value=1000, probability=20, contact_id=contact_id)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


class TestCandidates:
    def test_recruiter_submits_and_bdm_reviews(self, client, db_session, viewer_headers, auth_headers, test_tenant, stage):
        d = _deal(db_session, test_tenant.tenant_id, stage.stage_id)
        # recruiter submits a candidate
        resp = client.post(f"/api/v1/deals/{d.deal_id}/candidates", headers=viewer_headers,
                          json={"name": "John Candidate", "linkedin_url": "https://li/x", "email": "jc@x.com"})
        assert resp.status_code == 201, resp.text
        cid = resp.json()["candidate_id"]
        assert resp.json()["status"] == "submitted"
        assert resp.json()["submitted_by"]["id"] is not None
        # BDM moves it forward
        upd = client.put(f"/api/v1/deals/{d.deal_id}/candidates/{cid}", headers=auth_headers,
                        json={"status": "reviewed"})
        assert upd.status_code == 200
        assert upd.json()["status"] == "reviewed"
        # list shows it
        rows = client.get(f"/api/v1/deals/{d.deal_id}/candidates", headers=viewer_headers).json()
        assert len(rows) == 1 and rows[0]["name"] == "John Candidate"
        # detail exposes candidate_count
        detail = client.get(f"/api/v1/deals/{d.deal_id}", headers=viewer_headers).json()
        assert detail["candidate_count"] == 1

    def test_invalid_status_rejected(self, client, db_session, viewer_headers, test_tenant, stage):
        d = _deal(db_session, test_tenant.tenant_id, stage.stage_id)
        cid = client.post(f"/api/v1/deals/{d.deal_id}/candidates", headers=viewer_headers,
                         json={"name": "X"}).json()["candidate_id"]
        resp = client.put(f"/api/v1/deals/{d.deal_id}/candidates/{cid}", headers=viewer_headers, json={"status": "bogus"})
        assert resp.status_code == 400

    def test_delete_candidate(self, client, db_session, viewer_headers, test_tenant, stage):
        d = _deal(db_session, test_tenant.tenant_id, stage.stage_id)
        cid = client.post(f"/api/v1/deals/{d.deal_id}/candidates", headers=viewer_headers, json={"name": "Z"}).json()["candidate_id"]
        assert client.delete(f"/api/v1/deals/{d.deal_id}/candidates/{cid}", headers=viewer_headers).status_code == 204
        assert client.get(f"/api/v1/deals/{d.deal_id}/candidates", headers=viewer_headers).json() == []


class TestJobDetails:
    def test_detail_includes_job_from_lead(self, client, db_session, viewer_headers, test_tenant, stage):
        lead = LeadDetails(tenant_id=test_tenant.tenant_id, client_name="Acme", job_title="Senior PM",
                           job_link="https://jobs/acme/pm")
        db_session.add(lead)
        db_session.commit()
        db_session.refresh(lead)
        contact = ContactDetails(tenant_id=test_tenant.tenant_id, client_name="Acme", first_name="Jane",
                                 last_name="Doe", email="jane@acme.com", lead_id=lead.lead_id)
        db_session.add(contact)
        db_session.commit()
        db_session.refresh(contact)
        d = _deal(db_session, test_tenant.tenant_id, stage.stage_id, contact_id=contact.contact_id)
        detail = client.get(f"/api/v1/deals/{d.deal_id}", headers=viewer_headers).json()
        assert detail["job"] is not None
        assert detail["job"]["job_title"] == "Senior PM"
        assert detail["job"]["job_link"] == "https://jobs/acme/pm"


class TestMailChain:
    def test_messages_merge_and_order(self, client, db_session, viewer_headers, test_tenant, stage):
        contact = ContactDetails(tenant_id=test_tenant.tenant_id, client_name="Acme", first_name="Jane",
                                 last_name="Doe", email="jane@acme.com")
        db_session.add(contact)
        db_session.commit()
        db_session.refresh(contact)
        db_session.add(OutreachEvent(tenant_id=test_tenant.tenant_id, contact_id=contact.contact_id,
                                     channel=OutreachChannel.SMTP, status=OutreachStatus.SENT,
                                     subject="Hello", body_text="Initial outreach"))
        db_session.add(InboxMessage(tenant_id=test_tenant.tenant_id, contact_id=contact.contact_id,
                                    thread_id="t1", direction=MessageDirection.RECEIVED,
                                    from_email="jane@acme.com", to_email="ra@x.com",
                                    subject="Re: Hello", body_text="I'm interested"))
        db_session.commit()
        d = _deal(db_session, test_tenant.tenant_id, stage.stage_id, contact_id=contact.contact_id)
        body = client.get(f"/api/v1/deals/{d.deal_id}/messages", headers=viewer_headers).json()
        assert body["contact_id"] == contact.contact_id
        dirs = [m["direction"] for m in body["messages"]]
        assert "sent" in dirs and "received" in dirs

    def test_messages_empty_without_contact(self, client, db_session, viewer_headers, test_tenant, stage):
        d = _deal(db_session, test_tenant.tenant_id, stage.stage_id)
        body = client.get(f"/api/v1/deals/{d.deal_id}/messages", headers=viewer_headers).json()
        assert body["messages"] == []
