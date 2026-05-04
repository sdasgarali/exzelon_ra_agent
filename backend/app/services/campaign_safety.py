"""Campaign Safety Controls — idempotency, company caps, smart pause, reply detection.

Provides guardrails that protect sender reputation and prevent over-contacting.
These checks integrate into the campaign engine and outreach pipeline.
"""
import hashlib
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any

import structlog
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.db.models.campaign import (
    CampaignContact, CampaignContactStatus, Campaign,
)
from app.db.models.outreach import OutreachEvent, OutreachStatus
from app.db.models.outreach_draft import OutreachDraft, DraftStatus
from app.db.models.contact import ContactDetails
from app.db.models.inbox_message import InboxMessage, MessageDirection

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# 1. Job Idempotency Guard
# ---------------------------------------------------------------------------

_PROCESSING_KEYS: set[str] = set()


def get_idempotency_key(cc: CampaignContact) -> str:
    """Generate a unique key for a campaign-contact-step processing attempt."""
    return f"cc:{cc.id}:step:{cc.current_step}:date:{date.today().isoformat()}"


def check_already_processed(db: Session, cc: CampaignContact) -> bool:
    """Check if this contact's current step was already sent or drafted today.

    Prevents duplicate sends if the scheduler runs twice due to restart.
    Queries OutreachEvent for a SENT event AND OutreachDraft for a
    PENDING/APPROVED/SENT draft matching this campaign + contact + step.
    """
    today_start = datetime.combine(date.today(), datetime.min.time())

    existing = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == cc.campaign_id,
        OutreachEvent.contact_id == cc.contact_id,
        OutreachEvent.step_id is not None,
        OutreachEvent.status == OutreachStatus.SENT,
        OutreachEvent.sent_at >= today_start,
    ).first()

    if existing:
        logger.info(
            "idempotency_guard_blocked",
            cc_id=cc.id,
            campaign_id=cc.campaign_id,
            contact_id=cc.contact_id,
            existing_event=existing.event_id,
        )
        return True

    # Also check for existing drafts (preview mode dedup)
    existing_draft = db.query(OutreachDraft.draft_id).filter(
        OutreachDraft.campaign_id == cc.campaign_id,
        OutreachDraft.contact_id == cc.contact_id,
        OutreachDraft.step_id is not None,
        OutreachDraft.status.in_([
            DraftStatus.PENDING, DraftStatus.APPROVED, DraftStatus.SENT,
        ]),
    ).first()

    if existing_draft:
        logger.info(
            "idempotency_guard_blocked_draft",
            cc_id=cc.id,
            campaign_id=cc.campaign_id,
            contact_id=cc.contact_id,
            existing_draft=existing_draft.draft_id,
        )
        return True

    return False


# ---------------------------------------------------------------------------
# 2. Company-Level Contact Cap
# ---------------------------------------------------------------------------

def check_company_contact_cap(
    db: Session,
    contact: ContactDetails,
    tenant_id: int,
    max_per_company: int = 5,
) -> tuple[bool, str]:
    """Check if we've already contacted too many people at this company.

    Counts distinct contacts with SENT outreach events for the same
    client_name across ALL campaigns. Prevents over-targeting a single
    company which triggers spam complaints.

    Returns (allowed, reason).
    """
    if not contact.client_name:
        return True, ""

    company = contact.client_name.strip().lower()
    if not company or company in ("", "unknown", "n/a"):
        return True, ""

    # Count distinct contacts at this company who've received outreach
    contacted_count = (
        db.query(sa_func.count(sa_func.distinct(OutreachEvent.contact_id)))
        .join(ContactDetails, OutreachEvent.contact_id == ContactDetails.contact_id)
        .filter(
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.SENT,
            sa_func.lower(ContactDetails.client_name) == company,
        )
        .scalar()
    ) or 0

    if contacted_count >= max_per_company:
        logger.info(
            "company_cap_reached",
            company=contact.client_name,
            contacted=contacted_count,
            cap=max_per_company,
            contact_id=contact.contact_id,
        )
        return False, f"Company cap reached: {contacted_count}/{max_per_company} contacts at {contact.client_name}"

    return True, ""


