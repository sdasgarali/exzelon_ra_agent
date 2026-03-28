"""Campaign sequence engine — processes multi-step email campaigns.

Called by the scheduler every 2 minutes to advance contacts through
their campaign sequences (email steps, wait steps, condition branches).
"""
import json
import random
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import structlog

from sqlalchemy.orm import Session

from app.db.models.campaign import (
    Campaign, SequenceStep, CampaignContact,
    CampaignStatus, StepType, CampaignContactStatus,
)
from app.db.models.contact import ContactDetails
from app.db.models.outreach import OutreachEvent, OutreachStatus, OutreachChannel
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.core.config import settings

logger = structlog.get_logger()

BATCH_SIZE = 50


def process_campaign_queue(db: Session) -> Dict[str, Any]:
    """Main scheduler entry point — process all due campaign contacts.

    Queries campaign_contacts WHERE next_send_at <= now() AND status = active
    AND the parent campaign is active AND within send window.
    """
    now = datetime.utcnow()
    results = {"processed": 0, "sent": 0, "skipped": 0, "errors": 0, "conditions_evaluated": 0}

    # Get active campaigns
    active_campaigns = db.query(Campaign).filter(
        Campaign.status == CampaignStatus.ACTIVE,
        Campaign.is_archived == False,
    ).all()

    if not active_campaigns:
        return results

    campaign_ids = [c.campaign_id for c in active_campaigns]

    # Check send window per campaign
    eligible_campaign_ids = []
    for campaign in active_campaigns:
        if _is_within_send_window(campaign, now):
            eligible_campaign_ids.append(campaign.campaign_id)

    if not eligible_campaign_ids:
        return results

    # Get due contacts in batches
    due_contacts = db.query(CampaignContact).filter(
        CampaignContact.campaign_id.in_(eligible_campaign_ids),
        CampaignContact.status == CampaignContactStatus.ACTIVE,
        CampaignContact.next_send_at <= now,
    ).limit(BATCH_SIZE).all()

    for cc in due_contacts:
        try:
            campaign = db.query(Campaign).filter(
                Campaign.campaign_id == cc.campaign_id
            ).first()
            if not campaign:
                continue

            # Get the step this contact is on
            step = db.query(SequenceStep).filter(
                SequenceStep.campaign_id == cc.campaign_id,
                SequenceStep.step_order == cc.current_step,
            ).first()

            if not step:
                # No more steps — mark completed
                cc.status = CampaignContactStatus.COMPLETED
                cc.completed_at = now
                cc.next_send_at = None
                results["processed"] += 1
                continue

            if step.step_type == StepType.EMAIL:
                success = _execute_email_step(cc, step, campaign, db)
                if success:
                    results["sent"] += 1
                else:
                    results["skipped"] += 1

            elif step.step_type == StepType.CONDITION:
                _evaluate_condition(cc, step, campaign, db)
                results["conditions_evaluated"] += 1

            elif step.step_type == StepType.WAIT:
                # Advance past wait step
                _advance_to_next_step(cc, step, campaign, db)

            results["processed"] += 1

        except Exception as e:
            logger.error("Error processing campaign contact",
                         cc_id=cc.id, error=str(e))
            results["errors"] += 1

    db.commit()

    # Recalculate stats for affected campaigns
    for cid in set(cc.campaign_id for cc in due_contacts):
        recalculate_campaign_stats(cid, db)

    return results


def _is_within_send_window(campaign: Campaign, now: datetime) -> bool:
    """Check if current UTC time falls within campaign's send window."""
    try:
        current_time = now.strftime("%H:%M")
        start = campaign.send_window_start or "09:00"
        end = campaign.send_window_end or "17:00"

        # Check day of week
        days_json = campaign.send_days_json or '["mon","tue","wed","thu","fri"]'
        send_days = json.loads(days_json)
        day_abbr = now.strftime("%a").lower()[:3]
        if day_abbr not in send_days:
            return False

        return start <= current_time <= end
    except Exception:
        return True  # default to allowing sends on parse errors


