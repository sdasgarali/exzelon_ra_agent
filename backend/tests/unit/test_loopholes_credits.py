"""Credit-metering loopholes (Plan_Credit_Loopholes.md, Agent C items C1-C8).

Every test here pins a hole that let work happen without the tenant paying for it,
or let a tenant spend past what it had. Each one fails on decc862.
"""
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Query

from app.core.credit_costs import CREDIT_COSTS, cost_for, estimate_run_credits
from app.db.models.credit_balance import TenantCreditBalance
from app.db.models.credit_usage import CreditUsage
from app.services.credit_metering import (
    check_credit_budget, get_balance, has_credit_budget, refill_all_balances,
    refill_if_new_period, spend,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _enforce(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)


def _set_available(db, tenant_id, credits):
    balance = get_balance(db, tenant_id)
    balance.allowance_credits = float(credits)
    balance.topup_credits = 0.0
    db.commit()
    return balance


def _usage(db, tenant_id, action=None):
    db.expire_all()
    q = db.query(CreditUsage).filter(CreditUsage.tenant_id == tenant_id)
    if action:
        q = q.filter(CreditUsage.usage_type == action)
    return q.all()


class _LockSpy:
    """Counts Query.with_for_update() calls (a no-op on SQLite, so the only way to
    see that a lock was *requested*)."""

    def __init__(self, monkeypatch):
        self.calls = 0
        original = Query.with_for_update
        spy = self

        def _wrapped(self_q, *a, **k):
            spy.calls += 1
            return original(self_q, *a, **k)

        monkeypatch.setattr(Query, "with_for_update", _wrapped)


# ---------------------------------------------------------------------------
# C3 — overspend carried forward, not wiped at the month turn
# ---------------------------------------------------------------------------

def test_c3_refill_carries_negative_balance_forward(db_session, test_tenant):
    balance = get_balance(db_session, test_tenant.tenant_id)
    balance.allowance_credits = -500.0          # overspent last month
    balance.topup_credits = 40.0
    balance.period_start = date(2020, 1, 1)
    db_session.commit()

    assert refill_if_new_period(db_session, balance) is True
    assert balance.allowance_credits == 25_000 - 500   # debt comes out of the new month
    assert balance.topup_credits == 40.0                # top-ups untouched


def test_c3_refill_does_not_roll_over_unused_allowance(db_session, test_tenant):
    balance = get_balance(db_session, test_tenant.tenant_id)
    balance.allowance_credits = 1_234.0
    balance.period_start = date(2020, 1, 1)
    db_session.commit()

    refill_if_new_period(db_session, balance)
    assert balance.allowance_credits == 25_000


def test_c3_debt_larger_than_plan_keeps_tenant_blocked(db_session, starter_tenant, monkeypatch):
    _enforce(monkeypatch)
    balance = get_balance(db_session, starter_tenant.tenant_id)
    balance.allowance_credits = -1_000.0   # Free plan is 300/mo
    balance.period_start = date(2020, 1, 1)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        check_credit_budget(db_session, starter_tenant.tenant_id, credits_needed=1)
    assert exc.value.status_code == 402
    assert get_balance(db_session, starter_tenant.tenant_id).allowance_credits == 300 - 1_000


# ---------------------------------------------------------------------------
# C5 — refills take the row lock
# ---------------------------------------------------------------------------

def test_c5_gate_locks_the_row_before_a_lazy_refill(db_session, test_tenant, monkeypatch):
    _enforce(monkeypatch)
    balance = get_balance(db_session, test_tenant.tenant_id)
    balance.period_start = date(2020, 1, 1)
    db_session.commit()

    spy = _LockSpy(monkeypatch)
    check_credit_budget(db_session, test_tenant.tenant_id, credits_needed=1)
    assert spy.calls >= 1
    assert get_balance(db_session, test_tenant.tenant_id).period_start == date.today().replace(day=1)


def test_c5_unlocked_read_of_a_current_balance_takes_no_lock(db_session, test_tenant, monkeypatch):
    get_balance(db_session, test_tenant.tenant_id)  # create, current period
    db_session.commit()
    spy = _LockSpy(monkeypatch)
    get_balance(db_session, test_tenant.tenant_id)
    assert spy.calls == 0  # reads stay cheap; only refills lock


def test_c5_refill_all_balances_locks_each_row(db_session, test_tenant, professional_capped_tenant, monkeypatch):
    for t in (test_tenant, professional_capped_tenant):
        get_balance(db_session, t.tenant_id).period_start = date(2020, 1, 1)
    db_session.commit()

    spy = _LockSpy(monkeypatch)
    assert refill_all_balances(db_session) == 2
    assert spy.calls >= 2


# ---------------------------------------------------------------------------
# C2 — the gate asks for an estimate, not 1 credit
# ---------------------------------------------------------------------------

def test_c2_run_estimates_are_conservative_and_capped():
    assert estimate_run_credits("lead_sourcing") == 50 * cost_for("lead_sourced")
    assert estimate_run_credits("contact_enrichment", units=5, per_unit_multiplier=4) == 5 * 4 * 3
    assert estimate_run_credits("contact_enrichment", per_unit_multiplier=4) == 10 * 4 * 3
    assert estimate_run_credits("email_validation", units=7) == 7
    assert estimate_run_credits("email_validation") == 25
    assert estimate_run_credits("contact_enrichment", units=10_000, per_unit_multiplier=4) == 1_000


def _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits):
    """Enforcement on, `credits` available, pipelines stubbed. Returns headers for a
    super admin impersonating `test_tenant` (the run endpoints check module-tab
    permissions the plain admin fixture doesn't carry)."""
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, credits)
    # The background task must never actually run a pipeline in a unit test.
    import app.services.pipelines.lead_sourcing as ls
    import app.services.pipelines.contact_enrichment as ce
    import app.services.pipelines.email_validation as ev
    monkeypatch.setattr(ls, "run_lead_sourcing_pipeline", lambda **k: {})
    monkeypatch.setattr(ce, "run_contact_enrichment_pipeline", lambda **k: {})
    monkeypatch.setattr(ev, "run_email_validation_pipeline", lambda **k: {})
    return {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}


