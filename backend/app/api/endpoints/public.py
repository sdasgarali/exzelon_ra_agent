"""Public, unauthenticated site details (Plan_Launch_Readiness_6.md).

`GET /public/site-info` feeds the marketing/legal pages, the footer and the
billing buttons from backend config so none of them hardcode a support address,
legal entity or "payments are live" assumption. Nothing tenant-specific or secret
is returned — only values that are printed on public pages anyway.
"""
from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.core.rate_limiter import limiter

router = APIRouter(prefix="/public", tags=["Public"])

# Browsers/CDNs may reuse the answer for 5 minutes; the values change only on deploy.
_CACHE_SECONDS = 300


def payments_enabled() -> bool:
    """True only when a paid upgrade would actually succeed.

    Mirrors the checks `POST /billing/subscription/checkout` makes for the Pro
    monthly plan: billing switched on, a Stripe secret key, and a Pro price id.
    """
    if not settings.BILLING_ENABLED:
        return False
    if not (settings.STRIPE_SECRET_KEY or "").strip():
        return False
    from app.services.billing.subscription_service import price_id_for_plan
    return bool((price_id_for_plan("pro", annual=False) or "").strip())


def build_site_info() -> dict:
    support = (settings.SUPPORT_EMAIL or "").strip()
    return {
        "support_email": support,
        "privacy_email": (settings.PRIVACY_EMAIL or "").strip() or support,
        "legal_entity_name": (settings.LEGAL_ENTITY_NAME or "").strip(),
        "legal_address": (settings.LEGAL_ADDRESS or "").strip(),
        "legal_jurisdiction": (settings.LEGAL_JURISDICTION or "").strip(),
        "terms_version": (settings.TERMS_VERSION or "").strip(),
        "payments_enabled": payments_enabled(),
    }


@router.get("/site-info")
@limiter.limit("120/minute")
def site_info(request: Request, response: Response) -> dict:
    """Support/legal contact details and whether online payments are available."""
    response.headers["Cache-Control"] = f"public, max-age={_CACHE_SECONDS}"
    return build_site_info()
