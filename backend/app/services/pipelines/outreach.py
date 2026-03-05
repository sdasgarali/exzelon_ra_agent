"""Outreach pipeline service."""
import json
import os
import smtplib
import uuid
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List
import pandas as pd
import structlog

from app.db.base import SessionLocal
from app.db.models.lead import LeadDetails, LeadStatus, CLOSED_STATUSES, is_closed_status
from app.db.models.contact import ContactDetails
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.email_validation import EmailValidationResult, ValidationStatus
from app.db.models.outreach import OutreachEvent, OutreachStatus, OutreachChannel
from app.db.models.suppression import SuppressionList
from app.db.models.job_run import JobRun, JobStatus
from app.core.config import settings
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.services.pipelines.cancel_helper import check_cancel

logger = structlog.get_logger()


def send_outreach_email(
    sender_mailbox: SenderMailbox,
    to_email: str,
    subject: str,
    body_html: str,
    body_text: str
) -> Dict[str, Any]:
    """Send an outreach email using the sender mailbox's own SMTP credentials.

    Follows the same proven pattern as warmup peer emails.
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{sender_mailbox.display_name or sender_mailbox.email} <{sender_mailbox.email}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Message-ID"] = f"<{uuid.uuid4()}@{sender_mailbox.email.split('@')[1]}>"

        if body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        smtp_host = sender_mailbox.smtp_host or "smtp.office365.com"
        server = smtplib.SMTP(smtp_host, sender_mailbox.smtp_port or 587, timeout=30)
        server.starttls()
        from app.core.encryption import decrypt_field
        server.login(sender_mailbox.email, decrypt_field(sender_mailbox.password))
        server.sendmail(sender_mailbox.email, to_email, msg.as_string())
        server.quit()

        return {"success": True, "message_id": msg["Message-ID"], "error": None}
    except Exception as e:
        logger.error("SMTP send failed", sender=sender_mailbox.email, to=to_email, error=str(e))
        return {"success": False, "message_id": None, "error": str(e)}




def render_signature_html(sig_json: str) -> str:
    """Render structured signature JSON to clean HTML block."""
    try:
        sig = json.loads(sig_json)
    except (json.JSONDecodeError, TypeError):
        return ''

    parts = []
    if sig.get('sender_name'):
        parts.append(f'<strong style="font-size:14px;color:#333333;">{sig["sender_name"]}</strong>')
    if sig.get('title'):
        parts.append(f'<span style="font-size:13px;color:#555555;">{sig["title"]}</span>')
    if sig.get('company'):
        parts.append(f'<span style="font-size:13px;color:#555555;">{sig["company"]}</span>')

    contact_parts = []
    if sig.get('phone'):
        contact_parts.append(sig['phone'])
    if sig.get('email'):
        contact_parts.append(f'<a href="mailto:{sig["email"]}" style="color:#0066cc;text-decoration:none;">{sig["email"]}</a>')
    if contact_parts:
        parts.append('<span style="font-size:12px;color:#666666;">' + ' | '.join(contact_parts) + '</span>')

    if sig.get('website'):
        url = sig['website']
        if not url.startswith('http'):
            url = 'https://' + url
        parts.append(f'<a href="{url}" style="font-size:12px;color:#0066cc;text-decoration:none;">{sig["website"]}</a>')

    if sig.get('address'):
        parts.append(f'<span style="font-size:12px;color:#666666;">{sig["address"]}</span>')

    if not parts:
        return ''

    lines_html = '<br>'.join(parts)
    return (
        '<div style="margin-top:20px;padding-top:12px;border-top:1px solid #cccccc;font-family:Arial,sans-serif;">'
        + lines_html
        + '</div>'
    )

def get_active_template(db):
    """Get the currently active email template, if any."""
    from app.db.models.email_template import EmailTemplate, TemplateStatus
    return db.query(EmailTemplate).filter(
        EmailTemplate.status == TemplateStatus.ACTIVE
    ).first()


def generate_unsub_footer(tracking_id: str, base_url: str = "") -> Dict[str, str]:
    """Generate HTML and text unsubscribe footers with a clickable link."""
    from app.core.tracking import generate_tracking_token
    if not base_url:
        base_url = settings.EFFECTIVE_BASE_URL
    token = generate_tracking_token(tracking_id)
    unsub_url = f"{base_url}/unsub/{tracking_id}?token={token}"
    html = (
        '<hr style="border:none;border-top:1px solid #eee;margin-top:20px;" />'
        '<p style="font-size:11px;color:#999;text-align:center;">'
        f'<a href="{unsub_url}" style="color:#999;text-decoration:underline;">Unsubscribe</a>'
        ' | Reply with "UNSUBSCRIBE" to opt out</p>'
    )
    text = f"\n---\nUnsubscribe: {unsub_url}\nOr reply with \"UNSUBSCRIBE\" to opt out."
    return {"html": html, "text": text, "url": unsub_url}


def render_template(template, contact, lead, mailbox, signature_html, logo_url="https://www.exzelon.com/gallery/logo.png", unsub_url=""):
    """Render an email template with placeholder substitution."""

    # Determine sender first name
    sender_first = ""
    if mailbox.display_name:
        sender_first = mailbox.display_name.split()[0]
    else:
        sender_first = mailbox.email.split("@")[0]

    # Build placeholder map
    placeholders = {
        "{{contact_first_name}}": contact.first_name or "",
        "{{sender_first_name}}": sender_first,
        "{{job_title}}": (lead.job_title if lead and lead.job_title else "Open Position"),
        "{{job_location}}": (lead.state if lead and lead.state else ""),
        "{{company_name}}": (lead.client_name if lead and lead.client_name else (contact.client_name or "")),
        "{{signature}}": signature_html,
        "{{logo_url}}": logo_url,
        "{{unsubscribe_link}}": unsub_url,
    }

    subject = template.subject
    body_html = template.body_html
    body_text = template.body_text or ""

    for placeholder, value in placeholders.items():
        subject = subject.replace(placeholder, value)
        body_html = body_html.replace(placeholder, value)
        body_text = body_text.replace(placeholder, value)

    return subject, body_html, body_text


def check_send_eligibility(db, contact: ContactDetails) -> tuple[bool, str]:
    """
    Check if a contact is eligible for outreach.

    Returns (eligible, reason)
    """
    # Check contact-level outreach status first
    from app.db.models.contact import OutreachStatus as ContactOutreachStatus
    if hasattr(contact, 'outreach_status') and contact.outreach_status:
        if contact.outreach_status == ContactOutreachStatus.UNSUBSCRIBED:
            return False, "Unsubscribed"
        if contact.outreach_status == ContactOutreachStatus.INACTIVE:
            return False, "Inactive"

    email = contact.email.lower()

    # Check suppression list
    suppressed = db.query(SuppressionList).filter(
        SuppressionList.email == email,
        (SuppressionList.expires_at.is_(None) | (SuppressionList.expires_at > datetime.utcnow()))
    ).first()
    if suppressed:
        return False, f"Suppressed: {suppressed.reason}"

    # Check validation status
    if contact.validation_status not in ["valid", "Valid"]:
        validation = db.query(EmailValidationResult).filter(
            EmailValidationResult.email == email
        ).order_by(EmailValidationResult.validated_at.desc()).first()

        if not validation or validation.status != ValidationStatus.VALID:
            return False, "Email not validated or invalid"

    # Check cooldown period for this specific contact
    cooldown_date = datetime.utcnow() - timedelta(days=settings.COOLDOWN_DAYS)
    recent_outreach = db.query(OutreachEvent).filter(
        OutreachEvent.contact_id == contact.contact_id,
        OutreachEvent.sent_at >= cooldown_date,
        OutreachEvent.status == OutreachStatus.SENT
    ).first()
    if recent_outreach:
        return False, f"Cooldown: sent on {recent_outreach.sent_at.date()}"

    # Check per-lead contact limit (only contacts linked to the same lead)
    if contact.lead_id:
        lead_contacts_sent = db.query(OutreachEvent).join(ContactDetails).filter(
            ContactDetails.lead_id == contact.lead_id,
            OutreachEvent.status == OutreachStatus.SENT
        ).count()
        if lead_contacts_sent >= settings.MAX_CONTACTS_PER_COMPANY_PER_JOB:
            return False, f"Max contacts per lead reached ({lead_contacts_sent}/{settings.MAX_CONTACTS_PER_COMPANY_PER_JOB})"
    else:
        # Fallback for legacy contacts without lead_id
        company_contacts_sent = db.query(OutreachEvent).join(ContactDetails).filter(
            ContactDetails.client_name == contact.client_name,
            OutreachEvent.status == OutreachStatus.SENT
        ).count()
        if company_contacts_sent >= settings.MAX_CONTACTS_PER_COMPANY_PER_JOB:
            return False, "Max contacts per company reached"

    return True, "Eligible"


def run_outreach_mailmerge_pipeline(
    triggered_by: str = "system",
) -> Dict[str, Any]:
    """
    Generate mail merge export package.

    Creates:
    1. Verified contacts CSV
    2. Word template guide
    """
    db = SessionLocal()
    counters = {"eligible": 0, "skipped": 0, "exported": 0}

    # Create job run record
    job_run = JobRun(
        pipeline_name="outreach_mailmerge",
        status=JobStatus.RUNNING,
        triggered_by=triggered_by,
    )
    db.add(job_run)
    db.commit()

    try:
        logger.info("Starting mailmerge export")

        # Get validated contacts (excluding archived)
        contacts = db.query(ContactDetails).filter(
            ContactDetails.validation_status == "valid",
            ContactDetails.is_archived == False
        ).all()

        eligible_contacts = []
        for contact in contacts:
            eligible, reason = check_send_eligibility(db, contact)
            if eligible:
                eligible_contacts.append(contact)
                counters["eligible"] += 1
            else:
                counters["skipped"] += 1
                logger.debug("Contact skipped", email=contact.email, reason=reason)

        if not eligible_contacts:
            logger.info("No eligible contacts for mailmerge")
            job_run.status = JobStatus.COMPLETED
            job_run.ended_at = datetime.utcnow()
            job_run.counters_json = json.dumps(counters)
            db.commit()
            return counters

        # Create export directory
        os.makedirs(settings.EXPORT_PATH, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Export to CSV
        data = []
        for contact in eligible_contacts:
            data.append({
                "First Name": contact.first_name,
                "Last Name": contact.last_name,
                "Email": contact.email,
                "Title": contact.title,
                "Company": contact.client_name,
                "State": contact.location_state
            })

        df = pd.DataFrame(data)
        csv_path = os.path.join(settings.EXPORT_PATH, f"mailmerge_contacts_{timestamp}.csv")
        df.to_csv(csv_path, index=False)
        counters["exported"] = len(data)

        # Create template guide
        guide_content = f"""
