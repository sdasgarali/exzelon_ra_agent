"""Integration tests for OAuth2 mailbox endpoints.

Covers:
- GET  /api/v1/mailboxes/oauth/initiate
- POST /api/v1/mailboxes/oauth/callback

These endpoints manage the Microsoft 365 OAuth2 Authorization Code flow
for connecting sender mailboxes.
"""
import base64
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# GET /api/v1/mailboxes/oauth/initiate
# ---------------------------------------------------------------------------


class TestOAuthInitiate:
    """Tests for the OAuth2 initiation endpoint."""

    def test_requires_auth(self, client):
        """Must return 401 when no token is provided."""
        resp = client.get("/api/v1/mailboxes/oauth/initiate", params={"email": "x@x.com"})
        assert resp.status_code == 401

    def test_returns_400_when_oauth_not_configured(self, client, auth_headers):
        """With default test env (no MS365_OAUTH_CLIENT_ID), should return 400."""
        resp = client.get(
            "/api/v1/mailboxes/oauth/initiate",
            params={"email": "user@example.com"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "MS365 OAuth not configured" in resp.json()["detail"]

    @patch("app.core.config.settings.MS365_OAUTH_CLIENT_ID", "test-client-id")
    @patch("app.core.config.settings.MS365_OAUTH_TENANT_ID", "common")
    @patch("app.core.config.settings.MS365_OAUTH_REDIRECT_URI", "https://example.com/cb")
    def test_returns_authorization_url(self, client, auth_headers):
        """When OAuth is configured, returns a valid authorization URL."""
        resp = client.get(
            "/api/v1/mailboxes/oauth/initiate",
            params={"email": "user@example.com"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "authorization_url" in data
        url = data["authorization_url"]
        assert "login.microsoftonline.com" in url
        assert "test-client-id" in url

    @patch("app.core.config.settings.MS365_OAUTH_CLIENT_ID", "test-client-id")
    @patch("app.core.config.settings.MS365_OAUTH_TENANT_ID", "common")
    @patch("app.core.config.settings.MS365_OAUTH_REDIRECT_URI", "https://example.com/cb")
    def test_uses_mailbox_email_when_mailbox_id_provided(
        self, client, auth_headers, sample_mailbox
    ):
        """When mailbox_id is given, the URL should use the mailbox's email."""
        resp = client.get(
            "/api/v1/mailboxes/oauth/initiate",
            params={"mailbox_id": sample_mailbox.mailbox_id},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        url = resp.json()["authorization_url"]
        # The login_hint should contain the sample mailbox email (URL-encoded @)
        assert "test%40example.com" in url or "test@example.com" in url

    @patch("app.core.config.settings.MS365_OAUTH_CLIENT_ID", "test-client-id")
    @patch("app.core.config.settings.MS365_OAUTH_TENANT_ID", "common")
    @patch("app.core.config.settings.MS365_OAUTH_REDIRECT_URI", "https://example.com/cb")
    def test_requires_mailbox_id_or_email(self, client, auth_headers):
        """Must return 400 when neither mailbox_id nor email is provided."""
        resp = client.get(
            "/api/v1/mailboxes/oauth/initiate",
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "Either mailbox_id or email" in resp.json()["detail"]

    @patch("app.core.config.settings.MS365_OAUTH_CLIENT_ID", "test-client-id")
    @patch("app.core.config.settings.MS365_OAUTH_TENANT_ID", "common")
    @patch("app.core.config.settings.MS365_OAUTH_REDIRECT_URI", "https://example.com/cb")
    def test_returns_404_for_nonexistent_mailbox_id(self, client, auth_headers):
        """Must return 404 when the given mailbox_id does not exist."""
        resp = client.get(
            "/api/v1/mailboxes/oauth/initiate",
            params={"mailbox_id": 99999},
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/mailboxes/oauth/callback
# ---------------------------------------------------------------------------


class TestOAuthCallback:
    """Tests for the OAuth2 callback endpoint."""

    def test_requires_auth(self, client):
        """Must return 401 when no token is provided."""
        resp = client.post(
            "/api/v1/mailboxes/oauth/callback",
            json={"code": "abc", "state": "xyz"},
        )
        assert resp.status_code == 401

    def test_returns_400_when_code_missing(self, client, auth_headers):
        """Must return 400 when 'code' is missing from the body."""
        resp = client.post(
            "/api/v1/mailboxes/oauth/callback",
            json={"state": "some-state"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "code" in resp.json()["detail"].lower() or "required" in resp.json()["detail"].lower()

    def test_returns_400_when_state_missing(self, client, auth_headers):
        """Must return 400 when 'state' is missing from the body."""
        resp = client.post(
            "/api/v1/mailboxes/oauth/callback",
            json={"code": "auth-code-xyz"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_returns_400_with_invalid_state(self, client, auth_headers):
        """Must return 400 when 'state' is not valid base64 JSON."""
        resp = client.post(
            "/api/v1/mailboxes/oauth/callback",
            json={"code": "auth-code", "state": "not-valid-base64!!!"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "Invalid state" in resp.json()["detail"]

    @patch("app.services.oauth_helper.exchange_code_for_tokens")
    def test_success_stores_tokens_on_mailbox(
        self, mock_exchange, client, auth_headers, db_session, sample_mailbox, admin_user
    ):
        """Full success path: exchange tokens and store encrypted values on the mailbox."""
        mock_exchange.return_value = {
            "access_token": "access-token-123",
            "refresh_token": "refresh-token-456",
            "expires_in": 3600,
        }

        # Build a valid state payload with the sample mailbox's ID
        state_data = {
            "mailbox_id": sample_mailbox.mailbox_id,
            "email": sample_mailbox.email,
            "user_id": admin_user.user_id,
        }
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        resp = client.post(
            "/api/v1/mailboxes/oauth/callback",
            json={"code": "valid-auth-code", "state": state},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["mailbox_id"] == sample_mailbox.mailbox_id
        assert "OAuth2 connected" in data["message"]

        # Verify the mailbox was updated in the database
        db_session.refresh(sample_mailbox)
        assert sample_mailbox.auth_method == "oauth2"
        assert sample_mailbox.oauth_access_token is not None
        assert sample_mailbox.oauth_refresh_token is not None
        assert sample_mailbox.oauth_token_expires_at is not None

    def test_returns_404_for_nonexistent_mailbox_in_state(self, client, auth_headers, admin_user):
        """Must return 404 when the mailbox_id in the state does not exist."""
        state_data = {
            "mailbox_id": 99999,
            "email": "ghost@example.com",
            "user_id": admin_user.user_id,
        }
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        resp = client.post(
            "/api/v1/mailboxes/oauth/callback",
            json={"code": "auth-code", "state": state},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @patch("app.services.oauth_helper.exchange_code_for_tokens")
    def test_returns_400_when_token_exchange_fails(
        self, mock_exchange, client, auth_headers, db_session, sample_mailbox, admin_user
    ):
        """If exchange_code_for_tokens raises ValueError, endpoint returns 400."""
        mock_exchange.side_effect = ValueError("Token exchange failed (400): invalid_grant")

        state_data = {
            "mailbox_id": sample_mailbox.mailbox_id,
            "email": sample_mailbox.email,
            "user_id": admin_user.user_id,
        }
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        resp = client.post(
            "/api/v1/mailboxes/oauth/callback",
            json={"code": "expired-code", "state": state},
            headers=auth_headers,
        )

        assert resp.status_code == 400
        assert "Token exchange failed" in resp.json()["detail"]
