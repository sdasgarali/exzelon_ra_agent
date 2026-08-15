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
    Campaign, CampaignSchedule, SequenceStep, CampaignContact,
    CampaignStatus, StepType, CampaignContactStatus,
)
from app.db.models.contact import ContactDetails
from app.db.models.lead import LeadDetails
from app.db.models.outreach import OutreachEvent, OutreachStatus, OutreachChannel
from app.db.models.outreach_draft import OutreachDraft, DraftStatus
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus

logger = structlog.get_logger()

BATCH_SIZE = 50


def process_campaign_queue(db: Session) -> Dict[str, Any]:
    """Main scheduler entry point — process all due campaign contacts.

    Queries campaign_contacts WHERE next_send_at <= now() AND status = active
    AND the parent campaign is active AND within send window.
    """
    now = datetime.utcnow()
    results = {"processed": 0, "sent": 0, "skipped": 0, "errors": 0, "conditions_evaluated": 0}

    # Auto-activate scheduled campaigns whose send time has arrived
    scheduled = db.query(Campaign).filter(
        Campaign.status == CampaignStatus.DRAFT,
        Campaign.scheduled_send_at.isnot(None),
        Campaign.scheduled_send_at <= now,
        Campaign.is_archived == False,
    ).all()
    for sc in scheduled:
        sc.status = CampaignStatus.ACTIVE
        sc.scheduled_send_at = None
        logger.info("campaign_auto_activated", campaign_id=sc.campaign_id, name=sc.name)
    if scheduled:
        db.commit()

    # Get active campaigns
    active_campaigns = db.query(Campaign).filter(
        Campaign.status == CampaignStatus.ACTIVE,
        Campaign.is_archived == False,
    ).all()

    if not active_campaigns:
        logger.info("campaign_processor_no_active_campaigns")
        return results

    # Filter out campaigns whose tenant has campaigns disabled
    from app.core.settings_resolver import get_tenant_setting_bool
    tenant_ids = set(c.tenant_id for c in active_campaigns)
    disabled_tenants = set()
    for tid in tenant_ids:
        if not get_tenant_setting_bool(db, "feature_campaigns_enabled", tenant_id=tid, default=True):
            disabled_tenants.add(tid)
    if disabled_tenants:
        skipped_count = sum(1 for c in active_campaigns if c.tenant_id in disabled_tenants)
        logger.info("Skipping campaigns for disabled tenants",
                     disabled_tenants=list(disabled_tenants), skipped_campaigns=skipped_count)
        active_campaigns = [c for c in active_campaigns if c.tenant_id not in disabled_tenants]
        if not active_campaigns:
            return results

    campaign_ids = [c.campaign_id for c in active_campaigns]

    # Pre-fetch all CampaignSchedule rows for active campaigns
    all_schedules = db.query(CampaignSchedule).filter(
        CampaignSchedule.campaign_id.in_(campaign_ids),
        CampaignSchedule.is_archived == False,
    ).order_by(CampaignSchedule.schedule_order).all()
    schedules_map: Dict[int, List[CampaignSchedule]] = {}
    for sched in all_schedules:
        schedules_map.setdefault(sched.campaign_id, []).append(sched)

    # Check send window per campaign
    eligible_campaign_ids = []
    for campaign in active_campaigns:
        if _is_within_send_window(campaign, now, schedules=schedules_map.get(campaign.campaign_id)):
            eligible_campaign_ids.append(campaign.campaign_id)

    if not eligible_campaign_ids:
        logger.info("campaign_processor_no_eligible_campaigns",
                     active_count=len(active_campaigns),
                     reason="outside_send_window")
        return results

    logger.info("campaign_processor_eligible",
                 eligible_count=len(eligible_campaign_ids),
                 campaign_ids=eligible_campaign_ids)

    # Get due contacts in batches
    due_contacts = db.query(CampaignContact).filter(
        CampaignContact.campaign_id.in_(eligible_campaign_ids),
        CampaignContact.status == CampaignContactStatus.ACTIVE,
        CampaignContact.next_send_at <= now,
    ).limit(BATCH_SIZE).all()

    if due_contacts:
        logger.info("campaign_processor_due_contacts",
                     count=len(due_contacts),
                     contact_steps=[(cc.id, cc.campaign_id, cc.current_step) for cc in due_contacts[:10]])
    else:
        logger.info("campaign_processor_no_due_contacts",
                     eligible_campaign_ids=eligible_campaign_ids)

    # Pre-fetch all campaigns for this batch (eliminates N+1 query per contact)
    batch_campaign_ids = list(set(cc.campaign_id for cc in due_contacts))
    campaigns_map = {}
    if batch_campaign_ids:
        batch_campaigns = db.query(Campaign).filter(
            Campaign.campaign_id.in_(batch_campaign_ids)
        ).all()
        campaigns_map = {c.campaign_id: c for c in batch_campaigns}

    # Pre-fetch all relevant steps (eliminates N+1 step query per contact)
    step_keys = list(set((cc.campaign_id, cc.current_step) for cc in due_contacts))
    steps_map = {}
    if step_keys and batch_campaign_ids:
        all_steps = db.query(SequenceStep).filter(
            SequenceStep.campaign_id.in_(batch_campaign_ids)
        ).all()
        for s in all_steps:
            steps_map[(s.campaign_id, s.step_order)] = s

    for cc in due_contacts:
        try:
            campaign = campaigns_map.get(cc.campaign_id)
            if not campaign:
                continue

            # --- Safety: idempotency guard (prevent duplicate sends on restart) ---
            try:
                from app.services.campaign_safety import check_already_processed
                if check_already_processed(db, cc):
                    results["skipped"] += 1
                    results["processed"] += 1
                    continue
            except Exception as e_idem:
                logger.warning("Idempotency check failed, proceeding", error=str(e_idem))

            # --- Safety: smart pause on reply ---
            try:
                from app.services.campaign_safety import check_reply_received, pause_contact_on_reply
                if check_reply_received(db, cc.contact_id, cc.campaign_id):
                    pause_contact_on_reply(db, cc)
                    results["skipped"] += 1
                    results["processed"] += 1
                    continue
            except Exception as e_reply:
                logger.warning("Reply check failed, proceeding", error=str(e_reply))

            # Per-contact timezone check: if contact has timezone, verify it's within send window
            try:
                contact_for_tz = db.query(ContactDetails).with_entities(
                    ContactDetails.timezone
                ).filter(ContactDetails.contact_id == cc.contact_id).first()
                if contact_for_tz and contact_for_tz.timezone:
                    if not _is_within_send_window(campaign, now, contact_timezone=contact_for_tz.timezone,
                                                  schedules=schedules_map.get(cc.campaign_id)):
                        results["skipped"] += 1
                        results["processed"] += 1
                        continue
            except Exception:
                pass  # Fall through to campaign-level window (already passed)

            # Get the step this contact is on (from pre-fetched map)
            step = steps_map.get((cc.campaign_id, cc.current_step))

            if not step:
                # No more steps — mark completed
                cc.status = CampaignContactStatus.COMPLETED
                cc.completed_at = now
                cc.next_send_at = None
                results["processed"] += 1
                continue

            if step.step_type == StepType.EMAIL:
                # Preview mode: generate draft instead of sending
                if getattr(campaign, 'preview_mode', False) and campaign.preview_mode:
                    # Dedup: skip if a non-expired draft already exists for this contact+step
                    existing_draft = db.query(OutreachDraft.draft_id).filter(
                        OutreachDraft.campaign_id == cc.campaign_id,
                        OutreachDraft.contact_id == cc.contact_id,
                        OutreachDraft.step_id == step.step_id,
                        OutreachDraft.status.in_([
                            DraftStatus.PENDING, DraftStatus.APPROVED, DraftStatus.SENT,
                        ]),
                    ).first()
                    if existing_draft:
                        logger.debug(
                            "preview_draft_dedup_skip",
                            cc_id=cc.id,
                            campaign_id=cc.campaign_id,
                            step_id=step.step_id,
                            existing_draft_id=existing_draft.draft_id,
                        )
                        # Advance to next step so contact progresses through sequence
                        _advance_to_next_step(cc, step, campaign, db)
                        results["processed"] += 1
                        continue
                    try:
                        from app.services.email_preview_service import generate_single_campaign_draft
                        generate_single_campaign_draft(cc, step, campaign, db)
                        # Advance to next step (same as normal mode)
                        _advance_to_next_step(cc, step, campaign, db)
                        results["processed"] += 1
                        continue
                    except Exception as e_preview:
                        logger.error("Preview draft generation failed", cc_id=cc.id, error=str(e_preview))

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

            elif step.step_type == StepType.SMS:
                # SMS step — send via Twilio if phone available
                try:
                    contact = db.query(ContactDetails).filter(
                        ContactDetails.contact_id == cc.contact_id
                    ).first()
                    if not contact or not contact.phone:
                        cc.skip_reason = "no_phone_number"
                        logger.info("sms_step_skipped", contact_id=cc.contact_id, reason="no_phone_number")
                    else:
                        sms_body = step.body_text or step.body_html or ""
                        # Apply spintax if present
                        from app.services.spintax import process_spintax
                        sms_body = process_spintax(sms_body, seed=cc.contact_id)
                        # Render placeholders
                        sms_body = sms_body.replace("{{first_name}}", contact.first_name or "")
                        sms_body = sms_body.replace("{{last_name}}", contact.last_name or "")
                        sms_body = sms_body.replace("{{company}}", contact.client_name or "")
                        try:
                            from app.services.adapters.communications.twilio_adapter import TwilioAdapter
                            adapter = TwilioAdapter()
                            adapter.send_sms(contact.phone, sms_body)
                            step.total_sent = (step.total_sent or 0) + 1
                            logger.info("sms_sent", contact_id=cc.contact_id, step_id=step.step_id)
                        except Exception as sms_err:
                            logger.warning("sms_send_failed", error=str(sms_err), contact_id=cc.contact_id)
                            cc.skip_reason = f"sms_failed: {str(sms_err)[:100]}"
                except Exception as e:
                    logger.warning("sms_step_error", error=str(e))
                _advance_to_next_step(cc, step, campaign, db)

            elif step.step_type == StepType.CALL:
                # Call step — initiate via Twilio if phone available
                try:
                    contact = db.query(ContactDetails).filter(
                        ContactDetails.contact_id == cc.contact_id
                    ).first()
                    if not contact or not contact.phone:
                        cc.skip_reason = "no_phone_number"
                        logger.info("call_step_skipped", contact_id=cc.contact_id, reason="no_phone_number")
                    else:
                        twiml_url = step.body_text or ""
                        try:
                            from app.services.adapters.communications.twilio_adapter import TwilioAdapter
                            adapter = TwilioAdapter()
                            adapter.initiate_call(contact.phone, twiml_url=twiml_url)
                            step.total_sent = (step.total_sent or 0) + 1
                            logger.info("call_initiated", contact_id=cc.contact_id, step_id=step.step_id)
                        except Exception as call_err:
                            logger.warning("call_initiate_failed", error=str(call_err), contact_id=cc.contact_id)
                            cc.skip_reason = f"call_failed: {str(call_err)[:100]}"
                except Exception as e:
                    logger.warning("call_step_error", error=str(e))
                _advance_to_next_step(cc, step, campaign, db)

            elif step.step_type == StepType.LINKEDIN:
                # LinkedIn step — placeholder, log skip
                cc.skip_reason = "linkedin_not_configured"
                logger.info("linkedin_step_skipped", contact_id=cc.contact_id, reason="linkedin_not_configured")
                _advance_to_next_step(cc, step, campaign, db)

            results["processed"] += 1

        except Exception as e:
            logger.error("Error processing campaign contact",
                         cc_id=cc.id, error=str(e))
            results["errors"] += 1

    db.commit()

    # Recalculate stats + health scores for affected campaigns
    for cid in set(cc.campaign_id for cc in due_contacts):
        recalculate_campaign_stats(cid, db)
        try:
            from app.services.campaign_health import calculate_campaign_health
            result = calculate_campaign_health(cid, db)
            if result.get("score") is not None:
                c = db.query(Campaign).filter(Campaign.campaign_id == cid).first()
                if c:
                    c.health_score = result["score"]
                    db.commit()
        except Exception as e:
            logger.warning("health_score_refresh_failed", campaign_id=cid, error=str(e))

    return results


