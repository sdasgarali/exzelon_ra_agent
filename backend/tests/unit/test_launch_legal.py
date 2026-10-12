"""Launch readiness — legal & compliance (Plan_Launch_Readiness_6.md L1-L4 + site-info).

Covers:
- GET /public/site-info: shape, privacy-email fallback, payments flag, cache header
- L1: send gate refuses outreach without a workspace postal address; replies,
  warmup and transactional mail are unaffected; admins can set the address
- L2: no Exzelon logo default in template previews; empty logo drops the <img>
- L3: no "123 Business St" placeholder default
- L4: signup requires accept_terms and records terms_accepted_at / terms_version
"""
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.db.models.contact import ContactDetails
from app.db.models.email_template import EmailTemplate, TemplateStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.services.send_gate import unified_send_gate, tenant_has_postal_address

pytestmark = pytest.mark.unit

API = "/api/v1"
EXZELON_LOGO = "exzelon.com/gallery/logo.png"
PLACEHOLDER_ADDRESS = "123 Business St"


# ---------------------------------------------------------------------------
# Site info
# ---------------------------------------------------------------------------

class TestSiteInfo:
    KEYS = {"support_email", "privacy_email", "legal_entity_name", "legal_address",
            "legal_jurisdiction", "terms_version", "payments_enabled"}

    def test_public_shape_no_auth_and_cache_header(self, client, monkeypatch):
        monkeypatch.setattr(settings, "SUPPORT_EMAIL", "help@example.com")
        monkeypatch.setattr(settings, "PRIVACY_EMAIL", "")
        monkeypatch.setattr(settings, "LEGAL_ENTITY_NAME", "Acme Ltd")
        monkeypatch.setattr(settings, "LEGAL_ADDRESS", "1 Main St")
        monkeypatch.setattr(settings, "LEGAL_JURISDICTION", "Delaware")
        monkeypatch.setattr(settings, "TERMS_VERSION", "2026-10-01")
        r = client.get(f"{API}/public/site-info")
        assert r.status_code == 200
        body = r.json()
        assert set(body) == self.KEYS
        assert body["support_email"] == "help@example.com"
        assert body["privacy_email"] == "help@example.com"  # falls back to support
        assert body["legal_entity_name"] == "Acme Ltd"
        assert body["legal_address"] == "1 Main St"
        assert body["legal_jurisdiction"] == "Delaware"
        assert body["terms_version"] == "2026-10-01"
        assert "max-age=300" in r.headers.get("cache-control", "")

    def test_privacy_email_used_when_set(self, client, monkeypatch):
        monkeypatch.setattr(settings, "PRIVACY_EMAIL", "privacy@example.com")
        assert client.get(f"{API}/public/site-info").json()["privacy_email"] == "privacy@example.com"

    def _set_billing(self, monkeypatch, enabled, key, price):
        monkeypatch.setattr(settings, "BILLING_ENABLED", enabled)
        monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", key)
        monkeypatch.setattr(settings, "STRIPE_PRICE_PRO", price)

    def test_payments_enabled_when_fully_configured(self, client, monkeypatch):
        self._set_billing(monkeypatch, True, "sk_test_x", "price_pro")
        assert client.get(f"{API}/public/site-info").json()["payments_enabled"] is True

    @pytest.mark.parametrize("enabled,key,price", [
        (False, "sk_test_x", "price_pro"),   # billing switched off
        (True, "", "price_pro"),             # no Stripe key
        (True, "sk_test_x", ""),             # no Pro price
    ])
    def test_payments_disabled_when_anything_missing(self, client, monkeypatch, enabled, key, price):
        self._set_billing(monkeypatch, enabled, key, price)
        assert client.get(f"{API}/public/site-info").json()["payments_enabled"] is False


# ---------------------------------------------------------------------------
# L1 — postal address send gate
# ---------------------------------------------------------------------------

def _contact(db, tenant_id, email="buyer@prospect.com"):
    c = ContactDetails(tenant_id=tenant_id, email=email, first_name="Pat", last_name="Buyer",
                       client_name="Prospect Co", validation_status="valid")
    db.add(c)
    db.flush()
    return c


def _set_address(db, tenant, address):
    tenant.company_address = address
    db.commit()


