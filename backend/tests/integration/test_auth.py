"""Integration tests for authentication endpoints."""
import pytest

pytestmark = pytest.mark.integration


class TestAuthEndpoints:
    """Tests for authentication API endpoints."""

    def test_register_requires_auth(self, client):
        """Test that /register requires authentication."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@test.com",
                "password": "password123",
                "full_name": "New User"
            }
        )
        assert response.status_code == 401

    def test_register_user(self, client, auth_headers):
        """Test user registration (requires auth, always assigns viewer)."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@test.com",
                "password": "password123",
                "full_name": "New User"
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newuser@test.com"
        assert data["full_name"] == "New User"
        assert data["role"] == "viewer"
        assert "user_id" in data

    def test_register_duplicate_email(self, client, admin_user, auth_headers):
        """Test registration with duplicate email fails."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": admin_user.email,
                "password": "password123",
                "full_name": "Duplicate User"
            },
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]

    def test_login_success(self, client, admin_user):
        """Test successful login."""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": admin_user.email,
                "password": "testpassword"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == admin_user.email

    def test_login_wrong_password(self, client, admin_user):
        """Test login with wrong password fails."""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": admin_user.email,
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client):
        """Test login with nonexistent user fails."""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "nonexistent@test.com",
                "password": "password123"
            }
        )
        assert response.status_code == 401

    def test_get_me_authenticated(self, client, auth_headers):
        """Test getting current user when authenticated."""
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "role" in data

    def test_get_me_unauthenticated(self, client):
        """Test getting current user when not authenticated fails."""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401