# ---------------------------------------------------------------------------
# 3. Smart Pause on Reply
# ---------------------------------------------------------------------------

def check_reply_received(
    db: Session,
    contact_id: int,
    campaign_id: int,
) -> bool:
    """Check if this contact has replied to any email in this campaign.

    If a reply is detected, the contact's campaign sequence should be
    paused — sending more automated emails after a reply is the #1 way
    to trigger spam complaints and damage reputation.
    """
    reply = db.query(InboxMessage).filter(
        InboxMessage.contact_id == contact_id,
        InboxMessage.campaign_id == campaign_id,
        InboxMessage.direction == MessageDirection.RECEIVED,
    ).first()

    if reply:
        logger.info(
            "reply_detected_pause",
            contact_id=contact_id,
            campaign_id=campaign_id,
            reply_date=str(reply.received_at),
        )
        return True
    return False


def pause_contact_on_reply(
    db: Session,
    cc: CampaignContact,
) -> None:
    """Pause a campaign contact's sequence due to receiving a reply."""
    if cc.status == CampaignContactStatus.ACTIVE:
        cc.status = CampaignContactStatus.PAUSED
        cc.next_send_at = None
        logger.info(
            "contact_paused_on_reply",
            cc_id=cc.id,
            contact_id=cc.contact_id,
            campaign_id=cc.campaign_id,
        )


# ---------------------------------------------------------------------------
# 4. Sequence Fatigue Detection
# ---------------------------------------------------------------------------

def check_sequence_fatigue(
    db: Session,
    contact_id: int,
    tenant_id: int,
    max_unanswered: int = 5,
    lookback_days: int = 90,
) -> tuple[bool, str]:
    """Check if a contact has received too many unanswered emails.

    Counts SENT outreach events with no reply in the lookback period.
    If count >= max_unanswered, the contact is "fatigued" and should
    not receive more outreach.

    Returns (should_send, reason).
    """
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    sent_count = db.query(sa_func.count(OutreachEvent.event_id)).filter(
        OutreachEvent.contact_id == contact_id,
        OutreachEvent.tenant_id == tenant_id,
        OutreachEvent.status == OutreachStatus.SENT,
        OutreachEvent.sent_at >= cutoff,
    ).scalar() or 0

    if sent_count < max_unanswered:
        return True, ""

    # Check if there was any reply
    reply_count = db.query(sa_func.count(InboxMessage.message_id)).filter(
        InboxMessage.contact_id == contact_id,
        InboxMessage.tenant_id == tenant_id,
        InboxMessage.direction == MessageDirection.RECEIVED,
        InboxMessage.received_at >= cutoff,
    ).scalar() or 0

    if reply_count > 0:
        return True, ""

    logger.info(
        "sequence_fatigue_detected",
        contact_id=contact_id,
        sent_count=sent_count,
        max_unanswered=max_unanswered,
    )
    return False, f"Sequence fatigue: {sent_count} unanswered emails in {lookback_days} days"


# ---------------------------------------------------------------------------
# 5. Cross-Campaign Contact Dedup
# ---------------------------------------------------------------------------

def check_cross_campaign_conflict(
    db: Session,
    contact_id: int,
    campaign_id: int,
) -> tuple[bool, str]:
    """Check if a contact is actively enrolled in another campaign.

    Prevents sending from multiple campaigns simultaneously to the
    same contact, which looks spammy and confuses the recipient.

    Returns (allowed, reason).
    """
    active_in_other = db.query(CampaignContact).filter(
        CampaignContact.contact_id == contact_id,
        CampaignContact.campaign_id != campaign_id,
        CampaignContact.status == CampaignContactStatus.ACTIVE,
    ).first()

    if active_in_other:
        other_campaign = db.query(Campaign).filter(
            Campaign.campaign_id == active_in_other.campaign_id
        ).first()
        name = other_campaign.name if other_campaign else f"ID {active_in_other.campaign_id}"
        return False, f"Contact active in campaign: {name}"

    return True, ""