def _execute_email_step(
    cc: CampaignContact,
    step: SequenceStep,
    campaign: Campaign,
    db: Session,
) -> bool:
    """Send an email for this step to the contact. Returns True if sent."""
    from app.services.pipelines.outreach import (
        check_send_eligibility, send_outreach_email,
        render_signature_html, generate_unsub_footer,
    )
    from app.services.spintax import process_spintax

    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == cc.contact_id
    ).first()
    if not contact:
        cc.status = CampaignContactStatus.COMPLETED
        cc.next_send_at = None
        return False

    # Check eligibility (suppression, validation, etc.)
    eligible, reason = check_send_eligibility(db, contact)
    if not eligible:
        logger.info("Campaign contact not eligible", contact_id=cc.contact_id, reason=reason)
        # Don't remove from campaign — just skip this step and advance
        _advance_to_next_step(cc, step, campaign, db)
        return False

    # Select mailbox (health-aware scoring)
    mailbox = _select_mailbox(campaign, db)
    if not mailbox:
        logger.warning("No available mailbox for campaign", campaign_id=campaign.campaign_id)
        return False

    # Smart throttling: check hourly rate limit (daily_limit / 8 hours)
    max_hourly = max(mailbox.daily_send_limit // 8, 2)
    # Apply daily jitter: use 85-95% of actual limit
    effective_daily = int(mailbox.daily_send_limit * random.uniform(0.85, 0.95))
    if mailbox.emails_sent_today >= effective_daily:
        logger.info("Mailbox hit jittered daily limit", mailbox=mailbox.email,
                     sent=mailbox.emails_sent_today, effective=effective_daily)
        return False

    # Resolve A/B variant
    subject = step.subject or ""
    body_html = step.body_html or ""
    body_text = step.body_text or ""
    variant_index = None

    if step.variants_json:
        variant_index, subject, body_html, body_text = _select_variant(
            cc, step, db
        )

    # Apply spintax
    subject = process_spintax(subject, seed=cc.contact_id)
    body_html = process_spintax(body_html, seed=cc.contact_id)
    body_text = process_spintax(body_text, seed=cc.contact_id)

    # Render signature
    signature_html = ""
    if mailbox.email_signature_json:
        signature_html = render_signature_html(mailbox.email_signature_json)
    if signature_html and "{{signature}}" in body_html:
        body_html = body_html.replace("{{signature}}", signature_html)
    elif signature_html:
        body_html += signature_html

    # Placeholder substitution — Jinja2 with fallback to manual replace
    template_context = {
        "contact_first_name": contact.first_name or "",
        "contact_last_name": contact.last_name or "",
        "company_name": contact.client_name or "",
        "contact_title": contact.title or "",
        "contact": {
            "first_name": contact.first_name or "",
            "last_name": contact.last_name or "",
            "title": contact.title or "",
            "email": contact.email or "",
            "company": contact.client_name or "",
        },
        "sender": {
            "name": mailbox.display_name or "",
            "email": mailbox.email or "",
        },
    }
    try:
        from jinja2 import Template as Jinja2Template
        subject = Jinja2Template(subject).render(**template_context)
        body_html = Jinja2Template(body_html).render(**template_context)
        body_text = Jinja2Template(body_text).render(**template_context)
    except Exception:
        # Fallback to manual placeholder replacement
        placeholders = {
            "{{contact_first_name}}": contact.first_name or "",
            "{{contact_last_name}}": contact.last_name or "",
            "{{company_name}}": contact.client_name or "",
            "{{contact_title}}": contact.title or "",
        }
        for ph, val in placeholders.items():
            subject = subject.replace(ph, val)
            body_html = body_html.replace(ph, val)
            body_text = body_text.replace(ph, val)

    # Create outreach event
    event = OutreachEvent(
        tenant_id=campaign.tenant_id,
        contact_id=cc.contact_id,
        lead_id=cc.lead_id,
        sender_mailbox_id=mailbox.mailbox_id,
        channel=OutreachChannel.SMTP,
        status=OutreachStatus.SKIPPED,
        skip_reason="pending_send",
        campaign_id=campaign.campaign_id,
        step_id=step.step_id,
        variant_index=variant_index,
    )
    db.add(event)
    db.flush()

    # Add unsubscribe footer
    unsub_footer = generate_unsub_footer(event.tracking_id)
    if "unsub/" not in body_html:
        body_html += unsub_footer["html"]
        body_text += unsub_footer["text"]

    # Send
    result = send_outreach_email(
        sender_mailbox=mailbox,
        to_email=contact.email,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
    )

    if result["success"]:
        event.status = OutreachStatus.SENT
        event.skip_reason = None
        event.subject = subject
        event.body_html = body_html
        event.body_text = body_text
        event.message_id = result.get("message_id")

        # Update mailbox counters
        mailbox.emails_sent_today += 1
        mailbox.total_emails_sent += 1
        mailbox.last_sent_at = datetime.utcnow()

        # Update step stats
        step.total_sent += 1

        # Update campaign stats
        campaign.total_sent += 1

        # Update contact last outreach
        contact.last_outreach_date = datetime.utcnow().isoformat()

        # Deal automation: log email sent + auto-advance stage
        try:
            from app.services.deal_automation import auto_log_email_activity, auto_advance_stage
            from app.db.models.deal import Deal
            auto_log_email_activity(
                contact_id=cc.contact_id,
                event_type="email_sent",
                db=db,
                details={"subject": subject, "campaign": campaign.name},
            )
            contact_deals = db.query(Deal).filter(
                Deal.contact_id == cc.contact_id,
                Deal.is_archived == False,
            ).all()
            for deal in contact_deals:
                auto_advance_stage(deal.deal_id, "email_sent", db)
        except Exception as e_deal:
            logger.warning("Deal automation failed after campaign send",
                           contact_id=cc.contact_id, error=str(e_deal))

        # Advance to next step
        _advance_to_next_step(cc, step, campaign, db)

        # Smart throttling: random delay between sends (45-180 seconds)
        delay_sec = random.randint(45, 180)
        time.sleep(delay_sec)

        return True
    else:
        event.status = OutreachStatus.SKIPPED
        event.skip_reason = result.get("error", "Send failed")
        event.subject = subject
        logger.error("Campaign email send failed",
                     contact_id=cc.contact_id, error=result.get("error"))
        return False


def _select_mailbox(campaign: Campaign, db: Session) -> Optional[SenderMailbox]:
    """Select the best mailbox using health-aware scoring.

    Uses weighted scoring: health*0.4 + quota*0.3 + warmup_age*0.15 + deliverability*0.15.
    Falls back to least-loaded if scorer unavailable.
    """
    mailbox_ids = []
    if campaign.mailbox_ids_json:
        try:
            mailbox_ids = json.loads(campaign.mailbox_ids_json)
        except (json.JSONDecodeError, TypeError):
            pass

    try:
        from app.services.mailbox_selector import select_best_mailbox
        return select_best_mailbox(mailbox_ids, db)
    except Exception as e:
        logger.warning("Health-aware selector failed, using fallback", error=str(e))
        # Fallback to simple least-loaded
        query = db.query(SenderMailbox).filter(
            SenderMailbox.is_active == True,
            SenderMailbox.warmup_status.in_([WarmupStatus.COLD_READY, WarmupStatus.ACTIVE]),
            SenderMailbox.emails_sent_today < SenderMailbox.daily_send_limit,
            SenderMailbox.connection_status == "successful",
        )
        if mailbox_ids:
            query = query.filter(SenderMailbox.mailbox_id.in_(mailbox_ids))
        return query.order_by(SenderMailbox.emails_sent_today.asc()).first()


def _select_variant(
    cc: CampaignContact,
    step: SequenceStep,
    db: Session,
) -> tuple[int, str, str, str]:
    """Select A/B variant for this contact+step. Returns (index, subject, body_html, body_text)."""
    import random as stdlib_random

    try:
        variants = json.loads(step.variants_json)
    except (json.JSONDecodeError, TypeError):
        return (None, step.subject or "", step.body_html or "", step.body_text or "")

    if not variants:
        return (None, step.subject or "", step.body_html or "", step.body_text or "")

    # Check if contact already has an assignment for this step
    assignments = {}
    if cc.variant_assignments_json:
        try:
            assignments = json.loads(cc.variant_assignments_json)
        except (json.JSONDecodeError, TypeError):
            pass

    step_key = str(step.step_id)
    if step_key in assignments:
        idx = assignments[step_key]
        if 0 <= idx < len(variants):
            v = variants[idx]
            return (idx, v.get("subject", ""), v.get("body_html", ""), v.get("body_text", ""))

    # Weighted random assignment
    weights = [v.get("weight", 1) for v in variants]
    total = sum(weights)
    if total == 0:
        total = len(variants)
        weights = [1] * len(variants)

    rng = stdlib_random.Random(cc.contact_id + step.step_id)
    idx = rng.choices(range(len(variants)), weights=weights, k=1)[0]

    # Store assignment
    assignments[step_key] = idx
    cc.variant_assignments_json = json.dumps(assignments)

    v = variants[idx]
    return (idx, v.get("subject", ""), v.get("body_html", ""), v.get("body_text", ""))


def _advance_to_next_step(
    cc: CampaignContact,
    current_step: SequenceStep,
    campaign: Campaign,
    db: Session,
    jump_to_order: Optional[int] = None,
):
    """Advance a contact to the next step in the sequence."""
    if jump_to_order is not None:
        target_order = jump_to_order
    else:
        target_order = current_step.step_order + 1

    next_step = db.query(SequenceStep).filter(
        SequenceStep.campaign_id == campaign.campaign_id,
        SequenceStep.step_order == target_order,
    ).first()

    if not next_step:
        # Campaign complete for this contact
        cc.status = CampaignContactStatus.COMPLETED
        cc.completed_at = datetime.utcnow()
        cc.next_send_at = None
        return

    cc.current_step = target_order
    cc.next_send_at = datetime.utcnow() + timedelta(
        days=next_step.delay_days,
        hours=next_step.delay_hours,
    )


def _evaluate_condition(
    cc: CampaignContact,
    step: SequenceStep,
    campaign: Campaign,
    db: Session,
):
    """Evaluate a condition step and branch accordingly."""
    condition_type = step.condition_type  # opened/clicked/replied/no_action
    window_hours = step.condition_window_hours or 24

    # Look at the most recent email sent to this contact in this campaign
    # (the step before this condition)
    prev_event = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == campaign.campaign_id,
        OutreachEvent.contact_id == cc.contact_id,
        OutreachEvent.status == OutreachStatus.SENT,
    ).order_by(OutreachEvent.sent_at.desc()).first()

    condition_met = False

    if prev_event and condition_type:
        window_start = prev_event.sent_at
        window_end = window_start + timedelta(hours=window_hours)
        now = datetime.utcnow()

        if condition_type == "replied":
            condition_met = prev_event.reply_detected_at is not None
        elif condition_type == "opened":
            # Check tracking — opens are recorded separately
            from app.db.models.warmup_email import WarmupEmail
            # For outreach, opens are tracked via tracking pixel
            # We check if reply_detected_at or any open event exists
            condition_met = prev_event.reply_detected_at is not None
        elif condition_type == "no_action":
            # True if no reply within window and window has passed
            condition_met = (
                prev_event.reply_detected_at is None and
                now > window_end
            )

    if condition_met:
        target = step.yes_next_step
    else:
        target = step.no_next_step

    if target is not None:
        _advance_to_next_step(cc, step, campaign, db, jump_to_order=target)
    else:
        # No branch defined — advance sequentially
        _advance_to_next_step(cc, step, campaign, db)


