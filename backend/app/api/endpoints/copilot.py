"""AI Copilot — in-app assistant with per-user persistent memory.

* ``POST /copilot/chat``      — ask a question; the reply is grounded in the NeuraLeads
  feature catalog, the tenant's live business rules and stats, and the user's stored
  conversation history.
* ``GET /copilot/history``    — the user's own conversation, oldest → newest.
* ``DELETE /copilot/history`` — clear the user's own conversation.

Conversations are private to their author: every read and write is scoped by BOTH the
tenant and the user. Prompt content (scope, refusal rule, catalog) lives in
``services/copilot_knowledge.py``.
"""
from datetime import datetime
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_active_user, get_current_tenant_id, role_value
from app.api.deps.database import get_db
from app.db.models.copilot_message import CopilotMessage
from app.db.models.user import User
from app.services.adapters.ai_content import get_ai_adapter
from app.services.copilot_knowledge import build_system_prompt, load_business_rules

logger = structlog.get_logger()

router = APIRouter(prefix="/copilot", tags=["copilot"])

MAX_MESSAGE_CHARS = 4000
HISTORY_TURNS_FOR_PROMPT = 20
MAX_REPLY_TOKENS = 800
CONTEXT_PAGE_MAX = 64


class ChatMessage(BaseModel):
    role: str  # user/assistant
    content: str


class CopilotRequest(BaseModel):
    """New shape: ``{message, context?}``. Legacy shape: ``{messages: [...], context?}``
    — the last user message is used; the server-side history replaces the rest."""

    message: Optional[str] = Field(default=None, max_length=MAX_MESSAGE_CHARS)
    messages: Optional[List[ChatMessage]] = None
    context: Optional[str] = None  # page context (e.g., "campaigns", "inbox")

    @model_validator(mode="after")
    def _resolve_message(self) -> "CopilotRequest":
        text = self.message
        if text is None and self.messages:
            text = next((m.content for m in reversed(self.messages) if m.role == "user"), None)
        if text is None or not text.strip():
            raise ValueError("message is required (1-4000 characters)")
        if len(text) > MAX_MESSAGE_CHARS:
            raise ValueError(f"message must be at most {MAX_MESSAGE_CHARS} characters")
        self.message = text.strip()
        return self


def _storage_tenant_id(user: User, tenant_id: Optional[int]) -> Optional[int]:
    """Tenant a conversation is stored under.

    The effective (possibly impersonated) tenant when there is one; otherwise the
    user's own tenant. A global super admin with nothing selected has neither — that
    conversation is stored with tenant_id NULL, still scoped to the user.
    """
    return tenant_id if tenant_id is not None else user.tenant_id


def _history_query(db: Session, user: User, storage_tid: Optional[int]):
    tenant_clause = (
        CopilotMessage.tenant_id.is_(None) if storage_tid is None
        else CopilotMessage.tenant_id == storage_tid
    )
    return db.query(CopilotMessage).filter(tenant_clause, CopilotMessage.user_id == user.user_id)


def _workspace_stats(db: Session, tenant_id: Optional[int]) -> dict:
    """Live, tenant-scoped counts for the prompt."""
    from app.db.models.campaign import Campaign, CampaignStatus
    from app.db.models.contact import ContactDetails
    from app.db.models.lead import LeadDetails
    from app.db.models.outreach import OutreachEvent, OutreachStatus
    from app.db.models.sender_mailbox import SenderMailbox
    from app.db.query_helpers import tenant_filter

    return {
        "total_leads": tenant_filter(db.query(LeadDetails), LeadDetails, tenant_id).count(),
        "total_contacts": tenant_filter(db.query(ContactDetails), ContactDetails, tenant_id).count(),
        "active_campaigns": tenant_filter(
            db.query(Campaign).filter(Campaign.status == CampaignStatus.ACTIVE), Campaign, tenant_id,
        ).count(),
        "total_sent": tenant_filter(
            db.query(OutreachEvent).filter(OutreachEvent.status == OutreachStatus.SENT), OutreachEvent, tenant_id,
        ).count(),
        "active_mailboxes": tenant_filter(
            db.query(SenderMailbox).filter(SenderMailbox.is_active == True), SenderMailbox, tenant_id,  # noqa: E712
        ).count(),
    }


