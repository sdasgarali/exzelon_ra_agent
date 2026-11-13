"""A warming mailbox advances at most one warmup day per calendar day.

Regression: assess_mailbox advanced warmup_days_completed on every call, so each
extra assessment (manual "Run Assessment", per-mailbox runs) moved a mailbox a
day further up the ramp — prod history shows ~1,000 manual runs Mar-Sep 2026.
"""
from datetime import datetime, timedelta

import pytest

from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.services.pipelines.warmup_engine import (
    assess_mailbox, get_daily_limit_for_day, load_warmup_config,
)

pytestmark = pytest.mark.unit


def _warming(db, tenant, started_days_ago, completed):
    mb = SenderMailbox(
        tenant_id=tenant.tenant_id, email=f"w{started_days_ago}-{completed}@test.com",
        display_name="w", password="x", warmup_status=WarmupStatus.WARMING_UP,
        is_active=True, connection_status="successful", daily_send_limit=2,
        emails_sent_today=0, total_emails_sent=0,
        warmup_started_at=datetime.utcnow() - timedelta(days=started_days_ago),
        warmup_days_completed=completed,
    )
    db.add(mb)
    db.commit()
    return mb


@pytest.fixture
def config(db_session):
    return load_warmup_config(db_session)


def test_no_advance_on_start_day(db_session, test_tenant, config):
    mb = _warming(db_session, test_tenant, started_days_ago=0, completed=0)
    result = assess_mailbox(mb, config, db_session)
    assert result["action"] == "already_advanced_today"
    assert mb.warmup_days_completed == 0


def test_advances_once_next_day_then_holds(db_session, test_tenant, config):
    mb = _warming(db_session, test_tenant, started_days_ago=1, completed=0)
    assess_mailbox(mb, config, db_session)
    assert mb.warmup_days_completed == 1
    assert mb.daily_send_limit == get_daily_limit_for_day(1, config)

    for _ in range(5):                       # repeated manual runs the same day
        assert assess_mailbox(mb, config, db_session)["action"] == "already_advanced_today"
    assert mb.warmup_days_completed == 1


def test_catches_up_one_day_per_run_when_behind(db_session, test_tenant, config):
    """A mailbox behind the calendar (missed nightly runs) still advances, one day per run."""
    mb = _warming(db_session, test_tenant, started_days_ago=5, completed=2)
    assess_mailbox(mb, config, db_session)
    assert mb.warmup_days_completed == 3


def test_graduates_after_total_days(db_session, test_tenant, config):
    total = config["total_days"]
    mb = _warming(db_session, test_tenant, started_days_ago=total + 1, completed=total)
    result = assess_mailbox(mb, config, db_session)
    assert result["new_status"] == "cold_ready"


def test_legacy_mailbox_without_start_date_still_advances(db_session, test_tenant, config):
    mb = _warming(db_session, test_tenant, started_days_ago=0, completed=3)
    mb.warmup_started_at = None
    db_session.commit()
    assess_mailbox(mb, config, db_session)
    assert mb.warmup_days_completed == 4
