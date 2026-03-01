"""Cross-tenant isolation security tests.

Verifies that Tenant A users cannot access Tenant B data, and that
Super Admin can access both tenants' data.
"""
import pytest
from datetime import date

from app.core.security import get_password_hash, create_access_token
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.contact import ContactDetails
from app.db.models.client import ClientInfo
from app.db.models.email_template import EmailTemplate, TemplateStatus
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus


# ---------------------------------------------------------------------------
# Fixtures: Two tenants with separate users and data
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_a(db_session):
    """Tenant A (already seeded as tenant_id=1)."""
    return db_session.query(Tenant).filter(Tenant.tenant_id == 1).first()


@pytest.fixture
def tenant_b(db_session):
    """Create a second tenant (tenant_id=2)."""
    t = Tenant(
        name="Tenant B Corp",
        slug="tenant-b-corp",
        is_active=True,
        max_users=5,
        max_mailboxes=10,
        plan="free",
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def user_a(db_session, tenant_a):
    """Admin user belonging to Tenant A."""
    u = User(
        email="admin-a@test.com",
        password_hash=get_password_hash("password"),
        full_name="Admin A",
        role=UserRole.ADMIN,
        is_active=True,
        tenant_id=1,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def user_b(db_session, tenant_b):
    """Admin user belonging to Tenant B."""
    u = User(
        email="admin-b@test.com",
        password_hash=get_password_hash("password"),
        full_name="Admin B",
        role=UserRole.ADMIN,
        is_active=True,
        tenant_id=tenant_b.tenant_id,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def super_admin_user(db_session):
    """Global Super Admin user (tenant_id=1 = master tenant)."""
    u = User(
        email="superadmin@test.com",
        password_hash=get_password_hash("password"),
        full_name="Super Admin",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        tenant_id=1,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def headers_a(user_a):
    token = create_access_token(data={
        "sub": user_a.email,
        "tenant_id": user_a.tenant_id,
        "role": user_a.role.value,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def headers_b(user_b):
    token = create_access_token(data={
        "sub": user_b.email,
        "tenant_id": user_b.tenant_id,
        "role": user_b.role.value,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def headers_sa(super_admin_user):
    token = create_access_token(data={
        "sub": super_admin_user.email,
        "tenant_id": 1,
        "role": super_admin_user.role.value,
    })
    return {"Authorization": f"Bearer {token}"}


# --- Data belonging to Tenant A ---

@pytest.fixture
def lead_a(db_session):
    lead = LeadDetails(
        client_name="Company A",
        job_title="Manager",
        state="TX",
        posting_date=date.today(),
        job_link="https://example.com/a-1",
        salary_min=50000,
        source="linkedin",
        lead_status=LeadStatus.NEW,
        tenant_id=1,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    return lead


@pytest.fixture
def contact_a(db_session):
    c = ContactDetails(
        first_name="Alice",
        last_name="Alpha",
        email="alice@tenanta.com",
        client_name="Company A",
        tenant_id=1,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def client_a(db_session):
    cl = ClientInfo(
        client_name="Company A",
        status="active",
        tenant_id=1,
    )
    db_session.add(cl)
    db_session.commit()
    db_session.refresh(cl)
    return cl


@pytest.fixture
def template_a(db_session):
    t = EmailTemplate(
        name="Template A",
        subject="Hello A",
        body_html="<p>A</p>",
        body_text="A",
        status=TemplateStatus.INACTIVE,
        tenant_id=1,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def mailbox_a(db_session):
    m = SenderMailbox(
        email="sender-a@tenanta.com",
        display_name="Sender A",
        password="fake",
        warmup_status=WarmupStatus.COLD_READY,
        is_active=True,
        connection_status="successful",
        daily_send_limit=30,
        tenant_id=1,
    )
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


# --- Data belonging to Tenant B ---

@pytest.fixture
def lead_b(db_session, tenant_b):
    lead = LeadDetails(
        client_name="Company B",
        job_title="Director",
        state="CA",
        posting_date=date.today(),
        job_link="https://example.com/b-1",
        salary_min=80000,
        source="indeed",
        lead_status=LeadStatus.NEW,
        tenant_id=tenant_b.tenant_id,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    return lead


@pytest.fixture
def contact_b(db_session, tenant_b):
    c = ContactDetails(
        first_name="Bob",
        last_name="Beta",
        email="bob@tenantb.com",
        client_name="Company B",
        tenant_id=tenant_b.tenant_id,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def template_b(db_session, tenant_b):
    t = EmailTemplate(
        name="Template B",
        subject="Hello B",
        body_html="<p>B</p>",
        body_text="B",
        status=TemplateStatus.INACTIVE,
        tenant_id=tenant_b.tenant_id,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


# ===========================================================================
# CROSS-TENANT ISOLATION TESTS
# ===========================================================================


class TestLeadIsolation:
    """Tenant A user cannot access Tenant B leads."""

    def test_tenant_a_cannot_list_tenant_b_leads(
        self, client, headers_a, lead_a, lead_b
    ):
        resp = client.get("/api/v1/leads", headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        lead_ids = [l["lead_id"] for l in items]
        assert lead_a.lead_id in lead_ids
        assert lead_b.lead_id not in lead_ids

    def test_tenant_a_cannot_get_tenant_b_lead(
        self, client, headers_a, lead_b
    ):
        resp = client.get(f"/api/v1/leads/{lead_b.lead_id}", headers=headers_a)
        assert resp.status_code == 404

    def test_tenant_a_cannot_update_tenant_b_lead(
        self, client, headers_a, lead_b
    ):
        resp = client.put(
            f"/api/v1/leads/{lead_b.lead_id}",
            json={"client_name": "Hacked"},
            headers=headers_a,
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_delete_tenant_b_lead(
        self, client, headers_a, lead_b
    ):
        resp = client.delete(
            f"/api/v1/leads/{lead_b.lead_id}", headers=headers_a
        )
        assert resp.status_code == 404


class TestContactIsolation:
    """Tenant A user cannot access Tenant B contacts."""

    def test_tenant_a_cannot_list_tenant_b_contacts(
        self, client, headers_a, contact_a, contact_b
    ):
        resp = client.get("/api/v1/contacts", headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        emails = [c["email"] for c in items]
        assert "alice@tenanta.com" in emails
        assert "bob@tenantb.com" not in emails

    def test_tenant_a_cannot_get_tenant_b_contact(
        self, client, headers_a, contact_b
    ):
        resp = client.get(
            f"/api/v1/contacts/{contact_b.contact_id}", headers=headers_a
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_update_tenant_b_contact(
        self, client, headers_a, contact_b
    ):
        resp = client.put(
            f"/api/v1/contacts/{contact_b.contact_id}",
            json={"first_name": "Hacked"},
            headers=headers_a,
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_delete_tenant_b_contact(
        self, client, headers_a, contact_b
    ):
        resp = client.delete(
            f"/api/v1/contacts/{contact_b.contact_id}", headers=headers_a
        )
        assert resp.status_code == 404


class TestTemplateIsolation:
    """Tenant A user cannot access Tenant B templates."""

    def test_tenant_a_cannot_list_tenant_b_templates(
        self, client, headers_a, template_a, template_b
    ):
        resp = client.get("/api/v1/templates", headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        names = [t["name"] for t in items]
        assert "Template A" in names
        assert "Template B" not in names

    def test_tenant_a_cannot_get_tenant_b_template(
        self, client, headers_a, template_b
    ):
        resp = client.get(
            f"/api/v1/templates/{template_b.template_id}", headers=headers_a
        )
        assert resp.status_code == 404


class TestSuperAdminCrossTenant:
    """Super Admin can access data from all tenants."""

    def test_super_admin_sees_all_leads(
        self, client, headers_sa, lead_a, lead_b
    ):
        resp = client.get("/api/v1/leads", headers=headers_sa)
        assert resp.status_code == 200
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        lead_ids = [l["lead_id"] for l in items]
        assert lead_a.lead_id in lead_ids
        assert lead_b.lead_id in lead_ids

    def test_super_admin_sees_all_contacts(
        self, client, headers_sa, contact_a, contact_b
    ):
        resp = client.get("/api/v1/contacts", headers=headers_sa)
        assert resp.status_code == 200
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        emails = [c["email"] for c in items]
        assert "alice@tenanta.com" in emails
        assert "bob@tenantb.com" in emails

    def test_super_admin_can_get_any_lead(
        self, client, headers_sa, lead_a, lead_b
    ):
        resp_a = client.get(f"/api/v1/leads/{lead_a.lead_id}", headers=headers_sa)
        resp_b = client.get(f"/api/v1/leads/{lead_b.lead_id}", headers=headers_sa)
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200

    def test_super_admin_can_switch_tenant_context(
        self, client, headers_sa, lead_a, lead_b
    ):
        """Super Admin with X-Tenant-Id header sees only that tenant's data."""
        resp = client.get(
            "/api/v1/leads",
            headers={**headers_sa, "X-Tenant-Id": str(lead_b.tenant_id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        lead_ids = [l["lead_id"] for l in items]
        assert lead_b.lead_id in lead_ids
        assert lead_a.lead_id not in lead_ids


class TestTenantAPIIsolation:
    """Tenant management API is Super Admin only."""

    def test_tenant_admin_cannot_list_tenants(self, client, headers_a):
        resp = client.get("/api/v1/tenants", headers=headers_a)
        assert resp.status_code == 403

    def test_tenant_admin_cannot_create_tenant(self, client, headers_a):
        resp = client.post(
            "/api/v1/tenants",
            json={"name": "Evil Tenant", "slug": "evil-tenant"},
            headers=headers_a,
        )
        assert resp.status_code == 403

    def test_super_admin_can_list_tenants(
        self, client, headers_sa, tenant_a, tenant_b
    ):
        resp = client.get("/api/v1/tenants", headers=headers_sa)
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "Test Tenant" in names
        assert "Tenant B Corp" in names

    def test_super_admin_can_create_tenant(self, client, headers_sa):
        resp = client.post(
            "/api/v1/tenants",
            json={"name": "New Tenant", "slug": "new-tenant"},
            headers=headers_sa,
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "New Tenant"


class TestUserIsolation:
    """Tenant Admin cannot manage users in other tenants."""

    def test_tenant_admin_cannot_access_users_endpoint(
        self, client, headers_a, user_a, user_b
    ):
        """Tenant admin (non-SA) cannot access /users — requires super_admin role."""
        resp = client.get("/api/v1/users", headers=headers_a)
        assert resp.status_code == 403

    def test_tenant_admin_cannot_get_user_by_id(
        self, client, headers_a, user_b
    ):
        """Tenant admin cannot access individual user endpoint."""
        resp = client.get(
            f"/api/v1/users/{user_b.user_id}", headers=headers_a
        )
        assert resp.status_code == 403

    def test_super_admin_sees_all_users(
        self, client, headers_sa, user_a, user_b
    ):
        resp = client.get("/api/v1/users", headers=headers_sa)
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert "admin-a@test.com" in emails
        assert "admin-b@test.com" in emails
