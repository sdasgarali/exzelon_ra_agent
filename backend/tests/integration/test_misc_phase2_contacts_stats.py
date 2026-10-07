"""GET /contacts/stats: tenant-scoped link counts and plain enum-value keys (MCP phase 2)."""
import pytest

from app.core.security import create_access_token, get_password_hash
from app.db.models.contact import ContactDetails, PriorityLevel
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User, UserRole

pytestmark = pytest.mark.integration


def _tenant(db, slug):
    t = Tenant(name=slug.title(), slug=slug, plan=TenantPlan.ENTERPRISE,
               max_users=99, max_mailboxes=99, max_contacts=9999, max_campaigns=99, max_leads=9999)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _admin_headers(db, tenant, email):
    u = User(email=email, password_hash=get_password_hash("x"), full_name="A",
             role=UserRole.ADMIN, is_active=True, is_verified=True, tenant_id=tenant.tenant_id)
    db.add(u)
    db.commit()
    token = create_access_token(data={"sub": u.email, "role": "admin", "tenant_id": tenant.tenant_id,
                                      "plan": "enterprise"})
    return {"Authorization": f"Bearer {token}"}


def _contact(db, tenant, n, **kw):
    c = ContactDetails(tenant_id=tenant.tenant_id, client_name="Acme", first_name=f"F{n}",
                       last_name="L", email=f"c{n}-{tenant.slug}@acme.example", **kw)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def two_tenants(db_session, test_tenant):
    """test_tenant holds linked contacts; `empty` has nothing at all."""
    lead = LeadDetails(tenant_id=test_tenant.tenant_id, client_name="Acme", job_title="Nurse",
                       state="TX", lead_status=LeadStatus.OPEN, source="test")
    db_session.add(lead)
    db_session.commit()
    c1 = _contact(db_session, test_tenant, 1, priority_level=PriorityLevel.P1_JOB_POSTER,
                  validation_status="valid")
    c2 = _contact(db_session, test_tenant, 2, priority_level=PriorityLevel.P1_JOB_POSTER,
                  validation_status="invalid", lead_id=lead.lead_id)  # legacy FK link
    _contact(db_session, test_tenant, 3, priority_level=PriorityLevel.P3_HR_MANAGER)  # unlinked
    db_session.add(LeadContactAssociation(lead_id=lead.lead_id, contact_id=c1.contact_id))
    db_session.add(LeadContactAssociation(lead_id=lead.lead_id, contact_id=c2.contact_id))
    db_session.commit()
    return test_tenant, _tenant(db_session, "empty-co")


def test_empty_tenant_sees_zero_links_not_other_tenants(client, db_session, two_tenants):
    _, empty = two_tenants
    h = _admin_headers(db_session, empty, "admin@empty.example")
    data = client.get("/api/v1/contacts/stats", headers=h).json()
    assert data["total"] == 0
    assert data["linked_to_leads"] == 0
    assert data["unlinked"] == 0
    assert data["by_priority"] == {} and data["by_validation"] == {}


def test_linked_counts_junction_and_legacy_fk_once(client, auth_headers, two_tenants):
    data = client.get("/api/v1/contacts/stats", headers=auth_headers).json()
    assert data["total"] == 3
    assert data["linked_to_leads"] == 2  # c1 via junction, c2 via both -> counted once
    assert data["unlinked"] == 1


def test_stats_keys_are_enum_values(client, auth_headers, two_tenants):
    data = client.get("/api/v1/contacts/stats", headers=auth_headers).json()
    assert data["by_priority"] == {"p1_job_poster": 2, "p3_hr_manager": 1}
    assert data["by_validation"] == {"valid": 1, "invalid": 1}


def test_unlinked_never_negative_for_impersonating_super_admin(client, sa_headers, two_tenants):
    _, empty = two_tenants
    h = {**sa_headers, "X-Tenant-ID": str(empty.tenant_id)}
    data = client.get("/api/v1/contacts/stats", headers=h).json()
    assert data["linked_to_leads"] == 0 and data["unlinked"] == 0
