"""End-to-end tests for the complete workflow."""
import pytest
from datetime import date


class TestCompleteWorkflow:
    """End-to-end tests for the complete cold-email automation workflow."""

    def test_complete_workflow(self, client, auth_headers, db_session):
        """Test the complete workflow."""
        lead_response = client.post(
            "/api/v1/leads",
            headers=auth_headers,
            json={
                "client_name": "E2E Test Company",
                "job_title": "Warehouse Manager",
                "state": "CA",
                "source": "linkedin",
                "salary_min": 50000,
                "salary_max": 70000,
                "posting_date": date.today().isoformat()
            }
        )
        assert lead_response.status_code == 201
        lead = lead_response.json()
        lead_id = lead["lead_id"]

        contact_response = client.post(
            "/api/v1/contacts",
            headers=auth_headers,
            json={
                "client_name": "E2E Test Company",
                "first_name": "Test",
                "last_name": "Contact",
                "email": "test.contact@e2etestcompany.com",
                "title": "HR Manager"
            }
        )
        assert contact_response.status_code == 201
        contact = contact_response.json()
        contact_id = contact["contact_id"]

        update_response = client.put(
            f"/api/v1/contacts/{contact_id}",
            headers=auth_headers,
            json={"validation_status": "valid"}
        )
        assert update_response.status_code == 200

        lead_update_response = client.put(
            f"/api/v1/leads/{lead_id}",
            headers=auth_headers,
            json={
                "lead_status": "enriched",
                "first_name": contact["first_name"],
                "last_name": contact["last_name"],
                "contact_email": contact["email"]
            }
        )
        assert lead_update_response.status_code == 200

        lead_get_response = client.get(f"/api/v1/leads/{lead_id}", headers=auth_headers)
        assert lead_get_response.status_code == 200
        updated_lead = lead_get_response.json()
        assert updated_lead["lead_status"] == "enriched"
        assert updated_lead["contact_email"] == contact["email"]

        kpis_response = client.get("/api/v1/dashboard/kpis", headers=auth_headers)
        assert kpis_response.status_code == 200
        kpis = kpis_response.json()
        assert kpis["total_leads"] >= 1
        assert kpis["total_contacts"] >= 1

    def test_client_lifecycle(self, client, auth_headers):
        """Test client creation and category computation."""
        client_response = client.post(
            "/api/v1/clients",
            headers=auth_headers,
            json={
                "client_name": "Lifecycle Test Company",
                "industry": "Healthcare",
                "company_size": "51-200"
            }
        )
        assert client_response.status_code == 201
        client_data = client_response.json()
        client_id = client_data["client_id"]
        assert client_data["client_category"] == "prospect"

        update_response = client.put(
            f"/api/v1/clients/{client_id}",
            headers=auth_headers,
            json={"status": "active"}
        )
        assert update_response.status_code == 200

        refresh_response = client.post(
            f"/api/v1/clients/{client_id}/refresh-category",
            headers=auth_headers
        )
        assert refresh_response.status_code == 200

    def test_user_roles_access(self, client, auth_headers, operator_headers, viewer_headers):
        """Test that different roles have appropriate access."""
        # Admin (tenant_admin) cannot access /users — requires super_admin
        admin_users_response = client.get("/api/v1/users", headers=auth_headers)
        assert admin_users_response.status_code == 403

        viewer_leads_response = client.get("/api/v1/leads", headers=viewer_headers)
        assert viewer_leads_response.status_code == 200

        viewer_users_response = client.get("/api/v1/users", headers=viewer_headers)
        assert viewer_users_response.status_code == 403

    def test_pipeline_runs_listing(self, client, auth_headers):
        """Test listing pipeline runs."""
        response = client.get("/api/v1/pipelines/runs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_settings_management(self, client, sa_headers):
        """Test settings initialization and retrieval (Super Admin only)."""
        init_response = client.post("/api/v1/settings/initialize", headers=sa_headers)
        assert init_response.status_code == 200

        list_response = client.get("/api/v1/settings", headers=sa_headers)
        assert list_response.status_code == 200
        settings = list_response.json()
        assert len(settings) > 0

    def test_dashboard_tabs(self, client, auth_headers, db_session):
        """Test all dashboard tabs return data."""
        leads_response = client.get("/api/v1/dashboard/leads-sourced", headers=auth_headers)
        assert leads_response.status_code == 200

        contacts_response = client.get("/api/v1/dashboard/contacts-identified", headers=auth_headers)
        assert contacts_response.status_code == 200

        outreach_response = client.get("/api/v1/dashboard/outreach-sent", headers=auth_headers)
        assert outreach_response.status_code == 200

        categories_response = client.get("/api/v1/dashboard/client-categories", headers=auth_headers)
        assert categories_response.status_code == 200

        kpis_response = client.get("/api/v1/dashboard/kpis", headers=auth_headers)
        assert kpis_response.status_code == 200

        trends_response = client.get("/api/v1/dashboard/trends", headers=auth_headers)
        assert trends_response.status_code == 200


class TestNegativeScenarios:
    """Negative test scenarios."""

    def test_invalid_token(self, client):
        """Test invalid JWT token is rejected."""
        headers = {"Authorization": "Bearer invalid_token"}
        response = client.get("/api/v1/leads", headers=headers)
        assert response.status_code == 401

    def test_expired_token_format(self, client):
        """Test malformed token is rejected."""
        headers = {"Authorization": "Bearer "}
        response = client.get("/api/v1/leads", headers=headers)
        assert response.status_code == 401

    def test_missing_required_fields(self, client, auth_headers):
        """Test creating lead without required fields fails."""
        response = client.post(
            "/api/v1/leads",
            headers=auth_headers,
            json={}
        )
        assert response.status_code == 422

    def test_invalid_email_format(self, client, auth_headers):
        """Test creating contact with invalid email fails."""
        response = client.post(
            "/api/v1/contacts",
            headers=auth_headers,
            json={
                "client_name": "Test Company",
                "first_name": "John",
                "last_name": "Doe",
                "email": "not-an-email"
            }
        )
        assert response.status_code == 422

    def test_delete_nonexistent_resource(self, client, auth_headers):
        """Test deleting nonexistent resource returns 404."""
        response = client.delete("/api/v1/leads/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_update_nonexistent_resource(self, client, auth_headers):
        """Test updating nonexistent resource returns 404."""
        response = client.put(
            "/api/v1/leads/99999",
            headers=auth_headers,
            json={"job_title": "New Title"}
        )
        assert response.status_code == 404
