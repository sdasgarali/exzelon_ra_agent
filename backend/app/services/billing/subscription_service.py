"""Subscription business logic — plan<->Stripe-price mapping and webhook sync (ELR-021)."""
from datetime import datetime
from typing import Optional
import structlog

from app.core.config import settings
from app.db.models.subscription import SubscriptionRecord, SubscriptionStatus

logger = structlog.get_logger()


def price_id_for_plan(plan: Optional[str]) -> str:
    """Configured Stripe price id for a plan ("" if unset)."""
    return {
        "starter": settings.STRIPE_PRICE_STARTER,
        "professional": settings.STRIPE_PRICE_PROFESSIONAL,
        "enterprise": settings.STRIPE_PRICE_ENTERPRISE,
    }.get((plan or "").lower(), "")


def plan_for_price_id(price_id: str) -> Optional[str]:
    """Reverse mapping: Stripe price id -> plan name."""
    for plan in ("starter", "professional", "enterprise"):
        if price_id and price_id == price_id_for_plan(plan):
            return plan
    return None


def _map_status(stripe_status: str) -> SubscriptionStatus:
    try:
        return SubscriptionStatus(stripe_status)
    except ValueError:
        return SubscriptionStatus.INCOMPLETE


def upsert_from_stripe(db, sub_obj: dict, tenant_id: int) -> SubscriptionRecord:
    """Create or update the tenant's SubscriptionRecord from a Stripe subscription
    object (webhook payload). Also syncs tenant.plan when the price maps to a plan."""
    stripe_sub_id = sub_obj.get("id")
    record = None
    if stripe_sub_id:
        record = db.query(SubscriptionRecord).filter(
            SubscriptionRecord.stripe_subscription_id == stripe_sub_id
        ).first()
    if record is None:
        record = db.query(SubscriptionRecord).filter(
            SubscriptionRecord.tenant_id == tenant_id
        ).first()
    if record is None:
        record = SubscriptionRecord(tenant_id=tenant_id)
        db.add(record)

    # Price id lives under items.data[0].price.id
    price_id = ""
    try:
        price_id = sub_obj["items"]["data"][0]["price"]["id"]
    except (KeyError, IndexError, TypeError):
        price_id = sub_obj.get("price_id", "")

    record.stripe_subscription_id = stripe_sub_id
    record.stripe_customer_id = sub_obj.get("customer")
    record.stripe_price_id = price_id or record.stripe_price_id
    record.status = _map_status(sub_obj.get("status", "incomplete"))
    record.cancel_at_period_end = bool(sub_obj.get("cancel_at_period_end", False))
    cpe = sub_obj.get("current_period_end")
    if cpe:
        record.current_period_end = datetime.utcfromtimestamp(int(cpe))

    plan = plan_for_price_id(price_id) if price_id else None
    if plan:
        record.plan = plan
        # Keep the tenant's plan tier in sync with the active subscription.
        from app.db.models.tenant import Tenant, TenantPlan
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if tenant is not None and record.status in (
            SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING,
        ):
            try:
                tenant.plan = TenantPlan(plan)
            except ValueError:
                pass

    logger.info("Subscription upserted", tenant_id=tenant_id,
                stripe_sub_id=stripe_sub_id, status=record.status.value)
    return record
