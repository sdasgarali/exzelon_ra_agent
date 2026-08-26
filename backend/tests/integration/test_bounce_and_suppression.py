"""Soft-bounce enforcement + bounce-rate auto-pause (ELR-015) and per-tenant
suppression uniqueness (ELR-016)."""
import pytest

from app.services.bounce_handler import (
    handle_bounce, MAX_TEMP_FAILURES, _bump_mailbox_bounce,
    BOUNCE_RATE_AUTO_PAUSE_THRESHOLD,
)
from app.db.models.suppression import SuppressionList
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus

pytestmark = pytest.mark.integration


def test_soft_bounce_escalates_to_suppression_after_max(db_session, test_tenant):
    tid = test_tenant.tenant_id
    email = "soft@bounce.com"
    # 4xx temporary failures: no suppression until the threshold.
    for _ in range(MAX_TEMP_FAILURES - 1):
        res = handle_bounce(db_session, email, "451 temporary greylist, try again", tenant_id=tid)
        assert res["action"] == "logged"
    assert db_session.query(SuppressionList).filter(SuppressionList.email == email).count() == 0

    # The MAX-th soft bounce escalates to a permanent suppression.
    res = handle_bounce(db_session, email, "451 temporary greylist, try again", tenant_id=tid)
    assert res["action"] == "suppressed_after_max_soft"
    db_session.commit()
    assert db_session.query(SuppressionList).filter(SuppressionList.email == email).count() == 1


def test_mailbox_auto_paused_on_high_bounce_rate(db_session, test_tenant):
    mb = SenderMailbox(
        tenant_id=test_tenant.tenant_id, email="mb@x.com", display_name="MB",
        password="x", warmup_status=WarmupStatus.COLD_READY, is_active=True,
        connection_status="successful", daily_send_limit=30, emails_sent_today=0,
        total_emails_sent=100, bounce_count=5,  # 6% after next bump > 5% threshold
    )
    db_session.add(mb)
    db_session.commit()
    db_session.refresh(mb)

    _bump_mailbox_bounce(db_session, mb.mailbox_id)  # -> 6/100 = 6%
    db_session.commit()
    db_session.refresh(mb)
    assert mb.bounce_count == 6
    assert (6 / 100) > BOUNCE_RATE_AUTO_PAUSE_THRESHOLD
    assert mb.is_active is False


def test_two_tenants_can_suppress_same_email(db_session):
    # ELR-016: (tenant_id, email) uniqueness lets each tenant own its own opt-out
    # for the same address without a cross-tenant IntegrityError.
    from app.db.models.tenant import Tenant, TenantPlan
    t1 = Tenant(name="T1", slug="sup-t1", plan=TenantPlan.ENTERPRISE)
    t2 = Tenant(name="T2", slug="sup-t2", plan=TenantPlan.ENTERPRISE)
    db_session.add_all([t1, t2])
    db_session.commit()

    db_session.add(SuppressionList(tenant_id=t1.tenant_id, email="shared@x.com", reason="a"))
    db_session.add(SuppressionList(tenant_id=t2.tenant_id, email="shared@x.com", reason="b"))
    db_session.commit()  # must not raise

    assert db_session.query(SuppressionList).filter(
        SuppressionList.email == "shared@x.com").count() == 2
