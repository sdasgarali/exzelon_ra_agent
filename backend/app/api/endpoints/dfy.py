"""Done-For-You (DFY) domain setup endpoints."""
import structlog
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, get_current_tenant_id
from app.db.models.user import User
from app.services.dfy_service import DFYService

logger = structlog.get_logger()

router = APIRouter(prefix="/dfy", tags=["dfy"])

dfy_service = DFYService()


class DomainSuggestionRequest(BaseModel):
    primary_domain: str
    count: int = 5


class WarmupEstimateRequest(BaseModel):
    mailbox_count: int
    target_daily: int = 30


@router.post("/suggest-domains")
def suggest_domains(
    data: DomainSuggestionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Suggest secondary domains based on a primary domain."""
    if not data.primary_domain:
        raise HTTPException(status_code=400, detail="Primary domain is required")

    suggestions = dfy_service.suggest_secondary_domains(
        primary_domain=data.primary_domain,
        count=data.count,
    )

    logger.info(
        "domain_suggestions_generated",
        primary=data.primary_domain,
        count=len(suggestions),
        user=user.email,
    )
    return {
        "primary_domain": data.primary_domain,
        "suggestions": suggestions,
        "count": len(suggestions),
    }


@router.get("/dns-setup/{domain}")
def dns_setup(
    domain: str,
    provider: str = Query("generic", description="DNS provider name"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get DNS setup instructions for a domain."""
    if not domain:
        raise HTTPException(status_code=400, detail="Domain is required")

    instructions = dfy_service.get_dns_setup_instructions(
        domain=domain,
        provider=provider,
    )
    return instructions


@router.post("/warmup-estimate")
def warmup_estimate(
    data: WarmupEstimateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Estimate warmup timeline for a set of mailboxes."""
    if data.mailbox_count < 1:
        raise HTTPException(status_code=400, detail="mailbox_count must be at least 1")

    estimate = dfy_service.estimate_warmup_schedule(
        mailbox_count=data.mailbox_count,
        target_daily=data.target_daily,
    )
    return estimate


@router.get("/setup-checklist")
def setup_checklist(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Return the DFY setup checklist with status for each step.

    Checks the tenant's current state to mark steps as completed.
    """
    from app.db.models.sender_mailbox import SenderMailbox
    from app.db.models.tracking_domain import TrackingDomain
    from app.db.query_helpers import tenant_filter

    checklist = dfy_service.get_setup_checklist()

    # Step 4: Check if mailboxes are connected
    mailbox_q = db.query(SenderMailbox).filter(SenderMailbox.is_active == True)
    if tenant_id is not None:
        mailbox_q = tenant_filter(mailbox_q, SenderMailbox, tenant_id)
    mailbox_count = mailbox_q.count()
    if mailbox_count > 0:
        for step in checklist:
            if step["step"] == 4:
                step["status"] = "completed"
                step["detail"] = f"{mailbox_count} mailbox(es) connected"

    # Step 5: Check if any mailboxes are warming up or past warmup
    warming_q = db.query(SenderMailbox).filter(
        SenderMailbox.warmup_status.in_(["warming_up", "cold_ready", "active"]),
    )
    if tenant_id is not None:
        warming_q = tenant_filter(warming_q, SenderMailbox, tenant_id)
    warming_count = warming_q.count()
    if warming_count > 0:
        for step in checklist:
            if step["step"] == 5:
                step["status"] = "completed"
                step["detail"] = f"{warming_count} mailbox(es) in warmup or active"

    # Step 2: Check tracking domains (proxy for DNS setup)
    domain_q = db.query(TrackingDomain).filter(TrackingDomain.is_archived == False)
    if tenant_id is not None:
        domain_q = tenant_filter(domain_q, TrackingDomain, tenant_id)
    domain_count = domain_q.count()
    if domain_count > 0:
        for step in checklist:
            if step["step"] == 2:
                step["status"] = "completed"
                step["detail"] = f"{domain_count} tracking domain(s) configured"

    return {
        "checklist": checklist,
        "total_steps": len(checklist),
        "completed": sum(1 for s in checklist if s["status"] == "completed"),
    }
