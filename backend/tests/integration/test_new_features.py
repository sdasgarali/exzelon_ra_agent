"""Tests for Batch 5 features: template duplicate, CSV preview, contact duplicates, contact merge, job cancel."""
import pytest
from datetime import date

from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.contact import ContactDetails
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.job_run import JobRun, JobStatus
from app.db.models.email_template import EmailTemplate, TemplateStatus


pytestmark = pytest.mark.integration


class TestTemplateDuplicate:
    """Tests for POST /templates/{id}/duplicate."""

    def test_duplicate_template(self, client, db_session, auth_headers, sample_template):
        response = client.post(
            f"/api/v1/templates/{sample_template.template_id}/duplicate",
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == f"{sample_template.name} (Copy)"
        assert data["status"] == "inactive"
        assert data["is_default"] is False
        assert data["template_id"] != sample_template.template_id

    def test_duplicate_nonexistent_template(self, client, auth_headers):
        response = client.post(
            "/api/v1/templates/99999/duplicate",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestCSVImportPreview:
    """Tests for POST /leads/import/preview."""

    def test_preview_csv(self, client, auth_headers, db_session):
        csv_content = "Company Name,Job Title,State,Source\nAcme Corp,Engineer,TX,import\nBeta Inc,Manager,CA,import\n"
        response = client.post(
            "/api/v1/leads/import/preview",
            headers=auth_headers,
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_rows"] == 2
        assert data["duplicate_count"] == 0
        assert len(data["preview"]) == 2
        assert data["preview"][0]["company_name"] == "Acme Corp"

    def test_preview_non_csv(self, client, auth_headers):
        response = client.post(
            "/api/v1/leads/import/preview",
            headers=auth_headers,
            files={"file": ("test.txt", "hello", "text/plain")},
        )
        assert response.status_code == 400


class TestContactDuplicates:
    """Tests for GET /contacts/duplicates."""

    def test_find_duplicates(self, client, db_session, auth_headers):
        # Create two contacts with same email
        c1 = ContactDetails(first_name="John", last_name="Doe", email="dupe@test.com", client_name="Corp A", tenant_id=1)
        c2 = ContactDetails(first_name="Johnny", last_name="Doe", email="dupe@test.com", client_name="Corp B", tenant_id=1)
        db_session.add_all([c1, c2])
        db_session.commit()

        response = client.get("/api/v1/contacts/duplicates", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_groups"] >= 1
        group = next(g for g in data["duplicates"] if g["email"] == "dupe@test.com")
        assert group["count"] == 2

    def test_no_duplicates(self, client, db_session, auth_headers):
        c1 = ContactDetails(first_name="A", last_name="B", email="unique1@test.com", client_name="Corp X", tenant_id=1)
        c2 = ContactDetails(first_name="C", last_name="D", email="unique2@test.com", client_name="Corp Y", tenant_id=1)
        db_session.add_all([c1, c2])
        db_session.commit()

        response = client.get("/api/v1/contacts/duplicates", headers=auth_headers)
        assert response.status_code == 200
        # Should not include unique emails
        data = response.json()
        emails = [g["email"] for g in data["duplicates"]]
        assert "unique1@test.com" not in emails


class TestContactMerge:
    """Tests for POST /contacts/merge."""

    def test_merge_contacts(self, client, db_session, auth_headers, sample_lead):
        primary = ContactDetails(first_name="Primary", last_name="User", email="primary@test.com", client_name="Merge Corp", tenant_id=1)
        secondary = ContactDetails(first_name="Secondary", last_name="User", email="secondary@test.com", client_name="Merge Corp", tenant_id=1)
        db_session.add_all([primary, secondary])
        db_session.flush()

        # Link secondary to lead
        assoc = LeadContactAssociation(lead_id=sample_lead.lead_id, contact_id=secondary.contact_id, tenant_id=1)
        db_session.add(assoc)
        db_session.commit()

        response = client.post(
            "/api/v1/contacts/merge",
            headers=auth_headers,
            json={
                "primary_contact_id": primary.contact_id,
                "merge_contact_ids": [secondary.contact_id],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["merged_count"] == 1
        assert data["associations_transferred"] == 1

        # Secondary should be archived
        db_session.refresh(secondary)
        assert secondary.is_archived is True

    def test_merge_missing_primary(self, client, auth_headers):
        response = client.post(
            "/api/v1/contacts/merge",
            headers=auth_headers,
            json={"primary_contact_id": 99999, "merge_contact_ids": [1]},
        )
        assert response.status_code == 404


class TestJobCancel:
    """Tests for POST /pipelines/jobs/{run_id}/cancel."""

    def test_cancel_running_job(self, client, db_session, auth_headers):
        run = JobRun(pipeline_name="test", status=JobStatus.RUNNING, triggered_by="admin@test.com", tenant_id=1)
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        response = client.post(
            f"/api/v1/pipelines/jobs/{run.run_id}/cancel",
            headers=auth_headers,
        )
        assert response.status_code == 200
        db_session.refresh(run)
        assert run.is_cancel_requested == 1

    def test_cancel_completed_job_fails(self, client, db_session, auth_headers, sample_job_run):
        response = client.post(
            f"/api/v1/pipelines/jobs/{sample_job_run.run_id}/cancel",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_cancel_nonexistent_job(self, client, auth_headers):
        response = client.post(
            "/api/v1/pipelines/jobs/99999/cancel",
            headers=auth_headers,
        )
        assert response.status_code == 404
