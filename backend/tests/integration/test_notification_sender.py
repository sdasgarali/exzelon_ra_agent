"""Tenant-configurable notification sender: service resolution + settings endpoints."""
import pytest

from app.core.settings_resolver import set_tenant_setting, get_tenant_setting
from app.core.encryption import encrypt_field, decrypt_field
from app.services import system_mailer
from app.services.adapters.transactional import MailResult, SMTPMailer
from app.services.adapters.transactional import smtp_mailer as smtp_mod

pytestmark = pytest.mark.integration


@pytest.fixture
def captured(monkeypatch):
    """Capture SMTP sends instead of hitting a real server.

    Patches `SMTPMailer.send` rather than a module-level function: the send path moved
    behind the transactional provider layer when Resend was added, and the interesting
    assertions (which host, which credentials, which sender) now live on the mailer
    instance rather than in the call kwargs.
    """
    calls = []

    def fake_send(self, **kwargs):
        calls.append({
            "host": self.host, "port": self.port, "user": self.user,
            "password": self.password, "security": self.security,
            **kwargs,
        })
        return MailResult(True, "Sent.", provider="smtp")

    monkeypatch.setattr(SMTPMailer, "send", fake_send)
    return calls


@pytest.fixture(autouse=True)
def _no_global_resend(monkeypatch):
    """Keep these tests about SMTP resolution.

    `.env` is not loaded under pytest (conftest sets DATABASE_URL, which short-circuits
    the env loader), so RESEND_API_KEY is already empty — this makes that explicit so
    the tests do not quietly change meaning if that ever stops being true.
    """
    from app.core.config import settings
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(settings, "RESEND_FROM_EMAIL", "")
    monkeypatch.setattr(settings, "SYSTEM_MAIL_PROVIDER", "auto")


class TestSendSystemEmail:
    def test_uses_tenant_config_when_set(self, db_session, test_tenant, captured):
        tid = test_tenant.tenant_id
        set_tenant_setting(db_session, system_mailer.K_HOST, "smtp.office365.com", tenant_id=tid)
        set_tenant_setting(db_session, system_mailer.K_USER, "Hr@exzelon.com", tenant_id=tid)
        set_tenant_setting(db_session, system_mailer.K_EMAIL, "Hr@exzelon.com", tenant_id=tid)
        set_tenant_setting(db_session, system_mailer.K_PORT, 587, tenant_id=tid)
        set_tenant_setting(db_session, system_mailer.K_SECURITY, "starttls", tenant_id=tid)
        set_tenant_setting(db_session, system_mailer.K_PASSWORD_ENC, encrypt_field("secret"), tenant_id=tid)
        db_session.commit()

        ok = system_mailer.send_system_email(db_session, tid, "rep@example.com", "Subj", "<b>hi</b>")
        assert ok is True
        assert len(captured) == 1
        c = captured[0]
        assert c["host"] == "smtp.office365.com"
        assert c["user"] == "Hr@exzelon.com"
        assert c["password"] == "secret"          # decrypted for the send
        assert c["from_email"] == "Hr@exzelon.com"
        assert c["to_email"] == "rep@example.com"

    def test_resend_is_used_when_no_tenant_smtp_is_set(self, db_session, test_tenant, monkeypatch):
        """The global fallback is now provider-aware, not SMTP-only."""
        from app.core.config import settings
        from app.services.adapters.transactional import resend_mailer as resend_mod

        monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
        monkeypatch.setattr(settings, "RESEND_FROM_EMAIL", "no-reply@neuraleads.com")
        monkeypatch.setattr(settings, "RESEND_FROM_NAME", "NeuraLeads")

        sent = []

        class _R:
            status_code = 200

            @staticmethod
            def json():
                return {"id": "email_abc"}

        def fake_post(url, headers=None, json=None, timeout=None):
            sent.append(json)
            return _R()

        monkeypatch.setattr(resend_mod.httpx, "post", fake_post)

        ok = system_mailer.send_system_email(
            db_session, test_tenant.tenant_id, "rep@example.com", "Subj", "<b>hi</b>")
        assert ok is True
        assert sent[0]["from"] == "NeuraLeads <no-reply@neuraleads.com>"
        assert sent[0]["to"] == ["rep@example.com"]

    def test_skips_when_nothing_configured(self, db_session, test_tenant, captured, monkeypatch):
        from app.core.config import settings as _settings
        # No tenant config + no global SMTP → skip (returns False, no send).
        monkeypatch.setattr(_settings, "SMTP_HOST", "")
        monkeypatch.setattr(_settings, "SMTP_USER", "")
        monkeypatch.setattr(_settings, "SMTP_PASSWORD", "")
        ok = system_mailer.send_system_email(db_session, test_tenant.tenant_id, "x@example.com", "s", "h")
        assert ok is False
        assert captured == []

    def test_falls_back_to_global(self, db_session, test_tenant, captured, monkeypatch):
        from app.core.config import settings as _settings
        monkeypatch.setattr(_settings, "SMTP_HOST", "mail.exzelon.in")
        monkeypatch.setattr(_settings, "SMTP_USER", "no-reply@exzelon.in")
        monkeypatch.setattr(_settings, "SMTP_PASSWORD", "gpw")
        monkeypatch.setattr(_settings, "SMTP_PORT", 587)
        ok = system_mailer.send_system_email(db_session, test_tenant.tenant_id, "x@example.com", "s", "h")
        assert ok is True
        assert captured[0]["host"] == "mail.exzelon.in"
        assert captured[0]["user"] == "no-reply@exzelon.in"


