"""Recurring Stripe subscriptions (ELR-021)."""
import pytest

from app.db.models.subscription import SubscriptionRecord, SubscriptionStatus
from app.db.models.tenant import TenantPlan

pytestmark = pytest.mark.integration


def _configure_prices(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_PRICE_STARTER", "price_starter", raising=False)
    monkeypatch.setattr(settings, "STRIPE_PRICE_PROFESSIONAL", "price_pro", raising=False)
    monkeypatch.setattr(settings, "STRIPE_PRICE_ENTERPRISE", "price_ent", raising=False)


def test_price_plan_mapping(monkeypatch):
    from app.services.billing.subscription_service import price_id_for_plan, plan_for_price_id
    _configure_prices(monkeypatch)
    assert price_id_for_plan("professional") == "price_pro"
    assert plan_for_price_id("price_pro") == "professional"
    assert price_id_for_plan("nope") == ""


def test_upsert_from_stripe_creates_and_syncs_plan(db_session, test_tenant, monkeypatch):
    from app.services.billing.subscription_service import upsert_from_stripe
    _configure_prices(monkeypatch)
    sub_obj = {
        "id": "sub_1", "customer": "cus_1", "status": "active",
        "cancel_at_period_end": False, "current_period_end": 1893456000,
        "items": {"data": [{"price": {"id": "price_pro"}}]},
    }
    rec = upsert_from_stripe(db_session, sub_obj, test_tenant.tenant_id)
    db_session.commit()
    assert rec.status == SubscriptionStatus.ACTIVE
    assert rec.plan == "professional"
    db_session.refresh(test_tenant)
    assert test_tenant.plan == TenantPlan.PROFESSIONAL  # tenant plan synced

    # Update to canceled → status changes, only one row.
    upsert_from_stripe(db_session, {**sub_obj, "status": "canceled"}, test_tenant.tenant_id)
    db_session.commit()
    assert db_session.query(SubscriptionRecord).filter_by(
        tenant_id=test_tenant.tenant_id).count() == 1
    assert db_session.query(SubscriptionRecord).filter_by(
        stripe_subscription_id="sub_1").first().status == SubscriptionStatus.CANCELED


def test_checkout_400_without_price_configured(client, sa_headers, test_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_PRICE_ENTERPRISE", "", raising=False)
    r = client.post("/api/v1/billing/subscription/checkout", json={},
                    headers={**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)})
    assert r.status_code == 400


def test_checkout_returns_url_when_configured(client, sa_headers, test_tenant, monkeypatch):
    _configure_prices(monkeypatch)
    from app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test", raising=False)
    # Stub the gateway so no real Stripe call is made.
    import app.services.billing.payment_gateway as pg

    class _Stub:
        def create_subscription_checkout(self, **kw):
            return {"checkout_url": "https://stripe.test/session", "session_id": "cs_1"}
    monkeypatch.setattr(pg, "get_payment_gateway", lambda: _Stub())

    r = client.post("/api/v1/billing/subscription/checkout", json={"plan": "professional"},
                    headers={**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)})
    assert r.status_code == 200
    assert r.json()["checkout_url"] == "https://stripe.test/session"


def test_get_subscription_status(client, db_session, test_tenant, auth_headers):
    db_session.add(SubscriptionRecord(
        tenant_id=test_tenant.tenant_id, stripe_subscription_id="sub_x",
        plan="professional", status=SubscriptionStatus.ACTIVE))
    db_session.commit()
    r = client.get("/api/v1/billing/subscription", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["subscription"]["plan"] == "professional"
    assert r.json()["subscription"]["status"] == "active"
