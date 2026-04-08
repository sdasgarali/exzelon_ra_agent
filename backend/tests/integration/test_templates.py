"""Integration tests for email template endpoints."""
import pytest
from app.db.models.email_template import EmailTemplate, TemplateStatus, TemplateCategory

pytestmark = pytest.mark.integration


class TestTemplateEndpoints:
    """Tests for /api/v1/templates endpoints."""

    def test_list_templates(self, client, auth_headers, sample_template):
        """Test listing templates returns expected structure."""
        response = client.get("/api/v1/templates", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1
        # New per-category active IDs
        assert "active_outreach_template_id" in data
        assert "active_followup_template_id" in data

    def test_create_template(self, client, auth_headers):
        """Test creating a new template with category."""
        response = client.post(
            "/api/v1/templates",
            headers=auth_headers,
            json={
                "name": "New Template",
                "subject": "Hello {{contact_first_name}}",
                "body_html": "<p>Body</p>",
                "status": "inactive",
                "category": "outreach",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Template"
        assert data["status"] == "inactive"
        assert data["category"] == "outreach"

    def test_create_followup_template(self, client, auth_headers):
        """Test creating a follow-up template."""
        response = client.post(
            "/api/v1/templates",
            headers=auth_headers,
            json={
                "name": "Follow-up Template",
                "subject": "Following up on {{job_title}}",
                "body_html": "<p>Follow-up body</p>",
                "status": "inactive",
                "category": "followup",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["category"] == "followup"

    def test_get_template(self, client, auth_headers, sample_template):
        """Test getting a single template by ID."""
        response = client.get(
            f"/api/v1/templates/{sample_template.template_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["template_id"] == sample_template.template_id
        assert data["name"] == sample_template.name
        assert "category" in data

    def test_update_template(self, client, auth_headers, sample_template):
        """Test updating a template."""
        response = client.put(
            f"/api/v1/templates/{sample_template.template_id}",
            headers=auth_headers,
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_activate_template(self, client, auth_headers, sample_template):
        """Test activating a template."""
        response = client.post(
            f"/api/v1/templates/{sample_template.template_id}/activate",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "active"

    def test_delete_template(self, client, auth_headers, sample_template):
        """Test archiving (soft-deleting) a template."""
        response = client.delete(
            f"/api/v1/templates/{sample_template.template_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

    def test_only_one_active_per_category(self, client, auth_headers, db_session, test_tenant):
        """Test that activating one template deactivates others in the SAME category."""
        t1 = EmailTemplate(
            tenant_id=test_tenant.tenant_id,
            name="Outreach T1", subject="S1", body_html="<p>1</p>",
            status=TemplateStatus.ACTIVE, is_default=False,
            category=TemplateCategory.OUTREACH,
        )
        t2 = EmailTemplate(
            tenant_id=test_tenant.tenant_id,
            name="Outreach T2", subject="S2", body_html="<p>2</p>",
            status=TemplateStatus.INACTIVE, is_default=False,
            category=TemplateCategory.OUTREACH,
        )
        db_session.add_all([t1, t2])
        db_session.commit()
        db_session.refresh(t1)
        db_session.refresh(t2)

        # Activate t2
        response = client.post(
            f"/api/v1/templates/{t2.template_id}/activate",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "active"

        # t1 should now be inactive
        r = client.get(
            f"/api/v1/templates/{t1.template_id}",
            headers=auth_headers,
        )
        assert r.json()["status"] == "inactive"

    def test_per_category_active(self, client, auth_headers, db_session, test_tenant):
        """Test that both categories can have an active template simultaneously."""
        t_outreach = EmailTemplate(
            tenant_id=test_tenant.tenant_id,
            name="Active Outreach", subject="S1", body_html="<p>Outreach</p>",
            status=TemplateStatus.ACTIVE, is_default=False,
            category=TemplateCategory.OUTREACH,
        )
        t_followup = EmailTemplate(
            tenant_id=test_tenant.tenant_id,
            name="Active Followup", subject="S2", body_html="<p>Followup</p>",
            status=TemplateStatus.INACTIVE, is_default=False,
            category=TemplateCategory.FOLLOWUP,
        )
        db_session.add_all([t_outreach, t_followup])
        db_session.commit()
        db_session.refresh(t_outreach)
        db_session.refresh(t_followup)

        # Activate follow-up — should NOT deactivate the outreach template
        response = client.post(
            f"/api/v1/templates/{t_followup.template_id}/activate",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "active"
        assert response.json()["category"] == "followup"

        # Outreach should still be active
        r = client.get(
            f"/api/v1/templates/{t_outreach.template_id}",
            headers=auth_headers,
        )
        assert r.json()["status"] == "active"
        assert r.json()["category"] == "outreach"

        # List should show both active IDs
        list_r = client.get("/api/v1/templates", headers=auth_headers)
        list_data = list_r.json()
        assert list_data["active_outreach_template_id"] == t_outreach.template_id
        assert list_data["active_followup_template_id"] == t_followup.template_id

    def test_viewer_cannot_create(self, client, viewer_headers):
        """Test RBAC: viewer role cannot create templates."""
        response = client.post(
            "/api/v1/templates",
            headers=viewer_headers,
            json={
                "name": "Should Fail",
                "subject": "Nope",
                "body_html": "<p>No</p>",
            },
        )
        assert response.status_code == 403
