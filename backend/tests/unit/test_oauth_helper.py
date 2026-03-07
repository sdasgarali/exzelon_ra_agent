"""Unit tests for the OAuth2 helper module (app/services/oauth_helper.py).

Tests cover:
- XOAUTH2 string construction
- Authorization URL generation
- Token exchange (mocked HTTP)
- Token refresh (mocked HTTP)
- Access token retrieval with expiry logic
- SMTP and IMAP authentication dispatch
"""
import base64
import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timedelta

from app.services.oauth_helper import (
    build_xoauth2_string,
    get_oauth_authorization_url,
    exchange_code_for_tokens,
    refresh_oauth_token,
    get_valid_access_token,
    smtp_authenticate,
    imap_authenticate,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# build_xoauth2_string
# ---------------------------------------------------------------------------


class TestBuildXoauth2String:
    """Tests for the XOAUTH2 SASL string builder."""

    def test_produces_valid_base64(self):
        """The result must be valid base64."""
        result = build_xoauth2_string("user@example.com", "tok_abc")
        # Should not raise
        decoded = base64.b64decode(result).decode()
        assert isinstance(decoded, str)

    def test_contains_correct_format(self):
        """Decoded string must follow user={email}\\x01auth=Bearer {token}\\x01\\x01."""
        result = build_xoauth2_string("alice@contoso.com", "my-access-token")
        decoded = base64.b64decode(result).decode()
        expected = "user=alice@contoso.com\x01auth=Bearer my-access-token\x01\x01"
        assert decoded == expected

    def test_different_inputs_produce_different_output(self):
        """Sanity: different email / token combos yield distinct strings."""
        a = build_xoauth2_string("a@x.com", "tok1")
        b = build_xoauth2_string("b@x.com", "tok2")
        assert a != b


# ---------------------------------------------------------------------------
# get_oauth_authorization_url
# ---------------------------------------------------------------------------


class TestGetOAuthAuthorizationUrl:
    """Tests for authorization URL generation."""

    @patch("app.services.oauth_helper.settings")
    def test_returns_microsoft_login_url(self, mock_settings):
        mock_settings.MS365_OAUTH_CLIENT_ID = "test-client-id"
        mock_settings.MS365_OAUTH_TENANT_ID = "common"
        mock_settings.MS365_OAUTH_REDIRECT_URI = "https://example.com/callback"

        url = get_oauth_authorization_url("user@example.com", state="abc")
        assert "login.microsoftonline.com" in url

    @patch("app.services.oauth_helper.settings")
    def test_url_contains_required_params(self, mock_settings):
        mock_settings.MS365_OAUTH_CLIENT_ID = "cid-123"
        mock_settings.MS365_OAUTH_TENANT_ID = "common"
        mock_settings.MS365_OAUTH_REDIRECT_URI = "https://example.com/cb"

        url = get_oauth_authorization_url("user@example.com", state="s1")
        assert "client_id=cid-123" in url
        assert "redirect_uri=" in url
        assert "scope=" in url
        assert "state=s1" in url
        assert "login_hint=user%40example.com" in url

    @patch("app.services.oauth_helper.settings")
    def test_uses_common_tenant_when_none_specified(self, mock_settings):
        mock_settings.MS365_OAUTH_CLIENT_ID = "cid"
        mock_settings.MS365_OAUTH_TENANT_ID = ""
        mock_settings.MS365_OAUTH_REDIRECT_URI = "https://example.com/cb"

        url = get_oauth_authorization_url("u@x.com")
        assert "/common/oauth2/v2.0/authorize" in url

    @patch("app.services.oauth_helper.settings")
    def test_uses_custom_tenant_when_provided(self, mock_settings):
        mock_settings.MS365_OAUTH_CLIENT_ID = "cid"
        mock_settings.MS365_OAUTH_TENANT_ID = "default-tenant"
        mock_settings.MS365_OAUTH_REDIRECT_URI = "https://example.com/cb"

        url = get_oauth_authorization_url("u@x.com", tenant_id="my-tenant-uuid")
        assert "/my-tenant-uuid/oauth2/v2.0/authorize" in url
        # The default tenant should NOT appear
        assert "default-tenant" not in url


# ---------------------------------------------------------------------------
# exchange_code_for_tokens
# ---------------------------------------------------------------------------


class TestExchangeCodeForTokens:
    """Tests for the authorization code exchange."""

    @patch("app.services.oauth_helper.settings")
    @patch("app.services.oauth_helper.httpx.Client")
    def test_success_returns_tokens(self, mock_client_cls, mock_settings):
        mock_settings.MS365_OAUTH_CLIENT_ID = "cid"
        mock_settings.MS365_OAUTH_CLIENT_SECRET = "secret"
        mock_settings.MS365_OAUTH_TENANT_ID = "common"
        mock_settings.MS365_OAUTH_REDIRECT_URI = "https://example.com/cb"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "at-123",
            "refresh_token": "rt-456",
            "expires_in": 3600,
        }

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        result = exchange_code_for_tokens("auth-code-xyz")

        assert result["access_token"] == "at-123"
        assert result["refresh_token"] == "rt-456"
        assert result["expires_in"] == 3600

    @patch("app.services.oauth_helper.settings")
    @patch("app.services.oauth_helper.httpx.Client")
    def test_failure_raises_value_error(self, mock_client_cls, mock_settings):
        mock_settings.MS365_OAUTH_CLIENT_ID = "cid"
        mock_settings.MS365_OAUTH_CLIENT_SECRET = "secret"
        mock_settings.MS365_OAUTH_TENANT_ID = "common"
        mock_settings.MS365_OAUTH_REDIRECT_URI = "https://example.com/cb"

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant: The code has expired."

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        with pytest.raises(ValueError, match="Token exchange failed"):
            exchange_code_for_tokens("expired-code")


