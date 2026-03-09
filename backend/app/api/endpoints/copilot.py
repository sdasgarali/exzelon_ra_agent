"""AI Copilot chat endpoint."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user
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
):
    """AI copilot conversational endpoint."""
    from app.db.models.campaign import Campaign, CampaignStatus
    from app.db.models.contact import ContactDetails
    from app.db.models.lead import LeadDetails
    from app.db.models.outreach import OutreachEvent, OutreachStatus
    from app.db.models.sender_mailbox import SenderMailbox

    # Build system context with platform data
    stats = {
        "total_leads": db.query(LeadDetails).count(),
        "total_contacts": db.query(ContactDetails).count(),
        "active_campaigns": db.query(Campaign).filter(Campaign.status == CampaignStatus.ACTIVE).count(),
        "total_sent": db.query(OutreachEvent).filter(OutreachEvent.status == OutreachStatus.SENT).count(),
        "active_mailboxes": db.query(SenderMailbox).filter(SenderMailbox.is_active == True).count(),
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