def enroll_contacts(
    campaign_id: int,
    contact_ids: List[int],
    db: Session,
) -> Dict[str, Any]:
    """Enroll contacts into a campaign. Deduplicates against existing enrollments."""
    campaign = db.query(Campaign).filter(
        Campaign.campaign_id == campaign_id
    ).first()
    if not campaign:
        return {"error": "Campaign not found", "enrolled": 0, "duplicates": 0}

    # Get first step
    first_step = db.query(SequenceStep).filter(
        SequenceStep.campaign_id == campaign_id,
    ).order_by(SequenceStep.step_order.asc()).first()

    delay = timedelta(days=0)
    if first_step:
        delay = timedelta(days=first_step.delay_days, hours=first_step.delay_hours)

    # Check existing enrollments
    existing = set(
        row[0] for row in db.query(CampaignContact.contact_id).filter(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.contact_id.in_(contact_ids),
        ).all()
    )

    # Check suppression list
    from app.db.models.suppression import SuppressionList
    suppressed_emails = set(
        row[0] for row in db.query(SuppressionList.email).all()
    )
    contacts = db.query(ContactDetails).filter(
        ContactDetails.contact_id.in_(contact_ids)
    ).all()
    suppressed_ids = {c.contact_id for c in contacts if c.email and c.email.lower() in suppressed_emails}

    enrolled = 0
    duplicates = len(existing)
    suppressed = 0

    now = datetime.utcnow()
    for cid in contact_ids:
        if cid in existing:
            continue
        if cid in suppressed_ids:
            suppressed += 1
            continue

        # Find lead_id for this contact
        contact = db.query(ContactDetails).filter(
            ContactDetails.contact_id == cid
        ).first()

        cc = CampaignContact(
            campaign_id=campaign_id,
            contact_id=cid,
            lead_id=contact.lead_id if contact else None,
            status=CampaignContactStatus.ACTIVE,
            current_step=first_step.step_order if first_step else 0,
            next_send_at=now + delay if campaign.status == CampaignStatus.ACTIVE else None,
            enrolled_at=now,
        )
        db.add(cc)
        enrolled += 1

    # Update campaign contact count
    campaign.total_contacts = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id
    ).count() + enrolled

    db.commit()

    return {"enrolled": enrolled, "duplicates": duplicates, "suppressed": suppressed}


