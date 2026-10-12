"""Weekly OAuth keepalive: idle Microsoft mailboxes must not lose their sign-in.

Microsoft expires a refresh token after 90 days unused (AADSTS700082). Production
had three mailboxes die that way because nothing refreshed them while idle.
"""
from unittest.mock import patch

import pytest

from app.core.encryption import decrypt_field, encrypt_field
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.services.oauth_helper import refresh_idle_oauth_tokens

pytestmark = pytest.mark.unit


def _oauth_mailbox(db, tenant_id, email, *, active=True, archived=False, refresh="old-refresh"):
    mb = SenderMailbox(
        tenant_id=tenant_id, email=email, display_name="Sender", password="x",
        provider="microsoft_365", auth_method="oauth2", smtp_host="smtp.office365.com",
        smtp_port=587, warmup_status=WarmupStatus.COLD_READY, is_active=active,
        is_archived=archived, connection_status="successful", daily_send_limit=30,
        oauth_refresh_token=encrypt_field(refresh) if refresh else None,
    )
    db.add(mb)
    db.commit()
    return mb


def _ok(refresh_token, tenant):
    return {"access_token": f"access-for-{refresh_token}", "refresh_token": f"rotated-{refresh_token}",
            "expires_in": 3600}


def test_refreshes_and_persists_rotated_token(db_session, test_tenant):
    mb = _oauth_mailbox(db_session, test_tenant.tenant_id, "idle@exzelon-qa.com")
    with patch("app.services.oauth_helper.refresh_oauth_token", side_effect=_ok) as refresh:
        result = refresh_idle_oauth_tokens(db_session)

    refresh.assert_called_once()
    db_session.refresh(mb)
    assert decrypt_field(mb.oauth_refresh_token) == "rotated-old-refresh"
    assert decrypt_field(mb.oauth_access_token) == "access-for-old-refresh"
    assert mb.oauth_token_expires_at is not None
    assert result == {"checked": 1, "refreshed": 1, "failed": 0}


def test_dead_token_marks_mailbox_failed_with_reconnect_hint(db_session, test_tenant):
    dead = _oauth_mailbox(db_session, test_tenant.tenant_id, "dead@exzelon-qa.com", refresh="dead")
    alive = _oauth_mailbox(db_session, test_tenant.tenant_id, "alive@exzelon-qa.com", refresh="alive")

    def _refresh(token, tenant):
        if token == "dead":
            raise ValueError("Token refresh failed (400): invalid_grant AADSTS700082")
        return _ok(token, tenant)

    with patch("app.services.oauth_helper.refresh_oauth_token", side_effect=_refresh):
        result = refresh_idle_oauth_tokens(db_session)

    db_session.refresh(dead)
    db_session.refresh(alive)
    assert dead.connection_status == "failed"
    assert "reconnect" in dead.connection_error.lower()
    assert alive.connection_status == "successful"  # one failure doesn't stop the rest
    assert decrypt_field(alive.oauth_refresh_token) == "rotated-alive"
    assert result == {"checked": 2, "refreshed": 1, "failed": 1}


def test_skips_archived_inactive_and_password_mailboxes(db_session, test_tenant):
    _oauth_mailbox(db_session, test_tenant.tenant_id, "archived@exzelon-qa.com", archived=True)
    _oauth_mailbox(db_session, test_tenant.tenant_id, "paused@exzelon-qa.com", active=False)
    _oauth_mailbox(db_session, test_tenant.tenant_id, "never@exzelon-qa.com", refresh=None)
    db_session.add(SenderMailbox(
        tenant_id=test_tenant.tenant_id, email="smtp@exzelon-qa.com", display_name="S",
        password="x", provider="smtp", auth_method="password", warmup_status=WarmupStatus.COLD_READY,
        is_active=True, connection_status="successful", daily_send_limit=30,
    ))
    db_session.commit()

    with patch("app.services.oauth_helper.refresh_oauth_token", side_effect=_ok) as refresh:
        result = refresh_idle_oauth_tokens(db_session)

    refresh.assert_not_called()
    assert result == {"checked": 0, "refreshed": 0, "failed": 0}


def test_scheduler_registers_weekly_keepalive_job(monkeypatch):
    from contextlib import contextmanager
    from app.services.warmup import scheduler

    calls = []
    monkeypatch.setattr(scheduler, "_is_job_enabled", lambda job: True)

    @contextmanager
    def _lock(_name):
        yield True

    monkeypatch.setattr("app.core.job_lock.advisory_lock", _lock)
    monkeypatch.setattr("app.services.oauth_helper.refresh_idle_oauth_tokens",
                        lambda db: calls.append("ran") or {})
    scheduler.job_oauth_keepalive()
    assert calls == ["ran"]
