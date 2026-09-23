"""Plan gates over HTTP (Phase 3.2).

The unit tests cover the gate logic; these prove it is actually *mounted* — that a
Free tenant hitting a Pro router gets 402 rather than the feature, and that the
public tracking pixel was not caught in the blast radius.
"""
import pytest

from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User, UserRole
from app.core.security import create_access_token, get_password_hash

pytestmark = pytest.mark.integration


def _tenant_and_headers(db_session, plan, slug, email):
    tenant = Tenant(name=f"{slug} co", slug=slug, plan=plan)
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    user = User(
        email=email, password_hash=get_password_hash("testpassword"),
        full_name="Gate Admin", role=UserRole.ADMIN,
        is_active=True, is_verified=True, tenant_id=tenant.tenant_id,
    )
    db_session.add(user)
    db_session.commit()

    token = create_access_token(data={
        "sub": user.email, "role": user.role,
        "tenant_id": tenant.tenant_id, "plan": plan.value,
    })
    return tenant, {"Authorization": f"Bearer {token}"}


# Routers gated at mount time, with the plan each needs.
PRO_ONLY_PATHS = [
    "/api/v1/warmup/status",
    "/api/v1/webhooks",
    "/api/v1/automation/events",
    "/api/v1/roles",
]
MAX_ONLY_PATHS = [
    "/api/v1/backups",
    "/api/v1/visitors",
]


@pytest.mark.parametrize("path", PRO_ONLY_PATHS)
def test_free_tenant_gets_402_on_pro_routes(client, db_session, path):
    _, headers = _tenant_and_headers(
        db_session, TenantPlan.FREE, f"gate-free-{abs(hash(path)) % 9999}",
        f"free{abs(hash(path)) % 9999}@x.com")
    r = client.get(path, headers=headers)
    assert r.status_code == 402, f"{path} -> {r.status_code}"
    detail = r.json()["detail"]
    assert detail["code"] == "feature_not_in_plan"
    assert detail["required_plan"] in ("pro", "max")


@pytest.mark.parametrize("path", MAX_ONLY_PATHS)
def test_pro_tenant_gets_402_on_max_routes(client, db_session, path):
    _, headers = _tenant_and_headers(
        db_session, TenantPlan.PRO, f"gate-pro-{abs(hash(path)) % 9999}",
        f"pro{abs(hash(path)) % 9999}@x.com")
    r = client.get(path, headers=headers)
    assert r.status_code == 402, f"{path} -> {r.status_code}"
    assert r.json()["detail"]["required_plan"] == "max"


def test_max_tenant_is_not_gated(client, db_session):
    """Whatever these return, it must not be the plan gate."""
    _, headers = _tenant_and_headers(
        db_session, TenantPlan.MAX, "gate-max", "max@x.com")
    for path in PRO_ONLY_PATHS + MAX_ONLY_PATHS:
        r = client.get(path, headers=headers)
        assert r.status_code != 402, f"{path} unexpectedly gated for Max"


def test_free_tenant_keeps_the_core_loop(client, db_session):
    """Gating must not touch what Free is supposed to include."""
    _, headers = _tenant_and_headers(
        db_session, TenantPlan.FREE, "gate-core", "core@x.com")
    for path in ("/api/v1/leads", "/api/v1/contacts", "/api/v1/campaigns",
                 "/api/v1/templates", "/api/v1/mailboxes", "/api/v1/dashboard/stats"):
        r = client.get(path, headers=headers)
        assert r.status_code != 402, f"{path} should be included in Free"


def test_tracking_pixel_stays_public(client):
    """The pixel is served to anonymous browsers on the customer's own site.

    If the plan gate ever swallows this route it breaks every customer's website
    with a console error that looks like our bug.
    """
    r = client.get("/api/v1/visitors/pixel.js")
    assert r.status_code == 200
    assert "javascript" in r.headers.get("content-type", "").lower()


def test_track_beacon_accepts_but_drops_events_for_unentitled_plans(client, db_session):
    """A beacon must never 402 — it answers 200 and the event is simply not stored."""
    from app.db.models.visitor import VisitorEvent

    tenant, _ = _tenant_and_headers(
        db_session, TenantPlan.FREE, "gate-beacon", "beacon@x.com")

    r = client.post("/api/v1/visitors/track", json={
        "visitor_id": "v1", "page_url": "https://example.com/pricing",
        "site": tenant.slug,
    })
    assert r.status_code == 200
    assert r.json()["tracked"] is False
    assert db_session.query(VisitorEvent).filter(
        VisitorEvent.tenant_id == tenant.tenant_id).count() == 0


def test_track_beacon_stores_events_on_max(client, db_session):
    from app.db.models.visitor import VisitorEvent

    tenant, _ = _tenant_and_headers(
        db_session, TenantPlan.MAX, "gate-beacon-max", "beaconmax@x.com")

    r = client.post("/api/v1/visitors/track", json={
        "visitor_id": "v2", "page_url": "https://example.com/pricing",
        "site": tenant.slug,
    })
    assert r.status_code == 200
    assert db_session.query(VisitorEvent).filter(
        VisitorEvent.tenant_id == tenant.tenant_id).count() == 1
