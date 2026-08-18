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
        # Respect each rep's global in-app master toggle.
        inapp_reps = [r for r in reps if getattr(r, "notify_inapp_enabled", True)]
        for rep in inapp_reps:
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

        # Best-effort email fan-out (separately mutable). Honor each rep's email toggle.
        if _get_deal_setting(db, "deal_notify_reps_email", True):
            email_reps = [r for r in reps if getattr(r, "notify_email_enabled", True)]
            _email_reps(db, tid, email_reps, deal)

        logger.info("Forwarded new deal to reps", deal_id=deal.deal_id, tenant_id=tid, reps=len(reps))
        return len(reps)
    except Exception as e:
        logger.warning("forward_new_deal_to_reps failed", error=str(e))
        return 0


def notify_deal_assigned(db: Session, deal: Deal, assignee, actor, tenant_id: Optional[int]) -> bool:
    """Notify a user (in-app + email) that a deal was assigned to them.

    Honors the assignee's global notification master toggles:
    ``notify_inapp_enabled`` gates the bell notification and ``notify_email_enabled``
    the email. Best-effort — never raises to the caller. Returns True if any channel fired.
    """
    try:
        tid = tenant_id or getattr(deal, "tenant_id", None)
        if not assignee or not tid:
            return False
        actor_name = (getattr(actor, "full_name", None) or getattr(actor, "email", None)) if actor else "an admin"
        title = "A deal was assigned to you"
        message = f'"{deal.name}" was assigned to you by {actor_name}.'
        link = f"/dashboard/deals?deal_id={deal.deal_id}"
        fired = False

        if getattr(assignee, "notify_inapp_enabled", True):
            db.add(NotificationEntry(
                tenant_id=tid,
                user_id=assignee.user_id,
                title=title,
                message=message,
                category="deal",
                priority="high",
                link=link,
            ))
            db.flush()
            fired = True

        if getattr(assignee, "notify_email_enabled", True):
            _email_assignee(db, tid, assignee, deal, actor_name, link)
            fired = True

        logger.info("Notified assignee of deal", deal_id=deal.deal_id, tenant_id=tid,
                    assignee_id=assignee.user_id, fired=fired)
        return fired
    except Exception as e:
        logger.warning("notify_deal_assigned failed", error=str(e))
        return False


def _email_assignee(db, tenant_id, assignee, deal: Deal, actor_name: str, link_path: str) -> None:
    try:
        if not getattr(assignee, "email", None):
            return
        from app.services.system_mailer import send_system_email
        from app.core.config import settings
        base = settings.EFFECTIVE_BASE_URL
        frontend = "https://ra.partnerwithus.tech" if "ra.partnerwithus.tech" in base \
            else base.replace("/api/v1", "").replace(":8000", ":3000")
        link = f"{frontend}{link_path}"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
          <h2 style="color:#2563eb;">A deal was assigned to you</h2>
          <p><b>{actor_name}</b> assigned a deal to you:</p>
          <p style="font-size:16px;"><b>{deal.name}</b></p>
          <div style="text-align:center; margin:24px 0;">
            <a href="{link}" style="background:#2563eb;color:#fff;padding:12px 28px;border-radius:8px;
               text-decoration:none;font-weight:bold;display:inline-block;">View deal</a>
          </div>
          <p style="color:#666;font-size:13px;">You're receiving this because the deal was assigned to you.
             You can turn these emails off in your profile's notification settings.</p>
        </div>"""
        send_system_email(db, tenant_id, assignee.email, "A deal was assigned to you — NeuraLeads", html)
    except Exception as e:
        logger.warning("Deal assignment email failed", error=str(e))


def _email_reps(db, tenant_id, reps: list, deal: Deal) -> None:
    try:
        from app.services.system_mailer import send_system_email
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
                send_system_email(db, tenant_id, rep.email, "New lead to claim — NeuraLeads", html)
    except Exception as e:
        logger.warning("Deal email fan-out failed", error=str(e))
