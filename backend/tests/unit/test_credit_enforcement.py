"""Credit-budget enforcement tests (ELR-009).

Enforcement is OFF by default (never breaks a live pipeline). When enabled via
config (or a per-tenant setting) it blocks paid actions once the monthly plan
ceiling is reached.
"""
import pytest
from fastapi import HTTPException

from app.services.credit_metering import check_credit_budget, record_usage, plan_credit_limit

pytestmark = pytest.mark.unit


def test_noop_when_enforcement_disabled(db_session, professional_capped_tenant):
    tid = professional_capped_tenant.tenant_id
    record_usage(db_session, tid, "ai_generation", credits=999_999)
    # Disabled by default → over ceiling but no raise.
    check_credit_budget(db_session, tid, credits_needed=1.0)


def test_blocks_when_enabled_and_over_ceiling(db_session, professional_capped_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)
    monkeypatch.setattr(settings, "CREDIT_LIMIT_PRO_OVERRIDE", 10)
    tid = professional_capped_tenant.tenant_id
    record_usage(db_session, tid, "ai_generation", credits=10)
    with pytest.raises(HTTPException) as exc:
        check_credit_budget(db_session, tid, credits_needed=1.0)
    assert exc.value.status_code == 402


def test_allows_when_under_ceiling(db_session, professional_capped_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)
    monkeypatch.setattr(settings, "CREDIT_LIMIT_PRO_OVERRIDE", 100)
    tid = professional_capped_tenant.tenant_id
    record_usage(db_session, tid, "ai_generation", credits=5)
    check_credit_budget(db_session, tid, credits_needed=1.0)  # no raise


def test_max_plan_is_capped_not_unlimited(db_session, test_tenant, monkeypatch):
    """Max used to be unlimited (ceiling 0). Every tier now has a real allowance."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)
    tid = test_tenant.tenant_id  # resolves to the Max plan
    record_usage(db_session, tid, "ai_generation", credits=999_999)
    with pytest.raises(HTTPException) as exc:
        check_credit_budget(db_session, tid, credits_needed=1.0)
    assert exc.value.status_code == 402


def test_max_plan_allows_usage_under_its_allowance(db_session, test_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)
    tid = test_tenant.tenant_id
    record_usage(db_session, tid, "ai_generation", credits=100)
    check_credit_budget(db_session, tid, credits_needed=1.0)  # no raise


def test_super_admin_not_metered(db_session, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)
    check_credit_budget(db_session, None, credits_needed=1.0)  # no raise


def test_plan_credit_limit_matches_the_plan_matrix():
    """Allowances live in core.plans.PLAN_MATRIX — pricing, not deployment config."""
    from app.core.plans import PLAN_MATRIX
    assert plan_credit_limit("free") == PLAN_MATRIX["free"].credits_per_month == 300
    assert plan_credit_limit("pro") == PLAN_MATRIX["pro"].credits_per_month == 6_000
    assert plan_credit_limit("max") == PLAN_MATRIX["max"].credits_per_month == 25_000
    # Nothing is unlimited any more.
    assert all(s.credits_per_month > 0 for s in PLAN_MATRIX.values())


def test_plan_credit_limit_accepts_legacy_plan_names():
    """Old JWTs and rows carry starter/professional/enterprise for one more release."""
    assert plan_credit_limit("starter") == plan_credit_limit("free")
    assert plan_credit_limit("professional") == plan_credit_limit("pro")
    assert plan_credit_limit("enterprise") == plan_credit_limit("max")
    # An unrecognised claim must not 500 on the request path — it falls back to Free.
    assert plan_credit_limit("unknown-plan") == plan_credit_limit("free")
    assert plan_credit_limit(None) == plan_credit_limit("free")


def test_custom_plan_allowance_is_floored_at_max(db_session):
    """A custom contract is never smaller than the tier it sits above."""
    from app.db.models.tenant import Tenant, TenantPlan
    from app.core.plans import PLAN_MATRIX

    stingy = Tenant(name="C", slug="c-stingy", plan=TenantPlan.CUSTOM)
    assert plan_credit_limit("custom", tenant=stingy) == PLAN_MATRIX["max"].credits_per_month

    class _Contracted:
        plan = TenantPlan.CUSTOM
        credits_per_month = 80_000

    assert plan_credit_limit("custom", tenant=_Contracted()) == 80_000
