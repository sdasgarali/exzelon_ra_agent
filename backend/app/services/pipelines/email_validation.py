"""Email validation pipeline service."""
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
import structlog

from app.db.base import SessionLocal
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.contact import ContactDetails
from app.db.models.email_validation import EmailValidationResult, ValidationStatus
from app.db.models.job_run import JobRun, JobStatus
from app.core.config import settings
from app.services.adapters.email_validation.mock import MockEmailValidationAdapter
from app.services.adapters.email_validation.neverbounce import NeverBounceAdapter
from app.services.adapters.email_validation.zerobounce import ZeroBounceAdapter
from app.services.adapters.email_validation.hunter import HunterAdapter
from app.services.adapters.email_validation.clearout import ClearoutAdapter
from app.services.adapters.email_validation.emailable import EmailableAdapter
from app.services.adapters.email_validation.mailboxvalidator import MailboxValidatorAdapter
from app.services.adapters.email_validation.reacher import ReacherAdapter
from app.services.pipelines.cancel_helper import check_cancel

logger = structlog.get_logger()


def get_email_validation_adapter(provider: Optional[str] = None):
    """Get the configured email validation adapter."""
    provider = provider or settings.EMAIL_VALIDATION_PROVIDER

    adapters = {
        "neverbounce": NeverBounceAdapter,
        "zerobounce": ZeroBounceAdapter,
        "hunter": HunterAdapter,
        "clearout": ClearoutAdapter,
        "emailable": EmailableAdapter,
        "mailboxvalidator": MailboxValidatorAdapter,
        "reacher": ReacherAdapter,
    }

    adapter_class = adapters.get(provider)
    if adapter_class:
        return adapter_class()
    return MockEmailValidationAdapter()


def run_email_validation_pipeline(
    emails: Optional[List[str]] = None,
    provider: Optional[str] = None,
    triggered_by: str = "system",
    tenant_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the email validation pipeline.

    Steps:
    1. Get emails to validate (from parameter or unvalidated contacts)
    2. Clean and normalize emails
    3. Validate via provider
    4. Store results
    5. Update contact validation status

    Args:
        emails: Optional list of specific emails to validate
        provider: Email validation provider name
        triggered_by: Who triggered the pipeline
    """
    db = SessionLocal()
    counters = {"validated": 0, "valid": 0, "invalid": 0, "catch_all": 0, "unknown": 0, "errors": 0}

    # Create job run record
    job_run = JobRun(
        tenant_id=tenant_id or 1,
        pipeline_name="email_validation",
        status=JobStatus.RUNNING,
        triggered_by=triggered_by,
    )
    db.add(job_run)
    db.commit()

    try:
        logger.info("Starting email validation pipeline")

        adapter = get_email_validation_adapter(provider)

        # Get emails to validate
        if emails is None:
            # Get unvalidated contact emails
            q = db.query(ContactDetails).filter(
                ContactDetails.validation_status.is_(None),
                ContactDetails.is_archived == False
            )
            if tenant_id is not None:
                q = q.filter(ContactDetails.tenant_id == tenant_id)
            contacts = q.limit(500).all()
            emails = [c.email for c in contacts]

        if not emails:
            logger.info("No emails to validate")
            job_run.status = JobStatus.COMPLETED
            job_run.ended_at = datetime.utcnow()
            job_run.counters_json = json.dumps(counters)
            db.commit()
            return counters

        logger.info(f"Validating {len(emails)} emails")

        # Clean and deduplicate
        clean_emails = list(set([e.lower().strip() for e in emails if e]))

        # Validate
        total_emails = len(clean_emails)
        for idx, email in enumerate(clean_emails):
            # Cancel check
            if check_cancel(job_run.run_id, db):
                logger.info("Email validation cancelled by user", processed=idx)
                break

            # Update progress every 10 items
            if total_emails > 0 and idx % 10 == 0:
                job_run.progress_pct = int((idx / total_emails) * 100)
                db.commit()

            try:
                # Check if already validated
                existing = db.query(EmailValidationResult).filter(
                    EmailValidationResult.email == email
                ).first()

                if existing:
                    # Update contact with existing status
                    update_contact_validation_status(db, email, existing.status)
                    counters["validated"] += 1
                    continue

                # Validate email
                result = adapter.validate_email(email)

                # Store result
                validation = EmailValidationResult(
                    email=email,
                    provider=provider or settings.EMAIL_VALIDATION_PROVIDER,
                    status=result["status"],
                    sub_status=str(result.get("sub_status")),
                    raw_response_json=json.dumps(result.get("raw_response", {})),
                )
                db.add(validation)

                # Update contact
                update_contact_validation_status(db, email, result["status"])

                # Update counters
                counters["validated"] += 1
                if result["status"] == ValidationStatus.VALID:
                    counters["valid"] += 1
                elif result["status"] == ValidationStatus.INVALID:
                    counters["invalid"] += 1
                elif result["status"] == ValidationStatus.CATCH_ALL:
                    counters["catch_all"] += 1
                else:
                    counters["unknown"] += 1

            except Exception as e:
                logger.error("Error validating email", error=str(e), email=email)
                counters["errors"] += 1

        db.commit()

        # Update leads that have validated contacts
        update_lead_validation_status(db)

        # Calculate bounce rate
        total_validated = counters["valid"] + counters["invalid"] + counters["catch_all"] + counters["unknown"]
        bounce_rate = (counters["invalid"] / total_validated * 100) if total_validated > 0 else 0
        counters["estimated_bounce_rate"] = round(bounce_rate, 2)

        # Add provider and diagnostics info
        provider_name = provider or settings.EMAIL_VALIDATION_PROVIDER
        counters["provider_used"] = provider_name
        diag_status = "success"
        diag_error_type = None
        if counters["errors"] > 0 and counters["errors"] > total_validated * 0.5:
            diag_status = "error"
            diag_error_type = "high_error_rate"
        elif counters["errors"] > 0:
            diag_status = "warning"
        counters["api_diagnostics"] = [{
            "adapter": provider_name,
            "status": diag_status,
            "emails_checked": counters["validated"],
            "error_type": diag_error_type,
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

        logger.info("Email validation completed", counters=counters)
        return counters

    except Exception as e:
        logger.error("Email validation pipeline failed", error=str(e))
        job_run.status = JobStatus.FAILED
        job_run.error_message = str(e)
        job_run.ended_at = datetime.utcnow()
        db.commit()
        raise
    finally:
        db.close()


def update_contact_validation_status(db, email: str, status: ValidationStatus):
    """Update contact validation status."""
    contacts = db.query(ContactDetails).filter(
        ContactDetails.email == email
    ).all()

    for contact in contacts:
        contact.validation_status = status.value


def update_lead_validation_status(db):
    """Update leads that have validated contact emails."""
    leads = db.query(LeadDetails).filter(
        LeadDetails.lead_status == LeadStatus.ENRICHED,
        LeadDetails.contact_email.isnot(None)
    ).all()

    for lead in leads:
        validation = db.query(EmailValidationResult).filter(
            EmailValidationResult.email == lead.contact_email.lower()
        ).first()

        if validation and validation.status == ValidationStatus.VALID:
            lead.lead_status = LeadStatus.VALIDATED
