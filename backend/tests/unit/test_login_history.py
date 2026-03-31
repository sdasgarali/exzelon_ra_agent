"""Unit tests for login history and account lockout."""
import pytest
from datetime import datetime, timedelta


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """Disable rate limiter for login history tests to avoid cross-test interference."""
    from app.api.endpoints.auth import limiter
    limiter.enabled = False
    yield
    limiter.enabled = True


class TestLoginRecording:
    """Test that login attempts are recorded in login_history."""

    def test_successful_login_creates_history(self, client, db_session, admin_user, test_tenant):
        """Successful login creates LoginHistory with success=True."""
        resp = client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })
        assert resp.status_code == 200

        from app.db.models.login_history import LoginHistory
        records = db_session.query(LoginHistory).filter(
            LoginHistory.email_attempted == admin_user.email
        ).all()
        assert len(records) == 1
        assert records[0].success is True
        assert records[0].user_id == admin_user.user_id
        assert records[0].failure_reason is None

    def test_failed_login_wrong_password(self, client, db_session, admin_user, test_tenant):
        """Failed login (wrong password) creates history with reason 'invalid_credentials'."""
        resp = client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

        from app.db.models.login_history import LoginHistory
        records = db_session.query(LoginHistory).filter(
            LoginHistory.email_attempted == admin_user.email
        ).all()
        assert len(records) == 1
        assert records[0].success is False
        assert records[0].failure_reason == "invalid_credentials"

    def test_failed_login_unknown_email(self, client, db_session):
        """Unknown email records history with user_id=None."""
        resp = client.post("/api/v1/auth/login", data={
            "username": "nobody@example.com",
            "password": "password",
        })
        assert resp.status_code == 401

        from app.db.models.login_history import LoginHistory
        records = db_session.query(LoginHistory).filter(
            LoginHistory.email_attempted == "nobody@example.com"
        ).all()
        assert len(records) == 1
        assert records[0].user_id is None
        assert records[0].failure_reason == "invalid_credentials"

    def test_ip_and_user_agent_captured(self, client, db_session, admin_user, test_tenant):
        """IP address and user agent are stored from request headers."""
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": admin_user.email, "password": "testpassword"},
            headers={"User-Agent": "TestBrowser/1.0", "X-Forwarded-For": "203.0.113.50"},
        )
        assert resp.status_code == 200

        from app.db.models.login_history import LoginHistory
        record = db_session.query(LoginHistory).filter(
            LoginHistory.email_attempted == admin_user.email
        ).first()
        assert record.ip_address == "203.0.113.50"
        assert record.user_agent == "TestBrowser/1.0"

    def test_inactive_user_records_failure(self, client, db_session, test_tenant):
        """Inactive user login records failure with reason 'inactive'."""
        from app.db.models.user import User, UserRole
        from app.core.security import get_password_hash

        user = User(
            email="inactive@test.com",
            password_hash=get_password_hash("testpassword"),
            full_name="Inactive User",
            role=UserRole.VIEWER,
            is_active=False,
            is_verified=True,
            tenant_id=test_tenant.tenant_id,
        )
        db_session.add(user)
        db_session.commit()

        resp = client.post("/api/v1/auth/login", data={
            "username": "inactive@test.com",
            "password": "testpassword",
        })
        assert resp.status_code == 403

        from app.db.models.login_history import LoginHistory
        record = db_session.query(LoginHistory).filter(
            LoginHistory.email_attempted == "inactive@test.com"
        ).first()
        assert record.failure_reason == "inactive"


class TestAccountLockout:
    """Test account lockout after repeated failures."""

    def test_five_failures_triggers_lockout(self, client, db_session, admin_user, test_tenant):
        """5 consecutive failures sets locked_until on the user."""
        for _ in range(5):
            client.post("/api/v1/auth/login", data={
                "username": admin_user.email,
                "password": "wrongpassword",
            })

        db_session.refresh(admin_user)
        assert admin_user.failed_login_count >= 5
        assert admin_user.locked_until is not None
        assert admin_user.locked_until > datetime.utcnow()

    def test_locked_user_gets_423(self, client, db_session, admin_user, test_tenant):
        """Locked user gets HTTP 423 response."""
        # Lock the account
        admin_user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        admin_user.failed_login_count = 5
        db_session.commit()

        resp = client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })
        assert resp.status_code == 423
        assert "locked" in resp.json()["detail"].lower()

    def test_lockout_expires(self, client, db_session, admin_user, test_tenant):
        """Expired lockout allows login again."""
        # Set lockout in the past
        admin_user.locked_until = datetime.utcnow() - timedelta(minutes=1)
        admin_user.failed_login_count = 5
        db_session.commit()

        resp = client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })
        assert resp.status_code == 200

    def test_successful_login_resets_counters(self, client, db_session, admin_user, test_tenant):
        """Successful login resets failed_login_count and locked_until."""
        admin_user.failed_login_count = 3
        db_session.commit()

        resp = client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })
        assert resp.status_code == 200

        db_session.refresh(admin_user)
        assert admin_user.failed_login_count == 0
        assert admin_user.locked_until is None

    def test_locked_attempt_records_history(self, client, db_session, admin_user, test_tenant):
        """Login attempt against locked account records history with reason 'locked'."""
        admin_user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        admin_user.failed_login_count = 5
        db_session.commit()

        client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })

        from app.db.models.login_history import LoginHistory
        record = db_session.query(LoginHistory).filter(
            LoginHistory.email_attempted == admin_user.email,
            LoginHistory.failure_reason == "locked",
        ).first()
        assert record is not None
        assert record.success is False

    def test_super_admin_unlock_clears_lockout(self, client, db_session, admin_user, super_admin_user, sa_headers, test_tenant):
        """Super admin can unlock a locked user."""
        admin_user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        admin_user.failed_login_count = 5
        db_session.commit()

        resp = client.post(
            f"/api/v1/activity/unlock-user/{admin_user.user_id}",
            headers=sa_headers,
        )
        assert resp.status_code == 200

        db_session.refresh(admin_user)
        assert admin_user.failed_login_count == 0
        assert admin_user.locked_until is None
