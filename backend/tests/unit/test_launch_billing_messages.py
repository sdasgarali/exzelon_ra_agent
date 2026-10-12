"""U2: when Stripe isn't configured, billing endpoints return a user-safe 503.

The developer detail (which STRIPE_* key is missing) must stay in the server log and
never reach the browser — customers were seeing "Set STRIPE_PRICE_* first".
"""
import pytest

from app.api.endpoints import billing as billing_endpoints

pytestmark = pytest.mark.unit

SAFE = billing_endpoints.PAYMENTS_UNAVAILABLE_MESSAGE


def _hdr(sa_headers, tenant):
    return {**sa_headers, "X-Tenant-ID": str(tenant.tenant_id)}


def _assert_user_safe(r):
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail == SAFE
    assert "STRIPE" not in detail and "Set " not in detail
    assert "Request upgrade" in detail


def test_checkout_without_price_is_user_safe(client, sa_headers, test_tenant, monkeypatch):
    from app.core.config import settings
    for key in ("STRIPE_PRICE_PRO", "STRIPE_PRICE_MAX", "STRIPE_PRICE_PRO_ANNUAL", "STRIPE_PRICE_MAX_ANNUAL"):
        monkeypatch.setattr(settings, key, "", raising=False)
    r = client.post("/api/v1/billing/subscription/checkout", json={"plan": "pro"},
                    headers=_hdr(sa_headers, test_tenant))
    _assert_user_safe(r)


def test_checkout_without_secret_key_is_user_safe(client, sa_headers, test_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO", "price_pro", raising=False)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "", raising=False)
    r = client.post("/api/v1/billing/subscription/checkout", json={"plan": "pro"},
                    headers=_hdr(sa_headers, test_tenant))
    _assert_user_safe(r)


def test_topup_without_price_is_user_safe(client, sa_headers, test_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_PRICE_CREDIT_TOPUP", "", raising=False)
    r = client.post("/api/v1/billing/credits/topup", json={"blocks": 1},
                    headers=_hdr(sa_headers, test_tenant))
    _assert_user_safe(r)


def test_topup_without_secret_key_is_user_safe(client, sa_headers, test_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_PRICE_CREDIT_TOPUP", "price_topup", raising=False)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "", raising=False)
    r = client.post("/api/v1/billing/credits/topup", json={"blocks": 1},
                    headers=_hdr(sa_headers, test_tenant))
    _assert_user_safe(r)


def test_developer_detail_is_logged_not_returned(monkeypatch):
    seen = {}

    def fake_warning(event, **kw):
        seen["event"] = event
        seen.update(kw)

    monkeypatch.setattr(billing_endpoints.logger, "warning", fake_warning)
    exc = billing_endpoints._payments_unavailable("Set STRIPE_PRICE_CREDIT_TOPUP.", tenant_id=7)
    assert exc.status_code == 503
    assert exc.detail == SAFE
    assert seen["event"] == "stripe_not_configured"
    assert seen["detail"] == "Set STRIPE_PRICE_CREDIT_TOPUP."
    assert seen["tenant_id"] == 7
