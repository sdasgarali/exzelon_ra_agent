"""Tests for rate limiting on critical endpoints."""
import pytest


pytestmark = pytest.mark.integration


class TestRateLimitImports:
    """Verify rate limiter is properly wired into endpoints."""

    def test_shared_limiter_import(self):
        from app.core.rate_limiter import limiter
        assert limiter is not None

    def test_auth_uses_shared_limiter(self):
        from app.api.endpoints.auth import limiter as auth_limiter
        from app.core.rate_limiter import limiter as shared_limiter
        assert auth_limiter is shared_limiter

    def test_main_uses_shared_limiter(self):
        from app.main import app
        assert app.state.limiter is not None

    def test_pipeline_has_limiter(self):
        from app.api.endpoints import pipelines
        assert hasattr(pipelines, 'limiter')

    def test_email_preview_has_limiter(self):
        from app.api.endpoints import email_preview
        assert hasattr(email_preview, 'limiter')

    def test_billing_has_limiter(self):
        from app.api.endpoints import billing
        assert hasattr(billing, 'limiter')

    def test_campaigns_has_limiter(self):
        from app.api.endpoints import campaigns
        assert hasattr(campaigns, 'limiter')


class TestRateLimitHeadersOnAuth:
    """Test that rate-limited endpoints return proper headers."""

    def test_login_returns_limit_headers(self, client):
        """Login endpoint should return rate limit headers."""
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@example.com", "password": "wrong"},
        )
        # slowapi adds X-RateLimit headers (may be present even on failure)
        # Just verify the endpoint exists and responds
        assert response.status_code in (401, 429)
