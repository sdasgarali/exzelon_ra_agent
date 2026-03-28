"""Integration tests for tenant-aware settings API endpoints."""
import json
import pytest
from app.db.models.settings import Settings
from app.db.models.tenant_settings import TenantSettings
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User, UserRole
from app.core.security import get_password_hash, create_access_token


pytestmark = pytest.mark.integration


@pytest.fixture
def tenant_b(db_session):
    """Create a second tenant for isolation tests."""
    t = Tenant(name="Tenant B", slug="tenant-b", plan=TenantPlan.PROFESSIONAL, max_users=10)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def admin_b(db_session, tenant_b):
    """Create an admin user for Tenant B."""
    user = User(
        email="admin-b@test.com",
        password_hash=get_password_hash("testpassword"),
        full_name="Admin B",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
        tenant_id=tenant_b.tenant_id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_b_headers(admin_b):
    token = create_access_token(data={
        "sub": admin_b.email,
        "role": admin_b.role.value,
        "tenant_id": admin_b.tenant_id,
        "plan": "professional",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seed_global_settings(db_session):
    """Seed some global settings including role_permissions for admin access."""
    for key, val in [
        ("daily_send_limit", 30),
        ("cooldown_days", 10),
        ("groq_api_key", "global-groq-key"),
    ]:
        db_session.add(Settings(key=key, value_json=json.dumps(val), type="string"))
    # Admin needs role_permissions to access tab-mapped settings
    role_perms = {
        "admin": {"settings": "full"},
        "operator": {"settings": "read"},
        "viewer": {"settings": "no_access"},
    }
    db_session.add(Settings(key="role_permissions", value_json=json.dumps(role_perms), type="json"))
    db_session.commit()


class TestListSettings:
    """GET /settings — merged global+tenant settings."""

    def test_admin_sees_global_settings(self, client, auth_headers, seed_global_settings):
        resp = client.get("/api/v1/settings", headers=auth_headers)
        assert resp.status_code == 200
        keys = [s["key"] for s in resp.json()]
        assert "daily_send_limit" in keys

    def test_admin_sees_tenant_override(self, client, db_session, auth_headers, test_tenant, seed_global_settings):
        db_session.add(TenantSettings(
            tenant_id=test_tenant.tenant_id, key="daily_send_limit", value_json=json.dumps(50)
        ))
        db_session.commit()

        resp = client.get("/api/v1/settings", headers=auth_headers)
        assert resp.status_code == 200
        for s in resp.json():
            if s["key"] == "daily_send_limit":
                assert json.loads(s["value_json"]) == 50
                assert s["is_tenant_override"] is True
                break
        else:
            pytest.fail("daily_send_limit not found in response")


class TestGetSetting:
    """GET /settings/{key} — resolved with tenant overrides."""

    def test_returns_global_value(self, client, auth_headers, seed_global_settings):
        resp = client.get("/api/v1/settings/daily_send_limit", headers=auth_headers)
        assert resp.status_code == 200
        assert json.loads(resp.json()["value_json"]) == 30
        assert resp.json()["is_tenant_override"] is False

    def test_returns_tenant_override(self, client, db_session, auth_headers, test_tenant, seed_global_settings):
        db_session.add(TenantSettings(
            tenant_id=test_tenant.tenant_id, key="daily_send_limit", value_json=json.dumps(99)
        ))
        db_session.commit()

        resp = client.get("/api/v1/settings/daily_send_limit", headers=auth_headers)
        assert resp.status_code == 200
        assert json.loads(resp.json()["value_json"]) == 99
        assert resp.json()["is_tenant_override"] is True


class TestUpdateSetting:
    """PUT /settings/{key} — writes to tenant or global."""

    def test_admin_writes_to_tenant_settings(self, client, db_session, auth_headers, test_tenant, seed_global_settings):
        resp = client.put(
            "/api/v1/settings/daily_send_limit",
            headers=auth_headers,
            json={"value": 50},
        )
        assert resp.status_code == 200
        assert resp.json()["is_tenant_override"] is True

        # Verify tenant override was created
        ts = db_session.query(TenantSettings).filter(
            TenantSettings.tenant_id == test_tenant.tenant_id,
            TenantSettings.key == "daily_send_limit",
        ).first()
        assert ts is not None
        assert json.loads(ts.value_json) == 50

        # Global setting remains unchanged
        gs = db_session.query(Settings).filter(Settings.key == "daily_send_limit").first()
        assert json.loads(gs.value_json) == 30

    def test_super_admin_writes_to_global(self, client, db_session, sa_headers, seed_global_settings):
        resp = client.put(
            "/api/v1/settings/daily_send_limit",
            headers=sa_headers,
            json={"value": 100},
        )
        assert resp.status_code == 200
        assert resp.json().get("is_tenant_override", False) is False

        gs = db_session.query(Settings).filter(Settings.key == "daily_send_limit").first()
        assert json.loads(gs.value_json) == 100


class TestTenantIsolation:
    """Verify tenant A's overrides don't affect tenant B."""

    def test_tenant_a_override_invisible_to_tenant_b(
        self, client, db_session, auth_headers, admin_b_headers, test_tenant, tenant_b, seed_global_settings
    ):
        # Tenant A sets an override
        db_session.add(TenantSettings(
            tenant_id=test_tenant.tenant_id, key="groq_api_key", value_json=json.dumps("tenant-a-key")
        ))
        db_session.commit()

        # Tenant A sees override
        resp_a = client.get("/api/v1/settings/groq_api_key", headers=auth_headers)
        assert resp_a.status_code == 200
        assert json.loads(resp_a.json()["value_json"]) == "tenant-a-key"

        # Tenant B sees global
        resp_b = client.get("/api/v1/settings/groq_api_key", headers=admin_b_headers)
        assert resp_b.status_code == 200
        assert json.loads(resp_b.json()["value_json"]) == "global-groq-key"

    def test_super_admin_global_edit_affects_tenant_b_not_tenant_a(
        self, client, db_session, sa_headers, auth_headers, admin_b_headers,
        test_tenant, tenant_b, seed_global_settings
    ):
        # Tenant A has an override
        db_session.add(TenantSettings(
            tenant_id=test_tenant.tenant_id, key="cooldown_days", value_json=json.dumps(5)
        ))
        db_session.commit()

        # Super admin changes global to 20
        client.put("/api/v1/settings/cooldown_days", headers=sa_headers, json={"value": 20})

        # Tenant A still sees 5 (override)
        resp_a = client.get("/api/v1/settings/cooldown_days", headers=auth_headers)
        assert json.loads(resp_a.json()["value_json"]) == 5

        # Tenant B sees 20 (new global)
        resp_b = client.get("/api/v1/settings/cooldown_days", headers=admin_b_headers)
        assert json.loads(resp_b.json()["value_json"]) == 20


class TestTenantOverrideEndpoints:
    """Tests for tenant-override management endpoints."""

    def test_list_tenant_overrides(self, client, db_session, auth_headers, test_tenant, seed_global_settings):
        db_session.add(TenantSettings(
            tenant_id=test_tenant.tenant_id, key="daily_send_limit", value_json=json.dumps(50)
        ))
        db_session.commit()

        resp = client.get("/api/v1/settings/tenant-overrides", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "daily_send_limit" in data
        assert data["daily_send_limit"] == 50

    def test_delete_tenant_override_reverts_to_global(
        self, client, db_session, auth_headers, test_tenant, seed_global_settings
    ):
        db_session.add(TenantSettings(
            tenant_id=test_tenant.tenant_id, key="daily_send_limit", value_json=json.dumps(50)
        ))
        db_session.commit()

        # Delete the override
        resp = client.delete("/api/v1/settings/daily_send_limit/tenant-override", headers=auth_headers)
        assert resp.status_code == 200

        # Now the tenant sees the global value
        resp = client.get("/api/v1/settings/daily_send_limit", headers=auth_headers)
        assert json.loads(resp.json()["value_json"]) == 30
        assert resp.json()["is_tenant_override"] is False

    def test_delete_nonexistent_override_returns_404(
        self, client, auth_headers, seed_global_settings
    ):
        resp = client.delete("/api/v1/settings/daily_send_limit/tenant-override", headers=auth_headers)
        assert resp.status_code == 404
