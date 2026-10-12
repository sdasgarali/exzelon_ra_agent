"""Launch readiness D1-D3 + L2: outreach warmup gate, ISP ramp, per-IP cohort cap, logo default.

D1  A mailbox may send OUTREACH only when its status is cold_ready/active AND it has
    real warmup history (MIN_WARMUP_DAYS days AND MIN_WARMUP_EMAILS warmup emails).
    Warmup traffic itself is never gated.
D2  During the first 30 days of real outreach a mailbox's daily cap is clamped to the
    ISP ramp table in domain_reputation.
D3  Domains whose SMTP host resolves to one IP form a cohort; at most
    MAX_LIVE_DOMAINS_PER_IP of them may be live at once. DNS failure fails open.
L2  Templates no longer default to the Exzelon logo.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.db.models.audit_log import AuditLog
from app.db.models.contact import ContactDetails
from app.db.models.outreach import OutreachChannel, OutreachEvent, OutreachStatus
from app.db.models.sender_mailbox import EmailProvider, SenderMailbox, WarmupStatus
from app.services import mailbox_selector as ms
from app.services.warmup.domain_reputation import ISP_PROFILES, recommended_daily_ramp

pytestmark = pytest.mark.unit

SHARED_IP = "118.139.181.36"


@pytest.fixture(autouse=True)
def _gate_settings(monkeypatch):
    monkeypatch.setattr(settings, "MIN_WARMUP_DAYS", 14, raising=False)
    monkeypatch.setattr(settings, "MIN_WARMUP_EMAILS", 50, raising=False)
    monkeypatch.setattr(settings, "MAX_LIVE_DOMAINS_PER_IP", 1, raising=False)
    ms.clear_dns_cache()
    # Default: every SMTP host resolves to the same shared IP (the prod cPanel case).
    monkeypatch.setattr(ms, "_dns_lookup", lambda host: SHARED_IP)
    yield
    ms.clear_dns_cache()


_seq = {"n": 0}


def _mailbox(db, tenant, *, email=None, status=WarmupStatus.COLD_READY, days=30, emails=60,
             smtp_host="mail.example.in", provider=EmailProvider.SMTP, sent_today=0, limit=30):
    _seq["n"] += 1
    mb = SenderMailbox(
        tenant_id=tenant.tenant_id,
        email=email or f"sender{_seq['n']}@d{_seq['n']}.in",
        display_name="Sender",
        password="x",
        provider=provider,
        smtp_host=smtp_host,
        warmup_status=status,
        is_active=True,
        connection_status="successful",
        daily_send_limit=limit,
        emails_sent_today=sent_today,
        total_emails_sent=0,
        warmup_days_completed=days,
        warmup_emails_sent=emails,
        is_blacklisted=False,
    )
    db.add(mb)
    db.commit()
    db.refresh(mb)
    return mb


def _contact(db, tenant):
    _seq["n"] += 1
    c = ContactDetails(
        tenant_id=tenant.tenant_id, client_name="Acme", first_name="Ann", last_name="Lee",
        email=f"ann{_seq['n']}@acme.com",
    )
    db.add(c)
    db.commit()
    return c


def _sent_event(db, mailbox, when):
    c = _contact(db, SimpleNamespace(tenant_id=mailbox.tenant_id))
    ev = OutreachEvent(
        tenant_id=mailbox.tenant_id, contact_id=c.contact_id, sender_mailbox_id=mailbox.mailbox_id,
        sent_at=when, channel=OutreachChannel.SMTP, status=OutreachStatus.SENT,
    )
    db.add(ev)
    db.commit()
    return ev


# ---------------------------------------------------------------------------
# D1 — warmup gate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "days,emails,eligible",
    [
        (14, 50, True),   # both thresholds met
        (30, 0, False),   # days only (the seeded prod case)
        (3, 500, False),  # emails only
        (0, 0, False),    # neither
    ],
)
def test_is_outreach_eligible_requires_days_and_emails(db_session, test_tenant, days, emails, eligible):
    mb = _mailbox(db_session, test_tenant, days=days, emails=emails)
    assert ms.is_outreach_eligible(mb) is eligible
    ids = [m.mailbox_id for m in db_session.query(SenderMailbox).filter(ms.outreach_eligible_filter())]
    assert (mb.mailbox_id in ids) is eligible


def test_block_reason_text(db_session, test_tenant):
    mb = _mailbox(db_session, test_tenant, days=3, emails=12)
    assert ms.outreach_block_reason(mb) == "Warming up — 3/14 days, 12/50 emails"
    paused = _mailbox(db_session, test_tenant, status=WarmupStatus.PAUSED)
    assert "status: paused" in ms.outreach_block_reason(paused)


def test_select_best_mailbox_skips_unwarmed(db_session, test_tenant):
    cold = _mailbox(db_session, test_tenant, days=30, emails=0)
    assert ms.select_best_mailbox([cold.mailbox_id], db_session, tenant_id=test_tenant.tenant_id) is None
    warm = _mailbox(db_session, test_tenant, days=30, emails=60)
    picked = ms.select_best_mailbox([cold.mailbox_id, warm.mailbox_id], db_session,
                                    tenant_id=test_tenant.tenant_id)
    assert picked is not None and picked.mailbox_id == warm.mailbox_id


def test_sendable_mailboxes_query_applies_gate(db_session, test_tenant):
    from app.services.pipelines.outreach import sendable_mailboxes_query
    cold = _mailbox(db_session, test_tenant, days=30, emails=0)
    ids = [m.mailbox_id for m in sendable_mailboxes_query(db_session, test_tenant.tenant_id).all()]
    assert cold.mailbox_id not in ids
    warm = _mailbox(db_session, test_tenant)
    ids = [m.mailbox_id for m in sendable_mailboxes_query(db_session, test_tenant.tenant_id).all()]
    assert ids == [warm.mailbox_id]


def test_campaign_engine_fallback_selector_applies_gate(db_session, test_tenant, monkeypatch):
    from app.services import campaign_engine
    cold = _mailbox(db_session, test_tenant, days=30, emails=0)
    # Force the fallback path (primary selector raising).
    monkeypatch.setattr(ms, "select_best_mailbox", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    campaign = SimpleNamespace(mailbox_ids_json=f"[{cold.mailbox_id}]", tenant_id=test_tenant.tenant_id)
    assert campaign_engine._select_mailbox(campaign, db_session) is None
    warm = _mailbox(db_session, test_tenant)
    campaign.mailbox_ids_json = f"[{cold.mailbox_id}, {warm.mailbox_id}]"
    assert campaign_engine._select_mailbox(campaign, db_session).mailbox_id == warm.mailbox_id


def test_warmup_sends_are_not_gated(db_session, test_tenant):
    """Peer warmup still pairs brand-new warming mailboxes (0 days, 0 emails)."""
    from app.services.warmup.peer_warmup import get_peer_pairs
    a = _mailbox(db_session, test_tenant, status=WarmupStatus.WARMING_UP, days=0, emails=0)
    b = _mailbox(db_session, test_tenant, status=WarmupStatus.WARMING_UP, days=0, emails=0)
    assert [p.mailbox_id for p in get_peer_pairs(db_session, a, tenant_id=test_tenant.tenant_id)] == [b.mailbox_id]


# --- update-status endpoint ---------------------------------------------------

def test_update_status_refuses_unwarmed_cold_ready(client, db_session, test_tenant, auth_headers):
    mb = _mailbox(db_session, test_tenant, status=WarmupStatus.WARMING_UP, days=3, emails=12)
    r = client.post(f"/api/v1/mailboxes/{mb.mailbox_id}/update-status?new_status=cold_ready",
                    headers=auth_headers)
    assert r.status_code == 400
    assert "3/14 days, 12/50 emails" in r.json()["detail"]
    db_session.refresh(mb)
    assert mb.warmup_status == WarmupStatus.WARMING_UP


def test_update_status_force_requires_super_admin(client, db_session, test_tenant, auth_headers):
    mb = _mailbox(db_session, test_tenant, status=WarmupStatus.WARMING_UP, days=3, emails=12)
    r = client.post(f"/api/v1/mailboxes/{mb.mailbox_id}/update-status?new_status=active&force=true",
                    headers=auth_headers)
    assert r.status_code == 403


def test_update_status_super_admin_force_is_audited(client, db_session, test_tenant, super_admin_headers):
    mb = _mailbox(db_session, test_tenant, status=WarmupStatus.WARMING_UP, days=3, emails=12)
    r = client.post(f"/api/v1/mailboxes/{mb.mailbox_id}/update-status?new_status=cold_ready&force=true",
                    headers=super_admin_headers)
    assert r.status_code == 200, r.text
    db_session.refresh(mb)
    assert mb.warmup_status == WarmupStatus.COLD_READY
    log = db_session.query(AuditLog).filter(
        AuditLog.entity_type == "mailbox", AuditLog.entity_id == mb.mailbox_id,
        AuditLog.action == "warmup_gate_override",
    ).one()
    assert log.changed_by == "superadmin@test.com"
    # Still not outreach-eligible: the override changes status, not warmup history.
    assert r.json()["mailbox"]["outreach_eligible"] is False


def test_update_status_allows_warmed_mailbox(client, db_session, test_tenant, auth_headers):
    mb = _mailbox(db_session, test_tenant, status=WarmupStatus.WARMING_UP, days=14, emails=50)
    r = client.post(f"/api/v1/mailboxes/{mb.mailbox_id}/update-status?new_status=cold_ready",
                    headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["mailbox"]["outreach_eligible"] is True


def test_update_status_pause_not_gated(client, db_session, test_tenant, auth_headers):
    mb = _mailbox(db_session, test_tenant, days=0, emails=0)
    r = client.post(f"/api/v1/mailboxes/{mb.mailbox_id}/update-status?new_status=paused",
                    headers=auth_headers)
    assert r.status_code == 200


def test_list_mailboxes_reports_gate(client, db_session, test_tenant, auth_headers):
    _mailbox(db_session, test_tenant, email="cold@a.in", days=3, emails=12)
    _mailbox(db_session, test_tenant, email="warm@b.in")
    r = client.get("/api/v1/mailboxes", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    by_email = {i["email"]: i for i in body["items"]}
    assert by_email["cold@a.in"]["outreach_eligible"] is False
    assert by_email["cold@a.in"]["can_send"] is False
    assert by_email["cold@a.in"]["outreach_block_reason"] == "Warming up — 3/14 days, 12/50 emails"
    assert by_email["warm@b.in"]["outreach_eligible"] is True
    assert by_email["warm@b.in"]["outreach_block_reason"] is None
    assert body["outreach_eligible_count"] == 1


# ---------------------------------------------------------------------------
# D2 — ISP ramp
# ---------------------------------------------------------------------------

def test_recommended_daily_ramp_is_deterministic():
    other = ISP_PROFILES["other"]["recommended_daily_ramp"]
    assert recommended_daily_ramp(1) == other[0]
    assert recommended_daily_ramp(3) == other[2]
    assert recommended_daily_ramp(0) == other[0]
    assert recommended_daily_ramp(999) == other[-1]
    gmail = ISP_PROFILES["gmail"]["recommended_daily_ramp"]
    assert recommended_daily_ramp(2, email="a@gmail.com") == gmail[1]
    outlook = ISP_PROFILES["outlook"]["recommended_daily_ramp"]
    assert recommended_daily_ramp(2, email="a@corp.com", smtp_host="smtp.office365.com") == outlook[1]


def test_effective_daily_limit_by_day():
    mb = SimpleNamespace(daily_send_limit=30, email="a@x.in", smtp_host="mail.x.in")
    today = datetime(2026, 10, 12).date()
    assert ms.effective_daily_limit(mb, None, today) == 2  # never sent => day 1
    assert ms.effective_daily_limit(mb, datetime(2026, 10, 12, 9), today) == 2   # day 1
    assert ms.effective_daily_limit(mb, datetime(2026, 10, 10, 9), today) == 8   # day 3
    assert ms.effective_daily_limit(mb, datetime(2026, 9, 13), today) == 30      # day 30, plateau
    mb.daily_send_limit = 50
    assert ms.effective_daily_limit(mb, datetime(2026, 9, 13), today) == 30      # still in window
    assert ms.effective_daily_limit(mb, datetime(2026, 9, 1), today) == 50       # day 42: ramp over
    mb.daily_send_limit = 5
    assert ms.effective_daily_limit(mb, datetime(2026, 10, 1), today) == 5       # never above own limit


def test_ramp_blocks_mailbox_over_todays_cap(db_session, test_tenant):
    mb = _mailbox(db_session, test_tenant, sent_today=2)
    # First outreach today => day 1 => cap 2 => already used.
    _sent_event(db_session, mb, datetime.utcnow())
    assert ms.select_best_mailbox([mb.mailbox_id], db_session, tenant_id=test_tenant.tenant_id) is None
    assert ms.mailbox_effective_daily_limit(db_session, mb) == 2
    mb.emails_sent_today = 1
    db_session.commit()
    assert ms.select_best_mailbox([mb.mailbox_id], db_session, tenant_id=test_tenant.tenant_id) is not None


def test_ramp_ignores_skipped_and_mailmerge_events(db_session, test_tenant):
    mb = _mailbox(db_session, test_tenant)
    c = _contact(db_session, test_tenant)
    old = datetime.utcnow() - timedelta(days=60)
    for status, channel in ((OutreachStatus.SKIPPED, OutreachChannel.SMTP),
                            (OutreachStatus.SENT, OutreachChannel.MAILMERGE)):
        db_session.add(OutreachEvent(tenant_id=mb.tenant_id, contact_id=c.contact_id,
                                     sender_mailbox_id=mb.mailbox_id, sent_at=old,
                                     channel=channel, status=status))
    db_session.commit()
    assert ms.first_outreach_dates(db_session, [mb.mailbox_id]) == {}


# ---------------------------------------------------------------------------
# D3 — per-IP cohort cap
# ---------------------------------------------------------------------------

def test_cohort_second_domain_blocked_while_first_live(db_session, test_tenant):
    live = _mailbox(db_session, test_tenant, email="a@alpha.in")
    other = _mailbox(db_session, test_tenant, email="b@beta.in")
    _sent_event(db_session, live, datetime.utcnow() - timedelta(days=40))  # past ramp
    _sent_event(db_session, live, datetime.utcnow() - timedelta(days=2))   # live
    assert ms.cohort_blocked_ids(db_session, [live, other]) == {other.mailbox_id}
    assert ms.select_best_mailbox([other.mailbox_id], db_session, tenant_id=test_tenant.tenant_id) is None
    picked = ms.select_best_mailbox([live.mailbox_id, other.mailbox_id], db_session,
                                    tenant_id=test_tenant.tenant_id)
    assert picked.mailbox_id == live.mailbox_id


def test_cohort_frees_slot_after_live_window(db_session, test_tenant):
    old = _mailbox(db_session, test_tenant, email="a@alpha.in")
    other = _mailbox(db_session, test_tenant, email="b@beta.in")
    _sent_event(db_session, old, datetime.utcnow() - timedelta(days=20))
    assert ms.cohort_blocked_ids(db_session, [other]) == set()


def test_cohort_admits_only_cap_new_domains_per_selection(db_session, test_tenant):
    a = _mailbox(db_session, test_tenant, email="x@alpha.in")
    b = _mailbox(db_session, test_tenant, email="y@beta.in")
    a2 = _mailbox(db_session, test_tenant, email="z@alpha.in")
    # Nothing live yet: first domain alphabetically takes the one slot.
    assert ms.cohort_blocked_ids(db_session, [b, a, a2]) == {b.mailbox_id}


def test_cohort_different_ips_both_allowed(db_session, test_tenant, monkeypatch):
    monkeypatch.setattr(ms, "_dns_lookup", lambda host: {"mail.alpha.in": "1.1.1.1"}.get(host, "2.2.2.2"))
    live = _mailbox(db_session, test_tenant, email="a@alpha.in", smtp_host="mail.alpha.in")
    other = _mailbox(db_session, test_tenant, email="b@beta.in", smtp_host="mail.beta.in")
    _sent_event(db_session, live, datetime.utcnow() - timedelta(days=40))
    _sent_event(db_session, live, datetime.utcnow() - timedelta(days=1))
    assert ms.cohort_blocked_ids(db_session, [live, other]) == set()


def test_cohort_dns_failure_fails_open(db_session, test_tenant, monkeypatch):
    def boom(host):
        raise OSError("NXDOMAIN")
    monkeypatch.setattr(ms, "_dns_lookup", boom)
    live = _mailbox(db_session, test_tenant, email="a@alpha.in")
    other = _mailbox(db_session, test_tenant, email="b@beta.in")
    _sent_event(db_session, live, datetime.utcnow() - timedelta(days=1))
    assert ms.cohort_blocked_ids(db_session, [live, other]) == set()


def test_dns_cache_resolves_once(monkeypatch):
    calls = []
    monkeypatch.setattr(ms, "_dns_lookup", lambda host: calls.append(host) or "9.9.9.9")
    assert ms.resolve_sending_ip("mail.x.in") == "9.9.9.9"
    assert ms.resolve_sending_ip("MAIL.x.in") == "9.9.9.9"
    assert calls == ["mail.x.in"]


def test_cohort_ignores_esp_and_other_tenants(db_session, test_tenant):
    from app.db.models.tenant import Tenant, TenantPlan
    other_tenant = Tenant(name="Other", slug="other-org", plan=TenantPlan.ENTERPRISE)
    db_session.add(other_tenant)
    db_session.commit()
    foreign_live = _mailbox(db_session, other_tenant, email="f@foreign.in")
    _sent_event(db_session, foreign_live, datetime.utcnow() - timedelta(days=1))
    mine = _mailbox(db_session, test_tenant, email="m@mine.in")
    assert ms.cohort_blocked_ids(db_session, [mine]) == set()
    o365 = _mailbox(db_session, test_tenant, email="o@corp.com", smtp_host="smtp.office365.com",
                    provider=EmailProvider.MICROSOFT_365)
    assert ms.mailbox_sending_ip(o365) is None


# ---------------------------------------------------------------------------
# L2 — no Exzelon logo default
# ---------------------------------------------------------------------------

def test_render_template_has_no_exzelon_logo_default(db_session, test_tenant):
    import inspect
    from app.services.pipelines.outreach import render_template
    assert inspect.signature(render_template).parameters["logo_url"].default is None
    mb = _mailbox(db_session, test_tenant)
    tpl = SimpleNamespace(subject="Hi {{contact_first_name}}",
                          body_html='<p>Hello</p><img src="{{logo_url}}" alt="logo"><p>{{logo_url}}</p>',
                          body_text="Hello")
    contact = SimpleNamespace(first_name="Ann", client_name="Acme")
    _, html, _ = render_template(tpl, contact, None, mb, "")
    assert "exzelon" not in html.lower()
    assert "<img" not in html  # broken-image tag dropped when no logo is set
    assert "{{logo_url}}" not in html


def test_render_template_uses_tenant_logo(db_session, test_tenant):
    from app.services.pipelines.outreach import render_template
    test_tenant.logo_url = "https://cdn.example.com/acme.png"
    db_session.commit()
    mb = _mailbox(db_session, test_tenant)
    tpl = SimpleNamespace(subject="s", body_html='<img src="{{logo_url}}">', body_text="")
    _, html, _ = render_template(tpl, SimpleNamespace(first_name="A", client_name="C"), None, mb, "")
    assert 'src="https://cdn.example.com/acme.png"' in html
