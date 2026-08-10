"""Integration tests for the clients endpoints — focused on WYSIWYG CSV export.

Mirrors the leads-export regression: the export must apply the same filters as
the list (archived toggle, industry, location, text filters) so it never returns
a header-only "blank" file that doesn't match what the user is viewing.
"""
import pytest
from app.db.models.client import ClientInfo

pytestmark = pytest.mark.integration


class TestClientsExport:
    """CSV export honors the same filters as the clients list."""

    @pytest.fixture
    def sample_client(self, db_session, test_tenant):
        client = ClientInfo(
            tenant_id=test_tenant.tenant_id,
            client_name="Acme Health",
            industry="Healthcare",
            location_state="CA",
        )
        db_session.add(client)
        db_session.commit()
        db_session.refresh(client)
        return client

    @pytest.fixture
    def archived_client(self, db_session, test_tenant):
        client = ClientInfo(
            tenant_id=test_tenant.tenant_id,
            client_name="Archived Manufacturing",
            industry="Manufacturing",
            location_state="NY",
            is_archived=True,
        )
        db_session.add(client)
        db_session.commit()
        db_session.refresh(client)
        return client

    def test_export_requires_auth(self, client):
        response = client.get("/api/v1/clients/export/csv")
        assert response.status_code == 401

    def test_export_default_excludes_archived(self, client, auth_headers, sample_client, archived_client):
        """Default export returns only non-archived clients."""
        response = client.get("/api/v1/clients/export/csv", headers=auth_headers)
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        body = response.text
        assert "Client Name" in body               # header row
        assert "Acme Health" in body               # non-archived present
        assert "Archived Manufacturing" not in body  # archived excluded

    def test_export_show_archived_returns_archived(self, client, auth_headers, sample_client, archived_client):
        """WYSIWYG: viewing archived → export honors show_archived."""
        response = client.get(
            "/api/v1/clients/export/csv",
            headers=auth_headers,
            params={"show_archived": True},
        )
        assert response.status_code == 200
        body = response.text
        assert "Archived Manufacturing" in body   # archived now included
        assert "Acme Health" not in body          # non-archived excluded

    def test_export_honors_industry_filter(self, client, auth_headers, db_session, test_tenant):
        """Export scoped by industry returns only matching clients."""
        for name, industry in [("Alpha Health", "Healthcare"), ("Beta Mfg", "Manufacturing")]:
            db_session.add(ClientInfo(tenant_id=test_tenant.tenant_id, client_name=name, industry=industry))
        db_session.commit()
        response = client.get(
            "/api/v1/clients/export/csv",
            headers=auth_headers,
            params={"industry": "Healthcare"},
        )
        assert response.status_code == 200
        body = response.text
        assert "Alpha Health" in body
        assert "Beta Mfg" not in body

    def test_export_honors_industry_text_filter(self, client, auth_headers, db_session, test_tenant):
        """Excel-style text filter (industry contains) carried via query params."""
        for name, industry in [("Gamma Care", "Healthcare Services"), ("Delta Steel", "Steel")]:
            db_session.add(ClientInfo(tenant_id=test_tenant.tenant_id, client_name=name, industry=industry))
        db_session.commit()
        response = client.get(
            "/api/v1/clients/export/csv",
            headers=auth_headers,
            params={"industry_op": "contains", "industry_val": "Health"},
        )
        assert response.status_code == 200
        body = response.text
        assert "Gamma Care" in body
        assert "Delta Steel" not in body

    def test_export_honors_location_state(self, client, auth_headers, db_session, test_tenant):
        """Export scoped by location_state returns only that state's clients."""
        db_session.add(ClientInfo(tenant_id=test_tenant.tenant_id, client_name="TX Co", location_state="TX"))
        db_session.add(ClientInfo(tenant_id=test_tenant.tenant_id, client_name="WA Co", location_state="WA"))
        db_session.commit()
        response = client.get(
            "/api/v1/clients/export/csv",
            headers=auth_headers,
            params={"location_state": "TX"},
        )
        assert response.status_code == 200
        body = response.text
        assert "TX Co" in body
        assert "WA Co" not in body
