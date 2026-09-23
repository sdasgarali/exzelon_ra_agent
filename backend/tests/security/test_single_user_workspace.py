"""One user, one workspace (2026-09-23).

Anyone who signs up gets their own tenant under the platform and is its only user.
They cannot add users, lines of business or tenants — those are super_admin actions.
Each test here closes a route a tenant admin could otherwise use to do one of them.
"""
import pytest

from app.core.plans import PLAN_MATRIX
from app.db.models.outreach_role import OutreachRole
from app.db.models.user import User

pytestmark = pytest.mark.security


def _user_payload(email, **kw):
    return {"email": email, "password": "SecurePass123!", "full_name": "Extra Seat",
            "role": "recruiter", **kw}


def test_every_plan_is_one_user_and_one_lob():
    for key, spec in PLAN_MATRIX.items():
        assert spec.max_users == 1, key
        assert spec.max_lobs == 1, key


class TestTenantAdminCannotAddUsers:
    def test_users_endpoint(self, client, auth_headers):
        resp = client.post("/api/v1/users", headers=auth_headers, json=_user_payload("x1@test.com"))
        assert resp.status_code == 403

    def test_register_endpoint(self, client, auth_headers):
        resp = client.post("/api/v1/auth/register", headers=auth_headers, json=_user_payload("x2@test.com"))
        assert resp.status_code == 403

    def test_super_admin_still_can(self, client, sa_headers, test_tenant):
        resp = client.post("/api/v1/users", headers=sa_headers,
                           json=_user_payload("x3@test.com", tenant_id=test_tenant.tenant_id))
        assert resp.status_code == 201, resp.text

    def test_personal_mailbox_does_not_mint_a_login(self, client, db_session, auth_headers, test_tenant):
        """A non-RA mailbox would normally create a login user for its address — the
        back door to a second seat. For a tenant admin the mailbox is created, unlinked."""
        role = OutreachRole(tenant_id=test_tenant.tenant_id, role_name="BDM", auto_outbound=False)
        db_session.add(role)
        db_session.commit()
        db_session.refresh(role)

        resp = client.post("/api/v1/mailboxes", headers=auth_headers, json={
            "email": "second.seat@corp.com", "provider": "microsoft_365",
            "outreach_role_id": role.role_id, "login_password": "SecurePass123!",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["user_id"] is None
        assert db_session.query(User).filter(User.email == "second.seat@corp.com").first() is None


class TestTenantAdminCannotManageLobs:
    def test_create_lob(self, client, auth_headers):
        resp = client.post("/api/v1/lob/", headers=auth_headers,
                           json={"name": "Second line", "lob_type": "staffing"})
        assert resp.status_code == 403

    @pytest.mark.parametrize("method,path", [
        ("put", "/api/v1/lob/1"),
        ("delete", "/api/v1/lob/1"),
        ("post", "/api/v1/lob/1/set-default"),
    ])
    def test_modify_lob(self, client, auth_headers, method, path):
        kwargs = {"json": {"name": "Renamed"}} if method == "put" else {}
        resp = getattr(client, method)(path, headers=auth_headers, **kwargs)
        assert resp.status_code == 403


def test_tenant_admin_cannot_create_tenants(client, auth_headers):
    resp = client.post("/api/v1/admin/tenants", headers=auth_headers,
                       json={"name": "Sub Tenant", "slug": "sub-tenant"})
    assert resp.status_code == 403