def _is_within_send_window(
    campaign: Campaign,
    now: datetime,
    contact_timezone: Optional[str] = None,
    schedules: Optional[List[Any]] = None,
) -> bool:
    """Check if current time falls within send window.

    If schedule entries are provided, checks each entry whose date range covers today.
    Returns True if ANY schedule matches. Falls back to legacy campaign columns
    when no schedule entries exist.

    Uses contact's timezone if available, otherwise falls back to schedule/campaign timezone.
    """
    try:
        from zoneinfo import ZoneInfo

        if schedules:
            # Multi-schedule mode: check each schedule entry
            for sched in schedules:
                try:
                    # Check date range
                    today_str = now.strftime("%Y-%m-%d")
                    if sched.start_date and today_str < sched.start_date:
                        continue  # Schedule hasn't started yet
                    if sched.end_date and today_str > sched.end_date:
                        continue  # Schedule has expired

                    # Resolve timezone
                    tz_name = contact_timezone or sched.timezone or "UTC"
                    try:
                        tz = ZoneInfo(tz_name)
                    except (KeyError, Exception):
                        tz = ZoneInfo("UTC")

                    local_now = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
                    current_time = local_now.strftime("%H:%M")

                    # Check day of week
                    days_json = sched.send_days_json or '["mon","tue","wed","thu","fri"]'
                    send_days = json.loads(days_json)
                    day_abbr = local_now.strftime("%a").lower()[:3]
                    if day_abbr not in send_days:
                        continue

                    # Check time window
                    start = sched.send_window_start or "09:00"
                    end = sched.send_window_end or "17:00"
                    if start <= current_time <= end:
                        return True
                except Exception:
                    continue  # Skip broken schedule entries
            return False  # No schedule matched

        # Legacy fallback: use campaign-level columns
        tz_name = contact_timezone or campaign.timezone or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except (KeyError, Exception):
            tz = ZoneInfo("UTC")

        local_now = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        current_time = local_now.strftime("%H:%M")
        start = campaign.send_window_start or "09:00"
        end = campaign.send_window_end or "17:00"

        # Check day of week in the resolved timezone
        days_json = campaign.send_days_json or '["mon","tue","wed","thu","fri"]'
        send_days = json.loads(days_json)
        day_abbr = local_now.strftime("%a").lower()[:3]
        if day_abbr not in send_days:
            return False

        return start <= current_time <= end
    except Exception:
        return True  # default to allowing sends on parse errors


