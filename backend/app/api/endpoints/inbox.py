"""Unified Inbox (Unibox) API endpoints."""
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id
from app.db.query_helpers import tenant_filter
from app.db.models.user import User, UserRole
from app.db.models.inbox_message import InboxMessage, MessageDirection
from app.db.models.contact import ContactDetails
from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.campaign import Campaign
from app.db.models.outreach import OutreachEvent
from app.db.models.outreach_draft import OutreachDraft

router = APIRouter(prefix="/inbox", tags=["inbox"])


class ReplyCompose(BaseModel):
    thread_id: str
    mailbox_id: int
    body_html: str
    body_text: str = ""


class CategoryUpdate(BaseModel):
    category: str  # interested/not_interested/ooo/question/referral/do_not_contact/other


class BulkDeleteRequest(BaseModel):
    thread_ids: List[str]


# ─── Threads ───────────────────────────────────────────────────────

@router.get("/threads")
def list_threads(
    category: Optional[str] = None,
    mailbox_id: Optional[List[int]] = Query(None),
    campaign_id: Optional[List[int]] = Query(None),
    source: Optional[List[str]] = Query(None),
    is_read: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List inbox threads, sorted by latest message."""
    # Get distinct thread_ids with filters, then fetch latest message per thread
    thread_query = db.query(
        InboxMessage.thread_id,
        func.max(InboxMessage.received_at).label("latest"),
    ).filter(InboxMessage.is_deleted == False)
    thread_query = tenant_filter(thread_query, InboxMessage, tenant_id)

    if category:
        thread_query = thread_query.filter(InboxMessage.category == category)
    if mailbox_id:
        thread_query = thread_query.filter(InboxMessage.mailbox_id.in_(mailbox_id))
    if campaign_id:
        thread_query = thread_query.filter(InboxMessage.campaign_id.in_(campaign_id))
    if source:
        thread_query = thread_query.join(
            OutreachEvent, OutreachEvent.event_id == InboxMessage.outreach_event_id
        ).join(
            OutreachDraft,
            and_(
                OutreachDraft.contact_id == OutreachEvent.contact_id,
                OutreachDraft.mailbox_id == OutreachEvent.sender_mailbox_id,
                OutreachDraft.tenant_id == OutreachEvent.tenant_id,
            )
        ).filter(OutreachDraft.source.in_(source))
    if is_read is not None:
        thread_query = thread_query.filter(InboxMessage.is_read == is_read)
    if search:
        thread_query = thread_query.filter(
            InboxMessage.subject.ilike(f"%{search}%") |
            InboxMessage.from_email.ilike(f"%{search}%")
        )

    thread_query = thread_query.group_by(InboxMessage.thread_id)
    total = thread_query.count()

    threads = thread_query.order_by(
        desc("latest")
    ).offset((page - 1) * page_size).limit(page_size).all()

    # For each thread, get the latest message + thread metadata
    result = []
    for thread_id, latest_at in threads:
        latest_msg_query = db.query(InboxMessage).filter(
            InboxMessage.thread_id == thread_id,
        )
        latest_msg_query = tenant_filter(latest_msg_query, InboxMessage, tenant_id)
        latest_msg = latest_msg_query.order_by(InboxMessage.received_at.desc()).first()

        if not latest_msg:
            continue

        msg_count_query = db.query(InboxMessage).filter(
            InboxMessage.thread_id == thread_id
        )
        msg_count_query = tenant_filter(msg_count_query, InboxMessage, tenant_id)
        msg_count = msg_count_query.count()

        unread_count_query = db.query(InboxMessage).filter(
            InboxMessage.thread_id == thread_id,
            InboxMessage.is_read == False,
        )
        unread_count_query = tenant_filter(unread_count_query, InboxMessage, tenant_id)
        unread_count = unread_count_query.count()

        # Get contact info — always show the "other party" in the conversation,
        # not the app's own mailbox email.
        contact_name = None

        # 1. Try DB contact first (most reliable source of display name)
        _contact_id = latest_msg.contact_id
        if not _contact_id:
            # Check any message in the thread for a contact_id
            any_msg_with_contact = db.query(InboxMessage.contact_id).filter(
                InboxMessage.thread_id == thread_id,
                InboxMessage.contact_id.isnot(None),
            ).first()
            if any_msg_with_contact:
                _contact_id = any_msg_with_contact[0]

        if _contact_id:
            contact_query = db.query(ContactDetails).filter(
                ContactDetails.contact_id == _contact_id
            )
            contact_query = tenant_filter(contact_query, ContactDetails, tenant_id)
            contact = contact_query.first()
            if contact:
                full_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
                if full_name:
                    contact_name = full_name

        # 2. If no name from contact, determine the "other party" email
        if not contact_name:
            # Check for received messages — the external sender
            received_msg_query = db.query(InboxMessage).filter(
                InboxMessage.thread_id == thread_id,
                InboxMessage.direction == MessageDirection.RECEIVED,
            )
            received_msg_query = tenant_filter(received_msg_query, InboxMessage, tenant_id)
            received_msg = received_msg_query.first()
            if received_msg:
                contact_name = received_msg.from_email
            else:
                # Sent-only thread — use the RECIPIENT (to_email), not the sender
                sent_msg_query = db.query(InboxMessage).filter(
                    InboxMessage.thread_id == thread_id,
                    InboxMessage.direction == MessageDirection.SENT,
                )
                sent_msg_query = tenant_filter(sent_msg_query, InboxMessage, tenant_id)
                sent_msg = sent_msg_query.first()
                if sent_msg:
                    contact_name = sent_msg.to_email

        # 3. Final fallback
        if not contact_name:
            contact_name = latest_msg.to_email if latest_msg.direction == MessageDirection.SENT else latest_msg.from_email

        # Get category/sentiment/snippet from latest RECEIVED message (not sent)
        latest_received_query = db.query(InboxMessage).filter(
            InboxMessage.thread_id == thread_id,
            InboxMessage.direction == MessageDirection.RECEIVED,
        )
        latest_received_query = tenant_filter(latest_received_query, InboxMessage, tenant_id)
        latest_received = latest_received_query.order_by(InboxMessage.received_at.desc()).first()

        thread_category = latest_received.category if latest_received else None
        thread_sentiment = latest_received.sentiment if latest_received else None
        snippet = (latest_received.body_text or "")[:120] if latest_received else ""

        # Use the first message's subject for the thread subject
        first_msg_query = db.query(InboxMessage).filter(
            InboxMessage.thread_id == thread_id,
        )
        first_msg_query = tenant_filter(first_msg_query, InboxMessage, tenant_id)
        first_msg = first_msg_query.order_by(InboxMessage.received_at.asc()).first()

        result.append({
            "thread_id": thread_id,
            "subject": first_msg.subject if first_msg else latest_msg.subject,
            "latest_message_at": (latest_at.isoformat() + "Z") if latest_at else None,
            "from_email": contact_name,
            "contact_name": contact_name,
            "contact_id": latest_msg.contact_id,
            "mailbox_id": latest_msg.mailbox_id,
            "campaign_id": latest_msg.campaign_id,
            "category": thread_category,
            "sentiment": thread_sentiment,
            "message_count": msg_count,
            "unread_count": unread_count,
            "snippet": snippet,
            "direction": latest_msg.direction.value if latest_msg.direction else "sent",
        })

    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.get("/threads/{thread_id}")
def get_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get all messages in a thread."""
    messages_query = db.query(InboxMessage).filter(
        InboxMessage.thread_id == thread_id,
        InboxMessage.is_deleted == False,
    )
    messages_query = tenant_filter(messages_query, InboxMessage, tenant_id)
    messages = messages_query.order_by(InboxMessage.received_at.asc()).all()

    if not messages:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Get contact info
    contact_info = None
    contact_id = messages[0].contact_id
    if contact_id:
        contact_query = db.query(ContactDetails).filter(
            ContactDetails.contact_id == contact_id
        )
        contact_query = tenant_filter(contact_query, ContactDetails, tenant_id)
        contact = contact_query.first()
        if contact:
            contact_info = {
                "contact_id": contact.contact_id,
                "name": f"{contact.first_name or ''} {contact.last_name or ''}".strip(),
                "email": contact.email,
                "title": contact.title,
                "company": contact.client_name,
                "phone": contact.phone,
            }

    # Build mailbox lookup for sender names on sent messages
    mailbox_ids = {m.mailbox_id for m in messages if m.mailbox_id}
    mailbox_map: dict = {}
    if mailbox_ids:
        from app.db.models.sender_mailbox import SenderMailbox
        for mb in db.query(SenderMailbox).filter(SenderMailbox.mailbox_id.in_(mailbox_ids)).all():
            mailbox_map[mb.mailbox_id] = mb

    def _from_name(m: InboxMessage) -> str:
        """Derive a display name for the sender."""
        if m.from_name:
            return m.from_name
        if m.direction == MessageDirection.SENT and m.mailbox_id and m.mailbox_id in mailbox_map:
            mb = mailbox_map[m.mailbox_id]
            return getattr(mb, 'display_name', None) or getattr(mb, 'sender_name', None) or m.from_email
        if m.direction == MessageDirection.RECEIVED and contact_info:
            return contact_info["name"] or m.from_email
        return m.from_email

    return {
        "thread_id": thread_id,
        "contact": contact_info,
        "messages": [
            {
                "message_id": m.message_id,
                "direction": m.direction.value if m.direction else "sent",
                "from_email": m.from_email,
                "from_name": _from_name(m),
                "to_email": m.to_email,
                "cc_emails": getattr(m, 'cc_emails', None),
                "bcc_emails": getattr(m, 'bcc_emails', None),
                "subject": m.subject,
                "body_html": m.body_html,
                "body_text": m.body_text,
                "received_at": (m.received_at.isoformat() + "Z") if m.received_at else None,
                "is_read": m.is_read,
                "category": m.category,
                "sentiment": m.sentiment,
                "mailbox_id": m.mailbox_id,
            }
            for m in messages
        ],
    }


@router.put("/threads/{thread_id}/read")
def mark_thread_read(
    thread_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Mark all messages in a thread as read."""
    update_query = db.query(InboxMessage).filter(
        InboxMessage.thread_id == thread_id,
        InboxMessage.is_read == False,
    )
    update_query = tenant_filter(update_query, InboxMessage, tenant_id)
    updated = update_query.update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"marked_read": updated}


@router.put("/threads/{thread_id}/category")
def set_thread_category(
    thread_id: str,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Set category label for all messages in a thread."""
    update_query = db.query(InboxMessage).filter(
        InboxMessage.thread_id == thread_id,
    )
    update_query = tenant_filter(update_query, InboxMessage, tenant_id)
    updated = update_query.update({"category": data.category}, synchronize_session=False)
    db.commit()
    return {"updated": updated, "category": data.category}


# ─── Delete ────────────────────────────────────────────────────────

@router.delete("/threads/{thread_id}")
def delete_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Soft-delete all messages in a thread."""
    now = datetime.utcnow()
    update_query = db.query(InboxMessage).filter(
        InboxMessage.thread_id == thread_id,
        InboxMessage.is_deleted == False,
    )
    update_query = tenant_filter(update_query, InboxMessage, tenant_id)
    updated = update_query.update({"is_deleted": True, "deleted_at": now}, synchronize_session=False)
    db.commit()
    if not updated:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"deleted": updated, "thread_id": thread_id}


@router.post("/threads/bulk-delete")
def bulk_delete_threads(
    data: BulkDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Soft-delete multiple threads at once."""
    if not data.thread_ids:
        raise HTTPException(status_code=400, detail="No thread IDs provided")
    if len(data.thread_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 threads per request")

    now = datetime.utcnow()
    update_query = db.query(InboxMessage).filter(
        InboxMessage.thread_id.in_(data.thread_ids),
        InboxMessage.is_deleted == False,
    )
    update_query = tenant_filter(update_query, InboxMessage, tenant_id)
    updated = update_query.update({"is_deleted": True, "deleted_at": now}, synchronize_session=False)
    db.commit()
    return {"deleted": updated, "thread_ids": data.thread_ids}


# ─── Reply ─────────────────────────────────────────────────────────

@router.post("/reply")
def send_reply(
    data: ReplyCompose,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Send a reply in a thread."""
    # Get thread context
    last_received_query = db.query(InboxMessage).filter(
        InboxMessage.thread_id == data.thread_id,
        InboxMessage.direction == MessageDirection.RECEIVED,
    )
    last_received_query = tenant_filter(last_received_query, InboxMessage, tenant_id)
    last_received = last_received_query.order_by(InboxMessage.received_at.desc()).first()

    if not last_received:
        # Maybe replying to a sent-only thread
        last_msg_query = db.query(InboxMessage).filter(
            InboxMessage.thread_id == data.thread_id,
        )
        last_msg_query = tenant_filter(last_msg_query, InboxMessage, tenant_id)
        last_msg = last_msg_query.order_by(InboxMessage.received_at.desc()).first()
        if not last_msg:
            raise HTTPException(status_code=404, detail="Thread not found")
        to_email = last_msg.to_email if last_msg.direction == MessageDirection.SENT else last_msg.from_email
        subject = last_msg.subject or ""
    else:
        to_email = last_received.from_email
        subject = last_received.subject or ""

    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    # Get mailbox
    mailbox_query = db.query(SenderMailbox).filter(
        SenderMailbox.mailbox_id == data.mailbox_id
    )
    mailbox_query = tenant_filter(mailbox_query, SenderMailbox, tenant_id)
    mailbox = mailbox_query.first()
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    # Send via SMTP
    from app.services.pipelines.outreach import send_outreach_email
    result = send_outreach_email(
        sender_mailbox=mailbox,
        to_email=to_email,
        subject=subject,
        body_html=data.body_html,
        body_text=data.body_text,
        db=db,
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=f"Send failed: {result.get('error')}")

    # Record in inbox
    sent_msg = InboxMessage(
        thread_id=data.thread_id,
        contact_id=last_received.contact_id if last_received else None,
        mailbox_id=data.mailbox_id,
        campaign_id=last_received.campaign_id if last_received else None,
        direction=MessageDirection.SENT,
        from_email=mailbox.email,
        to_email=to_email,
        subject=subject,
        body_html=data.body_html,
        body_text=data.body_text,
        raw_message_id=result.get("message_id"),
        in_reply_to=last_received.raw_message_id if last_received else None,
        received_at=datetime.utcnow(),
        is_read=True,
        tenant_id=tenant_id or 1,
    )
    db.add(sent_msg)
    db.commit()

    return {"message": "Reply sent", "message_id": result.get("message_id")}


# ─── AI Suggest Reply ─────────────────────────────────────────────

@router.post("/threads/{thread_id}/suggest-reply")
def suggest_reply(
    thread_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Generate an AI-suggested reply for a thread."""
    messages_query = db.query(InboxMessage).filter(
        InboxMessage.thread_id == thread_id,
    )
    messages_query = tenant_filter(messages_query, InboxMessage, tenant_id)
    messages = messages_query.order_by(InboxMessage.received_at.asc()).all()

    if not messages:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Look up contact and campaign from thread messages
    contact = None
    campaign = None
    for msg in messages:
        if msg.contact_id and not contact:
            contact_query = db.query(ContactDetails).filter(
                ContactDetails.contact_id == msg.contact_id
            )
            contact_query = tenant_filter(contact_query, ContactDetails, tenant_id)
            contact = contact_query.first()
        if msg.campaign_id and not campaign:
            campaign_query = db.query(Campaign).filter(
                Campaign.campaign_id == msg.campaign_id
            )
            campaign_query = tenant_filter(campaign_query, Campaign, tenant_id)
            campaign = campaign_query.first()
        if contact and campaign:
            break

    from app.services.ai_reply_agent import generate_reply_suggestion
    return generate_reply_suggestion(messages, contact, campaign, db)


# ─── Stats ─────────────────────────────────────────────────────────

@router.get("/stats")
def inbox_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get inbox statistics."""
    total_threads_query = db.query(func.count(func.distinct(InboxMessage.thread_id))).filter(
        InboxMessage.is_deleted == False,
    )
    total_threads_query = tenant_filter(total_threads_query, InboxMessage, tenant_id)
    total_threads = total_threads_query.scalar() or 0

    unread_count_query = db.query(func.count(func.distinct(InboxMessage.thread_id))).filter(
        InboxMessage.is_read == False,
        InboxMessage.is_deleted == False,
    )
    unread_count_query = tenant_filter(unread_count_query, InboxMessage, tenant_id)
    unread_count = unread_count_query.scalar() or 0

    # Category breakdown
    categories_query = db.query(
        InboxMessage.category,
        func.count(func.distinct(InboxMessage.thread_id)),
    ).filter(InboxMessage.is_deleted == False)
    categories_query = tenant_filter(categories_query, InboxMessage, tenant_id)
    categories = categories_query.group_by(InboxMessage.category).all()

    return {
        "total_threads": total_threads,
        "unread_count": unread_count,
        "categories": {
            cat or "uncategorized": count for cat, count in categories
        },
    }


@router.post("/sync")
def trigger_sync(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Trigger manual inbox sync."""
    from app.services.inbox_syncer import sync_inbox
    result = sync_inbox(db, tenant_id=tenant_id)
    return {"message": "Sync completed", "result": result}


# ─── AI Reply Drafts ──────────────────────────────────────────────

@router.get("/threads/{thread_id}/drafts")
def list_drafts(
    thread_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List AI reply drafts for a thread."""
    from app.db.models.ai_reply_draft import AIReplyDraft

    drafts_q = db.query(AIReplyDraft).filter(
        AIReplyDraft.thread_id == thread_id,
        AIReplyDraft.status.in_(["pending", "approved"]),
        AIReplyDraft.is_archived == False,
    )
    drafts_q = tenant_filter(drafts_q, AIReplyDraft, tenant_id)
    drafts = drafts_q.order_by(AIReplyDraft.created_at.desc()).all()

    return {
        "thread_id": thread_id,
        "drafts": [
            {
                "draft_id": d.draft_id,
                "thread_id": d.thread_id,
                "subject": d.subject,
                "body_html": d.body_html,
                "body_text": d.body_text,
                "intent_detected": d.intent_detected,
                "confidence_score": d.confidence_score,
                "ai_model_used": d.ai_model_used,
                "status": d.status,
                "expires_at": d.expires_at.isoformat() if d.expires_at else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "mailbox_id": d.mailbox_id,
                "campaign_id": d.campaign_id,
                "contact_id": d.contact_id,
            }
            for d in drafts
        ],
        "count": len(drafts),
    }


@router.post("/threads/{thread_id}/drafts/{draft_id}/approve")
def approve_draft(
    thread_id: str,
    draft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Approve and send an AI reply draft."""
    from app.db.models.ai_reply_draft import AIReplyDraft
    from app.services.ai_reply_agent_service import _send_draft

    draft_q = db.query(AIReplyDraft).filter(
        AIReplyDraft.draft_id == draft_id,
        AIReplyDraft.thread_id == thread_id,
        AIReplyDraft.is_archived == False,
    )
    draft_q = tenant_filter(draft_q, AIReplyDraft, tenant_id)
    draft = draft_q.first()

    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status not in ("pending",):
        raise HTTPException(status_code=400, detail=f"Draft is already {draft.status}")

    # Send the draft
    success = _send_draft(db, draft)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send draft reply")

    draft.status = "approved"
    draft.approved_by = user.user_id
    draft.approved_at = datetime.utcnow()
    draft.sent_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Draft approved and sent",
        "draft_id": draft.draft_id,
        "thread_id": thread_id,
    }


@router.post("/threads/{thread_id}/drafts/{draft_id}/reject")
def reject_draft(
    thread_id: str,
    draft_id: int,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Reject an AI reply draft."""
    from app.db.models.ai_reply_draft import AIReplyDraft

    draft_q = db.query(AIReplyDraft).filter(
        AIReplyDraft.draft_id == draft_id,
        AIReplyDraft.thread_id == thread_id,
        AIReplyDraft.is_archived == False,
    )
    draft_q = tenant_filter(draft_q, AIReplyDraft, tenant_id)
    draft = draft_q.first()

    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status != "pending":
        raise HTTPException(status_code=400, detail=f"Draft is already {draft.status}")

    draft.status = "rejected"
    draft.approved_by = user.user_id
    draft.approved_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Draft rejected",
        "draft_id": draft.draft_id,
        "thread_id": thread_id,
    }


@router.post("/threads/{thread_id}/generate-draft")
def generate_draft(
    thread_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Manually trigger AI draft generation for a thread."""
    from app.services.ai_reply_agent_service import generate_ai_reply_draft

    # Find the latest received message in the thread
    last_received_q = db.query(InboxMessage).filter(
        InboxMessage.thread_id == thread_id,
        InboxMessage.direction == MessageDirection.RECEIVED,
    )
    last_received_q = tenant_filter(last_received_q, InboxMessage, tenant_id)
    last_received = last_received_q.order_by(InboxMessage.received_at.desc()).first()

    if not last_received:
        raise HTTPException(
            status_code=404,
            detail="No received message found in this thread",
        )

    # Look up contact and campaign
    contact = None
    campaign_obj = None
    if last_received.contact_id:
        from app.db.models.contact import ContactDetails as ContactModel
        contact_q = db.query(ContactModel).filter(
            ContactModel.contact_id == last_received.contact_id
        )
        contact_q = tenant_filter(contact_q, ContactModel, tenant_id)
        contact = contact_q.first()
    if last_received.campaign_id:
        campaign_q = db.query(Campaign).filter(
            Campaign.campaign_id == last_received.campaign_id
        )
        campaign_q = tenant_filter(campaign_q, Campaign, tenant_id)
        campaign_obj = campaign_q.first()

    draft = generate_ai_reply_draft(
        db=db,
        thread_id=thread_id,
        received_message=last_received,
        contact=contact,
        campaign=campaign_obj,
        tenant_id=tenant_id or 1,
    )

    if not draft:
        return {
            "message": "No draft generated (OOO or max replies reached)",
            "thread_id": thread_id,
        }

    return {
        "message": "AI draft generated",
        "draft": {
            "draft_id": draft.draft_id,
            "subject": draft.subject,
            "body_text": draft.body_text,
            "intent_detected": draft.intent_detected,
            "confidence_score": draft.confidence_score,
            "status": draft.status,
        },
    }
