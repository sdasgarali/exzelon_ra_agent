"""Warmup auto-replies must respect each mailbox's daily send limit.

Regression (2026-11-13, prod): the auto-reply loop counted replies in
emails_sent_today but never checked daily_send_limit, so 290 day-1 mailboxes
(limit 2) sent 3-10 warmup emails in one day. Replies now count against the
limit, and the send loop leaves part of the limit free for them.
"""
from datetime import datetime, timedelta

import pytest

from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.warmup_email import WarmupEmail, WarmupEmailStatus
from app.services.warmup import content_generator, peer_warmup, smart_scheduler
from app.services.warmup.peer_warmup import new_thread_budget

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("limit,rate,expected", [
    (2, 0.5, 1),     # day 1: one new thread, one reply slot
    (5, 0.5, 2),
    (35, 0.5, 17),
    (2, 0.0, 2),     # replies disabled -> whole limit for new threads
    (1, 0.5, 1),     # never starve new threads entirely
    (2, 1.0, 1),
    (0, 0.5, 0),     # no limit -> no sends
    (10, 1.7, 1),    # out-of-range rate is clamped
    (10, -1.0, 10),
])
def test_new_thread_budget(limit, rate, expected):
    assert new_thread_budget(limit, rate) == expected


@pytest.fixture
def fake_io(monkeypatch):
    """No SMTP, no AI, never a weekend; every reply attempt is sent."""
    sent = []

    def _send(mb, to, subject, html, text):
        sent.append((mb.email, to))
        return {"success": True, "message_id": f"<m{len(sent)}@test>"}

    monkeypatch.setattr(peer_warmup, "send_warmup_email", _send)
    monkeypatch.setattr(peer_warmup, "inject_tracking", lambda html, *a, **k: html)
    monkeypatch.setattr(smart_scheduler, "should_skip_weekend", lambda db, tenant_id=None: False)
    monkeypatch.setattr(content_generator, "generate_ai_warmup_content", lambda *a, **k: None)
    monkeypatch.setattr(content_generator, "generate_warmup_reply", lambda **k: {
        "subject": "Re: hi", "body_html": "<p>ok</p>", "body_text": "ok"})
    # Reply to everything, with no per-email delay.
    real_setting = peer_warmup.get_tenant_setting
    overrides = {"warmup_auto_reply_rate": 1.0, "warmup_auto_reply_min_delay": 0,
                 "warmup_auto_reply_max_delay": 0}

    def _setting(db, key, tenant_id=None, default=None):
        return overrides[key] if key in overrides else real_setting(db, key, tenant_id=tenant_id, default=default)

    monkeypatch.setattr(peer_warmup, "get_tenant_setting", _setting)
    return sent


def _mailbox(db, tenant, email, limit, sent_today=0):
    mb = SenderMailbox(
        tenant_id=tenant.tenant_id, email=email, display_name=email.split("@")[0], password="x",
        warmup_status=WarmupStatus.WARMING_UP, is_active=True,
        connection_status="successful", daily_send_limit=limit,
        emails_sent_today=sent_today, total_emails_sent=sent_today,
    )
    db.add(mb)
    db.commit()
    db.refresh(mb)
    return mb


def _inbound(db, sender, receiver, n):
    when = datetime.utcnow() - timedelta(hours=1)
    for _ in range(n):
        db.add(WarmupEmail(sender_mailbox_id=sender.mailbox_id, receiver_mailbox_id=receiver.mailbox_id,
                           subject="hi", body_text="hi", status=WarmupEmailStatus.SENT, sent_at=when))
    db.commit()


def test_auto_reply_stops_at_daily_limit(db_session, test_tenant, fake_io):
    sender = _mailbox(db_session, test_tenant, "a@test.com", limit=2)
    replier = _mailbox(db_session, test_tenant, "b@test.com", limit=2, sent_today=1)
    _inbound(db_session, sender, replier, 5)

    result = peer_warmup.run_auto_reply_cycle(db_session)

    db_session.refresh(replier)
    assert replier.emails_sent_today == 2           # 1 earlier + only 1 reply
    assert result["replied"] == 1
    assert len(fake_io) == 1
    unreplied = db_session.query(WarmupEmail).filter(
        WarmupEmail.receiver_mailbox_id == replier.mailbox_id,
        WarmupEmail.replied_at.is_(None)).count()
    assert unreplied == 4                           # left for after the daily reset


def test_auto_reply_skips_mailbox_already_at_limit(db_session, test_tenant, fake_io):
    sender = _mailbox(db_session, test_tenant, "a@test.com", limit=2)
    replier = _mailbox(db_session, test_tenant, "b@test.com", limit=2, sent_today=2)
    _inbound(db_session, sender, replier, 3)

    result = peer_warmup.run_auto_reply_cycle(db_session)

    assert result["replied"] == 0
    assert fake_io == []


def test_send_and_reply_together_stay_within_limit(db_session, test_tenant, fake_io):
    """A full day (send cycle, then reply cycle) never exceeds any mailbox's limit."""
    mbs = [_mailbox(db_session, test_tenant, f"m{i}@test.com", limit=2) for i in range(6)]

    peer_warmup.run_peer_warmup_cycle(db_session)
    for mb in mbs:
        db_session.refresh(mb)
        assert mb.emails_sent_today == 1            # new-thread budget on day 1

    # Make the new threads old enough to answer.
    db_session.query(WarmupEmail).update({WarmupEmail.sent_at: datetime.utcnow() - timedelta(hours=1)})
    db_session.commit()
    result = peer_warmup.run_auto_reply_cycle(db_session)

    assert result["replied"] >= 1
    for mb in mbs:
        db_session.refresh(mb)
        assert mb.emails_sent_today <= mb.daily_send_limit