def _build_lob_merge_fields(lead) -> dict:
    """Build LOB-specific merge fields from lead metadata.

    Extracts source-specific data stored in lead metadata (e.g., NPI number,
    PageSpeed score, tech stack) and maps it to merge field names that can
    be used in email templates.

    Returns dict of {field_name: value} pairs.
    """
    fields = {}
    if not lead:
        return fields

    # Try to load metadata from lead's source data
    # Metadata is stored during lead sourcing from LOB adapters
    metadata = {}
    try:
        # Check if lead has a metadata_json or similar field
        if hasattr(lead, 'metadata_json') and lead.metadata_json:
            import json
            metadata = json.loads(lead.metadata_json) if isinstance(lead.metadata_json, str) else lead.metadata_json
    except Exception:
        pass

    # RCM merge fields
    fields["practice_specialty"] = metadata.get("specialty", "")
    fields["provider_count"] = str(metadata.get("provider_count", ""))
    fields["npi_number"] = metadata.get("npi_number", "")

    # Software Dev merge fields
    tech_stack = metadata.get("tech_stack", [])
    fields["tech_stack"] = ", ".join(tech_stack[:5]) if tech_stack else ""
    fields["funding_stage"] = metadata.get("last_funding_type", "")
    fields["team_size"] = metadata.get("estimated_team_size", "") or str(metadata.get("num_employees", ""))

    # AI Services merge fields
    fields["ai_maturity"] = metadata.get("ai_adoption_level", "")
    fields["automation_score"] = str(metadata.get("automation_score", ""))

    # Digital Marketing merge fields
    fields["domain_authority"] = str(metadata.get("domain_authority", ""))
    fields["pagespeed_score"] = str(metadata.get("performance_score", ""))
    if fields["pagespeed_score"]:
        try:
            score = float(fields["pagespeed_score"])
            fields["pagespeed_score"] = f"{int(score * 100)}/100"
        except (ValueError, TypeError):
            pass
    fields["review_count"] = str(metadata.get("review_count", ""))

    # Clean up empty strings
    return {k: v for k, v in fields.items() if v}


