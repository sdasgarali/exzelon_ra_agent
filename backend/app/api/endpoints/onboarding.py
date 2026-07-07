"""Onboarding status endpoints — Getting Started workflow tracking."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, get_current_tenant_id, require_role, UserRole
from app.db.models.user import User
from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.db.models.campaign import Campaign
from app.db.models.deal import Deal

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


def _tenant_filter(query, model, tenant_id: Optional[int]):
    """Apply tenant filter if tenant_id is provided."""
    if tenant_id is not None and hasattr(model, "tenant_id"):
        return query.filter(model.tenant_id == tenant_id)
    return query


@router.get("/status")
async def get_onboarding_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get the 6-step onboarding completion status for the current user's tenant."""
    is_dismissed = current_user.onboarding_dismissed_at is not None

    # Step 1: Has active mailboxes
    mailbox_q = db.query(func.count(SenderMailbox.mailbox_id)).filter(SenderMailbox.is_active == True)
    mailbox_q = _tenant_filter(mailbox_q, SenderMailbox, tenant_id)
    has_mailboxes = mailbox_q.scalar() > 0

    # Step 2: Has leads
    leads_q = db.query(func.count(LeadDetails.lead_id))
    leads_q = _tenant_filter(leads_q, LeadDetails, tenant_id)
    has_leads = leads_q.scalar() > 0

    # Step 3: Has contacts
    contacts_q = db.query(func.count(ContactDetails.contact_id))
    contacts_q = _tenant_filter(contacts_q, ContactDetails, tenant_id)
    has_contacts = contacts_q.scalar() > 0

    # Step 4: Has valid contacts
    valid_q = db.query(func.count(ContactDetails.contact_id)).filter(
        ContactDetails.validation_status == "valid",
    )
    valid_q = _tenant_filter(valid_q, ContactDetails, tenant_id)
    has_valid_contacts = valid_q.scalar() > 0

    # Step 5: Has active campaign
    campaign_q = db.query(func.count(Campaign.campaign_id)).filter(Campaign.status == "active")
    campaign_q = _tenant_filter(campaign_q, Campaign, tenant_id)
    has_active_campaign = campaign_q.scalar() > 0

    # Step 6: Has deals
    deals_q = db.query(func.count(Deal.deal_id))
    deals_q = _tenant_filter(deals_q, Deal, tenant_id)
    has_deals = deals_q.scalar() > 0

    steps = {
        "has_mailboxes": has_mailboxes,
        "has_leads": has_leads,
        "has_contacts": has_contacts,
        "has_valid_contacts": has_valid_contacts,
        "has_active_campaign": has_active_campaign,
        "has_deals": has_deals,
    }
    completed_count = sum(1 for v in steps.values() if v)
    total_steps = 6
    completion_percentage = round((completed_count / total_steps) * 100)
    should_show = not is_dismissed and completion_percentage < 100

    return {
        "is_dismissed": is_dismissed,
        "steps": steps,
        "completed_count": completed_count,
        "total_steps": total_steps,
        "completion_percentage": completion_percentage,
        "should_show_onboarding": should_show,
    }


@router.post("/dismiss")
async def dismiss_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Dismiss the onboarding Getting Started guide for the current user."""
    current_user.onboarding_dismissed_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": "Onboarding dismissed"}


@router.post("/reset")
async def reset_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """Reset onboarding dismiss flag. Super admin only (for testing)."""
    current_user.onboarding_dismissed_at = None
    db.commit()
    return {"success": True, "message": "Onboarding reset"}
