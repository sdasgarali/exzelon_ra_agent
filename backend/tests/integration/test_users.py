"""Integration tests for user-tenant binding + tenant isolation on /users."""
import pytest

from app.core.security import get_password_hash
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant, TenantPlan

pytestmark = pytest.mark.integration


@pytest.fixture
def other_tenant(db_session):
    t = Tenant(name="Other Org", slug="other-org", plan=TenantPlan.ENTERPRISE,
               max_users=999, max_mailboxes=999, max_contacts=999999,
               max_campaigns=999, max_leads=999999)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def other_tenant_user(db_session, other_tenant):
    u = User(email="other@test.com", password_hash=get_password_hash("x"),
             full_name="Other User", role=UserRole.BDM, is_active=True,
             is_verified=True, tenant_id=other_tenant.tenant_id)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _payload(email, **kw):
    return {"email": email, "password": "SecurePass123!", "full_name": "X", **kw}


class TestCreateBindsTenant:
    def test_admin_create_forces_own_tenant(self, client, auth_headers, admin_user):
        # Admin passes a bogus tenant_id — must be ignored and forced to own tenant.
        resp = client.post("/api/v1/users", headers=auth_headers,
                           json=_payload("new1@test.com", role="bdm", tenant_id=99999))
        assert resp.status_code == 201, resp.text
        assert resp.json()["tenant_id"] == admin_user.tenant_id

    def test_super_admin_create_requires_tenant(self, client, sa_headers):
        resp = client.post("/api/v1/users", headers=sa_headers,
                           json=_payload("new2@test.com", role="bdm"))
        assert resp.status_code == 400
        assert "tenant" in resp.json()["detail"].lower()

    def test_super_admin_create_picks_tenant(self, client, sa_headers, other_tenant):
        resp = client.post("/api/v1/users", headers=sa_headers,
                           json=_payload("new3@test.com", role="recruiter", tenant_id=other_tenant.tenant_id))
        assert resp.status_code == 201, resp.text
        assert resp.json()["tenant_id"] == other_tenant.tenant_id

    def test_super_admin_create_invalid_tenant(self, client, sa_headers):
        resp = client.post("/api/v1/users", headers=sa_headers,
                           json=_payload("new4@test.com", role="bdm", tenant_id=99999))
        assert resp.status_code == 400

    def test_super_admin_role_user_is_global(self, client, sa_headers, other_tenant):
        # Even if a tenant is supplied, a super_admin-role user is global (NULL).
        resp = client.post("/api/v1/users", headers=sa_headers,
                           json=_payload("newsa@test.com", role="super_admin", tenant_id=other_tenant.tenant_id))
        assert resp.status_code == 201, resp.text
        assert resp.json()["tenant_id"] is None


class TestListScoping:
    def test_admin_sees_only_own_tenant(self, client, auth_headers, admin_user, other_tenant_user):
        rows = client.get("/api/v1/users", headers=auth_headers).json()
        tenant_ids = {u["tenant_id"] for u in rows}
        assert tenant_ids == {admin_user.tenant_id}
        assert all(u["email"] != "other@test.com" for u in rows)

    def test_super_admin_sees_all_and_can_filter(self, client, sa_headers, admin_user, other_tenant_user):
        allrows = client.get("/api/v1/users", headers=sa_headers).json()
        tenant_ids = {u["tenant_id"] for u in allrows}
        assert other_tenant_user.tenant_id in tenant_ids
        # filter by the other tenant
        filtered = client.get(f"/api/v1/users?tenant_id={other_tenant_user.tenant_id}", headers=sa_headers).json()
        assert {u["tenant_id"] for u in filtered} == {other_tenant_user.tenant_id}

    def test_super_admin_scoped_by_impersonated_tenant(self, client, sa_headers, admin_user, other_tenant, other_tenant_user):
        # Selecting a tenant in the sidebar sends X-Tenant-ID → list is scoped to it.
        headers = {**sa_headers, "X-Tenant-ID": str(admin_user.tenant_id)}
        rows = client.get("/api/v1/users", headers=headers).json()
        tenant_ids = {u["tenant_id"] for u in rows}
        assert tenant_ids == {admin_user.tenant_id}
        assert all(u["email"] != "other@test.com" for u in rows)

    def test_explicit_filter_overrides_impersonation(self, client, sa_headers, admin_user, other_tenant, other_tenant_user):
        # Impersonating tenant A but explicitly filtering tenant B → shows tenant B.
        headers = {**sa_headers, "X-Tenant-ID": str(admin_user.tenant_id)}
        rows = client.get(f"/api/v1/users?tenant_id={other_tenant.tenant_id}", headers=headers).json()
        assert {u["tenant_id"] for u in rows} == {other_tenant.tenant_id}


class TestIsolationGuards:
    def test_admin_cannot_get_other_tenant_user(self, client, auth_headers, other_tenant_user):
        resp = client.get(f"/api/v1/users/{other_tenant_user.user_id}", headers=auth_headers)
        assert resp.status_code == 404

    def test_admin_cannot_update_other_tenant_user(self, client, auth_headers, other_tenant_user):
        resp = client.put(f"/api/v1/users/{other_tenant_user.user_id}", headers=auth_headers,
                          json={"full_name": "Hacked"})
        assert resp.status_code == 404

    def test_admin_cannot_delete_other_tenant_user(self, client, auth_headers, other_tenant_user):
        resp = client.delete(f"/api/v1/users/{other_tenant_user.user_id}", headers=auth_headers)
        assert resp.status_code == 404

    def test_super_admin_can_access_other_tenant_user(self, client, sa_headers, other_tenant_user):
        resp = client.get(f"/api/v1/users/{other_tenant_user.user_id}", headers=sa_headers)
        assert resp.status_code == 200


class TestTenantReassignment:
    def test_super_admin_can_move_tenant(self, client, sa_headers, other_tenant, admin_user, test_tenant):
        # Create a user in test_tenant via SA, then move to other_tenant.
        created = client.post("/api/v1/users", headers=sa_headers,
                             json=_payload("move@test.com", role="bdm", tenant_id=test_tenant.tenant_id)).json()
        resp = client.put(f"/api/v1/users/{created['user_id']}", headers=sa_headers,
                         json={"tenant_id": other_tenant.tenant_id})
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == other_tenant.tenant_id

    def test_super_admin_explicit_null_tenant_rejected(self, client, sa_headers, other_tenant):
        # Clearing the tenant of a non-super-admin user must be rejected, not silently ignored.
        created = client.post("/api/v1/users", headers=sa_headers,
                             json=_payload("clr@test.com", role="bdm", tenant_id=other_tenant.tenant_id)).json()
        resp = client.put(f"/api/v1/users/{created['user_id']}", headers=sa_headers,
                         json={"tenant_id": None})
        assert resp.status_code == 400

    def test_admin_cannot_reassign_tenant(self, client, auth_headers, sa_headers, admin_user, other_tenant):
        # A user in the admin's own tenant; admin tries to push them to other_tenant → ignored.
        created = client.post("/api/v1/users", headers=auth_headers,
                             json=_payload("stay@test.com", role="bdm")).json()
        resp = client.put(f"/api/v1/users/{created['user_id']}", headers=auth_headers,
                         json={"tenant_id": other_tenant.tenant_id, "full_name": "Renamed"})
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == admin_user.tenant_id  # unchanged
        assert resp.json()["full_name"] == "Renamed"
