"""Credit balance, pricing and metering (Phase 2 / ELR-009b).

The balance row is the authoritative counter; `credit_usage` is the audit trail. These
tests pin the behaviours that are easy to regress: allowance-before-topup ordering,
monthly refill semantics, and the fact that metering never raises into a pipeline.
"""
import pytest
from datetime import date, datetime, timedelta

from app.core.credit_costs import CREDITS_PER_FULL_CONTACT, CREDIT_COSTS, cost_for
from app.db.models.credit_balance import TenantCreditBalance
from app.db.models.credit_usage import CreditUsage
from app.services.credit_metering import (
    available_credits, get_balance, grant_topup, meter,
    refill_all_balances, refill_if_new_period, spend,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def test_full_contact_costs_six_credits():
    """The number every plan allowance is sized against.

    Free's 300 credits is "50 contacts", Pro's 6,000 is "1,000". If this changes,
    every published allowance silently means something different.
    """
    assert CREDITS_PER_FULL_CONTACT == 6
    assert cost_for("lead_sourced") == 1
    assert cost_for("contact_enriched") == 3
    assert cost_for("email_validated") == 1
    assert cost_for("ai_personalization") == 1


def test_sends_and_warmup_are_free():
    """Sends are governed by the send quota, never by credits."""
    assert cost_for("email_send") == 0
    assert cost_for("warmup_email") == 0


def test_quantity_multiplies():
    assert cost_for("contact_enriched", 10) == 30


def test_unpriced_action_defaults_to_one_not_zero():
    """An action we forgot to price should show up in the ledger, not vanish."""
    assert cost_for("something_we_forgot_to_price") == 1


def test_every_cost_has_a_category_and_label():
    for action, spec in CREDIT_COSTS.items():
        assert spec.category in {"data", "validation", "ai", "comms"}, action
        assert spec.label and spec.credits > 0, action


# ---------------------------------------------------------------------------
# Balance creation and refill
# ---------------------------------------------------------------------------

def test_first_balance_carries_over_existing_ledger_spend(db_session, test_tenant):
    """Switching a live deployment onto balances must not hand out a free refill."""
    db_session.add(CreditUsage(
        tenant_id=test_tenant.tenant_id, usage_type="lead_sourced", credits_used=400,
    ))
    db_session.commit()

    balance = get_balance(db_session, test_tenant.tenant_id)
    # test_tenant is on Max (25,000/mo); 400 already spent this month.
    assert balance.allowance_credits == 25_000 - 400
    assert balance.period_spent == 400


def test_refill_resets_allowance_but_keeps_topups(db_session, test_tenant):
    balance = get_balance(db_session, test_tenant.tenant_id)
    balance.allowance_credits = 12.0
    balance.topup_credits = 5_000.0
    balance.period_spent = 24_988.0
    balance.period_start = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    db_session.commit()

    assert refill_if_new_period(db_session, balance) is True
    assert balance.allowance_credits == 25_000       # fresh grant
    assert balance.topup_credits == 5_000            # purchased credits never expire
    assert balance.period_spent == 0
    assert balance.period_start == date.today().replace(day=1)


def test_unused_allowance_does_not_roll_over(db_session, test_tenant):
    """No rollover in v1 — a refill is a reset, not an addition."""
    balance = get_balance(db_session, test_tenant.tenant_id)
    balance.allowance_credits = 20_000.0
    balance.period_start = date(2020, 1, 1)
    db_session.commit()

    refill_if_new_period(db_session, balance)
    assert balance.allowance_credits == 25_000  # not 45,000


def test_refill_is_idempotent_within_a_month(db_session, test_tenant):
    balance = get_balance(db_session, test_tenant.tenant_id)
    balance.allowance_credits = 10.0
    db_session.commit()
    assert refill_if_new_period(db_session, balance) is False
    assert balance.allowance_credits == 10.0


def test_refill_all_balances_sweeps_only_stale_rows(db_session, test_tenant, professional_capped_tenant):
    stale = get_balance(db_session, test_tenant.tenant_id)
    stale.period_start = date(2020, 1, 1)
    fresh = get_balance(db_session, professional_capped_tenant.tenant_id)
    fresh.allowance_credits = 3.0
    db_session.commit()

    assert refill_all_balances(db_session) == 1
    assert fresh.allowance_credits == 3.0  # untouched


# ---------------------------------------------------------------------------
# Spending
# ---------------------------------------------------------------------------

def test_spend_debits_balance_and_writes_ledger(db_session, test_tenant):
    tid = test_tenant.tenant_id
    get_balance(db_session, tid)

    entry = spend(db_session, tid, "contact_enriched", 5)
    db_session.commit()

    assert entry.credits_used == 15            # 3 credits x 5
    assert entry.usage_type == "contact_enriched"
    balance = get_balance(db_session, tid)
    assert balance.allowance_credits == 25_000 - 15
    assert balance.period_spent == 15
    assert balance.lifetime_spent == 15


def test_allowance_is_spent_before_topups(db_session, test_tenant):
    """A top-up must never be burned on a month the allowance would have covered."""
    tid = test_tenant.tenant_id
    balance = get_balance(db_session, tid)
    balance.allowance_credits = 10.0
    balance.topup_credits = 100.0
    db_session.commit()

    spend(db_session, tid, "contact_enriched", 2)  # 6 credits
    db_session.commit()

    balance = get_balance(db_session, tid)
    assert balance.allowance_credits == 4.0
    assert balance.topup_credits == 100.0  # untouched


def test_spend_spills_into_topups_when_allowance_runs_out(db_session, test_tenant):
    tid = test_tenant.tenant_id
    balance = get_balance(db_session, tid)
    balance.allowance_credits = 2.0
    balance.topup_credits = 50.0
    db_session.commit()

    spend(db_session, tid, "contact_enriched", 2)  # 6 credits: 2 allowance + 4 topup
    db_session.commit()

    balance = get_balance(db_session, tid)
    assert balance.allowance_credits == 0.0
    assert balance.topup_credits == 46.0


def test_overage_goes_negative_rather_than_clamping(db_session, test_tenant):
    """The gate blocks entry; the meter records truth.

    Clamping at zero would hide the overage. A negative allowance keeps the shortfall
    visible until the next refill.
    """
    tid = test_tenant.tenant_id
    balance = get_balance(db_session, tid)
    balance.allowance_credits = 1.0
    balance.topup_credits = 0.0
    db_session.commit()

    spend(db_session, tid, "icp_wizard")  # 10 credits against 1 available
    db_session.commit()

    balance = get_balance(db_session, tid)
    assert balance.allowance_credits == -9.0
    assert balance.period_spent == 10.0


def test_free_actions_are_not_recorded(db_session, test_tenant):
    tid = test_tenant.tenant_id
    get_balance(db_session, tid)
    assert spend(db_session, tid, "email_send", 5_000) is None
    assert db_session.query(CreditUsage).filter(
        CreditUsage.tenant_id == tid).count() == 0


def test_super_admin_is_not_metered(db_session):
    assert spend(db_session, None, "contact_enriched", 100) is None


def test_meter_never_raises_into_a_pipeline(db_session, test_tenant):
    """A metering failure must not fail work that already cost us a paid API call."""
    # A tenant_id that violates the FK — the savepoint should absorb it.
    meter(db_session, 999_999, "lead_sourced", 5)  # no exception


def test_zero_quantity_is_a_noop(db_session, test_tenant):
    tid = test_tenant.tenant_id
    get_balance(db_session, tid)
    assert spend(db_session, tid, "lead_sourced", 0) is None


# ---------------------------------------------------------------------------
# Top-ups
# ---------------------------------------------------------------------------

def test_grant_topup_adds_credits_and_logs_a_negative_ledger_entry(db_session, test_tenant):
    tid = test_tenant.tenant_id
    get_balance(db_session, tid)

    grant_topup(db_session, tid, 1_000, reference_id="cs_test_123")

    balance = get_balance(db_session, tid)
    assert balance.topup_credits == 1_000
    assert balance.lifetime_purchased == 1_000

    entry = db_session.query(CreditUsage).filter(
        CreditUsage.usage_type == "topup_purchase").first()
    # Negative: a grant, so usage reports net out correctly against consumption.
    assert entry.credits_used == -1_000
    assert entry.reference_id == "cs_test_123"


def test_topups_survive_the_monthly_refill(db_session, test_tenant):
    tid = test_tenant.tenant_id
    grant_topup(db_session, tid, 500)
    balance = get_balance(db_session, tid)
    balance.period_start = date(2020, 1, 1)
    db_session.commit()

    refill_if_new_period(db_session, balance)
    assert balance.topup_credits == 500


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def test_available_credits_reports_both_pools(db_session, test_tenant):
    tid = test_tenant.tenant_id
    grant_topup(db_session, tid, 250)
    spend(db_session, tid, "contact_enriched", 1)
    db_session.commit()

    info = available_credits(db_session, tid)
    assert info["allowance"] == 25_000 - 3
    assert info["topup"] == 250
    assert info["total"] == 25_000 - 3 + 250
    assert info["plan_allowance"] == 25_000
    assert info["metered"] is True


def test_available_credits_for_super_admin(db_session):
    assert available_credits(db_session, None)["metered"] is False
