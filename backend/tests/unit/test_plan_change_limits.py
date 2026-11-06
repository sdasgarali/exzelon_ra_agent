"""change_plan releases limits that were only copies of the old plan's defaults.

Tenants created by signup between 2026-09 and 2026-11 carry Free's numbers in their
`max_*` columns. Those explicit values override the plan, so without this an upgrade
to Pro/Max left a paying customer on Free limits.
"""
import pytest

from app.core.plans import LIMIT_FIELDS, PLAN_MATRIX, limits_for_tenant
from app.db.models.tenant import Tenant, TenantPlan
from app.services.billing.plan_change import change_plan

pytestmark = pytest.mark.unit


def _tenant(db, slug, plan=TenantPlan.FREE, **limits):
    t = Tenant(name=slug, slug=slug, plan=plan, **limits)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _copied_free_limits():
    free = PLAN_MATRIX["free"]
    return {f: getattr(free, f) for f in LIMIT_FIELDS}


def test_legacy_signup_row_gets_max_limits_on_upgrade(db_session):
    t = _tenant(db_session, "legacy-upgrade", **_copied_free_limits())
    assert limits_for_tenant(t)["max_mailboxes"] == PLAN_MATRIX["free"].max_mailboxes

    change_plan(db_session, t, TenantPlan.MAX, reason="stripe:active")
    db_session.commit()

    resolved = limits_for_tenant(t)
    for f in LIMIT_FIELDS:
        assert resolved[f] == getattr(PLAN_MATRIX["max"], f), f
        assert getattr(t, f) == 0, f


def test_deliberate_grant_is_kept(db_session):
    """A support grant (a value that differs from the old plan's default) survives."""
    limits = _copied_free_limits()
    limits["max_mailboxes"] = 5  # Free default is 1: this was granted on purpose
    t = _tenant(db_session, "granted", **limits)

    change_plan(db_session, t, TenantPlan.PRO, reason="test")
    db_session.commit()

    assert t.max_mailboxes == 5
    assert limits_for_tenant(t)["max_mailboxes"] == 5
    assert limits_for_tenant(t)["max_campaigns"] == PLAN_MATRIX["pro"].max_campaigns


def test_downgrade_to_free_follows_free(db_session):
    t = _tenant(db_session, "downgrader", plan=TenantPlan.PRO)
    change_plan(db_session, t, TenantPlan.FREE, reason="stripe:canceled")
    db_session.commit()
    assert limits_for_tenant(t)["max_mailboxes"] == PLAN_MATRIX["free"].max_mailboxes


def test_same_plan_changes_nothing(db_session):
    t = _tenant(db_session, "same-plan", **_copied_free_limits())
    change_plan(db_session, t, TenantPlan.FREE, reason="noop")
    assert t.max_mailboxes == PLAN_MATRIX["free"].max_mailboxes


def test_custom_rows_are_left_alone(db_session):
    """Custom tenants' rows are their contract; a move in or out never rewrites them."""
    big = {f: getattr(PLAN_MATRIX["max"], f) for f in LIMIT_FIELDS}
    t = _tenant(db_session, "custom-co", plan=TenantPlan.MAX, **big)
    change_plan(db_session, t, TenantPlan.CUSTOM, reason="contract")
    db_session.commit()
    for f in LIMIT_FIELDS:
        assert getattr(t, f) == big[f], f
