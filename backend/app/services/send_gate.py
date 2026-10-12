"""Centralized Send Gate — unified safety enforcement for all outreach channels.

Every email-sending path in the system MUST call ``unified_send_gate()``
before transmitting.  The gate runs an ordered sequence of checks (cheapest
first) and returns a structured result that callers can use for logging,
user feedback, and branch decisions.

Sending paths wired to this gate:
- Campaign Engine  (campaign_engine.py)
- Pipeline Outreach (outreach.py — run_outreach_send_pipeline / run_outreach_for_lead)
- Email Preview / Draft Send (email_preview_service.py)
- AI Reply Agent (ai_reply_agent_service.py)

The mail-merge export path (CSV only, no actual send) is **not** wired here.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

import structlog
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.db.models.contact import ContactDetails, OutreachStatus as ContactOutreachStatus
from app.db.models.outreach import OutreachEvent, OutreachStatus
from app.db.models.email_validation import ValidationStatus
from app.db.models.suppression import SuppressionList
from app.db.models.campaign import Campaign
from app.db.models.lead import LeadDetails
from app.core.config import settings

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class GateCheckResult:
    """Outcome of a single safety check."""
    name: str
    passed: bool
    reason: str = ""


@dataclass
class SendGateResult:
    """Aggregate outcome of the send gate."""
    allowed: bool
    reason_code: str = ""
    reason_message: str = ""
    checks: List[GateCheckResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# User-friendly message templates
# ---------------------------------------------------------------------------

_MESSAGES = {
    "SEND_QUOTA_EXCEEDED": (
        "Monthly send quota reached ({used}/{limit}). "
        "Upgrade your plan to send more this month."
    ),
    "UNSUBSCRIBED": "This contact has unsubscribed from communications.",
    "INACTIVE": "This contact is marked as inactive.",
    "SUPPRESSED": "This contact is on the suppression list: {reason}",
    "INVALID_EMAIL": "This contact's email has not been validated.",
    "CONTACT_LEAD_COOLDOWN": (
        "An email was already sent to this contact for this lead on {date}. "
        "Cooldown: {days} days."
    ),
    "CONTACT_COOLDOWN": (
        "An email was already sent to this contact on {date}. "
        "Cooldown: {days} days."
    ),
    "LEAD_CONTACT_LIMIT": (
        "Maximum contacts ({n}/{max}) already reached for this lead."
    ),
    "COMPANY_CAP": (
        "Too many contacts ({n}/{max}) already emailed at {company}."
    ),
    "SEQUENCE_FATIGUE": (
        "This contact has received {n} unanswered emails in {days} days."
    ),
    "DOMAIN_THROTTLE": (
        "Daily email limit reached for @{domain} ({n}/{max} today)."
    ),
    "AI_BLOCKED": "AI safety agent blocked this send: {reasons}",
    "BILLING_SUSPENDED": (
        "Account suspended for non-payment. Settle outstanding invoices to resume sending."
    ),
    "NO_POSTAL_ADDRESS": (
        "Add your company's postal address in Settings → Business Rules → Company Profile before sending; "
        "it's required in every outreach email (CAN-SPAM)."
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Send-safety business rules a tenant may tune, with the platform default and the
# config value that caps a tenant override. The effective ceiling is the larger of
# that config value and the super admin's global setting (so raising the global
# value raises it for everyone). Values stored before the range checks existed
# (e.g. cooldown_days=0, max_contacts_per_company_job=999) are clamped on read.
_RULE_FLOOR = {"cooldown_days": 1, "max_contacts_per_company_job": 1, "daily_send_limit": 1}


def _rule_default(key: str) -> int:
    return {
        "cooldown_days": settings.COOLDOWN_DAYS,
        "max_contacts_per_company_job": settings.MAX_CONTACTS_PER_COMPANY_PER_JOB,
        "daily_send_limit": settings.DAILY_SEND_LIMIT,
    }[key]


def _rule_config_cap(key: str) -> Optional[int]:
    return {
        "cooldown_days": 365,
        "max_contacts_per_company_job": settings.MAX_CONTACTS_PER_COMPANY_PER_JOB,
        "daily_send_limit": getattr(settings, "MAX_DAILY_SEND_LIMIT_PER_MAILBOX", 50),
    }[key]


def business_rule_ceiling(db: Session, key: str) -> int:
    """Highest value a tenant may use for ``key`` (see module notes above)."""
    cap = int(_rule_config_cap(key))
    if key == "cooldown_days":
        return cap
    try:
        from app.core.settings_resolver import get_tenant_setting
        global_val = get_tenant_setting(db, key, tenant_id=None, default=None)
        if global_val is not None:
            cap = max(cap, int(global_val))
    except Exception:
        pass
    return cap


def resolve_business_rule(db: Session, tenant_id: Optional[int], key: str) -> int:
    """Tenant-aware value of a send-safety rule, clamped to the platform range."""
    val = None
    try:
        from app.core.settings_resolver import get_tenant_setting
        raw = get_tenant_setting(db, key, tenant_id=tenant_id, default=None)
        if raw is not None:
            val = int(raw)
    except Exception:
        val = None
    if val is None:
        val = int(_rule_default(key))
    lo = _RULE_FLOOR[key]
    hi = business_rule_ceiling(db, key)
    return max(lo, min(val, hi))


def _resolve_cooldown_days(db: Session, tenant_id: Optional[int]) -> int:
    """Return the cooldown window in days (tenant setting, else config), min 1."""
    return resolve_business_rule(db, tenant_id, "cooldown_days")


def _resolve_max_contacts_per_lead(db: Session, tenant_id: Optional[int]) -> int:
    """Return the per-lead contact limit (tenant setting, else config), clamped."""
    return resolve_business_rule(db, tenant_id, "max_contacts_per_company_job")


def _tenant_billing_suspended(db: Session, tenant_id: Optional[int]) -> bool:
    if tenant_id is None:
        return False
    from app.db.models.tenant import Tenant
    suspended = db.query(Tenant.billing_suspended).filter(Tenant.tenant_id == tenant_id).scalar()
    # Strict: only a real true value counts (a missing tenant row → None → not suspended).
    return suspended is True or suspended == 1


def tenant_has_postal_address(db: Session, tenant_id: Optional[int]) -> bool:
    """True when the workspace has a non-blank postal address on its company profile.

    CAN-SPAM §5(a)(5) requires the SENDER's valid physical postal address in every
    commercial email. This deliberately does NOT fall back to the platform's
    BILLING_COMPANY_ADDRESS — that is NeuraLeads' address, not the customer's.
    """
    if tenant_id is None:
        return False
    from app.db.models.tenant import Tenant
    address = db.query(Tenant.company_address).filter(Tenant.tenant_id == tenant_id).scalar()
    return bool((address or "").strip())


def _resolve_company_cap(db: Session, tenant_id: Optional[int]) -> int:
    """Return the company-level contact cap from tenant settings or config defaults."""
    try:
        from app.core.settings_resolver import get_tenant_setting
        val = get_tenant_setting(
            db, "max_contacts_per_company_all_campaigns",
            tenant_id=tenant_id, default=None,
        )
        if val is not None:
            return int(val)
    except Exception:
        pass
    return 5


def _blocked(code: str, checks: List[GateCheckResult], **fmt) -> SendGateResult:
    """Shortcut to build a blocked result."""
    msg = _MESSAGES.get(code, code)
    if fmt:
        try:
            msg = msg.format(**fmt)
        except (KeyError, IndexError):
            pass
    return SendGateResult(
        allowed=False,
        reason_code=code,
        reason_message=msg,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def unified_send_gate(
    db: Session,
    contact: ContactDetails,
    tenant_id: int,
    lead: Optional[LeadDetails] = None,
    campaign: Optional[Campaign] = None,
    is_reply: bool = False,
    dry_run: bool = False,
    step_number: Optional[int] = None,
) -> SendGateResult:
    """Run all safety checks before sending an email.

    Args:
        db: Active SQLAlchemy session.
        contact: The recipient contact.
        tenant_id: The tenant performing the send.
        lead: Optional lead context (enables contact+lead cooldown).
        campaign: Optional campaign context (used by AI orchestrator).
        is_reply: True for AI reply agent — skips cooldown / fatigue /
                  AI orchestrator (replies are conversations, not cold outreach).
        dry_run: True for draft validation — skips domain throttle and
                 AI orchestrator (no actual send).
        step_number: Current campaign step (for AI orchestrator context).

    Returns:
        SendGateResult with allowed=True or allowed=False + reason.
    """
    checks: List[GateCheckResult] = []

    # ── -1. Billing suspension (tenant-level) ─────────────────────
    # Suspension used to be enforced only by the require_tenant_id dependency, so
    # bulk outreach, draft sends, the campaign engine and the reply agent all kept
    # sending. Checked here so every send path is covered. Fails CLOSED on error:
    # an unpaid account must not keep sending because a lookup failed.
    try:
        suspended = _tenant_billing_suspended(db, tenant_id)
    except Exception as e:
        logger.warning("send_gate_billing_check_error", tenant_id=tenant_id, error=str(e))
        suspended = True
    if suspended:
        checks.append(GateCheckResult("billing", False, "tenant billing suspended"))
        return _blocked("BILLING_SUSPENDED", checks)
    checks.append(GateCheckResult("billing", True))

    # ── 0. Monthly send quota (tenant-level) ──────────────────────
    # Runs FIRST rather than last: it is the only tenant-level check here, so when it
    # fails every per-contact check below is wasted work — including check 10, which
    # spends an LLM call. Skipped for dry runs (nothing is sent) and for replies,
    # which are conversations the customer is already in, not new outbound volume.
    if not dry_run and not is_reply:
        try:
            from app.services.send_quota import has_send_quota
            allowed, quota = has_send_quota(db, tenant_id)
            if not allowed:
                checks.append(GateCheckResult(
                    "send_quota", False, f"{quota['used']}/{quota['limit']} this month"))
                return _blocked(
                    "SEND_QUOTA_EXCEEDED", checks,
                    used=quota["used"], limit=quota["limit"],
                )
            checks.append(GateCheckResult("send_quota", True))
        except Exception as e:
            # Fail OPEN. A counting bug must not stop a paying customer's campaign;
            # the daily per-mailbox limit still bounds the damage.
            logger.warning("send_gate_quota_error", error=str(e))
            checks.append(GateCheckResult("send_quota", True, f"check failed: {e}"))
    else:
        checks.append(GateCheckResult(
            "send_quota", True, "skipped (dry_run)" if dry_run else "skipped (reply)"))

    # ── 0.5. Sender postal address (CAN-SPAM, tenant-level) ───────
    # Outreach is commercial email, so the workspace's own postal address must be
    # in the footer. Replies are conversations the recipient started and are not
    # blocked. Dry runs ARE checked so the preflight endpoint surfaces the problem.
    # Warmup and transactional/system mail never call this gate. Fails CLOSED: a
    # compliance requirement must not be skipped because a lookup failed.
    if not is_reply:
        try:
            has_address = tenant_has_postal_address(db, tenant_id)
        except Exception as e:
            logger.warning("send_gate_postal_address_error", tenant_id=tenant_id, error=str(e))
            has_address = False
        if not has_address:
            checks.append(GateCheckResult("postal_address", False, "workspace has no postal address"))
            return _blocked("NO_POSTAL_ADDRESS", checks)
        checks.append(GateCheckResult("postal_address", True))
    else:
        checks.append(GateCheckResult("postal_address", True, "skipped (reply)"))

    # ── 1. Contact status (no DB query) ────────────────────────────
    if hasattr(contact, "outreach_status") and contact.outreach_status:
        if contact.outreach_status == ContactOutreachStatus.UNSUBSCRIBED:
            checks.append(GateCheckResult("contact_status", False, "unsubscribed"))
            return _blocked("UNSUBSCRIBED", checks)
        if contact.outreach_status == ContactOutreachStatus.INACTIVE:
            checks.append(GateCheckResult("contact_status", False, "inactive"))
            return _blocked("INACTIVE", checks)
    checks.append(GateCheckResult("contact_status", True))

    # ── 2. Suppression list ────────────────────────────────────────
    email_lower = (contact.email or "").lower()
    suppressed = db.query(SuppressionList).filter(
        SuppressionList.email == email_lower,
        (
            SuppressionList.expires_at.is_(None)
            | (SuppressionList.expires_at > datetime.utcnow())
        ),
    ).first()
    if suppressed:
        checks.append(GateCheckResult("suppression", False, suppressed.reason or ""))
        return _blocked("SUPPRESSED", checks, reason=suppressed.reason or "unknown")
    checks.append(GateCheckResult("suppression", True))

    # ── 3. Email validation (skip when feature disabled for tenant) ──
    from app.core.settings_resolver import get_tenant_setting_bool
    validation_enabled = get_tenant_setting_bool(
        db, "feature_email_validation_enabled", tenant_id=tenant_id, default=True
    )
    if not validation_enabled:
        checks.append(GateCheckResult("email_validation", True, "skipped (feature disabled)"))
    else:
        # Only the contact's own (tenant-scoped) status counts. EmailValidationResult
        # has no tenant_id — it is a platform-wide cache of provider answers — so
        # falling back to it let one tenant send on another tenant's paid
        # validation. The validation pipeline always writes the result onto the
        # tenant's contact rows, so a contact this tenant validated is covered.
        valid_email = (contact.validation_status or "").lower() == ValidationStatus.VALID.value
        if not valid_email:
            checks.append(GateCheckResult("email_validation", False, "not validated"))
            return _blocked("INVALID_EMAIL", checks)
        checks.append(GateCheckResult("email_validation", True))

    # ── Checks 4-8 have skip logic for replies and test contacts ──

    _is_test_contact = getattr(contact, 'is_test', False)

    if not is_reply and not _is_test_contact:
        # ── 4. Contact + Lead cooldown (cross-channel) ────────────
        cooldown_days = _resolve_cooldown_days(db, tenant_id)
        cooldown_cutoff = datetime.utcnow() - timedelta(days=cooldown_days)

        if lead:
            recent_for_lead = db.query(OutreachEvent).filter(
                OutreachEvent.contact_id == contact.contact_id,
                OutreachEvent.lead_id == lead.lead_id,
                OutreachEvent.sent_at >= cooldown_cutoff,
                OutreachEvent.status == OutreachStatus.SENT,
            ).first()
            if recent_for_lead:
                sent_date = recent_for_lead.sent_at.date().isoformat() if recent_for_lead.sent_at else "unknown"
                checks.append(GateCheckResult(
                    "contact_lead_cooldown", False,
                    f"sent {sent_date} for lead {lead.lead_id}",
                ))
                return _blocked(
                    "CONTACT_LEAD_COOLDOWN", checks,
                    date=sent_date, days=cooldown_days,
                )
            checks.append(GateCheckResult("contact_lead_cooldown", True))

        # ── 5. Contact-level cooldown ─────────────────────────────
        recent_any = db.query(OutreachEvent).filter(
            OutreachEvent.contact_id == contact.contact_id,
            OutreachEvent.sent_at >= cooldown_cutoff,
            OutreachEvent.status == OutreachStatus.SENT,
        ).first()
        if recent_any:
            sent_date = recent_any.sent_at.date().isoformat() if recent_any.sent_at else "unknown"
            checks.append(GateCheckResult(
                "contact_cooldown", False,
                f"sent {sent_date}",
            ))
            return _blocked(
                "CONTACT_COOLDOWN", checks,
                date=sent_date, days=cooldown_days,
            )
        checks.append(GateCheckResult("contact_cooldown", True))

        # ── 6. Per-lead contact limit ─────────────────────────────
        max_contacts = _resolve_max_contacts_per_lead(db, tenant_id)
        _lead_id = lead.lead_id if lead else contact.lead_id
        if _lead_id:
            lead_contacts_sent = (
                db.query(sa_func.count(sa_func.distinct(OutreachEvent.contact_id)))
                .join(ContactDetails)
                .filter(
                    ContactDetails.lead_id == _lead_id,
                    OutreachEvent.status == OutreachStatus.SENT,
                )
                .scalar()
            ) or 0
            if lead_contacts_sent >= max_contacts:
                checks.append(GateCheckResult(
                    "lead_contact_limit", False,
                    f"{lead_contacts_sent}/{max_contacts}",
                ))
                return _blocked(
                    "LEAD_CONTACT_LIMIT", checks,
                    n=lead_contacts_sent, max=max_contacts,
                )
        elif contact.client_name:
            company_contacts_sent = (
                db.query(sa_func.count(sa_func.distinct(OutreachEvent.contact_id)))
                .join(ContactDetails)
                .filter(
                    ContactDetails.client_name == contact.client_name,
                    OutreachEvent.status == OutreachStatus.SENT,
                )
                .scalar()
            ) or 0
            if company_contacts_sent >= max_contacts:
                checks.append(GateCheckResult(
                    "lead_contact_limit", False,
                    f"{company_contacts_sent}/{max_contacts} (by company)",
                ))
                return _blocked(
                    "LEAD_CONTACT_LIMIT", checks,
                    n=company_contacts_sent, max=max_contacts,
                )
        checks.append(GateCheckResult("lead_contact_limit", True))

        # ── 7. Company contact cap ────────────────────────────────
        try:
            from app.services.campaign_safety import check_company_contact_cap
            max_company = _resolve_company_cap(db, tenant_id)
            allowed, cap_reason = check_company_contact_cap(
                db, contact, tenant_id, max_per_company=max_company,
            )
            if not allowed:
                # Parse count from reason string
                checks.append(GateCheckResult("company_cap", False, cap_reason))
                return _blocked(
                    "COMPANY_CAP", checks,
                    n="N", max=max_company,
                    company=contact.client_name or "unknown",
                )
            checks.append(GateCheckResult("company_cap", True))
        except Exception as e:
            logger.warning("send_gate_company_cap_error", error=str(e))
            checks.append(GateCheckResult("company_cap", True, f"check failed: {e}"))

        # ── 8. Sequence fatigue ───────────────────────────────────
        try:
            from app.services.campaign_safety import check_sequence_fatigue
            should_send, fatigue_reason = check_sequence_fatigue(
                db, contact.contact_id, tenant_id,
            )
            if not should_send:
                # Parse numbers from reason
                checks.append(GateCheckResult("sequence_fatigue", False, fatigue_reason))
                return _blocked(
                    "SEQUENCE_FATIGUE", checks,
                    n="multiple", days=90,
                )
            checks.append(GateCheckResult("sequence_fatigue", True))
        except Exception as e:
            logger.warning("send_gate_fatigue_error", error=str(e))
            checks.append(GateCheckResult("sequence_fatigue", True, f"check failed: {e}"))
    elif _is_test_contact:
        # Test contacts skip checks 4-8 (cooldown, fatigue, caps)
        logger.info("send_gate_test_bypass", contact_id=contact.contact_id, email=contact.email)
        checks.append(GateCheckResult("contact_lead_cooldown", True, "skipped (test contact)"))
        checks.append(GateCheckResult("contact_cooldown", True, "skipped (test contact)"))
        checks.append(GateCheckResult("lead_contact_limit", True, "skipped (test contact)"))
        checks.append(GateCheckResult("company_cap", True, "skipped (test contact)"))
        checks.append(GateCheckResult("sequence_fatigue", True, "skipped (test contact)"))
    else:
        # Replies skip checks 4-8
        checks.append(GateCheckResult("contact_lead_cooldown", True, "skipped (reply)"))
        checks.append(GateCheckResult("contact_cooldown", True, "skipped (reply)"))
        checks.append(GateCheckResult("lead_contact_limit", True, "skipped (reply)"))
        checks.append(GateCheckResult("company_cap", True, "skipped (reply)"))
        checks.append(GateCheckResult("sequence_fatigue", True, "skipped (reply)"))

    # ── 9. Domain throttle (skip for dry_run) ─────────────────────
    if not dry_run:
        try:
            from app.services.domain_throttle import check_domain_throttle
            domain_ok, domain_reason = check_domain_throttle(
                db, contact.email, tenant_id,
            )
            if not domain_ok:
                # Extract domain from email
                domain = contact.email.rsplit("@", 1)[1] if "@" in contact.email else "unknown"
                checks.append(GateCheckResult("domain_throttle", False, domain_reason))
                return _blocked(
                    "DOMAIN_THROTTLE", checks,
                    domain=domain, n="N", max="limit",
                )
            checks.append(GateCheckResult("domain_throttle", True))
        except Exception as e:
            logger.warning("send_gate_domain_throttle_error", error=str(e))
            checks.append(GateCheckResult("domain_throttle", True, f"check failed: {e}"))
    else:
        checks.append(GateCheckResult("domain_throttle", True, "skipped (dry_run)"))

    # ── 10. AI orchestrator (skip for reply and dry_run) ──────────
    if not is_reply and not dry_run and campaign:
        try:
            from app.services.ai_sales_agent.orchestrator import orchestrate_send
            ai_decision = orchestrate_send(
                db=db,
                contact=contact,
                lead=lead,
                campaign=campaign,
                tenant_id=tenant_id,
                step_number=step_number or 1,
            )
            if not ai_decision.get("should_send", True):
                reason_codes = ai_decision.get("reason_codes", [])
                reasons_str = ", ".join(reason_codes) if reason_codes else "unknown"
                checks.append(GateCheckResult("ai_orchestrator", False, reasons_str))
                return _blocked("AI_BLOCKED", checks, reasons=reasons_str)
            checks.append(GateCheckResult("ai_orchestrator", True))
        except Exception as e:
            logger.warning("send_gate_ai_orchestrator_error", error=str(e))
            checks.append(GateCheckResult("ai_orchestrator", True, f"check failed: {e}"))
    else:
        skip_reason = "skipped ("
        parts = []
        if is_reply:
            parts.append("reply")
        if dry_run:
            parts.append("dry_run")
        if not campaign:
            parts.append("no campaign")
        skip_reason += ", ".join(parts) + ")"
        checks.append(GateCheckResult("ai_orchestrator", True, skip_reason))

    # ── All checks passed ─────────────────────────────────────────
    return SendGateResult(allowed=True, checks=checks)