# ---------------------------------------------------------------------------
# refresh_oauth_token
# ---------------------------------------------------------------------------


class TestRefreshOAuthToken:
    """Tests for token refresh."""

    @patch("app.services.oauth_helper.settings")
    @patch("app.services.oauth_helper.httpx.Client")
    def test_success_returns_new_tokens(self, mock_client_cls, mock_settings):
        mock_settings.MS365_OAUTH_CLIENT_ID = "cid"
        mock_settings.MS365_OAUTH_CLIENT_SECRET = "secret"
        mock_settings.MS365_OAUTH_TENANT_ID = "common"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "expires_in": 3600,
        }

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        result = refresh_oauth_token("old-rt")

        assert result["access_token"] == "new-at"
        assert result["refresh_token"] == "new-rt"
        assert result["expires_in"] == 3600

    @patch("app.services.oauth_helper.settings")
    @patch("app.services.oauth_helper.httpx.Client")
    def test_failure_raises_value_error(self, mock_client_cls, mock_settings):
        mock_settings.MS365_OAUTH_CLIENT_ID = "cid"
        mock_settings.MS365_OAUTH_CLIENT_SECRET = "secret"
        mock_settings.MS365_OAUTH_TENANT_ID = "common"

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "invalid_grant: refresh token expired"

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        with pytest.raises(ValueError, match="Token refresh failed"):
            refresh_oauth_token("bad-refresh-token")


# ---------------------------------------------------------------------------
# get_valid_access_token
# ---------------------------------------------------------------------------


class TestGetValidAccessToken:
    """Tests for the token-validity gate that decides whether to refresh."""

    @patch("app.services.oauth_helper.decrypt_field")
    def test_returns_existing_token_when_not_expired(self, mock_decrypt):
        """If the token expires in the future (beyond 5-min buffer), return it."""
        mock_decrypt.side_effect = lambda v: f"plain-{v}"

        mailbox = MagicMock()
        mailbox.oauth_refresh_token = "enc-rt"
        mailbox.oauth_access_token = "enc-at"
        mailbox.oauth_token_expires_at = datetime.utcnow() + timedelta(hours=1)
        mailbox.oauth_tenant_id = "tid"

        db = MagicMock()

        token = get_valid_access_token(db, mailbox)
        assert token == "plain-enc-at"
        db.commit.assert_not_called()  # No refresh should have happened

    @patch("app.services.oauth_helper.encrypt_field", side_effect=lambda v: f"enc-{v}")
    @patch("app.services.oauth_helper.decrypt_field", side_effect=lambda v: f"plain-{v}")
    @patch("app.services.oauth_helper.refresh_oauth_token")
    def test_refreshes_when_token_expired(self, mock_refresh, mock_decrypt, mock_encrypt):
        """If the token has expired, refresh and persist new tokens."""
        mock_refresh.return_value = {
            "access_token": "fresh-at",
            "refresh_token": "fresh-rt",
            "expires_in": 3600,
        }

        mailbox = MagicMock()
        mailbox.oauth_refresh_token = "enc-old-rt"
        mailbox.oauth_access_token = "enc-old-at"
        mailbox.oauth_token_expires_at = datetime.utcnow() - timedelta(minutes=10)
        mailbox.oauth_tenant_id = "tid"

        db = MagicMock()

        token = get_valid_access_token(db, mailbox)
        assert token == "fresh-at"
        db.commit.assert_called_once()
        # Verify new tokens were encrypted and stored
        assert mailbox.oauth_access_token == "enc-fresh-at"
        assert mailbox.oauth_refresh_token == "enc-fresh-rt"

    @patch("app.services.oauth_helper.encrypt_field", side_effect=lambda v: f"enc-{v}")
    @patch("app.services.oauth_helper.decrypt_field", side_effect=lambda v: f"plain-{v}")
    @patch("app.services.oauth_helper.refresh_oauth_token")
    def test_refreshes_when_token_is_none(self, mock_refresh, mock_decrypt, mock_encrypt):
        """If access_token is None (never fetched), refresh from refresh_token."""
        mock_refresh.return_value = {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "expires_in": 3600,
        }

        mailbox = MagicMock()
        mailbox.oauth_refresh_token = "enc-rt"
        mailbox.oauth_access_token = None
        mailbox.oauth_token_expires_at = None
        mailbox.oauth_tenant_id = None

        db = MagicMock()

        token = get_valid_access_token(db, mailbox)
        assert token == "new-at"
        db.commit.assert_called_once()

    def test_raises_when_no_refresh_token(self):
        """Must raise ValueError when there is no stored refresh token."""
        mailbox = MagicMock()
        mailbox.oauth_refresh_token = None

        db = MagicMock()

        with pytest.raises(ValueError, match="No OAuth refresh token"):
            get_valid_access_token(db, mailbox)


