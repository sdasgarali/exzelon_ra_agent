"""Cross-tenant isolation regression suite (Epic 1A — ELR-001..007).

Each test builds TWO tenants (A and B) with their own data and asserts that
tenant A's admin can never read tenant B's data through the endpoints that were
found leaking in the 2026-08-25 enterprise-launch audit. A failure here is a
launch blocker — it means a paying tenant can see another tenant's data.
"""
import pytest

from app.core.security import get_password_hash, create_access_token
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.deal import Deal, DealStage
from app.db.models.contact import ContactDetails
from app.db.models.client import ClientInfo
from app.db.models.visitor import VisitorEvent

pytestmark = [pytest.mark.integration, pytest.mark.security]


# ---------------------------------------------------------------------------
# Two-tenant fixture
# ---------------------------------------------------------------------------

def _make_tenant(db, name, slug):
    t = Tenant(name=name, slug=slug, plan=TenantPlan.ENTERPRISE,
               max_users=999, max_mailboxes=999, max_contacts=999999,
               max_campaigns=999, max_leads=999999)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_admin(db, tenant, email):
    u = User(email=email, password_hash=get_password_hash("testpassword"),
             full_name=f"Admin {email}", role=UserRole.ADMIN,
             is_active=True, is_verified=True, tenant_id=tenant.tenant_id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _headers(user):
    tok = create_access_token(data={
        "sub": user.email, "role": user.role,
        "tenant_id": user.tenant_id, "plan": "enterprise",
    })
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def two_tenants(db_session):
    """Tenant A and Tenant B, each with an admin. Returns a dict of handles."""
    a = _make_tenant(db_session, "Tenant A", "tenant-a")
    b = _make_tenant(db_session, "Tenant B", "tenant-b")
    admin_a = _make_admin(db_session, a, "admin-a@test.com")
    admin_b = _make_admin(db_session, b, "admin-b@test.com")
    return {
        "db": db_session,
        "a": a, "b": b,
        "admin_a": admin_a, "admin_b": admin_b,
        "headers_a": _headers(admin_a), "headers_b": _headers(admin_b),
    }


def _won_stage(db, tenant):
    s = DealStage(tenant_id=tenant.tenant_id, name="Won", stage_order=1, is_won=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ---------------------------------------------------------------------------
# ELR-004 — visitor events
# ---------------------------------------------------------------------------

def test_visitors_isolated_by_tenant(two_tenants, client):
    db = two_tenants["db"]
    db.add_all([
        VisitorEvent(tenant_id=two_tenants["a"].tenant_id, visitor_id="vA",
                     page_url="https://a.example/page", company_name="ACo"),
        VisitorEvent(tenant_id=two_tenants["b"].tenant_id, visitor_id="vB",
                     page_url="https://b.example/secret", company_name="BCo"),
    ])
    db.commit()

    r = client.get("/api/v1/visitors?days=90", headers=two_tenants["headers_a"])
    assert r.status_code == 200
    items = r.json()["items"]
    vids = {i["visitor_id"] for i in items}
    assert "vA" in vids
    assert "vB" not in vids, "Tenant A leaked Tenant B visitor events"

    # Stats must not count the other tenant's events either.
    rs = client.get("/api/v1/visitors/stats?days=90", headers=two_tenants["headers_a"])
    assert rs.status_code == 200
    companies = {c["company_name"] for c in rs.json()["top_companies"]}
    assert "BCo" not in companies


def test_track_stamps_tenant_from_site_token(two_tenants, client):
    # The public pixel POST stamps the owning tenant via its slug token.
    r = client.post("/api/v1/visitors/track", json={
        "visitor_id": "v1", "page_url": "https://a.example/x",
        "site": two_tenants["a"].slug,
    })
    assert r.status_code == 200
    ev = two_tenants["db"].query(VisitorEvent).filter(
        VisitorEvent.visitor_id == "v1").first()
    assert ev is not None
    assert ev.tenant_id == two_tenants["a"].tenant_id

    # Unknown token → no tenant (super-admin-only, never leaked to a tenant).
    r2 = client.post("/api/v1/visitors/track", json={
        "visitor_id": "v2", "page_url": "https://x/y", "site": "no-such-slug",
    })
    assert r2.status_code == 200
    ev2 = two_tenants["db"].query(VisitorEvent).filter(
        VisitorEvent.visitor_id == "v2").first()
    assert ev2.tenant_id is None


# ---------------------------------------------------------------------------
# ELR-003 — deal sub-resource reads
# ---------------------------------------------------------------------------

def test_deal_detail_rejects_cross_tenant_subresources(two_tenants, client):
    db = two_tenants["db"]
    # Tenant B contact/client that must never surface in Tenant A's deal view.
    b_contact = ContactDetails(
        tenant_id=two_tenants["b"].tenant_id, client_name="BSecret Inc",
        first_name="Bob", last_name="Secret", email="bob@bsecret.com")
    b_client = ClientInfo(tenant_id=two_tenants["b"].tenant_id, client_name="BSecret Inc")
    db.add_all([b_contact, b_client])
    db.commit()
    db.refresh(b_contact)
    db.refresh(b_client)

    stage_a = _won_stage(db, two_tenants["a"])
    # A tenant-A deal that (via a bug/stale ref) points at tenant B's contact/client.
    deal = Deal(tenant_id=two_tenants["a"].tenant_id, name="Cross deal",
                stage_id=stage_a.stage_id, contact_id=b_contact.contact_id,
                client_id=b_client.client_id, owner_id=two_tenants["admin_a"].user_id)
    db.add(deal)
    db.commit()
    db.refresh(deal)

    r = client.get(f"/api/v1/deals/{deal.deal_id}", headers=two_tenants["headers_a"])
    assert r.status_code == 200
    body = r.json()
    # The cross-tenant contact/client must NOT be resolved into the response.
    assert body.get("contact_email") != "bob@bsecret.com"
    assert body.get("contact_name") != "Bob Secret"
    assert body.get("client_name") != "BSecret Inc"


# ---------------------------------------------------------------------------
# ELR-001 — team leaderboard is per-user + tenant scoped
# ---------------------------------------------------------------------------

def test_leaderboard_is_per_user_and_tenant_scoped(two_tenants, client):
    db = two_tenants["db"]
    stage_a = _won_stage(db, two_tenants["a"])
    stage_b = _won_stage(db, two_tenants["b"])
    # One won deal in each tenant.
    db.add_all([
        Deal(tenant_id=two_tenants["a"].tenant_id, name="A win", stage_id=stage_a.stage_id,
             value=1000, owner_id=two_tenants["admin_a"].user_id),
        Deal(tenant_id=two_tenants["b"].tenant_id, name="B win", stage_id=stage_b.stage_id,
             value=5000, owner_id=two_tenants["admin_b"].user_id),
    ])
    db.commit()

    r = client.get("/api/v1/analytics/team-leaderboard?days=90", headers=two_tenants["headers_a"])
    assert r.status_code == 200
    board = r.json()["leaderboard"]
    # Only tenant A's user appears, and their win count is exactly 1 (not inflated
    # by tenant B, and not the tenant-wide total for every row).
    emails_by_id = {row["user_id"]: row for row in board}
    assert two_tenants["admin_b"].user_id not in emails_by_id
    a_row = emails_by_id[two_tenants["admin_a"].user_id]
    assert a_row["deals_won"] == 1
    assert a_row["total_won_value"] == 1000.0


# ---------------------------------------------------------------------------
# ELR-002 — revenue analytics stage IDs are tenant scoped
# ---------------------------------------------------------------------------

def test_revenue_stage_ids_tenant_scoped(two_tenants, client):
    db = two_tenants["db"]
    stage_a = _won_stage(db, two_tenants["a"])
    stage_b = _won_stage(db, two_tenants["b"])
    db.add_all([
        Deal(tenant_id=two_tenants["a"].tenant_id, name="A win", stage_id=stage_a.stage_id,
             value=1000, owner_id=two_tenants["admin_a"].user_id),
        Deal(tenant_id=two_tenants["b"].tenant_id, name="B win", stage_id=stage_b.stage_id,
             value=5000, owner_id=two_tenants["admin_b"].user_id),
    ])
    db.commit()

    r = client.get("/api/v1/analytics/revenue?days=90", headers=two_tenants["headers_a"])
    assert r.status_code == 200
    body = r.json()
    # Tenant A revenue must be its own 1000, never 6000 (B's stage IDs pollute).
    assert float(body["total_won_value"]) == 1000.0
