"""Dashboard / mailbox-stats "ready" counts follow the outreach warmup gate.

Before: they counted every cold_ready mailbox, so prod's 494 never-warmed
mailboxes showed as ready to send while the senders (correctly) refused them.
"""
import pytest

from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus

pytestmark = pytest.mark.unit

API = "/api/v1"


def _mb(db, tenant_id, email, days, emails):
    db.add(SenderMailbox(
        tenant_id=tenant_id, email=email, display_name="S", password="x",
        warmup_status=WarmupStatus.COLD_READY, is_active=True, connection_status="successful",
        daily_send_limit=30, warmup_days_completed=days, warmup_emails_sent=emails,
    ))
    db.commit()


def test_dashboard_ready_to_send_counts_only_warmed_mailboxes(client, db_session, test_tenant, auth_headers):
    _mb(db_session, test_tenant.tenant_id, "warm@qa-ready.com", 20, 80)
    _mb(db_session, test_tenant.tenant_id, "cold1@qa-ready.com", 30, 0)   # seeded days, no warmup
    _mb(db_session, test_tenant.tenant_id, "cold2@qa-ready.com", 3, 10)

    r = client.get(f"{API}/dashboard/stats", headers=auth_headers)
    assert r.status_code == 200, r.text
    mailboxes = r.json()["mailboxes"]
    assert mailboxes["ready_to_send"] == 1
    assert mailboxes["total"] >= 3


def test_mailbox_stats_capacity_excludes_unwarmed(client, db_session, test_tenant, auth_headers):
    _mb(db_session, test_tenant.tenant_id, "warm@qa-cap.com", 20, 80)
    _mb(db_session, test_tenant.tenant_id, "cold@qa-cap.com", 30, 0)

    r = client.get(f"{API}/mailboxes/stats", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["total_daily_capacity"] == 30
