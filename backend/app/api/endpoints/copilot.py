"""AI Copilot chat endpoint."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, get_current_tenant_id
from app.db.models.user import User

router = APIRouter(prefix="/copilot", tags=["copilot"])


class ChatMessage(BaseModel):
    role: str  # user/assistant
    content: str

class CopilotRequest(BaseModel):
    messages: List[ChatMessage]
    context: Optional[str] = None  # page context (e.g., "campaigns", "inbox")


@router.post("/chat")
def copilot_chat(
    data: CopilotRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """AI copilot conversational endpoint."""
    from app.db.models.campaign import Campaign, CampaignStatus
    from app.db.models.contact import ContactDetails
    from app.db.models.lead import LeadDetails
    from app.db.models.outreach import OutreachEvent, OutreachStatus
    from app.db.models.sender_mailbox import SenderMailbox
    from app.db.query_helpers import tenant_filter

    # Build system context with platform data (tenant-scoped)
    leads_q = db.query(LeadDetails)
    leads_q = tenant_filter(leads_q, LeadDetails, tenant_id)
    contacts_q = db.query(ContactDetails)
    contacts_q = tenant_filter(contacts_q, ContactDetails, tenant_id)
    campaigns_q = db.query(Campaign).filter(Campaign.status == CampaignStatus.ACTIVE)
    campaigns_q = tenant_filter(campaigns_q, Campaign, tenant_id)
    sent_q = db.query(OutreachEvent).filter(OutreachEvent.status == OutreachStatus.SENT)
    sent_q = tenant_filter(sent_q, OutreachEvent, tenant_id)
    mailboxes_q = db.query(SenderMailbox).filter(SenderMailbox.is_active == True)
    mailboxes_q = tenant_filter(mailboxes_q, SenderMailbox, tenant_id)

    stats = {
        "total_leads": leads_q.count(),
        "total_contacts": contacts_q.count(),
        "active_campaigns": campaigns_q.count(),
        "total_sent": sent_q.count(),
        "active_mailboxes": mailboxes_q.count(),
    }

    system_prompt = (
        "You are an AI assistant for the Exzelon RA cold email automation platform. "
        "Help users with campaign strategy, email copywriting, lead analysis, and platform usage. "
        f"Current platform stats: {stats}. "
        f"User is on the '{data.context or 'dashboard'}' page. "
        "Be concise and actionable."
    )

    # Build messages for AI
    ai_messages = [{"role": "system", "content": system_prompt}]
    for msg in data.messages[-10:]:  # last 10 messages for context
        ai_messages.append({"role": msg.role, "content": msg.content})

    # Use existing AI adapter
    try:
        from app.services.adapters.ai_content import get_ai_adapter
        adapter = get_ai_adapter(db)
        if not adapter:
            raise HTTPException(status_code=503, detail="AI service not configured. Set an AI provider and API key in Settings.")
        response = adapter._call_api(ai_messages, max_tokens=500)
        return {"response": response, "context": data.context}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")