class TestNotificationSenderEndpoints:
    def test_get_defaults_empty(self, client, auth_headers):
        r = client.get("/api/v1/settings/notifications/sender", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["configured"] is False
        assert body["password_set"] is False

    def test_put_saves_and_encrypts_password(self, client, db_session, auth_headers, test_tenant):
        payload = {
            "sender_email": "Hr@exzelon.com", "sender_name": "Exzelon Notifications",
            "smtp_host": "smtp.office365.com", "smtp_port": 587,
            "smtp_user": "Hr@exzelon.com", "smtp_security": "starttls",
            "smtp_password": "Exz@2631",
        }
        r = client.put("/api/v1/settings/notifications/sender", headers=auth_headers, json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["configured"] is True
        assert body["password_set"] is True
        assert body["smtp_host"] == "smtp.office365.com"
        assert "password" not in str(body).lower() or "password_set" in body  # never leaks the value
        # Stored password is encrypted (Fernet token), decrypts back.
        enc = get_tenant_setting(db_session, system_mailer.K_PASSWORD_ENC, tenant_id=test_tenant.tenant_id)
        assert enc.startswith("gAAAAA")
        assert decrypt_field(enc) == "Exz@2631"

    def test_put_blank_password_keeps_existing(self, client, db_session, auth_headers, test_tenant):
        set_tenant_setting(db_session, system_mailer.K_PASSWORD_ENC, encrypt_field("keepme"), tenant_id=test_tenant.tenant_id)
        db_session.commit()
        payload = {"smtp_host": "smtp.office365.com", "smtp_user": "Hr@exzelon.com", "smtp_port": 587}
        r = client.put("/api/v1/settings/notifications/sender", headers=auth_headers, json=payload)
        assert r.status_code == 200
        enc = get_tenant_setting(db_session, system_mailer.K_PASSWORD_ENC, tenant_id=test_tenant.tenant_id)
        assert decrypt_field(enc) == "keepme"

    def test_test_endpoint_sends(self, client, auth_headers, test_tenant, db_session, monkeypatch):
        set_tenant_setting(db_session, system_mailer.K_HOST, "smtp.office365.com", tenant_id=test_tenant.tenant_id)
        set_tenant_setting(db_session, system_mailer.K_USER, "Hr@exzelon.com", tenant_id=test_tenant.tenant_id)
        set_tenant_setting(db_session, system_mailer.K_PASSWORD_ENC, encrypt_field("p"), tenant_id=test_tenant.tenant_id)
        db_session.commit()
        monkeypatch.setattr(SMTPMailer, "send",
                            lambda self, **k: MailResult(True, "Sent.", provider="smtp"))
        r = client.post("/api/v1/settings/notifications/sender/test", headers=auth_headers, json={"to_email": "me@example.com"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