class TestPostalAddressGate:

    @pytest.mark.parametrize("address", [None, "", "   "])
    def test_outreach_blocked_without_address(self, db_session, test_tenant, address):
        _set_address(db_session, test_tenant, address)
        c = _contact(db_session, test_tenant.tenant_id)
        result = unified_send_gate(db_session, c, test_tenant.tenant_id)
        assert result.allowed is False
        assert result.reason_code == "NO_POSTAL_ADDRESS"
        assert "postal address" in result.reason_message
        assert "CAN-SPAM" in result.reason_message

    def test_dry_run_also_reports_missing_address(self, db_session, test_tenant):
        c = _contact(db_session, test_tenant.tenant_id)
        result = unified_send_gate(db_session, c, test_tenant.tenant_id, dry_run=True)
        assert result.reason_code == "NO_POSTAL_ADDRESS"

    def test_platform_billing_address_is_not_a_fallback(self, db_session, test_tenant, monkeypatch):
        monkeypatch.setattr(settings, "BILLING_COMPANY_ADDRESS", "NeuraLeads HQ, 9 Platform Rd")
        c = _contact(db_session, test_tenant.tenant_id)
        assert unified_send_gate(db_session, c, test_tenant.tenant_id).reason_code == "NO_POSTAL_ADDRESS"

    def test_outreach_allowed_with_address(self, db_session, test_tenant):
        _set_address(db_session, test_tenant, "1 Main St, Springfield, IL 62701")
        c = _contact(db_session, test_tenant.tenant_id)
        result = unified_send_gate(db_session, c, test_tenant.tenant_id)
        assert result.allowed is True, result.reason_message
        assert any(ch.name == "postal_address" and ch.passed for ch in result.checks)

    def test_replies_not_blocked(self, db_session, test_tenant):
        c = _contact(db_session, test_tenant.tenant_id)
        result = unified_send_gate(db_session, c, test_tenant.tenant_id, is_reply=True)
        assert result.allowed is True, result.reason_message

    def test_address_is_per_tenant(self, db_session, test_tenant):
        other = Tenant(name="Other", slug="other-co", company_address="2 Side St")
        db_session.add(other)
        db_session.commit()
        assert tenant_has_postal_address(db_session, other.tenant_id) is True
        assert tenant_has_postal_address(db_session, test_tenant.tenant_id) is False
        assert tenant_has_postal_address(db_session, None) is False

    def test_lookup_failure_fails_closed(self, db_session, test_tenant):
        c = _contact(db_session, test_tenant.tenant_id)
        with patch("app.services.send_gate.tenant_has_postal_address", side_effect=RuntimeError("db")):
            result = unified_send_gate(db_session, c, test_tenant.tenant_id)
        assert result.reason_code == "NO_POSTAL_ADDRESS"

    def test_warmup_and_transactional_paths_do_not_use_the_gate(self):
        """Warmup and system mail must never be blocked by the outreach address rule:
        neither module routes through unified_send_gate."""
        import inspect
        import app.services.warmup.scheduler as warmup_scheduler
        import app.services.system_mailer as transactional
        for mod in (warmup_scheduler, transactional):
            assert "unified_send_gate" not in inspect.getsource(mod)


class TestCompanyProfileAddress:

    def test_admin_can_set_and_clear_address(self, client, auth_headers, db_session, test_tenant):
        r = client.put(f"{API}/settings/company-profile", headers=auth_headers,
                       json={"company_address": "  1 Main St, Springfield  "})
        assert r.status_code == 200
        assert r.json()["company_address"] == "1 Main St, Springfield"
        db_session.refresh(test_tenant)
        assert test_tenant.company_address == "1 Main St, Springfield"

        r = client.put(f"{API}/settings/company-profile", headers=auth_headers,
                       json={"company_address": "   "})
        assert r.status_code == 200
        db_session.refresh(test_tenant)
        assert test_tenant.company_address is None

    def test_non_admin_cannot_set_address(self, client, operator_headers):
        r = client.put(f"{API}/settings/company-profile", headers=operator_headers,
                       json={"company_address": "1 Main St"})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# L2 — no Exzelon logo default
# ---------------------------------------------------------------------------

