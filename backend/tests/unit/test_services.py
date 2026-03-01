"""Tests for service layer modules."""
import pytest
from datetime import date
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.contact import ContactDetails
from app.db.models.email_template import EmailTemplate, TemplateStatus


pytestmark = pytest.mark.unit


class TestLeadService:
    def test_get_lead_stats(self, db_session):
        from app.services.lead_service import get_lead_stats
        lead = LeadDetails(client_name="Test", job_title="Dev", lead_status=LeadStatus.NEW, posting_date=date.today(), tenant_id=1)
        db_session.add(lead)
        db_session.commit()
        stats = get_lead_stats(db_session)
        assert stats["total"] >= 1
        assert "by_status" in stats
        assert "by_source" in stats

    def test_bulk_archive_leads(self, db_session):
        from app.services.lead_service import bulk_archive_leads
        lead = LeadDetails(client_name="Del", job_title="QA", lead_status=LeadStatus.NEW, posting_date=date.today(), tenant_id=1)
        db_session.add(lead)
        db_session.commit()
        result = bulk_archive_leads(db_session, [lead.lead_id])
        db_session.commit()
        assert result["archived_count"] == 1

    def test_bulk_unarchive_leads(self, db_session):
        from app.services.lead_service import bulk_unarchive_leads
        lead = LeadDetails(client_name="Arc", job_title="PM", lead_status=LeadStatus.NEW, posting_date=date.today(), is_archived=True, tenant_id=1)
        db_session.add(lead)
        db_session.commit()
        count = bulk_unarchive_leads(db_session, [lead.lead_id])
        db_session.commit()
        assert count == 1


class TestContactService:
    def test_get_contact_stats(self, db_session):
        from app.services.contact_service import get_contact_stats
        c = ContactDetails(first_name="A", last_name="B", email="stats@test.com", client_name="Stats Corp", tenant_id=1)
        db_session.add(c)
        db_session.commit()
        stats = get_contact_stats(db_session)
        assert stats["total"] >= 1

    def test_find_duplicate_contacts(self, db_session):
        from app.services.contact_service import find_duplicate_contacts
        c1 = ContactDetails(first_name="X", last_name="Y", email="svcdup@test.com", client_name="A Corp", tenant_id=1)
        c2 = ContactDetails(first_name="X", last_name="Z", email="svcdup@test.com", client_name="B Corp", tenant_id=1)
        db_session.add_all([c1, c2])
        db_session.commit()
        dupes = find_duplicate_contacts(db_session)
        assert len(dupes) >= 1


class TestTemplateService:
    def test_preview_template(self, db_session):
        from app.services.template_service import preview_template
        t = EmailTemplate(name="Svc Test", subject="Hello {{contact_first_name}}", body_html="<p>Hi</p>", body_text="Hi", status=TemplateStatus.INACTIVE, tenant_id=1)
        db_session.add(t)
        db_session.commit()
        result = preview_template(db_session, t.template_id)
        assert result is not None
        assert "John" in result["subject"]

    def test_preview_nonexistent(self, db_session):
        from app.services.template_service import preview_template
        result = preview_template(db_session, 99999)
        assert result is None

    def test_duplicate_template(self, db_session):
        from app.services.template_service import duplicate_template
        t = EmailTemplate(name="Orig", subject="Sub", body_html="<p>Body</p>", body_text="Body", status=TemplateStatus.ACTIVE, tenant_id=1)
        db_session.add(t)
        db_session.commit()
        dup = duplicate_template(db_session, t.template_id)
        db_session.commit()
        assert dup is not None
        assert dup.name == "Orig (Copy)"
        assert dup.status == TemplateStatus.INACTIVE
