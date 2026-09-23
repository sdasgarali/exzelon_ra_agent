"""Transactional mail: provider selection, Resend adapter, and the best-effort contract.

No test here touches the network — the Resend adapter is exercised against a stubbed
`httpx.post`, so the suite stays offline and a missing API key can never turn into a
silent skip that hides a regression.
"""
import base64

import pytest

from app.services.adapters.transactional import (
    Attachment, ResendMailer, SMTPMailer, resolve_sender,
)
from app.services.adapters.transactional import resend_mailer as resend_mod

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


@pytest.fixture
def captured(monkeypatch):
    """Capture the outbound Resend request instead of sending it."""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json})
        return _Resp(200, {"id": "email_123"})

    monkeypatch.setattr(resend_mod.httpx, "post", fake_post)
    return calls


# ---------------------------------------------------------------------------
# Resend adapter
# ---------------------------------------------------------------------------

def test_resend_sends_and_returns_the_message_id(captured):
    mailer = ResendMailer(api_key="re_test", default_from_email="no-reply@example.com")
    result = mailer.send(
        to_email="dest@example.com", subject="Hi", html_body="<p>Body</p>",
        from_email="no-reply@example.com", from_name="NeuraLeads",
    )
    assert result.ok and result.message_id == "email_123" and result.provider == "resend"

    sent = captured[0]["json"]
    assert sent["from"] == "NeuraLeads <no-reply@example.com>"
    assert sent["to"] == ["dest@example.com"]
    assert sent["subject"] == "Hi"
    assert captured[0]["headers"]["Authorization"] == "Bearer re_test"


def test_resend_omits_the_display_name_when_there_is_none(captured):
    ResendMailer(api_key="re_test", default_from_email="a@b.com").send(
        to_email="d@e.com", subject="S", html_body="<p>x</p>", from_email="a@b.com",
    )
    assert captured[0]["json"]["from"] == "a@b.com"


def test_resend_base64_encodes_attachments(captured):
    ResendMailer(api_key="re_test", default_from_email="a@b.com").send(
        to_email="d@e.com", subject="Invoice", html_body="<p>x</p>", from_email="a@b.com",
        attachments=[Attachment(filename="inv.pdf", content=b"%PDF-1.4 fake")],
    )
    att = captured[0]["json"]["attachments"][0]
    assert att["filename"] == "inv.pdf"
    assert base64.b64decode(att["content"]) == b"%PDF-1.4 fake"


def test_resend_never_raises_on_a_network_error(monkeypatch):
    """Every call site treats system mail as best-effort; an exception here would
    500 a signup or roll back a deal."""
    def boom(*a, **k):
        raise ConnectionError("dns exploded")

    monkeypatch.setattr(resend_mod.httpx, "post", boom)
    result = ResendMailer(api_key="re_test", default_from_email="a@b.com").send(
        to_email="d@e.com", subject="S", html_body="<p>x</p>", from_email="a@b.com")
    assert result.ok is False
    assert "Could not reach Resend" in result.detail


def test_resend_surfaces_an_unverified_domain_verbatim(monkeypatch):
    """The most common real failure. A generic 'send failed' sends people hunting for
    a bug instead of verifying their domain."""
    monkeypatch.setattr(resend_mod.httpx, "post", lambda *a, **k: _Resp(
        403, {"name": "validation_error", "message": "The example.com domain is not verified"}))
    result = ResendMailer(api_key="re_test", default_from_email="a@example.com").send(
        to_email="d@e.com", subject="S", html_body="<p>x</p>", from_email="a@example.com")
    assert result.ok is False
    assert "not verified" in result.detail
    assert "verified in Resend" in result.detail  # the actionable hint


def test_resend_without_a_key_fails_cleanly():
    result = ResendMailer(api_key="", default_from_email="a@b.com").send(
        to_email="d@e.com", subject="S", html_body="<p>x</p>", from_email="a@b.com")
    assert result.ok is False and "RESEND_API_KEY" in result.detail


def test_resend_is_configured_needs_both_key_and_sender():
    assert ResendMailer(api_key="k", default_from_email="a@b.com").is_configured()
    assert not ResendMailer(api_key="k", default_from_email="").is_configured()
    assert not ResendMailer(api_key="", default_from_email="a@b.com").is_configured()


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def _set(monkeypatch, **kw):
    from app.core.config import settings
    for k, v in kw.items():
        monkeypatch.setattr(settings, k, v)


def test_auto_prefers_resend_when_a_key_is_set(db_session, monkeypatch):
    _set(monkeypatch, SYSTEM_MAIL_PROVIDER="auto", RESEND_API_KEY="re_x",
         RESEND_FROM_EMAIL="no-reply@example.com", RESEND_FROM_NAME="NL",
         SMTP_HOST="smtp.example.com", SMTP_USER="u", SMTP_PASSWORD="p")
    resolved = resolve_sender(db_session, tenant_id=None)
    assert resolved["provider"] == "resend"
    assert resolved["sender_email"] == "no-reply@example.com"