def handle_campaign_reply(event_id: int, db: Session):
    """Called when a reply is detected on a campaign outreach event."""
    event = db.query(OutreachEvent).filter(
        OutreachEvent.event_id == event_id
    ).first()
    if not event or not event.campaign_id:
        return

    cc = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == event.campaign_id,
        CampaignContact.contact_id == event.contact_id,
    ).first()
    if cc and cc.status == CampaignContactStatus.ACTIVE:
        cc.status = CampaignContactStatus.REPLIED
        cc.next_send_at = None
        cc.completed_at = datetime.utcnow()

        # Update campaign stats
        campaign = db.query(Campaign).filter(
            Campaign.campaign_id == event.campaign_id
        ).first()
        if campaign:
            campaign.total_replied += 1

        db.commit()


def handle_campaign_bounce(event_id: int, db: Session):
    """Called when a bounce is detected on a campaign outreach event."""
    event = db.query(OutreachEvent).filter(
        OutreachEvent.event_id == event_id
    ).first()
    if not event or not event.campaign_id:
        return

    cc = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == event.campaign_id,
        CampaignContact.contact_id == event.contact_id,
    ).first()
    if cc and cc.status == CampaignContactStatus.ACTIVE:
        cc.status = CampaignContactStatus.BOUNCED
        cc.next_send_at = None

        campaign = db.query(Campaign).filter(
            Campaign.campaign_id == event.campaign_id
        ).first()
        if campaign:
            campaign.total_bounced += 1

        db.commit()


def recalculate_campaign_stats(campaign_id: int, db: Session):
    """Recalculate denormalized stats on the campaign from actual data."""
    campaign = db.query(Campaign).filter(
        Campaign.campaign_id == campaign_id
    ).first()
    if not campaign:
        return

    campaign.total_contacts = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id
    ).count()

    campaign.total_sent = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == campaign_id,
        OutreachEvent.status == OutreachStatus.SENT,
    ).count()

    campaign.total_replied = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.status == CampaignContactStatus.REPLIED,
    ).count()

    campaign.total_bounced = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.status == CampaignContactStatus.BOUNCED,
    ).count()

    db.commit()
