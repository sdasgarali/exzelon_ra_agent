"""Monthly send quota — the second meter.

Credits (`credit_metering`) bill work with real external COGS. Sends are metered
separately and are *not* credits, because a send's marginal cost is ~$0: tenants
connect their own mailboxes. Charging credits for sends would make people ration the
one action the product exists to perform.

Counted from `OutreachEvent` rather than an incrementing counter, because all five
send paths (campaign engine, email preview, and three in the outreach pipeline)
already converge on that table. A counter would need incrementing at each of those
sites, and the one someone forgets to update becomes free sends that nobody notices.
"""
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.plans import get_plan, normalize_plan
from app.db.models.outreach import OutreachEvent, OutreachStatus

logger = structlog.get_logger()

#: Statuses representing a message we actually handed to a mail server. A BOUNCE still
#: counts — we sent it, the far end rejected it — and a REPLIED event was a send that
#: got an answer. SKIPPED never left the building, so it is not billed.
#:
#: Note `OutreachChannel` is the transport (mailmerge/smtp/m365/gmail/api), not a
#: message type, so there is no channel filter here: every OutreachEvent is an email.
BILLABLE_SEND_STATUSES = (
    OutreachStatus.SENT,
    OutreachStatus.REPLIED,
    OutreachStatus.BOUNCED,
)


def _month_start() -> datetime:
    return datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def sends_this_month(db: Session, tenant_id: int) -> int:
    """Emails this tenant has sent in the current calendar month.

    Warmup traffic never reaches this count: the warmup engine has its own tables and
    only reads `OutreachEvent` for open/click tracking. That is the right outcome —
    warmup is peer-to-peer between the tenant's own mailboxes, costs nothing, and
    billing it would punish tenants for following our own deliverability advice.
    """
    return int(
        db.query(func.count(OutreachEvent.event_id))
        .filter(
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.sent_at >= _month_start(),
            OutreachEvent.status.in_(BILLABLE_SEND_STATUSES),
        )
        .scalar()
        or 0
    )


def send_quota_for_tenant(tenant) -> int:
    """The tenant's monthly send allowance.

    Custom contracts carry their own figure on the tenant row, floored at Max's.
    """
    plan = normalize_plan(getattr(tenant, "plan", None))
    spec = get_plan(plan)
    if plan == "custom":
        row_value = getattr(tenant, "send_quota_per_month", None)
        return max(int(row_value or 0), spec.send_quota_per_month)
    return spec.send_quota_per_month


def quota_status(db: Session, tenant_id: Optional[int]) -> dict:
    """Used / limit / remaining for the current month."""
    if tenant_id is None:
        return {"metered": False}

    from app.db.models.tenant import Tenant
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    limit = send_quota_for_tenant(tenant)
    used = sends_this_month(db, tenant_id)
    return {
        "metered": True,
        "month": _month_start().strftime("%Y-%m"),
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "exhausted": used >= limit,
    }


def has_send_quota(db: Session, tenant_id: Optional[int]) -> tuple[bool, dict]:
    """(allowed, status). Super admins are not metered."""
    if tenant_id is None:
        return True, {"metered": False}
    status = quota_status(db, tenant_id)
    return (not status["exhausted"]), status
