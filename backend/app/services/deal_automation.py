"""Deal pipeline automation — signal-driven deal creation, stage progression, and activity logging.

Automates the CRM pipeline based on signals from campaigns, inbox, outreach, and lead scoring.
All automations are toggleable via settings and never override explicit manual actions.
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import structlog

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.deal import Deal, DealStage, DealActivity
from app.db.models.contact import ContactDetails
from app.db.models.client import ClientInfo
from app.db.models.settings import Settings

logger = structlog.get_logger()

# Stage name constants (match seeded stages in main.py)
STAGE_NEW_LEAD = "New Lead"
STAGE_CONTACTED = "Contacted"
STAGE_QUALIFIED = "Qualified"


def _get_deal_setting(db: Session, key: str, default: Any = None) -> Any:
    """Read a deal automation setting from the settings table."""
    setting = db.query(Settings).filter(Settings.key == key).first()
    if not setting:
        return default
    val = setting.value_json
    if isinstance(val, str):
        if val.lower() in ("true", "1", "yes"):
            return True
        if val.lower() in ("false", "0", "no"):
            return False
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return val


def _get_stage_by_name(db: Session, name: str) -> Optional[DealStage]:
    """Get a stage by its name (case-insensitive)."""
    return db.query(DealStage).filter(
        func.lower(DealStage.name) == name.lower(),
        DealStage.is_archived == False,
    ).first()


def _get_next_stage(db: Session, current_order: int) -> Optional[DealStage]:
    """Get the next stage in order after the current one (skipping won/lost)."""
    return db.query(DealStage).filter(
        DealStage.stage_order > current_order,
        DealStage.is_won == False,
        DealStage.is_lost == False,
        DealStage.is_archived == False,
    ).order_by(DealStage.stage_order.asc()).first()


# ─── 1. Auto-create deal from interested reply ─────────────────────

def auto_create_deal_from_interested_reply(
    contact_id: int,
    db: Session,
    campaign_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Create a deal automatically when an inbox reply is classified as 'interested'.

    - Checks deal_auto_create_on_interested setting
    - Avoids duplicates: skips if an open deal already exists for this contact
    - Auto-populates name, contact, client, campaign from contact data
    - Sets probability from lead score if available
    """
    if not _get_deal_setting(db, "deal_auto_create_on_interested", True):
        return None

    # Check for existing open deal for this contact
    existing = db.query(Deal).filter(
        Deal.contact_id == contact_id,
        Deal.is_archived == False,
    ).first()
    if existing:
        # Already has a deal — don't create duplicate, but log activity
        logger.info("Deal already exists for contact, skipping auto-create",
                     contact_id=contact_id, deal_id=existing.deal_id)
        return {"deal_id": existing.deal_id, "action": "existing", "name": existing.name}

    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == contact_id
    ).first()
    if not contact:
        return None

    # Build deal name
    contact_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "Unknown"
    company = contact.client_name or "Unknown Company"
    deal_name = f"{contact_name} — {company}"

    # Get "New Lead" stage
    stage = _get_stage_by_name(db, STAGE_NEW_LEAD)
    if not stage:
        logger.warning("Cannot auto-create deal: 'New Lead' stage not found")
        return None

    # Determine probability from lead score
    probability = 20  # default
    if hasattr(contact, "lead_score") and contact.lead_score:
        probability = _score_to_probability(contact.lead_score)

    # Find client_id from contact
    client_id = None
    if contact.client_name:
        client = db.query(ClientInfo).filter(
            func.lower(ClientInfo.client_name) == contact.client_name.lower()
        ).first()
        if client:
            client_id = client.client_id

    # Derive tenant_id from contact
    _contact = db.query(ContactDetails).filter(ContactDetails.contact_id == contact_id).first()
    _deal_tenant_id = getattr(_contact, 'tenant_id', None) or 1 if _contact else 1

    deal = Deal(
        tenant_id=_deal_tenant_id,
        name=deal_name,
        stage_id=stage.stage_id,
        contact_id=contact_id,
        client_id=client_id,
        campaign_id=campaign_id,
        value=0,
        probability=probability,
        is_auto_created=True,
        probability_manual=False,
    )
    db.add(deal)
    db.flush()

    # Log creation activity
    db.add(DealActivity(
        deal_id=deal.deal_id,
        activity_type="auto_created",
        description=f"Auto-created from interested reply by {contact_name}",
    ))

    logger.info("Auto-created deal from interested reply",
                 deal_id=deal.deal_id, contact_id=contact_id, name=deal_name)

    return {"deal_id": deal.deal_id, "action": "created", "name": deal_name}