def _execute_email_step(
    cc: CampaignContact,
    step: SequenceStep,
    campaign: Campaign,
    db: Session,
) -> bool:
    """Send an email for this step to the contact. Returns True if sent."""
    from app.services.pipelines.outreach import (
        send_outreach_email,
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

    # Look up associated lead for job_title / job_location placeholders
    contact_lead = None
    _lead_id = cc.lead_id or contact.lead_id
    if _lead_id:
        contact_lead = db.query(LeadDetails).filter(
            LeadDetails.lead_id == _lead_id
        ).first()

    # --- Unified Send Gate: all safety checks in one call ---
    from app.services.send_gate import unified_send_gate
    gate = unified_send_gate(
        db=db, contact=contact, tenant_id=campaign.tenant_id,
        lead=contact_lead, campaign=campaign, step_number=cc.current_step,
    )
    if not gate.allowed:
        logger.info("send_gate_blocked", contact_id=cc.contact_id,
                     code=gate.reason_code, message=gate.reason_message)
        if gate.reason_code == "SEQUENCE_FATIGUE":
            cc.status = CampaignContactStatus.COMPLETED
            cc.next_send_at = None
        else:
            _advance_to_next_step(cc, step, campaign, db)
        return False

    # Select mailbox (health-aware scoring)
    mailbox = _select_mailbox(campaign, db)
    if not mailbox:
        logger.warning("No available mailbox for campaign", campaign_id=campaign.campaign_id)
        return False

    # Slow ramp: if enabled, calculate today's effective campaign limit
    effective_limit = campaign.daily_limit or 30
    if getattr(campaign, 'slow_ramp_enabled', False) and campaign.slow_ramp_enabled:
        slow_ramp_increment = campaign.slow_ramp_increment or 2
        slow_ramp_day = campaign.slow_ramp_current_day or 0
        effective_limit = min(
            slow_ramp_increment * (slow_ramp_day + 1),
            campaign.daily_limit or 30,
        )

    # Smart throttling: check hourly rate limit (daily_limit / 8 hours)
    # Apply daily jitter: use 85-95% of actual limit
    effective_daily = int(min(mailbox.daily_send_limit, effective_limit) * random.uniform(0.85, 0.95))
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

    # Apply spintax — campaign_id mixed in so same contact gets different
    # variants across campaigns (Gap 12: campaign-aware seeding)
    subject = process_spintax(subject, seed=cc.contact_id, campaign_id=campaign.campaign_id)
    body_html = process_spintax(body_html, seed=cc.contact_id, campaign_id=campaign.campaign_id)
    body_text = process_spintax(body_text, seed=cc.contact_id, campaign_id=campaign.campaign_id)

    # Render signature (injected AFTER AI personalization to avoid AI stripping it)
    signature_html = ""
    if mailbox.email_signature_json:
        signature_html = render_signature_html(mailbox.email_signature_json)

    # Strip {{signature}} placeholder from body before AI — will be re-injected after
    body_html = body_html.replace("{{signature}}", "")
    body_text = body_text.replace("{{signature}}", "")

    # Convert plain-text template bodies to basic HTML (newlines → <br>/<p>)
    # Templates stored in DB often use literal \n instead of actual HTML tags
    if body_html and "<" not in body_html:
        paragraphs = body_html.replace("\\n\\n", "\n\n").replace("\\n", "\n").split("\n\n")
        body_html = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())

    # Placeholder substitution — Jinja2 with fallback to manual replace
    _job_title = (contact_lead.job_title if contact_lead and contact_lead.job_title else "")
    _job_location = (contact_lead.state if contact_lead and contact_lead.state else "")
    _company = (contact_lead.client_name if contact_lead and contact_lead.client_name else (contact.client_name or ""))
    _sender_first = mailbox.resolved_first_name if hasattr(mailbox, 'resolved_first_name') else (mailbox.display_name or mailbox.email).split()[0]
    # Build LOB-specific merge fields from lead metadata
    _lob_fields = _build_lob_merge_fields(contact_lead)

    # Resource Pool "ready candidates" hook for {{candidate_pitch}} templates
    # (best-effort; empty string when unconfigured / no >=80% matches).
    try:
        from app.services.integrations.resource_pool_client import build_candidate_pitch
        _candidate_pitch = build_candidate_pitch(
            db, getattr(contact_lead, "lead_id", None), getattr(campaign, "tenant_id", None)
        ) or ""
    except Exception:
        _candidate_pitch = ""

    template_context = {
        "contact_first_name": contact.first_name or "",
        "candidate_pitch": _candidate_pitch,
        "contact_last_name": contact.last_name or "",
        "company_name": _company,
        "contact_title": contact.title or "",
        "job_title": _job_title,
        "job_location": _job_location,
        "sender_first_name": _sender_first,
        "contact": {
            "first_name": contact.first_name or "",
            "last_name": contact.last_name or "",
            "title": contact.title or "",
            "email": contact.email or "",
            "company": contact.client_name or "",
        },
        "lead": {
            "job_title": _job_title,
            "location": _job_location,
            "company": _company,
        },
        "sender": {
            "name": mailbox.display_name or "",
            "email": mailbox.email or "",
            "first_name": _sender_first,
        },
        **_lob_fields,
    }
    try:
        from jinja2 import Template as Jinja2Template
        subject = Jinja2Template(subject).render(**template_context)
        body_html = Jinja2Template(body_html).render(**template_context)
        body_text = Jinja2Template(body_text).render(**template_context)
    except Exception:
        pass

    # Always do string replacement for {{placeholder}} style (covers both Jinja2 and fallback)
    _placeholders = {
        "{{contact_first_name}}": contact.first_name or "",
        "{{contact_last_name}}": contact.last_name or "",
        "{{company_name}}": _company,
        "{{contact_title}}": contact.title or "",
        "{{job_title}}": _job_title,
        "{{job_location}}": _job_location,
        "{{sender_first_name}}": _sender_first,
    }
    # Add LOB-specific placeholders
    for field_name, field_val in _lob_fields.items():
        _placeholders[f"{{{{{field_name}}}}}"] = str(field_val)

    for ph, val in _placeholders.items():
        subject = subject.replace(ph, val)
        body_html = body_html.replace(ph, val)
        body_text = body_text.replace(ph, val)

    # --- AI Personalization (if enabled) ---
    try:
        from app.services.ai_personalizer import personalize_email_for_contact
        ai_result = personalize_email_for_contact(
            db=db, tenant_id=campaign.tenant_id,
            subject=subject, body_html=body_html, body_text=body_text,
            contact=contact, lead=contact_lead,
        )
        if ai_result.get("ai_used"):
            subject = ai_result["subject"]
            body_html = ai_result["body_html"]
            body_text = ai_result["body_text"]
    except Exception:
        pass  # Continue with original content

    # --- Email Humanizer (anti-AI-detection pass) ---
    try:
        from app.services.email_humanizer import humanize_email
        humanized = humanize_email(subject, body_html, body_text, intensity="medium")
        subject = humanized["subject"]
        body_html = humanized["body_html"]
        body_text = humanized["body_text"]
    except Exception:
        pass

    # --- Inject signature AFTER AI/humanizer so it's never rewritten ---
    if signature_html:
        body_html += signature_html
        # Build plain-text signature for body_text
        try:
            sig = json.loads(mailbox.email_signature_json)
            sig_parts = []
            if sig.get("sender_name"):
                sig_parts.append(sig["sender_name"])
            if sig.get("title"):
                sig_parts.append(sig["title"])
            if sig.get("company"):
                sig_parts.append(sig["company"])
            if sig.get("phone"):
                sig_parts.append(sig["phone"])
            if sig.get("email"):
                sig_parts.append(sig["email"])
            if sig.get("website"):
                sig_parts.append(sig["website"])
            if sig_parts:
                body_text += "\n\n--\n" + "\n".join(sig_parts)
        except Exception:
            pass

    # Content uniqueness check (monitoring-only -- log but don't block)
    try:
        from app.services.content_fingerprint import check_content_uniqueness
        uniqueness = check_content_uniqueness(
            db=db,
            body_html=body_html,
            campaign_id=campaign.campaign_id,
            tenant_id=campaign.tenant_id,
        )
        if not uniqueness["unique"]:
            logger.warning(
                "content_similarity_high",
                campaign_id=campaign.campaign_id,
                contact_id=cc.contact_id,
                max_similarity=uniqueness["max_similarity"],
                similar_event_id=uniqueness["similar_event_id"],
                warning=uniqueness["warning"],
            )
    except Exception as e_fp:
        logger.warning("content_fingerprint_check_failed", error=str(e_fp))

    # --- Thread chaining: look up first step's Message-ID for this contact ---
    # This enables follow-up emails to thread under the original conversation
    # in Gmail/Outlook and in the portal unified inbox.
    _in_reply_to = ""
    _references = ""
    if step.step_order and step.step_order > 1:
        first_event = (
            db.query(OutreachEvent)
            .join(SequenceStep, OutreachEvent.step_id == SequenceStep.step_id)
            .filter(
                OutreachEvent.campaign_id == campaign.campaign_id,
                OutreachEvent.contact_id == cc.contact_id,
                OutreachEvent.status == OutreachStatus.SENT,
                OutreachEvent.message_id.isnot(None),
                SequenceStep.step_order < step.step_order,
            )
            .order_by(SequenceStep.step_order.asc())
            .first()
        )
        if first_event and first_event.message_id:
            _in_reply_to = first_event.message_id
            _references = first_event.message_id
            # Prepend "Re: " to subject if not already present — critical for
            # email client threading (Gmail, Outlook, Apple Mail)
            if not subject.lower().startswith("re:"):
                subject = f"Re: {first_event.subject or subject}"

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

    # Inject tracking pixel for open tracking
    try:
        from app.services.warmup.tracking import inject_tracking
        body_html = inject_tracking(body_html, event.tracking_id, db, tenant_id=campaign.tenant_id)
    except Exception as e_track:
        logger.warning("Failed to inject tracking pixel", error=str(e_track))

    # Add unsubscribe footer
    unsub_footer = generate_unsub_footer(event.tracking_id)
    if "unsub/" not in body_html:
        body_html += unsub_footer["html"]
        body_text += unsub_footer["text"]

    # Send (with threading headers for follow-up steps)
    result = send_outreach_email(
        sender_mailbox=mailbox,
        to_email=contact.email,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        db=db,
        unsub_url=unsub_footer.get("url", ""),
        in_reply_to=_in_reply_to,
        references=_references,
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

        # Sync to unified inbox immediately (don't wait for scheduled job)
        try:
            from app.services.pipelines.outreach import _sync_sent_to_inbox
            _sync_sent_to_inbox(db, event, contact, mailbox, in_reply_to=_in_reply_to)
        except Exception as e:
            logger.warning("Campaign inbox sync failed", error=str(e))

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

        # Smart throttling: delay based on campaign sending_speed setting
        speed = getattr(campaign, 'sending_speed', 'normal') or 'normal'
        speed_ranges = {
            'relaxed': (120, 300),
            'normal': (30, 90),
            'aggressive': (5, 15),
        }
        min_delay, max_delay = speed_ranges.get(speed, (30, 90))
        delay_sec = random.randint(min_delay, max_delay)
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
            SenderMailbox.is_blacklisted == False,  # noqa: E712 — mirror primary selector safety filter
        )
        if mailbox_ids:
            query = query.filter(SenderMailbox.mailbox_id.in_(mailbox_ids))
        else:
            # Automated pool: only auto_outbound (e.g. RA) roles — mirror select_best_mailbox.
            from app.db.models.outreach_role import OutreachRole
            query = query.join(
                OutreachRole, SenderMailbox.outreach_role_id == OutreachRole.role_id
            ).filter(OutreachRole.auto_outbound == True)  # noqa: E712
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
    """Advance a contact to the next step in the sequence.

    Uses the contact's timezone (if available) to schedule the next send
    during optimal business hours in the recipient's local time.
    """
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

    # Calculate base delay
    base_next = datetime.utcnow() + timedelta(
        days=next_step.delay_days,
        hours=next_step.delay_hours,
    )

    # If the next step is an email step and contact has timezone, optimize send time
    if next_step.step_type == StepType.EMAIL and next_step.delay_days >= 1:
        try:
            contact = db.query(ContactDetails).with_entities(
                ContactDetails.timezone, ContactDetails.location_state
            ).filter(ContactDetails.contact_id == cc.contact_id).first()
            if contact and (contact.timezone or contact.location_state):
                from app.services.send_time_optimizer import calculate_optimal_send_time
                optimal = calculate_optimal_send_time(
                    state=contact.location_state
                )
                optimal_utc = optimal.get("send_at_utc")
                if optimal_utc and optimal_utc > base_next:
                    # Use optimal time if it's after the minimum delay
                    cc.next_send_at = optimal_utc
                    return
        except Exception:
            pass  # Fall back to base delay

    cc.next_send_at = base_next


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
            # Check actual pixel-based open tracking on OutreachEvent
            condition_met = prev_event.opened_at is not None
        elif condition_type == "clicked":
            # Check actual link click tracking on OutreachEvent
            condition_met = prev_event.clicked_at is not None
        elif condition_type == "no_action":
            # True if no reply AND no open within window and window has passed
            condition_met = (
                prev_event.reply_detected_at is None and
                prev_event.opened_at is None and
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

    # Build contact lookup for is_test checks
    contact_map = {c.contact_id: c for c in contacts}

    enrolled = 0
    re_enrolled = 0
    duplicates = 0
    suppressed = 0

    now = datetime.utcnow()
    for cid in contact_ids:
        if cid in existing:
            # Allow re-enrollment for test contacts
            contact_obj = contact_map.get(cid)
            if contact_obj and getattr(contact_obj, 'is_test', False):
                cc = db.query(CampaignContact).filter(
                    CampaignContact.campaign_id == campaign_id,
                    CampaignContact.contact_id == cid,
                ).first()
                if cc:
                    cc.status = CampaignContactStatus.ACTIVE
                    cc.current_step = first_step.step_order if first_step else 0
                    cc.next_send_at = now + delay if campaign.status == CampaignStatus.ACTIVE else None
                    cc.completed_at = None
                    re_enrolled += 1
                    continue
            duplicates += 1
            continue
        if cid in suppressed_ids:
            suppressed += 1
            continue

        # Find lead_id for this contact
        contact = contact_map.get(cid) or db.query(ContactDetails).filter(
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

    return {"enrolled": enrolled, "re_enrolled": re_enrolled, "duplicates": duplicates, "suppressed": suppressed}


def handle_campaign_reply(event_id: int, db: Session):
    """Called when a reply is detected on a campaign outreach event.

    Accepts contacts in ACTIVE or COMPLETED status — replies typically
    arrive after the contact has already been advanced through all steps.
    """
    event = db.query(OutreachEvent).filter(
        OutreachEvent.event_id == event_id
    ).first()
    if not event or not event.campaign_id:
        return

    cc = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == event.campaign_id,
        CampaignContact.contact_id == event.contact_id,
    ).first()
    if cc and cc.status in (
        CampaignContactStatus.ACTIVE,
        CampaignContactStatus.COMPLETED,
    ):
        cc.status = CampaignContactStatus.REPLIED
        cc.next_send_at = None
        if not cc.completed_at:
            cc.completed_at = datetime.utcnow()

        db.commit()

    # Always recalculate stats from ground truth (OutreachEvent data)
    # so denormalized counters on Campaign + SequenceStep stay in sync.
    recalculate_campaign_stats(event.campaign_id, db)

    # Refresh health score immediately instead of waiting for daily job
    try:
        from app.services.campaign_health import calculate_campaign_health
        result = calculate_campaign_health(event.campaign_id, db)
        if result.get("score") is not None:
            campaign = db.query(Campaign).filter(
                Campaign.campaign_id == event.campaign_id
            ).first()
            if campaign:
                campaign.health_score = result["score"]
                db.commit()
    except Exception as e:
        logger.warning("health_score_refresh_failed", error=str(e))


def handle_campaign_bounce(event_id: int, db: Session):
    """Called when a bounce is detected on a campaign outreach event.

    Accepts contacts in ACTIVE or COMPLETED status — bounces can arrive
    after the contact was already advanced through remaining steps.
    """
    event = db.query(OutreachEvent).filter(
        OutreachEvent.event_id == event_id
    ).first()
    if not event or not event.campaign_id:
        return

    cc = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == event.campaign_id,
        CampaignContact.contact_id == event.contact_id,
    ).first()
    if cc and cc.status in (
        CampaignContactStatus.ACTIVE,
        CampaignContactStatus.COMPLETED,
    ):
        cc.status = CampaignContactStatus.BOUNCED
        cc.next_send_at = None

        db.commit()

    # Recalculate stats from ground truth
    recalculate_campaign_stats(event.campaign_id, db)


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

    # Count all events that were actually sent (a replied/bounced email was still sent)
    campaign.total_sent = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == campaign_id,
        OutreachEvent.sent_at.isnot(None),
    ).count()

    campaign.total_opened = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == campaign_id,
        OutreachEvent.opened_at.isnot(None),
    ).count()

    campaign.total_replied = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == campaign_id,
        OutreachEvent.reply_detected_at.isnot(None),
    ).count()

    campaign.total_bounced = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == campaign_id,
        OutreachEvent.status == OutreachStatus.BOUNCED,
    ).count()

    # Recalculate per-step stats from actual OutreachEvent data
    steps = db.query(SequenceStep).filter(
        SequenceStep.campaign_id == campaign_id
    ).all()
    for step in steps:
        step.total_sent = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == campaign_id,
            OutreachEvent.step_id == step.step_id,
            OutreachEvent.sent_at.isnot(None),
        ).count()
        step.total_opened = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == campaign_id,
            OutreachEvent.step_id == step.step_id,
            OutreachEvent.opened_at.isnot(None),
        ).count()
        step.total_replied = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == campaign_id,
            OutreachEvent.step_id == step.step_id,
            OutreachEvent.reply_detected_at.isnot(None),
        ).count()
        step.total_bounced = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == campaign_id,
            OutreachEvent.step_id == step.step_id,
            OutreachEvent.status == OutreachStatus.BOUNCED,
        ).count()

    db.commit()
