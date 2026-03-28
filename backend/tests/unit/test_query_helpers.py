"""Tests for database query helpers and contact utilities."""
import pytest
from datetime import date
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.contact import ContactDetails
from app.db.models.lead_contact import LeadContactAssociation
from app.db.query_helpers import active_query, paginate


pytestmark = pytest.mark.unit


class TestActiveQuery:
    def test_active_only(self, db_session, test_tenant):
        lead1 = LeadDetails(tenant_id=test_tenant.tenant_id, client_name="Active", job_title="Dev", lead_status=LeadStatus.NEW, posting_date=date.today())
        lead2 = LeadDetails(tenant_id=test_tenant.tenant_id, client_name="Archived", job_title="QA", lead_status=LeadStatus.NEW, posting_date=date.today(), is_archived=True)
        db_session.add_all([lead1, lead2])
        db_session.commit()

        q = active_query(db_session, LeadDetails, show_archived=False)
        results = q.all()
        names = [r.client_name for r in results]
        assert "Active" in names
        assert "Archived" not in names

    def test_archived_only(self, db_session, test_tenant):
        lead1 = LeadDetails(tenant_id=test_tenant.tenant_id, client_name="Active2", job_title="Dev", lead_status=LeadStatus.NEW, posting_date=date.today())
        lead2 = LeadDetails(tenant_id=test_tenant.tenant_id, client_name="Archived2", job_title="QA", lead_status=LeadStatus.NEW, posting_date=date.today(), is_archived=True)
        db_session.add_all([lead1, lead2])
        db_session.commit()

        q = active_query(db_session, LeadDetails, show_archived=True)
        results = q.all()
        names = [r.client_name for r in results]
        assert "Archived2" in names
        assert "Active2" not in names


class TestPaginate:
    def test_paginate(self, db_session, test_tenant):
        for i in range(25):
            db_session.add(LeadDetails(tenant_id=test_tenant.tenant_id, client_name=f"Co{i}", job_title="J", lead_status=LeadStatus.NEW, posting_date=date.today()))
        db_session.commit()

        q = db_session.query(LeadDetails)
        result = paginate(q, page=1, page_size=10)
        assert result["total"] == 25
        assert len(result["items"]) == 10
        assert result["pages"] == 3
        assert result["page"] == 1


class TestContactUtils:
    def test_get_contact_ids_for_lead(self, db_session, test_tenant):
        from app.db.contact_utils import get_contact_ids_for_lead
        lead = LeadDetails(tenant_id=test_tenant.tenant_id, client_name="CU", job_title="T", lead_status=LeadStatus.NEW, posting_date=date.today())
        db_session.add(lead)
        db_session.flush()

        c1 = ContactDetails(tenant_id=test_tenant.tenant_id, first_name="A", last_name="B", email="cu1@t.com", client_name="CU", lead_id=lead.lead_id)
        c2 = ContactDetails(tenant_id=test_tenant.tenant_id, first_name="C", last_name="D", email="cu2@t.com", client_name="CU")
        db_session.add_all([c1, c2])
        db_session.flush()

        assoc = LeadContactAssociation(lead_id=lead.lead_id, contact_id=c2.contact_id)
        db_session.add(assoc)
        db_session.commit()

        ids = get_contact_ids_for_lead(db_session, lead.lead_id)
        assert c1.contact_id in ids
        assert c2.contact_id in ids

    def test_get_contacts_for_lead(self, db_session, test_tenant):
        from app.db.contact_utils import get_contacts_for_lead
        lead = LeadDetails(tenant_id=test_tenant.tenant_id, client_name="CU2", job_title="T2", lead_status=LeadStatus.NEW, posting_date=date.today())
        db_session.add(lead)
        db_session.flush()

        c = ContactDetails(tenant_id=test_tenant.tenant_id, first_name="E", last_name="F", email="cu3@t.com", client_name="CU2", lead_id=lead.lead_id)
        db_session.add(c)
        db_session.commit()

        contacts = get_contacts_for_lead(db_session, lead.lead_id)
        assert len(contacts) == 1
        assert contacts[0].email == "cu3@t.com"