# ─── 2. Auto-log email activity on deals ───────────────────────────

def auto_log_email_activity(
    contact_id: int,
    event_type: str,
    db: Session,
    details: Optional[Dict[str, Any]] = None,
) -> int:
    """Log email events (sent/received/opened/bounced) as deal activities.

    Finds all open deals linked to this contact and adds an activity entry.
    Returns the number of deals that got activity logged.
    """
    if not _get_deal_setting(db, "deal_auto_log_activities", True):
        return 0

    deals = db.query(Deal).filter(
        Deal.contact_id == contact_id,
        Deal.is_archived == False,
    ).all()

    if not deals:
        return 0

    logged = 0
    for deal in deals:
        # Don't log to Won/Lost deals
        stage = db.query(DealStage).filter(DealStage.stage_id == deal.stage_id).first()
        if stage and (stage.is_won or stage.is_lost):
            continue

        description = _build_activity_description(event_type, details)
        db.add(DealActivity(
            deal_id=deal.deal_id,
            activity_type=event_type,
            description=description,
            metadata_json=json.dumps(details) if details else None,
        ))
        logged += 1

    return logged


def _build_activity_description(event_type: str, details: Optional[Dict] = None) -> str:
    """Build a human-readable description for an email activity."""
    subject = (details or {}).get("subject", "")
    subject_part = f': "{subject}"' if subject else ""

    type_labels = {
        "email_sent": f"Email sent{subject_part}",
        "email_received": f"Reply received{subject_part}",
        "email_opened": "Email opened",
        "email_bounced": f"Email bounced{subject_part}",
        "email_clicked": "Link clicked",
    }
    return type_labels.get(event_type, f"Activity: {event_type}")


# ─── 3. Auto-advance stage ─────────────────────────────────────────

def auto_advance_stage(
    deal_id: int,
    signal: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """Advance a deal to the next stage based on a signal.

    Signals:
    - "email_sent" → New Lead → Contacted
    - "reply_received" → Contacted → Qualified

    Rules:
    - Only advances forward, never backwards
    - Respects deal_auto_advance_stages setting
    - Logs stage change as activity
    """
    if not _get_deal_setting(db, "deal_auto_advance_stages", True):
        return None

    deal = db.query(Deal).filter(
        Deal.deal_id == deal_id,
        Deal.is_archived == False,
    ).first()
    if not deal:
        return None

    current_stage = db.query(DealStage).filter(
        DealStage.stage_id == deal.stage_id
    ).first()
    if not current_stage:
        return None

    # Don't advance Won/Lost deals
    if current_stage.is_won or current_stage.is_lost:
        return None

    target_stage = None

    if signal == "email_sent":
        # Only advance from "New Lead" to "Contacted"
        if current_stage.name.lower() == STAGE_NEW_LEAD.lower():
            target_stage = _get_stage_by_name(db, STAGE_CONTACTED)

    elif signal == "reply_received":
        # Only advance from "New Lead" or "Contacted" to "Qualified"
        if current_stage.name.lower() in (STAGE_NEW_LEAD.lower(), STAGE_CONTACTED.lower()):
            target_stage = _get_stage_by_name(db, STAGE_QUALIFIED)

    if not target_stage or target_stage.stage_id == deal.stage_id:
        return None

    # Only advance forward
    if target_stage.stage_order <= current_stage.stage_order:
        return None

    old_name = current_stage.name
    deal.stage_id = target_stage.stage_id

    db.add(DealActivity(
        deal_id=deal.deal_id,
        activity_type="stage_change",
        description=f"Auto-advanced from {old_name} to {target_stage.name} (signal: {signal})",
    ))

    logger.info("Auto-advanced deal stage",
                 deal_id=deal.deal_id, from_stage=old_name,
                 to_stage=target_stage.name, signal=signal)

    return {"deal_id": deal.deal_id, "from": old_name, "to": target_stage.name}


# ─── 4. Update deal probability from lead score ────────────────────

def _score_to_probability(score: int) -> int:
    """Map lead score (0-100) to deal probability (%)."""
    if score >= 81:
        return 80
    if score >= 61:
        return 60
    if score >= 41:
        return 40
    if score >= 21:
        return 20
    return 10


def update_deal_probability_from_score(contact_id: int, db: Session) -> int:
    """Update deal probability based on contact's lead score.

    Only updates deals where probability_manual is False (user hasn't overridden).
    Returns number of deals updated.
    """
    if not _get_deal_setting(db, "deal_score_to_probability", True):
        return 0

    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == contact_id
    ).first()
    if not contact or not getattr(contact, "lead_score", None):
        return 0

    deals = db.query(Deal).filter(
        Deal.contact_id == contact_id,
        Deal.is_archived == False,
        Deal.probability_manual == False,
    ).all()

    new_prob = _score_to_probability(contact.lead_score)
    updated = 0
    for deal in deals:
        if deal.probability != new_prob:
            deal.probability = new_prob
            updated += 1

    return updated


