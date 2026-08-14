"""Integration tests for role management (built-in + custom roles)."""
import pytest

from app.core.security import get_password_hash
from app.db.models.user import User


pytestmark = pytest.mark.integration


def _tenant_headers(sa_headers, test_tenant):
    return {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}


class TestListRoles:
    def test_lists_builtin_roles_with_renamed_labels(self, client, sa_headers):
        resp = client.get("/api/v1/roles", headers=sa_headers)
        assert resp.status_code == 200
        roles = {r["key"]: r for r in resp.json()["roles"]}
        assert set(["super_admin", "admin", "bdm", "recruiter"]).issubset(roles.keys())
        assert roles["bdm"]["label"] == "BDM"
        assert roles["recruiter"]["label"] == "Recruiter"
        assert roles["bdm"]["builtin"] is True

    def test_non_super_admin_forbidden(self, client, auth_headers):
        resp = client.get("/api/v1/roles", headers=auth_headers)
        assert resp.status_code == 403


class TestCreateRole:
    def test_create_custom_role(self, client, sa_headers, test_tenant):
        headers = _tenant_headers(sa_headers, test_tenant)
        resp = client.post("/api/v1/roles", headers=headers, json={
            "key": "bdm_lead", "label": "BDM Lead", "description": "Senior BDM",
            "base_role": "bdm",
        })
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["key"] == "bdm_lead"
        assert body["base_role"] == "bdm"
        assert body["builtin"] is False
        # appears in the list
        listed = {r["key"] for r in client.get("/api/v1/roles", headers=headers).json()["roles"]}
        assert "bdm_lead" in listed

    def test_create_requires_tenant_impersonation(self, client, sa_headers):
        # super admin without X-Tenant-ID → require_tenant_id → 400
        resp = client.post("/api/v1/roles", headers=sa_headers, json={
            "key": "no_tenant", "label": "X", "base_role": "bdm",
        })
        assert resp.status_code == 400

    def test_reject_builtin_key(self, client, sa_headers, test_tenant):
        headers = _tenant_headers(sa_headers, test_tenant)
        resp = client.post("/api/v1/roles", headers=headers, json={
            "key": "admin", "label": "Fake Admin", "base_role": "admin",
        })
        assert resp.status_code == 400

    def test_reject_invalid_base_role(self, client, sa_headers, test_tenant):
        headers = _tenant_headers(sa_headers, test_tenant)
        resp = client.post("/api/v1/roles", headers=headers, json={
            "key": "weird", "label": "Weird", "base_role": "super_admin",
        })
        assert resp.status_code == 400

    def test_reject_duplicate(self, client, sa_headers, test_tenant):
        headers = _tenant_headers(sa_headers, test_tenant)
        payload = {"key": "dup_role", "label": "Dup", "base_role": "recruiter"}
        assert client.post("/api/v1/roles", headers=headers, json=payload).status_code == 201
        assert client.post("/api/v1/roles", headers=headers, json=payload).status_code == 400


class TestUpdateRole:
    def test_update_custom_label(self, client, sa_headers, test_tenant):
        headers = _tenant_headers(sa_headers, test_tenant)
        client.post("/api/v1/roles", headers=headers, json={
            "key": "cust1", "label": "Old", "base_role": "bdm"})
        resp = client.put("/api/v1/roles/cust1", headers=headers, json={"label": "New Label"})
        assert resp.status_code == 200
        assert resp.json()["label"] == "New Label"

    def test_override_builtin_label(self, client, sa_headers, test_tenant):
        headers = _tenant_headers(sa_headers, test_tenant)
        resp = client.put("/api/v1/roles/bdm", headers=headers, json={"label": "Biz Dev Mgr"})
        assert resp.status_code == 200
        roles = {r["key"]: r for r in client.get("/api/v1/roles", headers=headers).json()["roles"]}
        assert roles["bdm"]["label"] == "Biz Dev Mgr"

    def test_cannot_change_builtin_base_role(self, client, sa_headers, test_tenant):
        headers = _tenant_headers(sa_headers, test_tenant)
        resp = client.put("/api/v1/roles/recruiter", headers=headers, json={"base_role": "admin"})
        assert resp.status_code == 400


class TestDeleteRole:
    def test_delete_custom_role(self, client, sa_headers, test_tenant):
        headers = _tenant_headers(sa_headers, test_tenant)
        client.post("/api/v1/roles", headers=headers, json={
            "key": "temp_role", "label": "Temp", "base_role": "recruiter"})
        resp = client.delete("/api/v1/roles/temp_role", headers=headers)
        assert resp.status_code == 200
        listed = {r["key"] for r in client.get("/api/v1/roles", headers=headers).json()["roles"]}
        assert "temp_role" not in listed

    def test_cannot_delete_builtin(self, client, sa_headers, test_tenant):
        headers = _tenant_headers(sa_headers, test_tenant)
        resp = client.delete("/api/v1/roles/bdm", headers=headers)
        assert resp.status_code == 400

    def test_cannot_delete_role_in_use(self, client, db_session, sa_headers, test_tenant):
        headers = _tenant_headers(sa_headers, test_tenant)
        client.post("/api/v1/roles", headers=headers, json={
            "key": "in_use_role", "label": "In Use", "base_role": "bdm"})
        # assign a user to it
        db_session.add(User(
            email="assigned@test.com", password_hash=get_password_hash("x"),
            full_name="Assigned", role="in_use_role", is_active=True,
            is_verified=True, tenant_id=test_tenant.tenant_id,
        ))
        db_session.commit()
        resp = client.delete("/api/v1/roles/in_use_role", headers=headers)
        assert resp.status_code == 400
        assert "assigned" in resp.json()["detail"].lower()
