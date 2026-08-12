"""Integration tests for leads endpoints."""
import pytest
from datetime import date
from app.db.models.lead import LeadDetails, LeadStatus

pytestmark = pytest.mark.integration


class TestLeadsEndpoints:
    """Tests for leads API endpoints."""

    @pytest.fixture
    def sample_lead(self, db_session, test_tenant):
        """Create a sample lead for testing."""
        lead = LeadDetails(
            tenant_id=test_tenant.tenant_id,
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

    def test_export_csv_post_with_lead_ids(self, client, auth_headers, sample_lead):
        """POST export with lead_ids in the body streams a CSV (no URL limit)."""
        response = client.post(
            "/api/v1/leads/export/csv",
            headers=auth_headers,
            json={"lead_ids": [sample_lead.lead_id]},
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        body = response.text
        assert "Company Name" in body  # header row
        assert "Test Company" in body  # the exported lead

    def test_export_csv_post_filtered(self, client, auth_headers, sample_lead):
        """POST export honors status/search filters like the GET route."""
        response = client.post(
            "/api/v1/leads/export/csv",
            headers=auth_headers,
            json={"status": "new", "search": "Test Company"},
        )
        assert response.status_code == 200
        assert "Test Company" in response.text

    def test_export_csv_post_unauthenticated(self, client):
        """POST export requires auth."""
        response = client.post("/api/v1/leads/export/csv", json={"lead_ids": [1]})
        assert response.status_code == 401

    @pytest.fixture
    def archived_lead(self, db_session, test_tenant):
        """An archived lead — the scenario that produced the 'blank CSV' bug."""
        lead = LeadDetails(
            tenant_id=test_tenant.tenant_id,
            client_name="Archived Corp",
            job_title="Archived Role",
            state="NY",
            posting_date=date.today(),
            job_link="https://jobs.example.com/arch",
            source="linkedin",
            lead_status=LeadStatus.NEW,
            is_archived=True,
        )
        db_session.add(lead)
        db_session.commit()
        db_session.refresh(lead)
        return lead

    def test_export_default_excludes_archived(self, client, auth_headers, sample_lead, archived_lead):
        """Default export (no show_archived) returns only non-archived leads."""
        response = client.post("/api/v1/leads/export/csv", headers=auth_headers, json={})
        assert response.status_code == 200
        body = response.text
        assert "Test Company" in body       # non-archived present
        assert "Archived Corp" not in body  # archived excluded

    def test_export_show_archived_returns_archived(self, client, auth_headers, sample_lead, archived_lead):
        """WYSIWYG: viewing archived → export honors show_archived and returns them.

        Regression for the header-only 'blank CSV': the export used to ignore the
        archived toggle and always filter is_archived == False.
        """
        response = client.post(
            "/api/v1/leads/export/csv", headers=auth_headers, json={"show_archived": True}
        )
        assert response.status_code == 200
        body = response.text
        assert "Archived Corp" in body       # archived now included
        assert "Test Company" not in body    # non-archived excluded

    def test_export_honors_industry_text_filter(self, client, auth_headers, db_session, test_tenant):
        """Excel-style text filter (industry contains) carried via the JSON body."""
        for name, industry in [("Alpha LLC", "Healthcare"), ("Beta LLC", "Manufacturing")]:
            db_session.add(LeadDetails(
                tenant_id=test_tenant.tenant_id, client_name=name, job_title="Role",
                state="CA", posting_date=date.today(), source="linkedin",
                lead_status=LeadStatus.NEW, industry=industry,
            ))
        db_session.commit()
        response = client.post(
            "/api/v1/leads/export/csv", headers=auth_headers,
            json={"industry_op": "contains", "industry_val": "Health"},
        )
        assert response.status_code == 200
        body = response.text
        assert "Alpha LLC" in body      # matches industry filter
        assert "Beta LLC" not in body   # filtered out

    def test_export_honors_lob_id(self, client, auth_headers, db_session, test_tenant):
        """Export scoped by lob_id returns only that LOB's leads."""
        keep = LeadDetails(
            tenant_id=test_tenant.tenant_id, client_name="LobKeep Inc", job_title="Role",
            state="CA", posting_date=date.today(), source="linkedin",
            lead_status=LeadStatus.NEW, lob_id=42,
        )
        drop = LeadDetails(
            tenant_id=test_tenant.tenant_id, client_name="LobDrop Inc", job_title="Role",
            state="CA", posting_date=date.today(), source="linkedin",
            lead_status=LeadStatus.NEW, lob_id=7,
        )
        db_session.add_all([keep, drop])
        db_session.commit()
        response = client.post(
            "/api/v1/leads/export/csv", headers=auth_headers, json={"lob_id": 42}
        )
        assert response.status_code == 200
        body = response.text
        assert "LobKeep Inc" in body
        assert "LobDrop Inc" not in body

    def test_list_leads(self, client, auth_headers, sample_lead):
        """Test listing leads."""
        response = client.get("/api/v1/leads", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) >= 1

    def test_list_leads_pagination(self, client, auth_headers, db_session, test_tenant):
        """Test leads pagination."""
        # Create multiple leads
        for i in range(15):
            lead = LeadDetails(
                tenant_id=test_tenant.tenant_id,
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

    def _make_hunting_lead(self, db_session, test_tenant):
        lead = LeadDetails(
            tenant_id=test_tenant.tenant_id,
            client_name="Hunting Corp",
            job_title="Recruiter",
            state="NY",
            posting_date=date.today(),
            source="linkedin",
            lead_status=LeadStatus.HUNTING,
        )
        db_session.add(lead)
        db_session.commit()
        db_session.refresh(lead)
        return lead

    def test_blocked_transition_returns_400(self, client, auth_headers, db_session, test_tenant):
        """hunting -> enriched is not allowed; without force it is rejected."""
        lead = self._make_hunting_lead(db_session, test_tenant)
        response = client.put(
            f"/api/v1/leads/{lead.lead_id}",
            headers=auth_headers,
            json={"lead_status": "enriched"},
        )
        assert response.status_code == 400
        assert "Cannot transition from 'hunting' to 'enriched'" in response.json()["detail"]

    def test_admin_can_force_blocked_transition(self, client, auth_headers, db_session, test_tenant):
        """An admin may override the blocked transition with ?force=true."""
        lead = self._make_hunting_lead(db_session, test_tenant)
        response = client.put(
            f"/api/v1/leads/{lead.lead_id}?force=true",
            headers=auth_headers,
            json={"lead_status": "enriched"},
        )
        assert response.status_code == 200
        assert response.json()["lead_status"] == "enriched"

    def test_operator_cannot_force_blocked_transition(self, client, operator_headers, db_session, test_tenant):
        """A non-admin cannot override even when passing force=true."""
        lead = self._make_hunting_lead(db_session, test_tenant)
        response = client.put(
            f"/api/v1/leads/{lead.lead_id}?force=true",
            headers=operator_headers,
            json={"lead_status": "enriched"},
        )
        assert response.status_code == 400

    def test_list_leads_exposes_mailing_status(self, client, auth_headers, sample_lead):
        """The list response carries the derived mailing_status + campaign_id fields."""
        response = client.get("/api/v1/leads", headers=auth_headers)
        assert response.status_code == 200
        item = next(i for i in response.json()["items"] if i["lead_id"] == sample_lead.lead_id)
        # Un-enrolled, never downloaded -> Not-Mailed, no campaign id.
        assert item["mailing_status"] == "Not-Mailed"
        assert item["campaign_id"] is None

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

    def test_filter_leads_by_status(self, client, auth_headers, db_session, test_tenant):
        """Test filtering leads by status."""
        # Create leads with different statuses
        for lead_status in [LeadStatus.NEW, LeadStatus.ENRICHED, LeadStatus.VALIDATED]:
            lead = LeadDetails(
                tenant_id=test_tenant.tenant_id,
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

    def test_excel_text_filter_company_contains(self, client, auth_headers, db_session, test_tenant):
        """Excel-style Text Filter: Company Name 'contains' works even for text not in any checklist."""
        for name in ["Northwind Traders", "Contoso Ltd", "Northern Lights Co"]:
            db_session.add(LeadDetails(tenant_id=test_tenant.tenant_id, client_name=name,
                                       job_title="Ops Manager", lead_status=LeadStatus.NEW))
        db_session.commit()
        resp = client.get("/api/v1/leads?company_op=contains&company_val=north", headers=auth_headers)
        assert resp.status_code == 200
        names = {i["client_name"] for i in resp.json()["items"]}
        assert "Northwind Traders" in names and "Northern Lights Co" in names
        assert "Contoso Ltd" not in names

    def test_excel_text_filter_whole_word(self, client, auth_headers, db_session, test_tenant):
        """Whole-word op matches 'IT' as a token, not the 'it' inside other words."""
        for ind in ["IT Services", "Global IT", "Litigation", "Digital Media"]:
            db_session.add(LeadDetails(tenant_id=test_tenant.tenant_id, client_name=f"Co {ind}",
                                       job_title="Manager", industry=ind, lead_status=LeadStatus.NEW))
        db_session.commit()
        resp = client.get("/api/v1/leads?industry_op=word&industry_val=IT", headers=auth_headers)
        assert resp.status_code == 200
        inds = {i.get("industry") for i in resp.json()["items"]}
        assert "IT Services" in inds and "Global IT" in inds
        assert "Litigation" not in inds and "Digital Media" not in inds

    def test_excel_text_filter_title_custom_or(self, client, auth_headers, db_session, test_tenant):
        """Custom Filter with OR across two conditions on Job Title."""
        for t in ["Warehouse Manager", "Plant Director", "Software Engineer"]:
            db_session.add(LeadDetails(tenant_id=test_tenant.tenant_id, client_name=f"Co {t}",
                                       job_title=t, lead_status=LeadStatus.NEW))
        db_session.commit()
        resp = client.get(
            "/api/v1/leads?title_op=contains&title_val=manager&title_op2=ends&title_val2=Director&title_conj=or",
            headers=auth_headers)
        assert resp.status_code == 200
        titles = {i["job_title"] for i in resp.json()["items"]}
        assert titles >= {"Warehouse Manager", "Plant Director"}
        assert "Software Engineer" not in titles

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