def test_c2_one_credit_cannot_launch_lead_sourcing(client, db_session, test_tenant, sa_headers, monkeypatch):
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=1)
    r = client.post("/api/v1/pipelines/lead-sourcing/run", headers=h)
    assert r.status_code == 402


def test_c2_enough_credits_launches_lead_sourcing(client, db_session, test_tenant, sa_headers, monkeypatch):
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=500)
    r = client.post("/api/v1/pipelines/lead-sourcing/run", headers=h)
    assert r.status_code == 200, r.text


def test_c2_enrichment_gate_scales_with_selected_leads(client, db_session, test_tenant, sa_headers, monkeypatch):
    # 20 leads x 4 contacts x 3 credits = 240 needed; 100 available.
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=100)
    r = client.post("/api/v1/pipelines/contact-enrichment/run", headers=h,
                    json={"lead_ids": list(range(1, 21))})
    assert r.status_code == 402
    # 2 leads x 4 x 3 = 24 → fits.
    r = client.post("/api/v1/pipelines/contact-enrichment/run", headers=h,
                    json={"lead_ids": [1, 2]})
    assert r.status_code == 200, r.text


def test_c2_validation_gate_needs_more_than_one_credit(client, db_session, test_tenant, sa_headers, monkeypatch):
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=3)
    r = client.post("/api/v1/pipelines/email-validation/run", headers=h)
    assert r.status_code == 402


def test_c2_spend_still_never_raises_past_zero(db_session, test_tenant):
    _set_available(db_session, test_tenant.tenant_id, 1)
    spend(db_session, test_tenant.tenant_id, "contact_enriched", 10, commit=True)
    assert get_balance(db_session, test_tenant.tenant_id).allowance_credits == 1 - 30


# ---------------------------------------------------------------------------
# C4 — has_credit_budget (scheduler helper)
# ---------------------------------------------------------------------------

def test_c4_has_credit_budget(db_session, test_tenant, monkeypatch):
    tid = test_tenant.tenant_id
    _set_available(db_session, tid, 10)
    # Enforcement off → always True.
    assert has_credit_budget(db_session, tid, 1_000) is True
    _enforce(monkeypatch)
    assert has_credit_budget(db_session, tid, 5) is True
    assert has_credit_budget(db_session, tid, 50) is False
    assert has_credit_budget(db_session, None, 10**9) is True  # internal work