MAIL MERGE GUIDE
================

Generated: {datetime.now().isoformat()}
Total Contacts: {len(data)}

MERGE FIELDS:
- {{First Name}} - Contact first name
- {{Last Name}} - Contact last name
- {{Email}} - Contact email address
- {{Title}} - Contact job title
- {{Company}} - Company name
- {{State}} - State

STEPS:
1. Open your Word template
2. Use Insert > Mail Merge > Start Mail Merge
3. Select the CSV file: {csv_path}
4. Insert merge fields into your template
5. Preview and send

COMPLIANCE NOTES:
- Always include unsubscribe link
- Include company mailing address: {settings.company_address if hasattr(settings, 'company_address') else 'Configure in settings'}
- Do not send to same contact within {settings.COOLDOWN_DAYS} days
"""

        guide_path = os.path.join(settings.EXPORT_PATH, f"mailmerge_guide_{timestamp}.txt")
        with open(guide_path, "w") as f:
            f.write(guide_content)

        # Record outreach events
        total_eligible = len(eligible_contacts)
        for idx, contact in enumerate(eligible_contacts):
            # Cancel check
            if check_cancel(job_run.run_id, db):
                logger.info("Mailmerge cancelled by user", processed=idx)
                break

            # Update progress
            if total_eligible > 0 and idx % 10 == 0:
                job_run.progress_pct = int((idx / total_eligible) * 100)
                db.commit()

            event = OutreachEvent(
                contact_id=contact.contact_id,
                channel=OutreachChannel.MAILMERGE,
                status=OutreachStatus.SENT,
                skip_reason=None,
            )
            db.add(event)

            # Update contact last outreach date
            contact.last_outreach_date = datetime.now().isoformat()

        db.commit()

        # Update job run
        db.refresh(job_run)
        if job_run.is_cancel_requested == 1:
            job_run.status = JobStatus.CANCELLED
        else:
            job_run.status = JobStatus.COMPLETED
        job_run.progress_pct = 100
        job_run.ended_at = datetime.utcnow()
        job_run.counters_json = json.dumps(counters)
        job_run.logs_path = csv_path
        db.commit()

        logger.info("Mailmerge export completed", counters=counters, csv_path=csv_path)
        return counters

    except Exception as e:
        logger.error("Mailmerge pipeline failed", error=str(e))
        job_run.status = JobStatus.FAILED
        job_run.error_message = str(e)
        job_run.ended_at = datetime.utcnow()
        db.commit()
        raise
    finally:
        db.close()


def run_outreach_send_pipeline(
    dry_run: bool = True,
    limit: int = 30,
    triggered_by: str = "system",
) -> Dict[str, Any]:
    """
    Send emails programmatically with rate limiting.
    """
    db = SessionLocal()
    counters = {"sent": 0, "skipped": 0, "errors": 0}
    skip_reasons: Dict[str, int] = {"cooldown": 0, "daily_limit": 0, "no_mailbox": 0, "dry_run": 0, "not_eligible": 0}
    per_mailbox: Dict[str, Dict[str, int]] = {}

    # Create job run record
    job_run = JobRun(
        pipeline_name="outreach_send",
        status=JobStatus.RUNNING,
        triggered_by=triggered_by,
    )
    db.add(job_run)
    db.commit()

    try:
        logger.info("Starting outreach send", dry_run=dry_run, limit=limit)

        # Check daily limit
        today = datetime.utcnow().date()
        today_sent = db.query(OutreachEvent).filter(
            OutreachEvent.sent_at >= datetime.combine(today, datetime.min.time()),
            OutreachEvent.status == OutreachStatus.SENT,
            OutreachEvent.channel != OutreachChannel.MAILMERGE
        ).count()

        remaining_limit = min(limit, settings.DAILY_SEND_LIMIT - today_sent)
        if remaining_limit <= 0:
            logger.info("Daily send limit reached")
            job_run.status = JobStatus.COMPLETED
            job_run.ended_at = datetime.utcnow()
            job_run.counters_json = json.dumps({"message": "Daily limit reached"})
            db.commit()
            return counters

        # Get validated contacts not yet sent (excluding contacts from closed/archived leads)
        contacts = db.query(ContactDetails).filter(
            ContactDetails.validation_status == "valid",
            ContactDetails.is_archived == False
        ).all()

        # Get active email template
        active_template = get_active_template(db)
        used_template_id = active_template.template_id if active_template else None

        sent_count = 0
        total_contacts = len(contacts)
        for idx, contact in enumerate(contacts):
            # Cancel check
            if check_cancel(job_run.run_id, db):
                logger.info("Outreach send cancelled by user", processed=idx)
                break

            # Update progress
            if total_contacts > 0 and idx % 5 == 0:
                job_run.progress_pct = int((idx / total_contacts) * 100)
                db.commit()

            if sent_count >= remaining_limit:
                break

            eligible, reason = check_send_eligibility(db, contact)
            if not eligible:
                counters["skipped"] += 1
                if "cooldown" in reason.lower():
                    skip_reasons["cooldown"] += 1
                elif "limit" in reason.lower():
                    skip_reasons["daily_limit"] += 1
                else:
                    skip_reasons["not_eligible"] += 1
                continue

            # Get sending mailbox (Cold Ready or Active, least loaded, with successful connection)
            sending_mailbox = db.query(SenderMailbox).filter(
                SenderMailbox.is_active == True,
                SenderMailbox.warmup_status.in_([WarmupStatus.COLD_READY, WarmupStatus.ACTIVE]),
                SenderMailbox.emails_sent_today < SenderMailbox.daily_send_limit,
                SenderMailbox.connection_status == "successful"
            ).order_by(SenderMailbox.emails_sent_today.asc()).first()

            if not sending_mailbox:
                logger.warning("No available sender mailbox with successful connection")
                counters["skipped"] += 1
                skip_reasons["no_mailbox"] += 1
                continue

            signature_html = ""
            if sending_mailbox.email_signature_json:
                signature_html = render_signature_html(sending_mailbox.email_signature_json)

            # Pre-create event to get tracking_id for unsub link
            event = OutreachEvent(
                contact_id=contact.contact_id,
                channel=OutreachChannel.SMTP,
                status=OutreachStatus.SKIPPED,
                skip_reason="pending_send",
                template_id=used_template_id,
                sender_mailbox_id=sending_mailbox.mailbox_id,
            )
            db.add(event)
            db.flush()  # Get tracking_id

            # Generate unsub footer
            unsub_footer = generate_unsub_footer(event.tracking_id)

            # Use template if available, otherwise fallback to hardcoded
            if active_template:
                subject, body_content, body_text = render_template(
                    active_template, contact, None, sending_mailbox, signature_html,
                    unsub_url=unsub_footer["url"]
                )
                # Append unsub footer if template doesn't include {{unsubscribe_link}}
                if "unsub/" not in body_content:
                    body_content += unsub_footer["html"]
                    body_text += unsub_footer["text"]
            else:
                body_content = f"<p>Dear {contact.first_name},</p>"
                body_content += "<p>We noticed your company is hiring and wanted to reach out about our staffing solutions.</p>"
                body_content += signature_html
                body_content += unsub_footer["html"]

                subject = f"Exciting Opportunity at {contact.client_name}"
                body_text = f"Dear {contact.first_name},\nWe noticed your company is hiring..."
                body_text += unsub_footer["text"]

            # Initialize per-mailbox tracking
            mbx_email = sending_mailbox.email
            if mbx_email not in per_mailbox:
                per_mailbox[mbx_email] = {"sent": 0, "errors": 0}

            try:
                if dry_run:
                    logger.info("DRY RUN - Would send to", email=contact.email, via=sending_mailbox.email)
                    event.status = OutreachStatus.SKIPPED
                    event.skip_reason = "dry_run"
                    skip_reasons["dry_run"] += 1
                else:
                    result = send_outreach_email(
                        sender_mailbox=sending_mailbox,
                        to_email=contact.email,
                        subject=subject,
                        body_html=body_content,
                        body_text=body_text
                    )

                    if result["success"]:
                        event.status = OutreachStatus.SENT
                        event.skip_reason = None
                        counters["sent"] += 1
                        sent_count += 1
                        per_mailbox[mbx_email]["sent"] += 1
                        # Update mailbox counters
                        sending_mailbox.emails_sent_today += 1
                        sending_mailbox.total_emails_sent += 1
                        sending_mailbox.last_sent_at = datetime.utcnow()
                    else:
                        event.status = OutreachStatus.SKIPPED
                        event.skip_reason = result.get("error", "Unknown error")
                        counters["errors"] += 1
                        per_mailbox[mbx_email]["errors"] += 1

                # Update event with email content
                event.subject = subject
                event.body_html = body_content
                event.body_text = body_text
                if not dry_run and result.get("success"):
                    event.message_id = result["message_id"]

                if event.status == OutreachStatus.SENT:
                    contact.last_outreach_date = datetime.now().isoformat()

            except Exception as e:
                logger.error("Error sending email", error=str(e), email=contact.email)
                event.status = OutreachStatus.SKIPPED
                event.skip_reason = str(e)
                counters["errors"] += 1
                per_mailbox[mbx_email]["errors"] += 1

        db.commit()

        # Add enriched counter data
        counters["skip_reasons"] = skip_reasons
        counters["per_mailbox"] = per_mailbox
        counters["total"] = counters["sent"] + counters["skipped"] + counters["errors"]
        diag_status = "success"
        if counters["errors"] > 0 and counters["sent"] == 0:
            diag_status = "error"
        elif counters["errors"] > 0:
            diag_status = "warning"
        counters["api_diagnostics"] = [{
            "adapter": "smtp",
            "status": diag_status,
            "emails_sent": counters["sent"],
            "error_type": None,
            "error_message": None,
        }]

        # Update job run
        db.refresh(job_run)
        if job_run.is_cancel_requested == 1:
            job_run.status = JobStatus.CANCELLED
        else:
            job_run.status = JobStatus.COMPLETED
        job_run.progress_pct = 100
        job_run.ended_at = datetime.utcnow()
        job_run.counters_json = json.dumps(counters)
        db.commit()

        logger.info("Outreach send completed", counters=counters)
        return counters

    except Exception as e:
        logger.error("Outreach send pipeline failed", error=str(e))
        job_run.status = JobStatus.FAILED
        job_run.error_message = str(e)
        job_run.ended_at = datetime.utcnow()
        counters["skip_reasons"] = skip_reasons
        counters["per_mailbox"] = per_mailbox
        counters["total"] = counters["sent"] + counters["skipped"] + counters["errors"]
        counters["api_diagnostics"] = [{"adapter": "smtp", "status": "error", "emails_sent": counters["sent"], "error_type": "smtp_failure", "error_message": str(e)[:200]}]
        job_run.counters_json = json.dumps(counters)
        db.commit()
        raise
    finally:
        db.close()


def run_outreach_for_lead(
    lead_id: int,
    dry_run: bool = True,
    triggered_by: str = "system",
) -> Dict[str, Any]:
    """
    Send outreach emails to contacts of a specific lead only.
    """
    db = SessionLocal()
    counters = {"sent": 0, "skipped": 0, "errors": 0, "lead_id": lead_id}

    try:
        logger.info("Starting outreach for lead", lead_id=lead_id, dry_run=dry_run)

        lead = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id).first()
        if not lead:
            return {"error": "Lead not found", "lead_id": lead_id}

        # Skip closed or archived leads
        if is_closed_status(lead.lead_status):
            return {"message": f"Lead is closed ({lead.lead_status.value}), skipping outreach", **counters}
        if lead.is_archived:
            return {"message": "Lead is archived, skipping outreach", **counters}

        # Get contacts via junction table + legacy FK
        junction_cids = [row[0] for row in db.query(LeadContactAssociation).filter(
            LeadContactAssociation.lead_id == lead_id
        ).all()]

        if junction_cids:
            contacts = db.query(ContactDetails).filter(
                (ContactDetails.lead_id == lead_id) |
                (ContactDetails.contact_id.in_(junction_cids))
            ).all()
        else:
            contacts = db.query(ContactDetails).filter(
                ContactDetails.lead_id == lead_id
            ).all()

        if not contacts:
            return {"message": "No contacts found for this lead", **counters}

        # Get active email template
        active_template = get_active_template(db)
        used_template_id = active_template.template_id if active_template else None

        for contact in contacts:
            eligible, reason = check_send_eligibility(db, contact)
            if not eligible:
                counters["skipped"] += 1
                logger.debug("Contact skipped", email=contact.email, reason=reason)
                continue

            # Get sending mailbox (Cold Ready or Active, least loaded, with successful connection)
            sending_mailbox = db.query(SenderMailbox).filter(
                SenderMailbox.is_active == True,
                SenderMailbox.warmup_status.in_([WarmupStatus.COLD_READY, WarmupStatus.ACTIVE]),
                SenderMailbox.emails_sent_today < SenderMailbox.daily_send_limit,
                SenderMailbox.connection_status == "successful"
            ).order_by(SenderMailbox.emails_sent_today.asc()).first()

            if not sending_mailbox:
                logger.warning("No available sender mailbox with successful connection")
                counters["skipped"] += 1
                continue

            signature_html = ""
            if sending_mailbox.email_signature_json:
                signature_html = render_signature_html(sending_mailbox.email_signature_json)

            # Pre-create event to get tracking_id for unsub link
            event = OutreachEvent(
                contact_id=contact.contact_id,
                lead_id=lead_id,
                channel=OutreachChannel.SMTP,
                status=OutreachStatus.SKIPPED,
                skip_reason="pending_send",
                template_id=used_template_id,
                sender_mailbox_id=sending_mailbox.mailbox_id,
            )
            db.add(event)
            db.flush()  # Get tracking_id

            # Generate unsub footer
            unsub_footer = generate_unsub_footer(event.tracking_id)

            # Use template if available, otherwise fallback to hardcoded
            if active_template:
                subject, body_content, body_text = render_template(
                    active_template, contact, lead, sending_mailbox, signature_html,
                    unsub_url=unsub_footer["url"]
                )
                # Append unsub footer if template doesn't include {{unsubscribe_link}}
                if "unsub/" not in body_content:
                    body_content += unsub_footer["html"]
                    body_text += unsub_footer["text"]
            else:
                body_content = f"<p>Dear {contact.first_name},</p>"
                body_content += f"<p>We noticed {lead.client_name} is hiring for {lead.job_title} and wanted to reach out about our staffing solutions.</p>"
                body_content += signature_html
                body_content += unsub_footer["html"]

                subject = f"Staffing for {lead.job_title} at {lead.client_name}"
                body_text = f"Dear {contact.first_name},\nWe noticed {lead.client_name} is hiring for {lead.job_title}..."
                body_text += unsub_footer["text"]

            try:
                if dry_run:
                    logger.info("DRY RUN - Would send to", email=contact.email, via=sending_mailbox.email)
                    event.status = OutreachStatus.SKIPPED
                    event.skip_reason = "dry_run"
                else:
                    result = send_outreach_email(
                        sender_mailbox=sending_mailbox,
                        to_email=contact.email,
                        subject=subject,
                        body_html=body_content,
                        body_text=body_text
                    )
                    if result["success"]:
                        event.status = OutreachStatus.SENT
                        event.skip_reason = None
                        counters["sent"] += 1
                        # Update mailbox counters
                        sending_mailbox.emails_sent_today += 1
                        sending_mailbox.total_emails_sent += 1
                        sending_mailbox.last_sent_at = datetime.utcnow()
                    else:
                        event.status = OutreachStatus.SKIPPED
                        event.skip_reason = result.get("error", "Unknown error")
                        counters["errors"] += 1

                # Update event with email content
                event.subject = subject
                event.body_html = body_content
                event.body_text = body_text
                if not dry_run and result.get("success"):
                    event.message_id = result["message_id"]

                if event.status == OutreachStatus.SENT:
                    contact.last_outreach_date = datetime.now().isoformat()

            except Exception as e:
                logger.error("Error sending to contact", error=str(e), email=contact.email)
                event.status = OutreachStatus.SKIPPED
                event.skip_reason = str(e)
                counters["errors"] += 1

        db.commit()
        logger.info("Lead outreach completed", counters=counters)
        return counters

    except Exception as e:
        logger.error("Lead outreach failed", error=str(e))
        raise
    finally:
        db.close()
