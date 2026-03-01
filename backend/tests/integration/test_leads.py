"""Integration tests for leads endpoints."""
import pytest
from datetime import date
from app.db.models.lead import LeadDetails, LeadStatus


class TestLeadsEndpoints:
    """Tests for leads API endpoints."""

    @pytest.fixture
    def sample_lead(self, db_session):
        """Create a sample lead for testing."""
        lead = LeadDetails(
            client_name="Test Company",
            job_title="Test Position",
            state="CA",
            posting_date=date.today(),
            job_link="https://jobs.example.com/1",
            salary_min=50000,
            salary_max=70000,
            source="linkedin",
            lead_status=LeadStatus.NEW,
        )
        db_session.add(lead)
        db_session.commit()
        db_session.refresh(lead)
        return lead

    def test_list_leads(self, client, auth_headers, sample_lead):
        """Test listing leads."""
        response = client.get("/api/v1/leads", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) >= 1

    def test_list_leads_pagination(self, client, auth_headers, db_session):
        """Test leads pagination."""
        # Create multiple leads
        for i in range(15):
            lead = LeadDetails(
                client_name=f"Company {i}",
                job_title=f"Position {i}",
                state="CA",
                source="linkedin",
                lead_status=LeadStatus.NEW,
            )
            db_session.add(lead)
        db_session.commit()

        response = client.get("/api/v1/leads?page=1&page_size=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15
        assert data["pages"] == 2

    def test_get_lead(self, client, auth_headers, sample_lead):
        """Test getting a specific lead."""
        response = client.get(f"/api/v1/leads/{sample_lead.lead_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["lead_id"] == sample_lead.lead_id
        assert data["client_name"] == sample_lead.client_name

    def test_get_lead_not_found(self, client, auth_headers):
        """Test getting a nonexistent lead."""
        response = client.get("/api/v1/leads/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_create_lead(self, client, auth_headers):
        """Test creating a new lead."""
        response = client.post(
            "/api/v1/leads",
            headers=auth_headers,
            json={
                "client_name": "New Company",
                "job_title": "New Position",
                "state": "TX",
                "source": "indeed"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["client_name"] == "New Company"
        assert data["job_title"] == "New Position"
        assert data["lead_status"] == "new"

    def test_create_duplicate_lead(self, client, auth_headers, sample_lead):
        """Test creating a lead with duplicate job_link fails."""
        response = client.post(
            "/api/v1/leads",
            headers=auth_headers,
            json={
                "client_name": "Another Company",
                "job_title": "Another Position",
                "job_link": sample_lead.job_link  # Same link
            }
        )
        assert response.status_code == 400

    def test_update_lead(self, client, auth_headers, sample_lead):
        """Test updating a lead."""
        response = client.put(
            f"/api/v1/leads/{sample_lead.lead_id}",
            headers=auth_headers,
            json={
                "job_title": "Updated Position",
                "lead_status": "enriched"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["job_title"] == "Updated Position"
        assert data["lead_status"] == "enriched"

    def test_delete_lead(self, client, auth_headers, sample_lead):
        """Test deleting (archiving) a lead."""
        response = client.delete(
            f"/api/v1/leads/{sample_lead.lead_id}",
            headers=auth_headers
        )
        assert response.status_code == 204

        # After soft-delete, the lead is archived.
        # The list endpoint filters out archived by default, so it should not appear.
        list_response = client.get("/api/v1/leads", headers=auth_headers)
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        lead_ids = [item["lead_id"] for item in items]
        assert sample_lead.lead_id not in lead_ids

    def test_filter_leads_by_status(self, client, auth_headers, db_session):
        """Test filtering leads by status."""
        # Create leads with different statuses
        for lead_status in [LeadStatus.NEW, LeadStatus.ENRICHED, LeadStatus.VALIDATED]:
            lead = LeadDetails(
                client_name=f"Company {lead_status.value}",
                job_title="Position",
                lead_status=lead_status,
            )
            db_session.add(lead)
        db_session.commit()

        response = client.get(
            "/api/v1/leads?status=enriched",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["lead_status"] == "enriched"

    def test_filter_leads_by_search(self, client, auth_headers, sample_lead):
        """Test searching leads."""
        response = client.get(
            f"/api/v1/leads?search={sample_lead.client_name[:5]}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1

    def test_leads_stats(self, client, auth_headers, sample_lead):
        """Test getting lead statistics."""
        response = client.get("/api/v1/leads/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "by_status" in data
        assert "by_source" in data

    def test_leads_unauthenticated(self, client):
        """Test leads endpoint without authentication."""
        response = client.get("/api/v1/leads")
        assert response.status_code == 401
