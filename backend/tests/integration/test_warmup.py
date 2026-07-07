"""Integration tests for warmup engine endpoints."""
import pytest

pytestmark = pytest.mark.integration


class TestWarmupEndpoints:
    """Tests for /api/v1/warmup endpoints."""

    def test_get_warmup_status(self, client, super_admin_headers, sample_mailbox):
        """Test warmup status returns mailbox list and aggregate counts."""
        response = client.get("/api/v1/warmup/status", headers=super_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "mailboxes" in data
        assert "total_mailboxes" in data
        assert data["total_mailboxes"] >= 1

    def test_get_warmup_config(self, client, super_admin_headers):
        """Test warmup config returns phase settings and thresholds."""
        response = client.get("/api/v1/warmup/config", headers=super_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "phase_1" in data
        assert "bounce_rate_good" in data

    def test_update_warmup_config(self, client, super_admin_headers):
        """Test updating warmup config (admin only)."""
        response = client.put(
            "/api/v1/warmup/config",
            headers=super_admin_headers,
            json={"bounce_rate_good": 1.5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "updated_keys" in data

    def test_list_warmup_profiles(self, client, super_admin_headers, sample_warmup_profile):
        """Test listing warmup profiles."""
        response = client.get("/api/v1/warmup/profiles", headers=super_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1

    def test_get_health_scores(self, client, super_admin_headers, sample_mailbox):
        """Test health scores returns per-mailbox scores."""
        response = client.get("/api/v1/warmup/health-scores", headers=super_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "mailboxes" in data
        assert "avg_health_score" in data

    def test_list_alerts(self, client, super_admin_headers):
        """Test listing warmup alerts."""
        response = client.get("/api/v1/warmup/alerts", headers=super_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "unread_count" in data

    def test_viewer_cannot_modify(self, client, viewer_headers):
        """Test RBAC: viewer cannot update warmup config."""
        response = client.put(
            "/api/v1/warmup/config",
            headers=viewer_headers,
            json={"bounce_rate_good": 1.0},
        )
        assert response.status_code == 403
