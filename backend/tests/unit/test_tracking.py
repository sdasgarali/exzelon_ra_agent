"""Tests for tracking token generation and URL sanitization."""
import pytest
from app.core.tracking import generate_tracking_token, validate_tracking_token, sanitize_redirect_url


pytestmark = pytest.mark.unit


class TestTrackingTokens:
    def test_generate_token(self):
        token = generate_tracking_token("test-id-123")
        assert isinstance(token, str)
        assert len(token) == 16

    def test_validate_valid_token(self):
        token = generate_tracking_token("test-id-456")
        assert validate_tracking_token("test-id-456", token) is True

    def test_validate_invalid_token(self):
        assert validate_tracking_token("test-id-456", "invalid-token!!") is False

    def test_different_ids_produce_different_tokens(self):
        t1 = generate_tracking_token("id-1")
        t2 = generate_tracking_token("id-2")
        assert t1 != t2

    def test_same_id_produces_same_token(self):
        t1 = generate_tracking_token("id-same")
        t2 = generate_tracking_token("id-same")
        assert t1 == t2


class TestSanitizeRedirectUrl:
    def test_valid_https(self):
        assert sanitize_redirect_url("https://example.com/page") == "https://example.com/page"

    def test_valid_http(self):
        assert sanitize_redirect_url("http://example.com") == "http://example.com"

    def test_empty_url(self):
        assert sanitize_redirect_url("") is None

    def test_javascript_scheme_blocked(self):
        assert sanitize_redirect_url("javascript:alert(1)") is None

    def test_data_scheme_blocked(self):
        assert sanitize_redirect_url("data:text/html,<h1>bad</h1>") is None

    def test_protocol_relative_blocked(self):
        assert sanitize_redirect_url("//evil.com") is None

    def test_ftp_blocked(self):
        assert sanitize_redirect_url("ftp://files.example.com/file") is None
