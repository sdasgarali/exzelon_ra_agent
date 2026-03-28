"""Integration tests for signup, verification, and login flow."""
import pytest
from unittest.mock import patch


class TestSignupFlow:
    """Test the full signup -> verify -> login flow."""

    def test_signup_success(self, client):
        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            resp = client.post("/api/v1/auth/signup", json={
                "email": "new@startup.com",
                "password": "SecurePass123",
                "full_name": "Jane Doe",
                "company_name": "My Startup",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["message"] == "Verification email sent. Check your inbox."
        assert "user_id" in data

    def test_signup_duplicate_email(self, client):
        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            client.post("/api/v1/auth/signup", json={
                "email": "dup@test.com",
                "password": "SecurePass123",
                "full_name": "User One",
                "company_name": "Company A",
            })
            resp = client.post("/api/v1/auth/signup", json={
                "email": "dup@test.com",
                "password": "SecurePass123",
                "full_name": "User Two",
                "company_name": "Company B",
            })
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    def test_signup_weak_password(self, client):
        resp = client.post("/api/v1/auth/signup", json={
            "email": "weak@test.com",
            "password": "short",
            "full_name": "Weak User",
            "company_name": "Corp",
        })
        assert resp.status_code == 422  # Pydantic validation (min_length=8)

    def test_signup_missing_company_name(self, client):
        resp = client.post("/api/v1/auth/signup", json={
            "email": "nocompany@test.com",
            "password": "SecurePass123",
            "full_name": "No Company User",
        })
        assert resp.status_code == 422

    def test_verify_email_success(self, client, db_session):
        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            signup_resp = client.post("/api/v1/auth/signup", json={
                "email": "verify@test.com",
                "password": "SecurePass123",
                "full_name": "Verify User",
                "company_name": "Verify Corp",
            })
        user_id = signup_resp.json()["user_id"]

        # Get the verification token from DB
        from app.db.models.user import User
        user = db_session.query(User).filter(User.user_id == user_id).first()
        token = user.verification_token

        resp = client.get(f"/api/v1/auth/verify?token={token}")
        assert resp.status_code == 200
        assert resp.json()["verified"] is True

    def test_verify_invalid_token(self, client):
        resp = client.get("/api/v1/auth/verify?token=invalid.token.here")
        assert resp.status_code == 400

    def test_login_unverified_user_blocked(self, client):
        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            client.post("/api/v1/auth/signup", json={
                "email": "unverified@test.com",
                "password": "SecurePass123",
                "full_name": "Unverified",
                "company_name": "UV Corp",
            })
        # Try to login without verifying
        resp = client.post("/api/v1/auth/login", data={
            "username": "unverified@test.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 403
        assert "not verified" in resp.json()["detail"].lower()

    def test_login_after_verification(self, client, db_session):
        # Create tenant + user directly to avoid rate-limiting on signup
        from app.db.models.tenant import Tenant, TenantPlan
        from app.db.models.user import User, UserRole
        from app.core.security import get_password_hash

        tenant = Tenant(name="V Corp", slug="v-corp", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="verified@test.com",
            password_hash=get_password_hash("SecurePass123"),
            full_name="Verified User",
            role=UserRole.ADMIN,
            tenant_id=tenant.tenant_id,
            is_active=True,
            is_verified=True,
        )
        db_session.add(user)
        db_session.commit()

        # Login
        resp = client.post("/api/v1/auth/login", data={
            "username": "verified@test.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["tenant_id"] is not None
        assert data["user"]["tenant"]["plan"] == "starter"

    def test_register_endpoint_requires_auth(self, client):
        """Old /register endpoint should require authentication now."""
        resp = client.post("/api/v1/auth/register", json={
            "email": "admin-created@test.com",
            "password": "SecurePass123",
            "full_name": "Admin Created",
        })
        assert resp.status_code == 401

    def test_register_endpoint_no_role_injection(self, client, admin_token):
        """Verify role from request body is ignored -- always viewer."""
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "email": "tryrole@test.com",
                "password": "SecurePass123",
                "full_name": "Role Injector",
                "role": "admin",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "viewer"


class TestResendVerification:
    """Test resend verification endpoint."""

    def test_resend_success(self, client):
        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            client.post("/api/v1/auth/signup", json={
                "email": "resend@test.com",
                "password": "SecurePass123",
                "full_name": "Resend User",
                "company_name": "Resend Corp",
            })
            resp = client.post("/api/v1/auth/resend-verification", json={
                "email": "resend@test.com",
            })
        assert resp.status_code == 200
        assert "sent" in resp.json()["message"].lower()

    def test_resend_nonexistent_email(self, client):
        resp = client.post("/api/v1/auth/resend-verification", json={
            "email": "ghost@nowhere.com",
        })
        # Should return 200 to prevent email enumeration
        assert resp.status_code == 200
