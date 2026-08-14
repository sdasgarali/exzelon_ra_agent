"""Integration tests for activity log API endpoints."""
import pytest
from datetime import datetime, timedelta


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """Disable rate limiter for activity log tests to avoid cross-test interference."""
    from app.api.endpoints.auth import limiter
    limiter.enabled = False
    yield
    limiter.enabled = True


class TestLoginHistoryEndpoint:
    """Test GET /activity/login-history."""

    def test_login_history_super_admin(self, client, db_session, super_admin_user, sa_headers, admin_user, test_tenant):
        """Super admin can list login history."""
        # Generate some login history
        client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })
        client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "wrongpassword",
        })

        resp = client.get("/api/v1/activity/login-history", headers=sa_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 2

    def test_login_history_email_filter(self, client, db_session, super_admin_user, sa_headers, admin_user, test_tenant):
        """Login history can be filtered by email."""
        client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })

        resp = client.get(
            "/api/v1/activity/login-history",
            params={"email": admin_user.email},
            headers=sa_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert admin_user.email in item["email_attempted"]

    def test_login_history_success_filter(self, client, db_session, super_admin_user, sa_headers, admin_user, test_tenant):
        """Login history can be filtered by success status."""
        client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "wrongpassword",
        })
        client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })

        resp = client.get(
            "/api/v1/activity/login-history",
            params={"success": "false"},
            headers=sa_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["success"] is False

    def test_login_history_non_super_admin_forbidden(self, client, auth_headers):
        """Non-super-admin gets 403 on login history endpoint."""
        resp = client.get("/api/v1/activity/login-history", headers=auth_headers)
        assert resp.status_code == 403


class TestLoginStatsEndpoint:
    """Test GET /activity/login-history/stats."""

    def test_stats_returns_counts(self, client, db_session, super_admin_user, sa_headers, admin_user, test_tenant):
        """Stats endpoint returns correct structure."""
        # Generate some login activity
        client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })
        client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "wrongpassword",
        })

        resp = client.get("/api/v1/activity/login-history/stats", headers=sa_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "logins_24h" in data
        assert "failed_24h" in data
        assert "locked_accounts" in data
        assert "unique_users_24h" in data
        assert "unique_users_7d" in data
        assert data["logins_24h"] >= 2
        assert data["failed_24h"] >= 1


class TestAuthEventsEndpoint:
    """Test GET /activity/auth-events."""

    def test_auth_events_returns_audit_entries(self, client, db_session, super_admin_user, sa_headers, admin_user, test_tenant):
        """Auth events returns audit log entries."""
        # Login to generate an audit entry
        client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })

        resp = client.get("/api/v1/activity/auth-events", headers=sa_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data


class TestActiveUsersEndpoint:
    """Test GET /activity/active-users."""

    def test_active_users_returns_user_list(self, client, db_session, super_admin_user, sa_headers, admin_user, test_tenant):
        """Active users returns list with login counts."""
        resp = client.get("/api/v1/activity/active-users", headers=sa_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        if data["items"]:
            user_item = data["items"][0]
            assert "email" in user_item
            assert "logins_30d" in user_item
            assert "is_online" in user_item
            assert "is_locked" in user_item


class TestMyLoginHistoryEndpoint:
    """Test GET /activity/my-login-history."""

    def test_my_login_history_returns_own_records(self, client, db_session, admin_user, auth_headers, test_tenant):
        """Users can see their own login history."""
        # Generate login history first
        client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "testpassword",
        })

        resp = client.get("/api/v1/activity/my-login-history", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        for item in data["items"]:
            assert item["email_attempted"] == admin_user.email


class TestUnlockUserEndpoint:
    """Test POST /activity/unlock-user/{user_id}."""

    def test_unlock_user_resets_lockout(self, client, db_session, admin_user, super_admin_user, sa_headers, test_tenant):
        """Super admin can unlock a locked user account."""
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

    def test_unlock_non_super_admin_forbidden(self, client, auth_headers, admin_user):
        """Non-super-admin cannot unlock users."""
        resp = client.post(
            f"/api/v1/activity/unlock-user/{admin_user.user_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 403


class TestUserCRUDAudit:
    """Test that user create/update/delete creates audit log entries."""

    def test_create_user_creates_audit(self, client, db_session, sa_headers, super_admin_user):
        """Creating a user writes an audit log entry."""
        resp = client.post("/api/v1/users", json={
            "email": "newuser@test.com",
            "password": "password123",
            "full_name": "New User",
            "role": "recruiter",
        }, headers=sa_headers)
        assert resp.status_code == 201

        from app.db.models.audit_log import AuditLog
        audit = db_session.query(AuditLog).filter(
            AuditLog.entity_type == "user",
            AuditLog.action == "user_created",
        ).first()
        assert audit is not None
        assert "newuser@test.com" in (audit.notes or "")

    def test_update_user_role_creates_audit(self, client, db_session, sa_headers, super_admin_user, admin_user, test_tenant):
        """Updating a user's role writes audit with changed_fields."""
        resp = client.put(f"/api/v1/users/{admin_user.user_id}", json={
            "role": "bdm",
        }, headers=sa_headers)
        assert resp.status_code == 200

        from app.db.models.audit_log import AuditLog
        audit = db_session.query(AuditLog).filter(
            AuditLog.entity_type == "user",
            AuditLog.action == "user_updated",
            AuditLog.entity_id == admin_user.user_id,
        ).first()
        assert audit is not None
        assert audit.changed_fields is not None
        assert "role" in audit.changed_fields

    def test_delete_user_creates_audit(self, client, db_session, sa_headers, super_admin_user, test_tenant):
        """Deleting a user writes an audit log entry."""
        from app.db.models.user import User, UserRole
        from app.core.security import get_password_hash

        user = User(
            email="todelete@test.com",
            password_hash=get_password_hash("pass"),
            full_name="To Delete",
            role=UserRole.RECRUITER,
            is_active=True,
            is_verified=True,
            tenant_id=test_tenant.tenant_id,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        uid = user.user_id

        resp = client.delete(f"/api/v1/users/{uid}", headers=sa_headers)
        assert resp.status_code == 204

        from app.db.models.audit_log import AuditLog
        audit = db_session.query(AuditLog).filter(
            AuditLog.entity_type == "user",
            AuditLog.action == "user_deleted",
            AuditLog.entity_id == uid,
        ).first()
        assert audit is not None
        assert "todelete@test.com" in (audit.notes or "")
