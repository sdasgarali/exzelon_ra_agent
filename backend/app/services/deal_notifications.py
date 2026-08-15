"""Forward newly-created (unclaimed) deals to the tenant's BDMs and Recruiters.

When an interested reply auto-creates a deal, it enters the shared Unclaimed queue.
This module fans that out to every BDM/Recruiter in the tenant as (a) an in-app
notification and (b) a best-effort email, so reps know there's a lead to claim.
Gated by settings so email can be muted while keeping in-app notifications.
"""
from typing import Optional
import structlog

from sqlalchemy.orm import Session

from app.db.models.user import User
from app.db.models.deal import Deal
from app.db.models.notification import NotificationEntry
from app.api.deps.auth import effective_base_role
from app.services.deal_automation import _get_deal_setting

logger = structlog.get_logger()

REP_BASE_ROLES = ("bdm", "recruiter")
_DEALS_LINK = "/dashboard/deals?claimed_by=unclaimed"


def _tenant_reps(db: Session, tenant_id: int) -> list:
    """Active users in the tenant whose effective role is BDM or Recruiter."""
    users = db.query(User).filter(
        User.tenant_id == tenant_id,
        User.is_active == True,  # noqa: E712
    ).all()
    return [u for u in users if effective_base_role(u, None, db) in REP_BASE_ROLES]


def forward_new_deal_to_reps(db: Session, deal: Deal, tenant_id: Optional[int]) -> int:
    """Notify (in-app + email) every BDM/Recruiter of the tenant about a new unclaimed deal.

    Returns the number of reps notified. Best-effort — never raises to the caller.
    """
    try:
        if not _get_deal_setting(db, "deal_notify_reps_on_new", True):
            return 0
        tid = tenant_id or getattr(deal, "tenant_id", None)
        if not tid:
            return 0
        reps = _tenant_reps(db, tid)
        if not reps:
            return 0

        title = "New unclaimed lead to claim"
        message = f'"{deal.name}" is in the deal queue — claim it if you can work it.'
        for rep in reps:
            db.add(NotificationEntry(
                tenant_id=tid,
                user_id=rep.user_id,
                title=title,
                message=message,
                category="deal",
                priority="high",
                link=_DEALS_LINK,
            ))
        db.flush()

        # Best-effort email fan-out (separately mutable).
        if _get_deal_setting(db, "deal_notify_reps_email", True):
            _email_reps(reps, deal)

        logger.info("Forwarded new deal to reps", deal_id=deal.deal_id, tenant_id=tid, reps=len(reps))
        return len(reps)
    except Exception as e:
        logger.warning("forward_new_deal_to_reps failed", error=str(e))
        return 0


def _email_reps(reps: list, deal: Deal) -> None:
    try:
        from app.services.email_verification import _send_email
        from app.core.config import settings
        base = settings.EFFECTIVE_BASE_URL
        frontend = "https://ra.partnerwithus.tech" if "ra.partnerwithus.tech" in base \
            else base.replace("/api/v1", "").replace(":8000", ":3000")
        link = f"{frontend}{_DEALS_LINK}"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
          <h2 style="color:#2563eb;">New lead to claim</h2>
          <p>A new lead just entered the deal queue and is <b>Unclaimed</b>:</p>
          <p style="font-size:16px;"><b>{deal.name}</b></p>
          <div style="text-align:center; margin:24px 0;">
            <a href="{link}" style="background:#2563eb;color:#fff;padding:12px 28px;border-radius:8px;
               text-decoration:none;font-weight:bold;display:inline-block;">View &amp; Claim</a>
          </div>
          <p style="color:#666;font-size:13px;">You're receiving this because you're a BDM/Recruiter on this account.</p>
        </div>"""
        for rep in reps:
            if rep.email:
                _send_email(rep.email, "New lead to claim — NeuraLeads", html)
    except Exception as e:
        logger.warning("Deal email fan-out failed", error=str(e))
