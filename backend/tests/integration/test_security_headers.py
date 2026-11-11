"""Tests for security headers middleware — verifies headers on all responses."""
import pytest


pytestmark = pytest.mark.integration


class TestSecurityHeaders:
    """Test that security headers are present on API responses."""

    def test_health_endpoint_has_security_headers(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "strict-origin" in resp.headers.get("Referrer-Policy", "").lower()

    def test_api_endpoint_has_csp(self, client, auth_headers):
        resp = client.get("/api/v1/leads", headers=auth_headers)
        csp = resp.headers.get("Content-Security-Policy", "")
        # CSP should be present on non-docs endpoints
        assert "default-src" in csp or resp.status_code == 403

    def test_permissions_policy_present(self, client):
        resp = client.get("/health")
        pp = resp.headers.get("Permissions-Policy", "")
        assert "camera=()" in pp
        assert "microphone=()" in pp

    @pytest.mark.parametrize("path", ["/api/docs", "/api/redoc", "/api/openapi.json"])
    def test_docs_endpoints_skip_csp(self, client, path):
        """Swagger UI / ReDoc load their bundles from a CDN, so the docs paths get no CSP.

        Regression: the exemption used to list /docs while the app serves /api/docs,
        so the CSP blocked the Swagger bundle and the public API docs page was blank.
        """
        resp = client.get(path)
        assert resp.status_code == 200
        assert "Content-Security-Policy" not in resp.headers
        # The other security headers still apply to the docs pages.
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"


class TestPublicApiSchema:
    """The published OpenAPI schema lists the customer API, not platform-ops routes."""

    def test_admin_and_backup_routes_hidden_from_schema(self, client):
        paths = client.get("/api/openapi.json").json()["paths"]
        assert not [p for p in paths if p.startswith("/api/v1/admin/tenants")]
        assert not [p for p in paths if p.startswith("/api/v1/backups")]
        # Customer-facing routes are still documented.
        assert any(p.startswith("/api/v1/leads") for p in paths)

    def test_hidden_routes_still_served(self, client, super_admin_headers):
        """Leaving a route out of the schema must not unmount it."""
        resp = client.get("/api/v1/backups", headers=super_admin_headers)
        assert resp.status_code != 404
