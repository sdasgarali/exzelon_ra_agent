"""/billing/usage `upgrade_options`: the in-app plan picker's source of truth.

A Free workspace must be offered Pro AND Max (the pricing page lets a visitor pick
Max, and the picker has to honour that), priced from PLAN_MATRIX, never hardcoded.
"""
import pytest

from app.core.plans import PLAN_MATRIX
from app.core.security import create_access_token, get_password_hash
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User, UserRole

pytestmark = pytest.mark.integration


def _admin(db, plan, slug):
    t = Tenant(name=f"Upg {slug}", slug=slug, plan=plan)
    db.add(t)
    db.commit()
    db.refresh(t)
    u = User(email=f"{slug}@test.com", password_hash=get_password_hash("testpassword"),
             full_name="Admin", role=UserRole.ADMIN, is_active=True, is_verified=True,
             tenant_id=t.tenant_id)
    db.add(u)
    db.commit()
    tok = create_access_token(data={"sub": u.email, "role": u.role,
                                    "tenant_id": t.tenant_id, "plan": plan.value})
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.parametrize("plan,expected", [
    (TenantPlan.FREE, ["pro", "max"]),
    (TenantPlan.PRO, ["max"]),
    (TenantPlan.MAX, []),
])
def test_upgrade_options_list_every_higher_tier(client, db_session, plan, expected):
    headers = _admin(db_session, plan, f"upg-{plan.value}")
    r = client.get("/api/v1/billing/usage", headers=headers)
    assert r.status_code == 200
    opts = r.json()["upgrade_options"]
    assert [o["key"] for o in opts] == expected
    for o in opts:
        spec = PLAN_MATRIX[o["key"]]
        assert o["label"] == spec.label
        assert o["monthly_price_cents"] == spec.monthly_price_cents
        assert o["annual_price_cents"] == spec.annual_price_cents
        assert o["credits_per_month"] == spec.credits_per_month
        assert o["send_quota_per_month"] == spec.send_quota_per_month