def test_auto_falls_back_to_smtp_without_a_resend_key(db_session, monkeypatch):
    _set(monkeypatch, SYSTEM_MAIL_PROVIDER="auto", RESEND_API_KEY="", RESEND_FROM_EMAIL="",
         SMTP_HOST="smtp.example.com", SMTP_USER="u@example.com", SMTP_PASSWORD="p",
         SMTP_PORT=587)
    resolved = resolve_sender(db_session, tenant_id=None)
    assert resolved["provider"] == "smtp"
    assert isinstance(resolved["mailer"], SMTPMailer)


def test_forcing_resend_does_not_silently_fall_back_to_smtp(db_session, monkeypatch):
    """Mail arriving from an unexpected sender is harder to diagnose than mail that
    does not arrive at all — so an explicit choice fails loudly."""
    _set(monkeypatch, SYSTEM_MAIL_PROVIDER="resend", RESEND_API_KEY="", RESEND_FROM_EMAIL="",
         SMTP_HOST="smtp.example.com", SMTP_USER="u", SMTP_PASSWORD="p")
    resolved = resolve_sender(db_session, tenant_id=None)
    assert resolved["mailer"] is None
    assert resolved["source"] == "none"


def test_none_disables_the_global_sender(db_session, monkeypatch):
    _set(monkeypatch, SYSTEM_MAIL_PROVIDER="none", RESEND_API_KEY="re_x",
         RESEND_FROM_EMAIL="a@b.com")
    assert resolve_sender(db_session, tenant_id=None)["mailer"] is None


def test_nothing_configured_resolves_to_none(db_session, monkeypatch):
    _set(monkeypatch, SYSTEM_MAIL_PROVIDER="auto", RESEND_API_KEY="", RESEND_FROM_EMAIL="",
         SMTP_HOST="", SMTP_USER="", SMTP_PASSWORD="")
    resolved = resolve_sender(db_session, tenant_id=None)
    assert resolved["source"] == "none" and resolved["mailer"] is None


def test_a_tenants_own_smtp_beats_the_global_resend(db_session, test_tenant, monkeypatch):
    """A tenant who configured their own sender did so to have mail come from THEIR
    domain. Routing it through our shared provider would undo that and put their mail
    under our reputation."""
    from app.core.encryption import encrypt_field
    from app.core.settings_resolver import set_tenant_setting

    _set(monkeypatch, SYSTEM_MAIL_PROVIDER="auto", RESEND_API_KEY="re_x",
         RESEND_FROM_EMAIL="shared@neuraleads.com")

    tid = test_tenant.tenant_id
    set_tenant_setting(db_session, "notification_smtp_host", "mail.tenant.com", tenant_id=tid)
    set_tenant_setting(db_session, "notification_smtp_user", "bot@tenant.com", tenant_id=tid)
    set_tenant_setting(db_session, "notification_smtp_password_enc",
                       encrypt_field("secret"), tenant_id=tid)
    set_tenant_setting(db_session, "notification_sender_email", "hello@tenant.com", tenant_id=tid)
    db_session.commit()

    resolved = resolve_sender(db_session, tenant_id=tid)
    assert resolved["source"] == "tenant"
    assert resolved["provider"] == "smtp"
    assert resolved["sender_email"] == "hello@tenant.com"


# ---------------------------------------------------------------------------
# send_system_email contract
# ---------------------------------------------------------------------------

def test_send_system_email_returns_false_with_no_sender(db_session, monkeypatch):
    from app.services.system_mailer import send_system_email
    _set(monkeypatch, SYSTEM_MAIL_PROVIDER="none")
    assert send_system_email(db_session, None, "a@b.com", "S", "<p>x</p>") is False


def test_send_system_email_rejects_an_empty_recipient(db_session):
    from app.services.system_mailer import send_system_email
    assert send_system_email(db_session, None, "", "S", "<p>x</p>") is False


def test_send_system_email_routes_through_resend(db_session, monkeypatch, captured):
    from app.services.system_mailer import send_system_email
    _set(monkeypatch, SYSTEM_MAIL_PROVIDER="resend", RESEND_API_KEY="re_x",
         RESEND_FROM_EMAIL="no-reply@example.com", RESEND_FROM_NAME="NeuraLeads")

    assert send_system_email(db_session, None, "dest@example.com", "Verify", "<p>x</p>") is True
    assert captured[0]["json"]["to"] == ["dest@example.com"]


def test_cold_outreach_never_uses_the_transactional_path():
    """Structural guard.

    Campaign sending must go through the tenant's own mailboxes: their domain
    reputation, their warmup history, the 30/day pacing the send gate enforces. Routing
    it through a shared transactional provider would get that provider's account
    terminated — Resend and every comparable service bans cold email — and would put
    every tenant behind one sender reputation.
    """
    import inspect

    from app.services import campaign_engine
    from app.services.pipelines import outreach

    for module in (campaign_engine, outreach):
        source = inspect.getsource(module)
        assert "adapters.transactional" not in source, (
            f"{module.__name__} imports the transactional mailer — cold outreach must "
            "use the tenant's own mailboxes"
        )
        assert "ResendMailer" not in source, f"{module.__name__} references Resend"