def _plan_features(db: Session, tenant_id: Optional[int]) -> Optional[set]:
    """Features in the effective tenant's plan; None when not acting as a tenant."""
    if tenant_id is None:
        return None
    from app.core.plans import plan_features
    from app.db.models.tenant import Tenant
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    return set(plan_features(getattr(tenant, "plan", None)))


def _base_role(db: Session, user: User, tenant_id: Optional[int]) -> str:
    from app.services.role_registry import resolve_base_role
    key = role_value(user)
    try:
        return resolve_base_role(db, tenant_id if tenant_id is not None else user.tenant_id, key)
    except Exception:  # pragma: no cover - malformed custom-role setting
        return "recruiter"


@router.post("/chat")
def copilot_chat(
    data: CopilotRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Answer one copilot message, remembering the user's conversation."""
    context_page = (data.context or "").strip()[:CONTEXT_PAGE_MAX] or None
    storage_tid = _storage_tenant_id(user, tenant_id)

    adapter = get_ai_adapter(db, tenant_id=tenant_id)
    if not adapter:
        raise HTTPException(
            status_code=503,
            detail="AI service not configured. Set an AI provider and API key in Settings.",
        )

    system_prompt = build_system_prompt(
        stats=_workspace_stats(db, tenant_id),
        context_page=context_page or "dashboard",
        user_role=_base_role(db, user, tenant_id),
        plan_features=_plan_features(db, tenant_id),
        business_rules=load_business_rules(db, tenant_id),
    )

    history: List[CopilotMessage] = list(reversed(
        _history_query(db, user, storage_tid)
        .order_by(CopilotMessage.created_at.desc(), CopilotMessage.id.desc())
        .limit(HISTORY_TURNS_FOR_PROMPT)
        .all()
    ))

    ai_messages = [{"role": "system", "content": system_prompt}]
    ai_messages += [
        {"role": m.role, "content": m.content}
        for m in history if m.role in ("user", "assistant")
    ]
    ai_messages.append({"role": "user", "content": data.message})

    try:
        reply = adapter._call_api(ai_messages, max_tokens=MAX_REPLY_TOKENS)
    except Exception as exc:
        # Never echo the provider error: it can carry request details or key fragments.
        logger.error(
            "copilot_provider_error",
            tenant_id=tenant_id, user_id=user.user_id,
            error_type=type(exc).__name__, exc_info=True,
        )
        raise HTTPException(status_code=502, detail="AI provider error — please try again")

    reply = (reply or "").strip() if isinstance(reply, str) else ""
    if not reply:
        logger.error("copilot_empty_reply", tenant_id=tenant_id, user_id=user.user_id)
        raise HTTPException(status_code=502, detail="AI provider error — please try again")

    # Persist both turns only on success, so a failed attempt can be retried cleanly.
    now = datetime.utcnow()
    db.add(CopilotMessage(
        tenant_id=storage_tid, user_id=user.user_id, role="user",
        content=data.message, context_page=context_page, created_at=now, updated_at=now,
    ))
    db.add(CopilotMessage(
        tenant_id=storage_tid, user_id=user.user_id, role="assistant",
        content=reply, context_page=context_page, created_at=now, updated_at=now,
    ))
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error("copilot_persist_failed", tenant_id=storage_tid, user_id=user.user_id,
                     exc_info=True)
        # The answer is still valid; only the memory write failed.

    return {"response": reply}


@router.get("/history")
def copilot_history(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """The current user's most recent ``limit`` copilot messages, oldest → newest."""
    storage_tid = _storage_tenant_id(user, tenant_id)
    rows = (
        _history_query(db, user, storage_tid)
        .order_by(CopilotMessage.created_at.desc(), CopilotMessage.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "context_page": m.context_page,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in reversed(rows)
        ]
    }


@router.delete("/history")
def clear_copilot_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Delete the current user's copilot conversation (in the effective tenant only)."""
    storage_tid = _storage_tenant_id(user, tenant_id)
    deleted = _history_query(db, user, storage_tid).delete(synchronize_session=False)
    db.commit()
    logger.info("copilot_history_cleared", tenant_id=storage_tid, user_id=user.user_id, deleted=deleted)
    return {"deleted": deleted}
