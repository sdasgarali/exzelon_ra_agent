"""Outreach Draft Service — orchestrates AI-personalized email drafting.

Single entry point: draft_outreach_email().
Returns (subject, body_html, body_text) or None on any failure,
so the caller's existing hardcoded fallback always works.
"""
import structlog
from typing import Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.contact import ContactDetails
from app.db.models.lead import LeadDetails
from app.db.models.client import ClientInfo
from app.db.models.sender_mailbox import SenderMailbox
from app.services.adapters.ai_content import get_ai_adapter
from app.services.adapters.ai.prompts import (
    OUTREACH_SYSTEM_PROMPT,
    build_outreach_user_prompt,
    parse_ai_email_response,
)
from app.core.settings_resolver import get_tenant_setting_bool

logger = structlog.get_logger()

# Per-run company research cache — cleared at start of each pipeline batch
_research_cache: Dict[str, Dict[str, Any]] = {}


def clear_research_cache() -> None:
    """Clear the company research cache. Call at start of each pipeline batch."""
    _research_cache.clear()


def draft_outreach_email(
    db: Session,
    contact: ContactDetails,
    lead: Optional[LeadDetails] = None,
    mailbox: Optional[SenderMailbox] = None,
    tenant_id: Optional[int] = None,
    step_number: int = 1,
) -> Optional[Tuple[str, str, str]]:
    """Draft an AI-personalized outreach email.

    Returns:
        (subject, body_html, body_text) on success.
        None if disabled, no adapter configured, or any error — caller uses
        existing fallback.
    """
    try:
        # 1. Check feature toggle
        effective_tenant = tenant_id or getattr(contact, "tenant_id", None)
        if not get_tenant_setting_bool(db, "ai_outreach_drafting", tenant_id=effective_tenant, default=False):
            logger.debug("ai_draft_skipped: feature disabled", tenant_id=effective_tenant)
            return None

        # 2. Get AI adapter
        adapter = get_ai_adapter(db, tenant_id=effective_tenant)
        if adapter is None:
            logger.debug("ai_draft_skipped: no AI adapter configured", tenant_id=effective_tenant)
            return None

        # 3. Gather context from DB
        context = _gather_context(db, contact, lead, mailbox, effective_tenant)

        # 4. Research company if context is thin
        _research_company_if_needed(adapter, context)

        # 5. Build prompt and call AI
        job_title = context.get("job_title") or "Open Position"
        user_prompt = build_outreach_user_prompt(
            contact_name=contact.first_name or "there",
            contact_title=contact.title or "",
            company_name=context.get("company_name") or contact.client_name or "your company",
            job_title=job_title,
            context=context,
            step_number=step_number,
        )

        result = adapter.generate_email(
            contact_name=contact.first_name or "there",
            contact_title=contact.title or "",
            company_name=context.get("company_name") or contact.client_name or "",
            job_title=job_title,
            context=context,
        )

        # 6. Validate result
        if not result or not result.get("subject") or not result.get("body_html"):
            logger.warning("ai_draft_failed: empty result from adapter")
            return None

        # Check for error key (adapter fallback content)
        if result.get("error"):
            logger.warning("ai_draft_failed: adapter returned error fallback", error=result["error"])
            return None

        subject = result["subject"]
        body_html = result["body_html"]
        body_text = result.get("body_text") or body_html.replace("<p>", "").replace("</p>", "\n").strip()

        logger.info(
            "ai_draft_success",
            contact=contact.email,
            company=contact.client_name,
            step=step_number,
        )
        return (subject, body_html, body_text)

    except Exception as e:
        logger.error("ai_draft_error", error=str(e), contact=getattr(contact, "email", "?"))
        return None


def _gather_context(
    db: Session,
    contact: ContactDetails,
    lead: Optional[LeadDetails],
    mailbox: Optional[SenderMailbox],
    tenant_id: Optional[int],
) -> Dict[str, Any]:
    """Query DB for contact/lead/company data to build rich context."""
    ctx: Dict[str, Any] = {}

    # Contact info
    ctx["contact_name"] = contact.first_name or ""
    ctx["contact_title"] = contact.title or ""
    ctx["company_name"] = contact.client_name or ""
    ctx["location"] = contact.location_state or ""

    # Lead info — use passed lead or load from FK
    if lead is None and contact.lead_id:
        lead = db.query(LeadDetails).filter(LeadDetails.lead_id == contact.lead_id).first()

    if lead:
        ctx["job_title"] = lead.job_title or ""
        ctx["company_name"] = lead.client_name or ctx["company_name"]
        ctx["location"] = lead.state or ctx["location"]
        if lead.city:
            ctx["location"] = f"{lead.city}, {lead.state}" if lead.state else lead.city

    # Company/client info
    client_name = ctx.get("company_name")
    if client_name:
        q = db.query(ClientInfo).filter(ClientInfo.client_name == client_name)
        if tenant_id is not None:
            q = q.filter(ClientInfo.tenant_id == tenant_id)
        client = q.first()
        if client:
            ctx["industry"] = client.industry or ""
            ctx["description"] = client.description or ""
            ctx["company_size"] = client.company_size or ""
            ctx["headquarters"] = client.headquarters or ""
            ctx["website"] = getattr(client, "website", "") or ""

    # Sender info from mailbox
    if mailbox:
        ctx["sender_name"] = mailbox.display_name or mailbox.email.split("@")[0]
        ctx["sender_title"] = "Account Executive"

    return ctx


def _is_context_thin(context: Dict[str, Any]) -> bool:
    """Check if company context is too thin to personalize well."""
    return not any([
        context.get("industry"),
        context.get("description"),
        context.get("company_size"),
    ])


def _research_company_if_needed(
    adapter: Any,
    context: Dict[str, Any],
) -> None:
    """Call adapter.research_company() when context is thin. Uses cache."""
    if not _is_context_thin(context):
        return

    company_name = context.get("company_name", "")
    if not company_name:
        return

    # Check cache
    if company_name in _research_cache:
        cached = _research_cache[company_name]
        if cached:  # Non-empty means successful research
            _merge_research(context, cached)
        return

    # Call AI research
    try:
        research = adapter.research_company(
            company_name=company_name,
            domain=context.get("website"),
            location=context.get("location"),
        )
        _research_cache[company_name] = research or {}
        if research:
            _merge_research(context, research)
    except Exception as e:
        logger.debug("company_research_failed", company=company_name, error=str(e))
        _research_cache[company_name] = {}  # Cache the failure


def _merge_research(context: Dict[str, Any], research: Dict[str, Any]) -> None:
    """Merge research results into context without overwriting existing values."""
    for key in ("industry", "description", "company_size", "headquarters"):
        if not context.get(key) and research.get(key):
            context[key] = research[key]
