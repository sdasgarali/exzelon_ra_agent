"""Access-token revocation on logout (ELR-027)."""
import pytest

from app.core.token_blacklist import reset_for_tests, is_revoked, revoke

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clear_blacklist():
    reset_for_tests()
    yield
    reset_for_tests()


def test_logout_revokes_the_token(client, auth_headers):
    # Token works before logout.
    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 200
    # Logout revokes it.
    assert client.post("/api/v1/auth/logout", headers=auth_headers).status_code == 200
    # Same token is now rejected.
    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 401


def test_blacklist_ttl_expiry():
    revoke("jti-abc", ttl_seconds=100)
    assert is_revoked("jti-abc") is True
    # A zero/negative TTL is a no-op (already expired).
    revoke("jti-none", ttl_seconds=0)
    assert is_revoked("jti-none") is False
    assert is_revoked("never-added") is False
