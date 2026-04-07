"""Tests for JWT refresh token endpoint."""
import pytest
from app.core.security import create_refresh_token, create_access_token

pytestmark = pytest.mark.integration


class TestRefreshToken:
    """Test POST /auth/refresh endpoint."""

    def test_refresh_with_valid_token(self, client, admin_user):
        """Valid refresh token returns new access + refresh tokens."""
        refresh = create_refresh_token(data={"sub": admin_user.email})
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == admin_user.email

    def test_refresh_with_expired_token(self, client, admin_user):
        """Expired refresh token returns 401."""
        from datetime import timedelta
        refresh = create_refresh_token(
            data={"sub": admin_user.email},
            expires_delta=timedelta(seconds=-1),
        )
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 401

    def test_refresh_with_access_token_rejected(self, client, admin_user):
        """Access token used as refresh token is rejected (wrong type claim)."""
        access = create_access_token(data={
            "sub": admin_user.email,
            "role": admin_user.role.value,
            "tenant_id": admin_user.tenant_id,
            "plan": None,
        })
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": access})
        assert resp.status_code == 401

    def test_refresh_with_invalid_token(self, client):
        """Garbage token returns 401."""
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid.token.here"})
        assert resp.status_code == 401

    def test_refresh_with_inactive_user(self, client, admin_user, db_session):
        """Refresh token for deactivated user returns 401."""
        refresh = create_refresh_token(data={"sub": admin_user.email})
        admin_user.is_active = False
        db_session.commit()
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 401

    def test_login_returns_refresh_token(self, client, admin_user):
        """Login endpoint now returns a refresh_token field."""
        resp = client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "refresh_token" in data
        assert len(data["refresh_token"]) > 0

    def test_refresh_returns_valid_new_tokens(self, client, admin_user):
        """Using refresh returns valid new access + refresh tokens that work."""
        refresh = create_refresh_token(data={"sub": admin_user.email})
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 200
        new_access = resp.json()["access_token"]
        new_refresh = resp.json()["refresh_token"]
        # New access token should work for authenticated requests
        me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == admin_user.email
        # New refresh token should also work
        resp2 = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
        assert resp2.status_code == 200
