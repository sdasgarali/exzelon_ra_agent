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
    monkeypatch.setattr(settings, "CREDIT_LIMIT_PROFESSIONAL", 10)
    tid = professional_capped_tenant.tenant_id
    record_usage(db_session, tid, "ai_generation", credits=10)
    with pytest.raises(HTTPException) as exc:
        check_credit_budget(db_session, tid, credits_needed=1.0)
    assert exc.value.status_code == 402


def test_allows_when_under_ceiling(db_session, professional_capped_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)
    monkeypatch.setattr(settings, "CREDIT_LIMIT_PROFESSIONAL", 100)
    tid = professional_capped_tenant.tenant_id
    record_usage(db_session, tid, "ai_generation", credits=5)
    check_credit_budget(db_session, tid, credits_needed=1.0)  # no raise


def test_enterprise_is_unlimited(db_session, test_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)
    tid = test_tenant.tenant_id  # ENTERPRISE → ceiling 0 = unlimited
    record_usage(db_session, tid, "ai_generation", credits=999_999)
    check_credit_budget(db_session, tid, credits_needed=1.0)  # no raise


def test_super_admin_not_metered(db_session, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)
    check_credit_budget(db_session, None, credits_needed=1.0)  # no raise


def test_plan_credit_limit_defaults():
    assert plan_credit_limit("professional") == 5000
    assert plan_credit_limit("enterprise") == 0  # unlimited
    assert plan_credit_limit("unknown-plan") == 1000  # starter fallback