# ---------------------------------------------------------------------------
# smtp_authenticate
# ---------------------------------------------------------------------------


class TestSmtpAuthenticate:
    """Tests for SMTP authentication dispatch."""

    @patch("app.services.oauth_helper.decrypt_field", return_value="plain-pw")
    @patch("app.services.oauth_helper.get_valid_access_token", return_value="at-xyz")
    @patch("app.services.oauth_helper.build_xoauth2_string", return_value="xoauth2-blob")
    def test_uses_xoauth2_for_oauth2_mailbox(self, mock_xoauth, mock_get_token, mock_decrypt):
        server = MagicMock()
        mailbox = MagicMock()
        mailbox.auth_method = "oauth2"
        db = MagicMock()

        smtp_authenticate(server, "user@example.com", mailbox, db)

        mock_get_token.assert_called_once_with(db, mailbox)
        mock_xoauth.assert_called_once_with("user@example.com", "at-xyz")
        server.auth.assert_called_once()
        # Ensure server.login was NOT called
        server.login.assert_not_called()

    @patch("app.services.oauth_helper.decrypt_field", return_value="my-password")
    def test_uses_password_login_for_password_mailbox(self, mock_decrypt):
        server = MagicMock()
        mailbox = MagicMock()
        mailbox.auth_method = "password"
        mailbox.password = "enc-pw"
        db = MagicMock()

        smtp_authenticate(server, "user@example.com", mailbox, db)

        server.login.assert_called_once_with("user@example.com", "my-password")
        server.auth.assert_not_called()

    @patch("app.services.oauth_helper.decrypt_field", return_value="fallback-pw")
    def test_defaults_to_password_when_auth_method_missing(self, mock_decrypt):
        """If auth_method attribute is absent, default to password login."""
        server = MagicMock()
        mailbox = MagicMock(spec=[])  # Empty spec — no auth_method attr
        mailbox.password = "enc-pw"
        db = MagicMock()

        smtp_authenticate(server, "user@example.com", mailbox, db)

        server.login.assert_called_once()


# ---------------------------------------------------------------------------
# imap_authenticate
# ---------------------------------------------------------------------------


class TestImapAuthenticate:
    """Tests for IMAP authentication dispatch."""

    @patch("app.services.oauth_helper.decrypt_field", return_value="plain-pw")
    @patch("app.services.oauth_helper.get_valid_access_token", return_value="at-imap")
    @patch("app.services.oauth_helper.build_xoauth2_string", return_value="xoauth2-imap")
    def test_uses_xoauth2_for_oauth2_mailbox(self, mock_xoauth, mock_get_token, mock_decrypt):
        imap = MagicMock()
        mailbox = MagicMock()
        mailbox.auth_method = "oauth2"
        db = MagicMock()

        imap_authenticate(imap, "user@example.com", mailbox, db)

        mock_get_token.assert_called_once_with(db, mailbox)
        mock_xoauth.assert_called_once_with("user@example.com", "at-imap")
        imap.authenticate.assert_called_once()
        imap.login.assert_not_called()

    @patch("app.services.oauth_helper.decrypt_field", return_value="imap-pw")
    def test_uses_password_login_for_password_mailbox(self, mock_decrypt):
        imap = MagicMock()
        mailbox = MagicMock()
        mailbox.auth_method = "password"
        mailbox.password = "enc-imap-pw"
        db = MagicMock()

        imap_authenticate(imap, "user@example.com", mailbox, db)

        imap.login.assert_called_once_with("user@example.com", "imap-pw")
        imap.authenticate.assert_not_called()
