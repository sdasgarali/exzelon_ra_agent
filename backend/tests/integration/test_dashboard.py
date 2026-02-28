"""Integration tests for dashboard endpoints."""
import pytest
from datetime import date, timedelta


class TestDashboardEndpoints:
    """Tests for /api/v1/dashboard endpoints."""

    def test_get_kpis(self, client, auth_headers):
        """Test getting KPIs returns expected structure."""
        response = client.get("/api/v1/dashboard/kpis", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "period" in data
        assert "total_leads" in data
        assert "total_contacts" in data
        assert "emails_sent" in data
        assert "bounce_rate_percent" in data
        assert "reply_rate_percent" in data

    def test_get_kpis_with_date_range(self, client, auth_headers):
        """Test KPIs with explicit date range."""
        today = date.today()
        from_str = (today - timedelta(days=7)).isoformat()
        to_str = today.isoformat()
        response = client.get(
            f"/api/v1/dashboard/kpis?from_date={from_str}&to_date={to_str}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period"]["from"] == from_str
        assert data["period"]["to"] == to_str

    def test_get_leads_sourced(self, client, auth_headers, sample_lead):
        """Test leads-sourced tab returns a list."""
        response = client.get("/api/v1/dashboard/leads-sourced", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_contacts_identified(self, client, auth_headers):
        """Test contacts-identified tab returns a list."""
        response = client.get(
            "/api/v1/dashboard/contacts-identified", headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_outreach_sent(self, client, auth_headers):
        """Test outreach-sent tab returns a list."""
        response = client.get("/api/v1/dashboard/outreach-sent", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_client_categories(self, client, auth_headers):
        """Test client-categories tab returns summary and clients."""
        response = client.get(
            "/api/v1/dashboard/client-categories", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "clients" in data

    def test_get_trends(self, client, auth_headers):
        """Test trends endpoint returns daily data."""
        response = client.get("/api/v1/dashboard/trends", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "daily_leads" in data
        assert "daily_outreach" in data

    def test_get_stats(self, client, auth_headers, sample_lead):
        """Test consolidated stats endpoint."""
        response = client.get("/api/v1/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "leads" in data
        assert data["leads"]["total"] >= 1
        assert "by_status" in data["leads"]
        assert "by_source" in data["leads"]
        assert "contacts" in data
        assert "outreach" in data
        assert "mailboxes" in data
        assert "templates" in data
