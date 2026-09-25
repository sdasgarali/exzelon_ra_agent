"""Top-up pricing and per-purchase expiry (2026-09-25).

Top-ups used to be $10/1k and never expire — cheaper per credit than every plan, so
buying credits beat upgrading. They are now $20/1k and each purchase lapses 12 months
after it was bought. These tests pin the price, the lot bookkeeping, the spend order
(soonest expiry first) and the expiry sweep.
"""
from datetime import date, datetime, timedelta

import pytest

from app.core.config import settings
from app.core.plans import PLAN_MATRIX
from app.db.models.credit_topup_lot import CreditTopupLot
from app.services.credit_metering import (
    available_credits, expire_topup_lots, get_balance, grant_topup,
    refill_if_new_period, spend,
)

pytestmark = pytest.mark.unit


def _lots(db, tid):
    return db.query(CreditTopupLot).filter(
        CreditTopupLot.tenant_id == tid).order_by(CreditTopupLot.lot_id).all()


def _no_allowance(db, tid):
    balance = get_balance(db, tid)
    balance.allowance_credits = 0.0
    db.commit()


# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------

def test_topup_costs_more_per_credit_than_every_paid_plan():
    """The whole point of the repricing: topping up must never beat upgrading."""
    topup_per_credit = settings.CREDIT_TOPUP_BLOCK_PRICE_CENTS / settings.CREDIT_TOPUP_BLOCK_SIZE
    for key in ("pro", "max"):
        spec = PLAN_MATRIX[key]
        for price in (spec.monthly_price_cents, spec.annual_price_cents):
            assert topup_per_credit > price / spec.credits_per_month, key


def test_default_topup_is_twenty_dollars_per_thousand_valid_a_year():
    assert settings.CREDIT_TOPUP_BLOCK_SIZE == 1000
    assert settings.CREDIT_TOPUP_BLOCK_PRICE_CENTS == 2000
    assert settings.CREDIT_TOPUP_VALIDITY_DAYS == 365


# ---------------------------------------------------------------------------
# Lots
# ---------------------------------------------------------------------------

def test_grant_creates_a_lot_expiring_after_the_validity_window(db_session, test_tenant):
    tid = test_tenant.tenant_id
    before = datetime.utcnow()
    grant_topup(db_session, tid, 1_000, reference_id="cs_1")

    [lot] = _lots(db_session, tid)
    assert lot.credits_purchased == lot.credits_remaining == 1_000
    assert lot.reference_id == "cs_1"
    assert lot.expired_at is None
    window = timedelta(days=settings.CREDIT_TOPUP_VALIDITY_DAYS)
    assert before + window <= lot.expires_at <= datetime.utcnow() + window


def test_spend_drains_the_soonest_expiring_lot_first(db_session, test_tenant):
    tid = test_tenant.tenant_id
    grant_topup(db_session, tid, 10)
    grant_topup(db_session, tid, 10)
    older, newer = _lots(db_session, tid)
    older.expires_at = datetime.utcnow() + timedelta(days=5)
    newer.expires_at = datetime.utcnow() + timedelta(days=300)
    _no_allowance(db_session, tid)

    spend(db_session, tid, "contact_enriched", 4)  # 12 credits
    db_session.commit()

    older, newer = _lots(db_session, tid)
    assert older.credits_remaining == 0
    assert newer.credits_remaining == 8
    assert get_balance(db_session, tid).topup_credits == 8


def test_allowance_is_still_spent_before_any_lot(db_session, test_tenant):
    tid = test_tenant.tenant_id
    grant_topup(db_session, tid, 100)
    balance = get_balance(db_session, tid)
    balance.allowance_credits = 50.0
    db_session.commit()

    spend(db_session, tid, "contact_enriched", 2)  # 6 credits, all from allowance
    db_session.commit()

    assert _lots(db_session, tid)[0].credits_remaining == 100


def test_lots_survive_the_monthly_refill(db_session, test_tenant):
    tid = test_tenant.tenant_id
    grant_topup(db_session, tid, 500)
    balance = get_balance(db_session, tid)
    balance.period_start = date(2020, 1, 1)
    db_session.commit()

    refill_if_new_period(db_session, balance)
    db_session.commit()

    assert _lots(db_session, tid)[0].credits_remaining == 500
    assert get_balance(db_session, tid).topup_credits == 500


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def test_sweep_lapses_only_lots_past_their_date(db_session, test_tenant):
    tid = test_tenant.tenant_id
    grant_topup(db_session, tid, 300)
    grant_topup(db_session, tid, 200)
    stale, live = _lots(db_session, tid)
    stale.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()

    assert expire_topup_lots(db_session) == 300

    stale, live = _lots(db_session, tid)
    assert stale.credits_remaining == 0 and stale.expired_at is not None
    assert live.credits_remaining == 200 and live.expired_at is None
    assert get_balance(db_session, tid).topup_credits == 200
    # Idempotent: nothing left to lapse.
    assert expire_topup_lots(db_session) == 0


def test_spend_never_uses_a_lapsed_lot_even_before_the_sweep(db_session, test_tenant):
    tid = test_tenant.tenant_id
    grant_topup(db_session, tid, 100)
    lot = _lots(db_session, tid)[0]
    lot.expires_at = datetime.utcnow() - timedelta(days=1)
    _no_allowance(db_session, tid)

    spend(db_session, tid, "contact_enriched", 1)  # 3 credits, nothing valid to draw on
    db_session.commit()

    balance = get_balance(db_session, tid)
    assert balance.topup_credits == 0
    assert balance.allowance_credits == -3  # overage stays visible, as before
    assert _lots(db_session, tid)[0].expired_at is not None


def test_available_credits_reports_the_next_expiry(db_session, test_tenant):
    tid = test_tenant.tenant_id
    assert available_credits(db_session, tid)["topup_next_expiry"] is None

    grant_topup(db_session, tid, 400)
    grant_topup(db_session, tid, 600)
    first, _ = _lots(db_session, tid)
    first.expires_at = datetime.utcnow() + timedelta(days=10)
    db_session.commit()

    info = available_credits(db_session, tid)
    assert info["topup"] == 1_000
    assert info["topup_next_expiry"] == first.expires_at.isoformat()
    assert info["topup_next_expiry_credits"] == 400


def test_sweep_is_tenant_isolated(db_session, test_tenant, professional_capped_tenant):
    a, b = test_tenant.tenant_id, professional_capped_tenant.tenant_id
    grant_topup(db_session, a, 50)
    grant_topup(db_session, b, 70)
    _lots(db_session, a)[0].expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    expire_topup_lots(db_session)

    assert get_balance(db_session, a).topup_credits == 0
    assert get_balance(db_session, b).topup_credits == 70
