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

    def test_docs_endpoint_skips_csp(self, client):
        """Swagger UI needs inline scripts, so CSP is skipped for /docs."""
        resp = client.get("/docs")
        # /docs may redirect, but should not have restrictive CSP
        csp = resp.headers.get("Content-Security-Policy", "")
        # Either no CSP or a permissive one for docs
        if resp.status_code == 200:
            # Docs pages should either have no CSP or a relaxed one
            assert "default-src 'none'" not in csp
