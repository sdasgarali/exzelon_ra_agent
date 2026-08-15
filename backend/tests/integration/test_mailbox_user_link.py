"""Tests for mailbox↔user linking on mailbox creation (personal vs RA/machine)."""
import pytest

from app.db.models.outreach_role import OutreachRole
from app.db.models.user import User
from app.services.mailbox_user_link import map_outreach_role_to_rbac

pytestmark = pytest.mark.integration


@pytest.fixture
def roles(db_session, test_tenant):
    tid = test_tenant.tenant_id
    ra = OutreachRole(tenant_id=tid, role_name="RA", auto_outbound=True)
    bdm = OutreachRole(tenant_id=tid, role_name="BDM", auto_outbound=False)
    db_session.add_all([ra, bdm])
    db_session.commit()
    db_session.refresh(ra)
    db_session.refresh(bdm)
    return {"ra": ra, "bdm": bdm}


def _mb(email, role_id, **kw):
    return {"email": email, "provider": "microsoft_365", "outreach_role_id": role_id, **kw}


class TestRoleMap:
    def test_maps_known_roles(self):
        assert map_outreach_role_to_rbac("BDM") == "bdm"
        assert map_outreach_role_to_rbac("BD") == "bdm"
        assert map_outreach_role_to_rbac("Recruiter") == "recruiter"
        assert map_outreach_role_to_rbac("Admin") == "admin"

    def test_unknown_falls_back_to_recruiter(self):
        assert map_outreach_role_to_rbac("Some Custom") == "recruiter"
        assert map_outreach_role_to_rbac(None) == "recruiter"


class TestPersonalMailboxCreatesUser:
    def test_non_ra_with_login_password_creates_user(self, client, db_session, sa_headers, test_tenant, roles):
        headers = {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}
        resp = client.post("/api/v1/mailboxes", headers=headers,
                          json=_mb("bdmbox@corp.com", roles["bdm"].role_id,
                                   login_password="SecurePass123!", display_name="Deal Maker"))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["user_id"] is not None
        # a login user now exists with the mailbox email + mapped role
        u = db_session.query(User).filter(User.email == "bdmbox@corp.com").first()
        assert u is not None
        assert u.role == "bdm"
        assert u.tenant_id == test_tenant.tenant_id

    def test_non_ra_without_login_password_rejected(self, client, sa_headers, test_tenant, roles):
        headers = {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}
        resp = client.post("/api/v1/mailboxes", headers=headers,
                          json=_mb("nopass@corp.com", roles["bdm"].role_id))
        assert resp.status_code == 400
        assert "password" in resp.json()["detail"].lower()

    def test_non_ra_links_existing_user(self, client, db_session, sa_headers, test_tenant, roles):
        existing = User(email="already@corp.com", password_hash="x", full_name="Already",
                        role="bdm", tenant_id=test_tenant.tenant_id, is_active=True, is_verified=True)
        db_session.add(existing)
        db_session.commit()
        db_session.refresh(existing)
        before = db_session.query(User).count()
        headers = {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}
        resp = client.post("/api/v1/mailboxes", headers=headers,
                          json=_mb("already@corp.com", roles["bdm"].role_id))
        assert resp.status_code == 200, resp.text
        assert resp.json()["user_id"] == existing.user_id
        assert db_session.query(User).count() == before  # linked, not created


class TestRaMailboxHasNoUser:
    def test_ra_mailbox_creates_no_user(self, client, db_session, sa_headers, test_tenant, roles):
        headers = {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}
        resp = client.post("/api/v1/mailboxes", headers=headers,
                          json=_mb("ra1@machine.com", roles["ra"].role_id, login_password="ignored"))
        assert resp.status_code == 200, resp.text
        assert resp.json()["user_id"] is None
        assert db_session.query(User).filter(User.email == "ra1@machine.com").first() is None
