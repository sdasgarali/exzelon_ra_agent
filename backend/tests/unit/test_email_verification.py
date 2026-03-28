"""Tests for email verification and tenant dependency."""
import pytest
from unittest.mock import patch, MagicMock
from app.core.security import create_verification_token, decode_verification_token
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant, TenantPlan


class TestVerificationTokens:
    """Test verification token creation and decoding."""

    def test_create_verification_token(self):
        token = create_verification_token(user_id=42)
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_verification_token(self):
        token = create_verification_token(user_id=42)
        payload = decode_verification_token(token)
        assert payload is not None
        assert payload["user_id"] == 42
        assert payload["purpose"] == "email_verification"

    def test_decode_expired_token(self):
        from datetime import timedelta
        token = create_verification_token(user_id=42, expires_delta=timedelta(seconds=-1))
        payload = decode_verification_token(token)
        assert payload is None

    def test_decode_invalid_token(self):
        payload = decode_verification_token("not.a.valid.token")
        assert payload is None

    def test_jwt_contains_tenant_id(self):
        from app.core.security import create_access_token, decode_access_token
        token = create_access_token(data={
            "sub": "user@test.com",
            "role": "admin",
            "tenant_id": 5,
            "plan": "professional",
        })
        payload = decode_access_token(token)
        assert payload["tenant_id"] == 5
        assert payload["plan"] == "professional"


class TestEmailVerificationService:
    """Test email verification service functions."""

    def test_send_verification_email_sets_token(self, db_session):
        from app.services.email_verification import send_verification_email

        tenant = Tenant(name="T", slug="t-svc", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="test@example.com",
            password_hash="hash",
            tenant_id=tenant.tenant_id,
            is_verified=False,
        )
        db_session.add(user)
        db_session.commit()

        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            result = send_verification_email(user, db_session)
            assert result is True
            db_session.refresh(user)
            assert user.verification_token is not None
            assert user.verification_sent_at is not None
            mock_send.assert_called_once()

    def test_verify_user_email_success(self, db_session):
        from app.services.email_verification import verify_user_email

        tenant = Tenant(name="V", slug="v-svc", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="verify@example.com",
            password_hash="hash",
            tenant_id=tenant.tenant_id,
            is_verified=False,
        )
        db_session.add(user)
        db_session.commit()

        token = create_verification_token(user_id=user.user_id)
        user.verification_token = token
        db_session.commit()

        result = verify_user_email(token, db_session)
        assert result is True
        db_session.refresh(user)
        assert user.is_verified is True
        assert user.verification_token is None

    def test_verify_user_email_invalid_token(self, db_session):
        from app.services.email_verification import verify_user_email
        result = verify_user_email("bad.token.here", db_session)
        assert result is False

    def test_verify_user_email_already_verified(self, db_session):
        from app.services.email_verification import verify_user_email

        tenant = Tenant(name="AV", slug="av-svc", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="already@example.com",
            password_hash="hash",
            tenant_id=tenant.tenant_id,
            is_verified=True,
        )
        db_session.add(user)
        db_session.commit()

        token = create_verification_token(user_id=user.user_id)
        result = verify_user_email(token, db_session)
        assert result is True  # Idempotent


class TestTenantDependency:
    """Test the tenant_id extraction dependency."""

    def test_tenant_id_from_regular_user(self, db_session):
        from app.api.deps.auth import _extract_tenant_id

        tenant = Tenant(name="Dep", slug="dep-svc", plan=TenantPlan.PROFESSIONAL)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="dep@test.com", password_hash="h", tenant_id=tenant.tenant_id,
            is_verified=True, role=UserRole.ADMIN,
        )
        db_session.add(user)
        db_session.commit()

        tid = _extract_tenant_id(user, x_tenant_id=None)
        assert tid == tenant.tenant_id

    def test_tenant_id_none_for_super_admin(self, db_session):
        from app.api.deps.auth import _extract_tenant_id

        sa = User(
            email="sa@test-dep.com", password_hash="h", tenant_id=None,
            is_verified=True, role=UserRole.SUPER_ADMIN,
        )
        db_session.add(sa)
        db_session.commit()

        tid = _extract_tenant_id(sa, x_tenant_id=None)
        assert tid is None

    def test_super_admin_can_impersonate_tenant(self, db_session):
        from app.api.deps.auth import _extract_tenant_id

        tenant = Tenant(name="Imp", slug="imp-svc", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        sa = User(
            email="sa2@test-dep.com", password_hash="h", tenant_id=None,
            is_verified=True, role=UserRole.SUPER_ADMIN,
        )
        db_session.add(sa)
        db_session.commit()

        tid = _extract_tenant_id(sa, x_tenant_id=tenant.tenant_id)
        assert tid == tenant.tenant_id

    def test_regular_user_cannot_impersonate(self, db_session):
        from app.api.deps.auth import _extract_tenant_id

        tenant = Tenant(name="No", slug="no-svc", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="noimper@test-dep.com", password_hash="h",
            tenant_id=tenant.tenant_id, is_verified=True, role=UserRole.ADMIN,
        )
        db_session.add(user)
        db_session.commit()

        # Even if X-Tenant-ID is passed, regular user's own tenant_id is returned
        tid = _extract_tenant_id(user, x_tenant_id=999)
        assert tid == tenant.tenant_id
