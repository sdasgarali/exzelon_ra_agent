"""Tenant-isolation audit follow-ups (2026-10-07)."""
from datetime import date

import pytest

from app.db.models.contact import ContactDetails
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.tenant import Tenant, TenantPlan

pytestmark = pytest.mark.integration


def test_lead_detail_never_lists_other_tenants_contacts(client, db_session, auth_headers, test_tenant):
    other = Tenant(name="Other AF", slug="other-audit-fu", plan=TenantPlan.ENTERPRISE)
    db_session.add(other)
    db_session.flush()
    lead = LeadDetails(tenant_id=test_tenant.tenant_id, client_name="Acme", job_title="Ops", state="TX",
                       posting_date=date.today(), source="manual", lead_status=LeadStatus.NEW)
    db_session.add(lead)
    db_session.flush()
    mine = ContactDetails(tenant_id=test_tenant.tenant_id, client_name="Acme", first_name="M", last_name="E",
                          email="mine@acme.example.com", lead_id=lead.lead_id)
    theirs = ContactDetails(tenant_id=other.tenant_id, client_name="Acme", first_name="T", last_name="H",
                            email="theirs@acme.example.com")
    db_session.add_all([mine, theirs])
    db_session.flush()
    # a stray cross-tenant junction row (e.g. created before the contact-create fix)
    db_session.add(LeadContactAssociation(lead_id=lead.lead_id, contact_id=theirs.contact_id))
    db_session.commit()

    r = client.get(f"/api/v1/leads/{lead.lead_id}/detail", headers=auth_headers)
    assert r.status_code == 200, r.text
    emails = {c["email"] for c in r.json()["contacts"]}
    assert emails == {"mine@acme.example.com"}


def test_validation_pipeline_refuses_without_tenant(monkeypatch):
    from app.services.pipelines import email_validation

    def boom():
        raise AssertionError("must not open a session / create a JobRun without a tenant")

    monkeypatch.setattr(email_validation, "SessionLocal", boom)
    out = email_validation.run_email_validation_pipeline(emails=["a@b.example.com"], tenant_id=None)
    assert out["error"] == "tenant_id is required"
