"""A plan change moves the month's credits with it, and an ended subscription returns
the tenant to Free (2026-09-23).

Before this, an upgrade's credits only arrived at the next monthly refill, and a
cancelled or unpaid subscription left the tenant on the paid plan indefinitely.
"""
from datetime import date, timedelta

import pytest

from app.db.models.credit_balance import TenantCreditBalance
from app.db.models.subscription import SubscriptionRecord
from app.db.models.tenant import TenantPlan
from app.services.billing.plan_change import change_plan
from app.services.credit_metering import get_balance

pytestmark = pytest.mark.integration

FREE, PRO, MAX = 300, 6_000, 25_000


def _balance(db, tenant, *, allowance, topup=0.0):
    b = get_balance(db, tenant.tenant_id)
    b.allowance_credits = float(allowance)
    b.topup_credits = float(topup)
    db.commit()
    return b


def _on_plan(db, tenant, plan):
    tenant.plan = plan
    db.commit()
    return tenant


class TestCreditsFollowThePlan:
    def test_upgrade_mid_month_adds_the_difference_now(self, db_session, starter_tenant):
        b = _balance(db_session, starter_tenant, allowance=FREE - 100)  # spent 100 of Free
        change_plan(db_session, starter_tenant, TenantPlan.PRO, reason="test")
        assert b.allowance_credits == PRO - 100

    def test_downgrade_keeps_what_is_left_of_the_new_allowance(self, db_session, starter_tenant):
        _on_plan(db_session, starter_tenant, TenantPlan.PRO)
        b = _balance(db_session, starter_tenant, allowance=PRO - 100)
        change_plan(db_session, starter_tenant, TenantPlan.FREE, reason="test")
        assert b.allowance_credits == FREE - 100

    def test_downgrade_never_goes_below_zero(self, db_session, starter_tenant):
        _on_plan(db_session, starter_tenant, TenantPlan.PRO)
        b = _balance(db_session, starter_tenant, allowance=PRO - 5_000)
        change_plan(db_session, starter_tenant, TenantPlan.FREE, reason="test")
        assert b.allowance_credits == 0

    def test_downgrade_does_not_deepen_existing_overage(self, db_session, starter_tenant):
        _on_plan(db_session, starter_tenant, TenantPlan.PRO)
        b = _balance(db_session, starter_tenant, allowance=-50)
        change_plan(db_session, starter_tenant, TenantPlan.FREE, reason="test")
        assert b.allowance_credits == -50

    def test_topups_are_never_touched(self, db_session, starter_tenant):
        b = _balance(db_session, starter_tenant, allowance=FREE, topup=1_000)
        change_plan(db_session, starter_tenant, TenantPlan.MAX, reason="test")
        assert b.topup_credits == 1_000
        change_plan(db_session, starter_tenant, TenantPlan.FREE, reason="test")
        assert b.topup_credits == 1_000

    def test_stale_month_refills_on_the_new_plan_without_a_second_delta(self, db_session, starter_tenant):
        b = _balance(db_session, starter_tenant, allowance=10)
        b.period_start = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
        db_session.commit()
        change_plan(db_session, starter_tenant, TenantPlan.PRO, reason="test")
        assert b.allowance_credits == PRO

    def test_no_balance_row_yet_is_seeded_from_the_new_plan(self, db_session, starter_tenant):
        change_plan(db_session, starter_tenant, TenantPlan.PRO, reason="test")
        db_session.commit()
        assert get_balance(db_session, starter_tenant.tenant_id).allowance_credits == PRO


def _prices(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO", "price_pro", raising=False)
    monkeypatch.setattr(settings, "STRIPE_PRICE_MAX", "price_max", raising=False)


def _sub(sub_id="sub_1", status="active", price="price_pro"):
    return {"id": sub_id, "customer": "cus_1", "status": status,
            "items": {"data": [{"price": {"id": price}}]}}


class TestStripeSync:
    def _upsert(self, db, tenant, sub_obj):
        from app.services.billing.subscription_service import upsert_from_stripe
        upsert_from_stripe(db, sub_obj, tenant.tenant_id)
        db.commit()
        db.refresh(tenant)

    def test_paid_upgrade_grants_the_new_allowance_immediately(self, db_session, starter_tenant, monkeypatch):
        _prices(monkeypatch)
        b = _balance(db_session, starter_tenant, allowance=FREE)
        self._upsert(db_session, starter_tenant, _sub())
        assert starter_tenant.plan == TenantPlan.PRO
        assert b.allowance_credits == PRO

    @pytest.mark.parametrize("ended", ["canceled", "unpaid"])
    def test_ended_subscription_returns_the_tenant_to_free(self, db_session, starter_tenant, monkeypatch, ended):
        _prices(monkeypatch)
        self._upsert(db_session, starter_tenant, _sub())
        b = _balance(db_session, starter_tenant, allowance=PRO - 100)
        self._upsert(db_session, starter_tenant, _sub(status=ended))
        assert starter_tenant.plan == TenantPlan.FREE
        assert b.allowance_credits == FREE - 100

    def test_past_due_keeps_the_plan_while_stripe_retries(self, db_session, starter_tenant, monkeypatch):
        _prices(monkeypatch)
        self._upsert(db_session, starter_tenant, _sub())
        self._upsert(db_session, starter_tenant, _sub(status="past_due"))
        assert starter_tenant.plan == TenantPlan.PRO

    def test_end_of_a_superseded_subscription_is_ignored(self, db_session, starter_tenant, monkeypatch):
        """They moved to sub_2; Stripe's late 'deleted' for sub_1 must not downgrade them."""
        _prices(monkeypatch)
        self._upsert(db_session, starter_tenant, _sub("sub_1"))
        self._upsert(db_session, starter_tenant, _sub("sub_2", price="price_max"))
        self._upsert(db_session, starter_tenant, _sub("sub_1", status="canceled"))
        assert starter_tenant.plan == TenantPlan.MAX
        rec = db_session.query(SubscriptionRecord).filter_by(tenant_id=starter_tenant.tenant_id).one()
        assert rec.stripe_subscription_id == "sub_2"


def test_super_admin_plan_change_moves_credits(client, db_session, sa_headers, starter_tenant):
    b = _balance(db_session, starter_tenant, allowance=FREE - 100)
    resp = client.put(f"/api/v1/admin/tenants/{starter_tenant.tenant_id}", headers=sa_headers,
                      json={"plan": "pro"})
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    b = db_session.query(TenantCreditBalance).filter_by(tenant_id=starter_tenant.tenant_id).one()
    assert b.allowance_credits == PRO - 100
