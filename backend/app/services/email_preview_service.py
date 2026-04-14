"""Email Preview Service — draft generation, AI rewriting, deliverability scoring, spam fixing.

Supports 3 entry points for draft generation:
1. Campaign drafts (from campaign engine)
2. Pipeline drafts (from outreach send pipeline)
3. Broadcast drafts (ad-hoc send to selected contacts)
"""
import json
import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.db.models.outreach_draft import OutreachDraft, DraftStatus, DraftSource
from app.db.models.campaign import (
    Campaign, SequenceStep, CampaignContact,
    CampaignStatus, StepType, CampaignContactStatus,
)
from app.db.models.contact import ContactDetails
from app.db.models.lead import LeadDetails
from app.db.models.outreach import OutreachEvent, OutreachStatus, OutreachChannel
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.email_template import EmailTemplate
from app.services.spam_checker import check_spam_score

logger = structlog.get_logger()


# ─── Draft Generation ────────────────────────────────────────────────


def generate_campaign_drafts(
    campaign_id: int,
    step_index: int,
    db: Session,
    tenant_id: int,
) -> Dict[str, Any]:
    """Generate preview drafts for a campaign email step.

    Mirrors _execute_email_step() logic but creates OutreachDraft records
    instead of sending.
    """
    from app.services.pipelines.outreach import render_signature_html, generate_unsub_footer
    from app.services.spintax import process_spintax
    from app.services.campaign_engine import _select_mailbox, _select_variant

    campaign = db.query(Campaign).filter(
        Campaign.campaign_id == campaign_id,
        Campaign.tenant_id == tenant_id,
    ).first()
    if not campaign:
        return {"error": "Campaign not found", "drafts_created": 0}

    step = db.query(SequenceStep).filter(
        SequenceStep.campaign_id == campaign_id,
        SequenceStep.step_order == step_index,
        SequenceStep.step_type == StepType.EMAIL,
    ).first()
    if not step:
        return {"error": f"Email step at index {step_index} not found", "drafts_created": 0}

    # Get active contacts for this campaign at this step
    contacts_due = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.status == CampaignContactStatus.ACTIVE,
        CampaignContact.current_step == step_index,
    ).all()

    if not contacts_due:
        # Also include all active contacts if none are at this step yet
        contacts_due = db.query(CampaignContact).filter(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.status == CampaignContactStatus.ACTIVE,
        ).all()

    batch_id = str(uuid.uuid4())
    drafts_created = 0

    mailbox = _select_mailbox(campaign, db)
    if not mailbox:
        return {"error": "No available mailbox", "drafts_created": 0, "batch_id": batch_id}

    for cc in contacts_due:
        contact = db.query(ContactDetails).filter(
            ContactDetails.contact_id == cc.contact_id
        ).first()
        if not contact:
            continue

        contact_lead = None
        _lead_id = cc.lead_id or contact.lead_id
        if _lead_id:
            contact_lead = db.query(LeadDetails).filter(
                LeadDetails.lead_id == _lead_id
            ).first()

        # Resolve variant
        subject = step.subject or ""
        body_html = step.body_html or ""
        body_text = step.body_text or ""
        variant_index = None

        if step.variants_json:
            variant_index, subject, body_html, body_text = _select_variant(cc, step, db)

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

        # Placeholder substitution
        subject, body_html, body_text = _substitute_placeholders(
            subject, body_html, body_text, contact, contact_lead, mailbox
        )

        # Run spam check
        spam_result = check_spam_score(subject, body_html)

        draft = OutreachDraft(
            tenant_id=tenant_id,
            contact_id=cc.contact_id,
            lead_id=_lead_id,
            campaign_id=campaign_id,
            step_id=step.step_id,
            mailbox_id=mailbox.mailbox_id,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            original_subject=subject,
            original_body_html=body_html,
            status=DraftStatus.PENDING,
            source=DraftSource.CAMPAIGN,
            spam_score=spam_result["score"],
            spam_grade=spam_result["grade"],
            flagged_words_json=json.dumps(spam_result["flagged_words"]),
            batch_id=batch_id,
            variant_index=variant_index,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.add(draft)
        drafts_created += 1

    db.commit()

    return {
        "batch_id": batch_id,
        "drafts_created": drafts_created,
        "campaign_id": campaign_id,
        "step_index": step_index,
    }


def generate_single_campaign_draft(
    cc: CampaignContact,
    step: SequenceStep,
    campaign: Campaign,
    db: Session,
) -> Optional[OutreachDraft]:
    """Generate a single draft for a campaign contact (called from campaign engine)."""
    from app.services.pipelines.outreach import render_signature_html
    from app.services.spintax import process_spintax
    from app.services.campaign_engine import _select_mailbox, _select_variant

    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == cc.contact_id
    ).first()
    if not contact:
        return None

    contact_lead = None
    _lead_id = cc.lead_id or contact.lead_id
    if _lead_id:
        contact_lead = db.query(LeadDetails).filter(
            LeadDetails.lead_id == _lead_id
        ).first()

    mailbox = _select_mailbox(campaign, db)
    if not mailbox:
        return None

    subject = step.subject or ""
    body_html = step.body_html or ""
    body_text = step.body_text or ""
    variant_index = None

    if step.variants_json:
        variant_index, subject, body_html, body_text = _select_variant(cc, step, db)

    subject = process_spintax(subject, seed=cc.contact_id)
    body_html = process_spintax(body_html, seed=cc.contact_id)
    body_text = process_spintax(body_text, seed=cc.contact_id)

    signature_html = ""
    if mailbox.email_signature_json:
        signature_html = render_signature_html(mailbox.email_signature_json)
    if signature_html and "{{signature}}" in body_html:
        body_html = body_html.replace("{{signature}}", signature_html)
    elif signature_html:
        body_html += signature_html

    subject, body_html, body_text = _substitute_placeholders(
        subject, body_html, body_text, contact, contact_lead, mailbox
    )

    spam_result = check_spam_score(subject, body_html)

    draft = OutreachDraft(
        tenant_id=campaign.tenant_id,
        contact_id=cc.contact_id,
        lead_id=_lead_id,
        campaign_id=campaign.campaign_id,
        step_id=step.step_id,
        mailbox_id=mailbox.mailbox_id,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        original_subject=subject,
        original_body_html=body_html,
        status=DraftStatus.PENDING,
        source=DraftSource.CAMPAIGN,
        spam_score=spam_result["score"],
        spam_grade=spam_result["grade"],
        flagged_words_json=json.dumps(spam_result["flagged_words"]),
        batch_id=None,  # individual drafts from scheduler don't have a batch
        variant_index=variant_index,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(draft)
    return draft


def generate_pipeline_drafts(
    tenant_id: int,
    limit: int,
    db: Session,
) -> Dict[str, Any]:
    """Generate preview drafts from the pipeline outreach flow.

    Mirrors run_outreach_send_pipeline() but creates OutreachDraft records.
    """
    from app.services.pipelines.outreach import (
        check_send_eligibility, render_template, render_signature_html,
        get_active_template, resolve_business_rules,
    )
    from app.services.outreach_draft_service import draft_outreach_email

    batch_id = str(uuid.uuid4())
    drafts_created = 0

    biz_rules = resolve_business_rules(db, tenant_id=tenant_id)

    contacts = db.query(ContactDetails).filter(
        ContactDetails.validation_status == "valid",
        ContactDetails.is_archived == False,
        ContactDetails.tenant_id == tenant_id,
    ).limit(limit * 3).all()  # over-fetch to account for ineligible

    active_template = get_active_template(db, category="outreach", tenant_id=tenant_id)

    for contact in contacts:
        if drafts_created >= limit:
            break

        eligible, reason = check_send_eligibility(db, contact, business_rules=biz_rules)
        if not eligible:
            continue

        mailbox = db.query(SenderMailbox).filter(
            SenderMailbox.is_active == True,
            SenderMailbox.warmup_status.in_([WarmupStatus.COLD_READY, WarmupStatus.ACTIVE]),
            SenderMailbox.emails_sent_today < SenderMailbox.daily_send_limit,
            SenderMailbox.connection_status == "successful",
        ).order_by(SenderMailbox.emails_sent_today.asc()).first()

        if not mailbox:
            break

        contact_lead = None
        if contact.lead_id:
            contact_lead = db.query(LeadDetails).filter(
                LeadDetails.lead_id == contact.lead_id
            ).first()

        signature_html = ""
        if mailbox.email_signature_json:
            signature_html = render_signature_html(mailbox.email_signature_json)

        if active_template:
            subject, body_html, body_text = render_template(
                active_template, contact, contact_lead, mailbox, signature_html,
            )
        else:
            ai_draft = draft_outreach_email(
                db, contact, lead=contact_lead, mailbox=mailbox, tenant_id=tenant_id,
            )
            if ai_draft:
                subject, body_html, body_text = ai_draft
                body_html += signature_html
            else:
                subject = f"Regarding your open position at {contact.client_name or 'your company'}"
                body_html = f"<p>Hi {contact.first_name or 'there'},</p><p>We noticed your company is hiring and wanted to reach out about our staffing solutions.</p>"
                body_html += signature_html
                body_text = f"Hi {contact.first_name or 'there'},\nWe noticed your company is hiring..."

        spam_result = check_spam_score(subject, body_html)

        draft = OutreachDraft(
            tenant_id=tenant_id,
            contact_id=contact.contact_id,
            lead_id=contact.lead_id,
            mailbox_id=mailbox.mailbox_id,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            original_subject=subject,
            original_body_html=body_html,
            status=DraftStatus.PENDING,
            source=DraftSource.PIPELINE,
            spam_score=spam_result["score"],
            spam_grade=spam_result["grade"],
            flagged_words_json=json.dumps(spam_result["flagged_words"]),
            batch_id=batch_id,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.add(draft)
        drafts_created += 1

    db.commit()
    return {"batch_id": batch_id, "drafts_created": drafts_created}


def generate_broadcast_drafts(
    contact_ids: List[int],
    template_id: int,
    mailbox_id: int,
    db: Session,
    tenant_id: int,
) -> Dict[str, Any]:
    """Generate drafts for a broadcast send to specific contacts using a template."""
    from app.services.pipelines.outreach import render_template, render_signature_html

    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        return {"error": "Template not found", "drafts_created": 0}

    mailbox = db.query(SenderMailbox).filter(
        SenderMailbox.mailbox_id == mailbox_id
    ).first()
    if not mailbox:
        return {"error": "Mailbox not found", "drafts_created": 0}

    batch_id = str(uuid.uuid4())
    drafts_created = 0

    signature_html = ""
    if mailbox.email_signature_json:
        signature_html = render_signature_html(mailbox.email_signature_json)

    contacts = db.query(ContactDetails).filter(
        ContactDetails.contact_id.in_(contact_ids),
        ContactDetails.tenant_id == tenant_id,
    ).all()

    for contact in contacts:
        contact_lead = None
        if contact.lead_id:
            contact_lead = db.query(LeadDetails).filter(
                LeadDetails.lead_id == contact.lead_id
            ).first()

        subject, body_html, body_text = render_template(
            template, contact, contact_lead, mailbox, signature_html,
        )

        spam_result = check_spam_score(subject, body_html)

        draft = OutreachDraft(
            tenant_id=tenant_id,
            contact_id=contact.contact_id,
            lead_id=contact.lead_id,
            mailbox_id=mailbox_id,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            original_subject=subject,
            original_body_html=body_html,
            status=DraftStatus.PENDING,
            source=DraftSource.BROADCAST,
            spam_score=spam_result["score"],
            spam_grade=spam_result["grade"],
            flagged_words_json=json.dumps(spam_result["flagged_words"]),
            batch_id=batch_id,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.add(draft)
        drafts_created += 1

    db.commit()
    return {"batch_id": batch_id, "drafts_created": drafts_created}


# ─── AI Rewriting ─────────────────────────────────────────────────


def ai_rewrite_draft(draft_id: int, db: Session, tenant_id: int) -> Dict[str, Any]:
    """AI-rewrite a draft to make it unique and human-sounding."""
    from app.services.adapters.ai_content import get_ai_adapter

    draft = db.query(OutreachDraft).filter(
        OutreachDraft.draft_id == draft_id,
        OutreachDraft.tenant_id == tenant_id,
    ).first()
    if not draft:
        return {"error": "Draft not found"}

    ai = get_ai_adapter(db, tenant_id)
    if not ai:
        return {"error": "No AI provider configured"}

    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == draft.contact_id
    ).first()

    contact_name = ""
    company_name = ""
    if contact:
        contact_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
        company_name = contact.client_name or ""

    prompt = (
        "Rewrite the following cold outreach email to make it sound more natural, "
        "human, and personalized. Vary the sentence structure and word choice to avoid "
        "spam filters and AI detection. Keep the same intent and key information. "
        "Do NOT add markdown formatting. Keep it concise.\n\n"
        f"Recipient: {contact_name} at {company_name}\n\n"
        f"Subject: {draft.subject}\n\n"
        f"Body:\n{draft.body_html}\n\n"
        "Return the rewritten email in this exact format:\n"
        "SUBJECT: <rewritten subject>\n"
        "BODY: <rewritten HTML body>"
    )

    try:
        result = ai._call_api([
            {"role": "system", "content": "You are an expert cold email copywriter. Rewrite emails to sound natural and avoid spam filters."},
            {"role": "user", "content": prompt},
        ], temperature=0.8, max_tokens=1500)

        # Parse result
        new_subject = draft.subject
        new_body = draft.body_html

        if "SUBJECT:" in result and "BODY:" in result:
            parts = result.split("BODY:", 1)
            subject_part = parts[0].replace("SUBJECT:", "").strip()
            body_part = parts[1].strip()
            if subject_part:
                new_subject = subject_part
            if body_part:
                new_body = body_part
        elif result.strip():
            new_body = result.strip()

        # Store originals if not already stored
        if not draft.original_subject:
            draft.original_subject = draft.subject
        if not draft.original_body_html:
            draft.original_body_html = draft.body_html

        draft.subject = new_subject
        draft.body_html = new_body
        draft.ai_rewritten = True

        # Re-run spam check
        spam_result = check_spam_score(new_subject, new_body)
        draft.spam_score = spam_result["score"]
        draft.spam_grade = spam_result["grade"]
        draft.flagged_words_json = json.dumps(spam_result["flagged_words"])

        db.commit()
        return {
            "draft_id": draft_id,
            "subject": new_subject,
            "body_html": new_body,
            "spam_score": spam_result["score"],
            "spam_grade": spam_result["grade"],
            "ai_rewritten": True,
        }
    except Exception as e:
        logger.error("AI rewrite failed", draft_id=draft_id, error=str(e))
        return {"error": f"AI rewrite failed: {str(e)}"}


# ─── Deliverability Score ────────────────────────────────────────


def calculate_deliverability_score(
    mailbox_id: int,
    subject: str,
    body_html: str,
    db: Session,
    tenant_id: int,
) -> Dict[str, Any]:
    """Composite deliverability score combining DNS, spam, blacklist, and reputation."""
    # 1. DNS score (35% weight)
    dns_data = {"score": 0, "spf": {}, "dkim": {}, "dmarc": {}, "mx": {}}
    try:
        from app.services.warmup.dns_checker import run_dns_health_check
        dns_data = run_dns_health_check(mailbox_id, db, tenant_id=tenant_id)
    except Exception as e:
        logger.warning("DNS check failed in deliverability", error=str(e))

    dns_score = dns_data.get("score", 0)

    # 2. Spam score inverted (30% weight)
    spam_data = check_spam_score(subject, body_html)
    spam_score_raw = spam_data.get("score", 0)
    spam_score = max(0, 100 - spam_score_raw)  # invert: 0 spam = 100 score

    # 3. Blacklist check (20% weight)
    blacklist_data = {"is_clean": True, "results": [], "total_listed": 0}
    try:
        from app.services.warmup.blacklist_monitor import run_blacklist_check
        blacklist_data = run_blacklist_check(mailbox_id, db, tenant_id=tenant_id)
    except Exception as e:
        logger.warning("Blacklist check failed in deliverability", error=str(e))

    blacklist_score = 100 if blacklist_data.get("is_clean", True) else max(0, 100 - blacklist_data.get("total_listed", 0) * 25)

    # 4. Mailbox reputation (15% weight)
    reputation_data = {"reputation_score": 50}
    try:
        from app.services.warmup.domain_reputation import get_domain_reputation
        reputation_data = get_domain_reputation(mailbox_id, db)
    except Exception as e:
        logger.warning("Reputation check failed in deliverability", error=str(e))

    reputation_score = reputation_data.get("reputation_score", 50)

    # Weighted composite
    overall = (
        dns_score * 0.35 +
        spam_score * 0.30 +
        blacklist_score * 0.20 +
        reputation_score * 0.15
    )

    return {
        "overall_score": round(overall, 1),
        "dns": {
            "score": dns_score,
            "weight": 35,
            "spf": dns_data.get("spf", {}),
            "dkim": dns_data.get("dkim", {}),
            "dmarc": dns_data.get("dmarc", {}),
            "mx": dns_data.get("mx", {}),
        },
        "spam": {
            "score": spam_score,
            "raw_score": spam_score_raw,
            "weight": 30,
            "grade": spam_data.get("grade", "unknown"),
            "flagged_words": spam_data.get("flagged_words", []),
        },
        "blacklist": {
            "score": blacklist_score,
            "weight": 20,
            "is_clean": blacklist_data.get("is_clean", True),
            "ip": blacklist_data.get("ip"),
            "total_checked": blacklist_data.get("total_checked", 0),
            "total_listed": blacklist_data.get("total_listed", 0),
            "results": blacklist_data.get("results", []),
        },
        "reputation": {
            "score": reputation_score,
            "weight": 15,
            "domain": reputation_data.get("domain"),
            "bounce_rate": reputation_data.get("bounce_rate", 0),
            "is_blacklisted": reputation_data.get("is_blacklisted", False),
        },
        "rendering": _get_rendering_warnings(body_html),
    }


def _get_rendering_warnings(body_html: str) -> Dict[str, Any]:
    """Run rendering checker and return warnings (Gap 11)."""
    try:
        from app.services.rendering_checker import check_rendering
        result = check_rendering(body_html)
        return {
            "score": result.get("score", 100),
            "warnings": result.get("warnings", []),
            "stats": result.get("stats", {}),
        }
    except Exception as e:
        logger.warning("rendering_check_failed", error=str(e))
        return {"score": 100, "warnings": [], "stats": {}}


# ─── Spam Check + AI Suggestions ─────────────────────────────────


def check_spam_and_suggest(
    subject: str,
    body_html: str,
    db: Session,
    tenant_id: int,
) -> Dict[str, Any]:
    """Run spam check and generate AI-powered replacement suggestions."""
    from app.services.adapters.ai_content import get_ai_adapter

    spam_result = check_spam_score(subject, body_html)

    suggestions = []
    flagged = spam_result.get("flagged_words", [])

    if flagged:
        ai = get_ai_adapter(db, tenant_id)
        if ai:
            # Build list of flagged words for AI
            words_list = [f.get("word", "") for f in flagged if not f.get("word", "").startswith("[pattern:")]
            if words_list:
                prompt = (
                    "For each spam trigger word/phrase below, suggest a non-spammy "
                    "alternative that preserves the original meaning in a cold outreach email context. "
                    "Return ONLY a JSON array of objects with 'original' and 'replacement' keys.\n\n"
                    f"Words: {json.dumps(words_list)}"
                )
                try:
                    import re
                    result = ai._call_api([
                        {"role": "system", "content": "You are a spam filter expert. Return only valid JSON."},
                        {"role": "user", "content": prompt},
                    ], temperature=0.5, max_tokens=800)
                    cleaned = re.sub(r"```(?:json)?\s*", "", result).strip().rstrip("`")
                    suggestions = json.loads(cleaned)
                except Exception as e:
                    logger.warning("AI spam suggestions failed", error=str(e))
                    # Fallback: provide basic suggestions
                    suggestions = [
                        {"original": w, "replacement": f"[consider rephrasing '{w}']"}
                        for w in words_list[:10]
                    ]
        else:
            # No AI — provide basic guidance
            suggestions = [
                {"original": f.get("word", ""), "replacement": f"[rephrase '{f.get('word', '')}']"}
                for f in flagged if not f.get("word", "").startswith("[pattern:")
            ][:10]

    return {
        "score": spam_result["score"],
        "grade": spam_result["grade"],
        "flagged_words": flagged,
        "suggestions": suggestions,
        "total_triggers": spam_result.get("total_triggers", 0),
    }


# ─── Approval / Rejection ────────────────────────────────────────


def approve_draft(draft_id: int, user_id: int, db: Session, tenant_id: int) -> Dict[str, Any]:
    """Approve a draft for sending."""
    draft = db.query(OutreachDraft).filter(
        OutreachDraft.draft_id == draft_id,
        OutreachDraft.tenant_id == tenant_id,
        OutreachDraft.status == DraftStatus.PENDING,
    ).first()
    if not draft:
        return {"error": "Draft not found or not in pending status"}

    draft.status = DraftStatus.APPROVED
    draft.approved_by = user_id
    draft.approved_at = datetime.utcnow()
    db.commit()

    return {"draft_id": draft_id, "status": "approved"}


def reject_draft(draft_id: int, user_id: int, db: Session, tenant_id: int) -> Dict[str, Any]:
    """Reject a draft."""
    draft = db.query(OutreachDraft).filter(
        OutreachDraft.draft_id == draft_id,
        OutreachDraft.tenant_id == tenant_id,
        OutreachDraft.status == DraftStatus.PENDING,
    ).first()
    if not draft:
        return {"error": "Draft not found or not in pending status"}

    draft.status = DraftStatus.REJECTED
    draft.rejected_by = user_id
    draft.rejected_at = datetime.utcnow()
    db.commit()

    return {"draft_id": draft_id, "status": "rejected"}


def approve_batch(batch_id: str, user_id: int, db: Session, tenant_id: int) -> Dict[str, Any]:
    """Bulk approve all pending drafts in a batch."""
    drafts = db.query(OutreachDraft).filter(
        OutreachDraft.batch_id == batch_id,
        OutreachDraft.tenant_id == tenant_id,
        OutreachDraft.status == DraftStatus.PENDING,
    ).all()

    count = 0
    now = datetime.utcnow()
    for d in drafts:
        d.status = DraftStatus.APPROVED
        d.approved_by = user_id
        d.approved_at = now
        count += 1

    db.commit()
    return {"batch_id": batch_id, "approved_count": count}


def apply_spam_fix(
    draft_id: int,
    replacements: List[Dict[str, str]],
    db: Session,
    tenant_id: int,
) -> Dict[str, Any]:
    """Apply spam word replacements to a draft and re-run spam check."""
    draft = db.query(OutreachDraft).filter(
        OutreachDraft.draft_id == draft_id,
        OutreachDraft.tenant_id == tenant_id,
    ).first()
    if not draft:
        return {"error": "Draft not found"}

    subject = draft.subject
    body_html = draft.body_html

    for r in replacements:
        original = r.get("original", "")
        replacement = r.get("replacement", "")
        if original and replacement:
            subject = subject.replace(original, replacement)
            body_html = body_html.replace(original, replacement)

    draft.subject = subject
    draft.body_html = body_html

    # Re-run spam check
    spam_result = check_spam_score(subject, body_html)
    draft.spam_score = spam_result["score"]
    draft.spam_grade = spam_result["grade"]
    draft.flagged_words_json = json.dumps(spam_result["flagged_words"])

    db.commit()

    return {
        "draft_id": draft_id,
        "subject": subject,
        "body_html": body_html,
        "spam_score": spam_result["score"],
        "spam_grade": spam_result["grade"],
        "flagged_words": spam_result["flagged_words"],
    }


# ─── Sending ─────────────────────────────────────────────────────


def send_single_draft(draft_id: int, db: Session, tenant_id: int) -> Dict[str, Any]:
    """Send a single approved draft."""
    from app.services.pipelines.outreach import (
        send_outreach_email, generate_unsub_footer, _sync_sent_to_inbox,
    )

    draft = db.query(OutreachDraft).filter(
        OutreachDraft.draft_id == draft_id,
        OutreachDraft.tenant_id == tenant_id,
        OutreachDraft.status == DraftStatus.APPROVED,
    ).first()
    if not draft:
        return {"error": "Draft not found or not approved"}

    mailbox = db.query(SenderMailbox).filter(
        SenderMailbox.mailbox_id == draft.mailbox_id
    ).first()
    if not mailbox:
        return {"error": "Mailbox not found"}

    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == draft.contact_id
    ).first()
    if not contact:
        return {"error": "Contact not found"}

    # --- Unified Send Gate ---
    from app.services.send_gate import unified_send_gate
    lead = (
        db.query(LeadDetails).filter(LeadDetails.lead_id == draft.lead_id).first()
        if draft.lead_id else None
    )
    gate = unified_send_gate(db=db, contact=contact, tenant_id=tenant_id, lead=lead)
    if not gate.allowed:
        return {"error": gate.reason_message, "reason_code": gate.reason_code, "blocked": True}

    # Create outreach event
    event = OutreachEvent(
        tenant_id=tenant_id,
        contact_id=draft.contact_id,
        lead_id=draft.lead_id,
        sender_mailbox_id=draft.mailbox_id,
        channel=OutreachChannel.SMTP,
        status=OutreachStatus.SKIPPED,
        skip_reason="pending_send",
        campaign_id=draft.campaign_id,
        step_id=draft.step_id,
        variant_index=draft.variant_index,
    )
    db.add(event)
    db.flush()

    # Add unsub footer if not present
    body_html = draft.body_html
    body_text = draft.body_text or ""
    unsub_footer = generate_unsub_footer(event.tracking_id)
    if "unsub/" not in body_html:
        body_html += unsub_footer["html"]
        body_text += unsub_footer["text"]

    result = send_outreach_email(
        sender_mailbox=mailbox,
        to_email=contact.email,
        subject=draft.subject,
        body_html=body_html,
        body_text=body_text,
        db=db,
        unsub_url=unsub_footer.get("url", ""),
    )

    if result["success"]:
        event.status = OutreachStatus.SENT
        event.skip_reason = None
        event.subject = draft.subject
        event.body_html = body_html
        event.body_text = body_text
        event.message_id = result.get("message_id")

        mailbox.emails_sent_today += 1
        mailbox.total_emails_sent += 1
        mailbox.last_sent_at = datetime.utcnow()
        contact.last_outreach_date = datetime.utcnow().isoformat()

        draft.status = DraftStatus.SENT
        draft.sent_at = datetime.utcnow()

        # Sync to inbox
        try:
            _sync_sent_to_inbox(db, event, contact, mailbox)
        except Exception as e:
            logger.warning("Inbox sync failed for draft send", error=str(e))

        db.commit()
        return {"draft_id": draft_id, "status": "sent", "message_id": result.get("message_id")}
    else:
        event.status = OutreachStatus.SKIPPED
        event.skip_reason = result.get("error", "Send failed")
        event.subject = draft.subject
        db.commit()
        return {"error": result.get("error", "Send failed"), "draft_id": draft_id}


def send_batch(batch_id: str, db: Session, tenant_id: int) -> Dict[str, Any]:
    """Send all approved drafts in a batch with throttling."""
    import time

    drafts = db.query(OutreachDraft).filter(
        OutreachDraft.batch_id == batch_id,
        OutreachDraft.tenant_id == tenant_id,
        OutreachDraft.status == DraftStatus.APPROVED,
    ).all()

    if not drafts:
        return {"error": "No approved drafts in batch", "sent": 0}

    sent = 0
    errors = 0

    for draft in drafts:
        result = send_single_draft(draft.draft_id, db, tenant_id)
        if result.get("status") == "sent":
            sent += 1
            # Throttle between sends
            from app.core.config import settings as app_cfg
            delay = random.randint(app_cfg.SEND_DELAY_MIN_SEC, app_cfg.SEND_DELAY_MAX_SEC)
            time.sleep(delay)
        else:
            errors += 1

    return {"batch_id": batch_id, "sent": sent, "errors": errors, "total": len(drafts)}


# ─── Helpers ──────────────────────────────────────────────────────


def _substitute_placeholders(
    subject: str,
    body_html: str,
    body_text: str,
    contact: ContactDetails,
    lead: Optional[LeadDetails],
    mailbox: SenderMailbox,
) -> Tuple[str, str, str]:
    """Apply Jinja2 placeholder substitution with manual fallback."""
    _job_title = (lead.job_title if lead and lead.job_title else "")
    _job_location = (lead.state if lead and lead.state else "")
    _company = (lead.client_name if lead and lead.client_name else (contact.client_name or ""))

    template_context = {
        "contact_first_name": contact.first_name or "",
        "contact_last_name": contact.last_name or "",
        "company_name": _company,
        "contact_title": contact.title or "",
        "job_title": _job_title,
        "job_location": _job_location,
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
            "first_name": mailbox.resolved_first_name if hasattr(mailbox, 'resolved_first_name') else (mailbox.display_name or mailbox.email).split()[0],
        },
        "sender_first_name": mailbox.resolved_first_name if hasattr(mailbox, 'resolved_first_name') else (mailbox.display_name or mailbox.email).split()[0],
    }

    try:
        from jinja2 import Template as Jinja2Template
        subject = Jinja2Template(subject).render(**template_context)
        body_html = Jinja2Template(body_html).render(**template_context)
        body_text = Jinja2Template(body_text).render(**template_context)
    except Exception:
        pass

    # Always do string replacement for {{placeholder}} style
    _sfn = mailbox.resolved_first_name if hasattr(mailbox, 'resolved_first_name') else (mailbox.display_name or mailbox.email).split()[0]
    _ph_map = {
        "{{contact_first_name}}": contact.first_name or "",
        "{{contact_last_name}}": contact.last_name or "",
        "{{company_name}}": _company,
        "{{contact_title}}": contact.title or "",
        "{{job_title}}": _job_title,
        "{{job_location}}": _job_location,
        "{{sender_first_name}}": _sfn,
    }
    for ph, val in _ph_map.items():
        subject = subject.replace(ph, val)
        body_html = body_html.replace(ph, val)
        body_text = body_text.replace(ph, val)

    return subject, body_html, body_text
