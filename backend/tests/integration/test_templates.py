"""Integration tests for email template endpoints."""
import pytest
from app.db.models.email_template import EmailTemplate, TemplateStatus

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

    def test_create_template(self, client, auth_headers):
        """Test creating a new template."""
        response = client.post(
            "/api/v1/templates",
            headers=auth_headers,
            json={
                "name": "New Template",
                "subject": "Hello {{contact_first_name}}",
                "body_html": "<p>Body</p>",
                "status": "inactive",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Template"
        assert data["status"] == "inactive"

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

    def test_only_one_active(self, client, auth_headers, db_session):
        """Test that activating one template deactivates others."""
        t1 = EmailTemplate(
            name="T1", subject="S1", body_html="<p>1</p>",
            status=TemplateStatus.ACTIVE, is_default=False,
        )
        t2 = EmailTemplate(
            name="T2", subject="S2", body_html="<p>2</p>",
            status=TemplateStatus.INACTIVE, is_default=False,
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