LOGO_BODY = ('<p>Hi {{contact_first_name}}</p>'
             '<div><img src="{{logo_url}}" alt="logo" style="max-width:150px" /></div>')


def _template(db, tenant_id):
    t = EmailTemplate(tenant_id=tenant_id, name="T", subject="Hello {{contact_first_name}}",
                      body_html=LOGO_BODY, body_text="Hi {{contact_first_name}}",
                      status=TemplateStatus.ACTIVE)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


class TestLogoDefault:

    def test_sources_have_no_exzelon_logo(self):
        import inspect
        import app.services.template_service as ts
        import app.api.endpoints.templates as te
        for mod in (ts, te):
            assert EXZELON_LOGO not in inspect.getsource(mod)

    def test_service_preview_without_logo_drops_img(self, db_session, test_tenant):
        from app.services.template_service import preview_template
        t = _template(db_session, test_tenant.tenant_id)
        out = preview_template(db_session, t.template_id)
        assert "<img" not in out["body_html"]
        assert "{{logo_url}}" not in out["body_html"]
        assert "Hi John" in out["body_html"]

    def test_service_preview_uses_tenant_logo(self, db_session, test_tenant):
        from app.services.template_service import preview_template
        test_tenant.brand_logo_url = "https://cdn.acme.test/logo.png"
        db_session.commit()
        t = _template(db_session, test_tenant.tenant_id)
        out = preview_template(db_session, t.template_id)
        assert '<img src="https://cdn.acme.test/logo.png"' in out["body_html"]

    def test_profile_logo_used_when_no_brand_logo(self, db_session, test_tenant):
        from app.services.template_service import tenant_logo_url
        test_tenant.logo_url = "https://acme.test/l.png"
        db_session.commit()
        assert tenant_logo_url(db_session, test_tenant.tenant_id) == "https://acme.test/l.png"
        assert tenant_logo_url(db_session, None) == ""

    def test_endpoint_preview_without_logo(self, client, auth_headers, db_session, test_tenant):
        t = _template(db_session, test_tenant.tenant_id)
        r = client.post(f"{API}/templates/{t.template_id}/preview", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()["body_html"]
        assert "<img" not in body and EXZELON_LOGO not in body

    def test_apply_logo_escapes_and_handles_empty(self):
        from app.services.template_service import apply_logo
        assert apply_logo("", "x") == ""
        assert apply_logo('<img src="{{logo_url}}">', "") == ""
        assert apply_logo('<img src="{{logo_url}}">', "https://a/b.png") == '<img src="https://a/b.png">'


# ---------------------------------------------------------------------------
# L3 — no placeholder address default
# ---------------------------------------------------------------------------

class TestPlaceholderAddress:

    def test_default_setting_is_empty(self):
        import inspect
        import app.api.endpoints.settings as s
        assert PLACEHOLDER_ADDRESS not in inspect.getsource(s)
        assert s.DEFAULT_SETTINGS["company_address"]["value"] == ""


# ---------------------------------------------------------------------------
# L4 — terms acceptance at signup
# ---------------------------------------------------------------------------

def _signup(client, email, **extra):
    payload = {"email": email, "password": "SecurePass123!", "full_name": "Jane Doe",
               "company_name": f"Co {email}", **extra}
    with patch("app.services.email_verification._send_email", return_value=True):
        return client.post(f"{API}/auth/signup", json=payload)


class TestSignupTerms:

    @pytest.mark.parametrize("extra", [{}, {"accept_terms": False}])
    def test_rejected_without_acceptance(self, client, db_session, extra):
        r = _signup(client, "noterms@acme-co.com", **extra)
        assert r.status_code == 400
        assert r.json()["detail"] == "You must accept the Terms of Service and Privacy Policy"
        assert db_session.query(User).filter(User.email == "noterms@acme-co.com").first() is None

    def test_acceptance_recorded(self, client, db_session, monkeypatch):
        monkeypatch.setattr(settings, "TERMS_VERSION", "2026-10-12")
        r = _signup(client, "terms@acme-co.com", accept_terms=True)
        assert r.status_code == 201, r.text
        user = db_session.query(User).filter(User.email == "terms@acme-co.com").first()
        assert user.terms_accepted_at is not None
        assert user.terms_version == "2026-10-12"