# ─── 5. Detect stale deals ─────────────────────────────────────────

def detect_stale_deals(db: Session, days_threshold: Optional[int] = None, tenant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Find deals with no recent activity.

    Returns list of stale deals with deal info + days since last activity.
    Excludes Won/Lost stages.
    """
    if days_threshold is None:
        days_threshold = _get_deal_setting(db, "deal_stale_threshold_days", 7)

    cutoff = datetime.utcnow() - timedelta(days=days_threshold)

    # Get Won/Lost stage IDs to exclude
    terminal_query = db.query(DealStage.stage_id).filter(
        (DealStage.is_won == True) | (DealStage.is_lost == True)
    )
    if tenant_id is not None:
        terminal_query = terminal_query.filter(DealStage.tenant_id == tenant_id)
    terminal_stages = terminal_query.all()
    terminal_ids = [s[0] for s in terminal_stages]

    # Get all active deals not in terminal stages
    deals_query = db.query(Deal).filter(
        Deal.is_archived == False,
    )
    if tenant_id is not None:
        deals_query = deals_query.filter(Deal.tenant_id == tenant_id)
    if terminal_ids:
        deals_query = deals_query.filter(~Deal.stage_id.in_(terminal_ids))

    deals = deals_query.all()
    stale = []

    for deal in deals:
        # Get most recent activity
        latest = db.query(func.max(DealActivity.created_at)).filter(
            DealActivity.deal_id == deal.deal_id
        ).scalar()

        last_activity = latest or deal.created_at
        if last_activity and last_activity < cutoff:
            days_idle = (datetime.utcnow() - last_activity).days
            stale.append({
                "deal_id": deal.deal_id,
                "name": deal.name,
                "stage_id": deal.stage_id,
                "value": float(deal.value) if deal.value else 0,
                "days_idle": days_idle,
                "last_activity": last_activity.isoformat(),
            })

    stale.sort(key=lambda x: x["days_idle"], reverse=True)
    return stale


# ─── 6. Weighted pipeline forecast ─────────────────────────────────

def calculate_pipeline_forecast(db: Session, tenant_id: Optional[int] = None) -> Dict[str, Any]:
    """Calculate weighted pipeline value: sum of (value * probability / 100).

    Excludes Won/Lost deals.
    """
    terminal_query = db.query(DealStage.stage_id).filter(
        (DealStage.is_won == True) | (DealStage.is_lost == True)
    )
    if tenant_id is not None:
        terminal_query = terminal_query.filter(DealStage.tenant_id == tenant_id)
    terminal_stages = terminal_query.all()
    terminal_ids = [s[0] for s in terminal_stages]

    deals_query = db.query(Deal).filter(Deal.is_archived == False)
    if tenant_id is not None:
        deals_query = deals_query.filter(Deal.tenant_id == tenant_id)
    if terminal_ids:
        deals_query = deals_query.filter(~Deal.stage_id.in_(terminal_ids))

    deals = deals_query.all()

    weighted_value = sum(
        float(d.value or 0) * (d.probability or 0) / 100
        for d in deals
    )
    total_value = sum(float(d.value or 0) for d in deals)
    deal_count = len(deals)

    return {
        "weighted_value": round(weighted_value, 2),
        "total_pipeline_value": round(total_value, 2),
        "active_deals": deal_count,
    }
