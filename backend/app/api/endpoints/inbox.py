"""Unified Inbox (Unibox) API endpoints."""
import json
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role
from app.db.models.user import User, UserRole
from app.db.models.inbox_message import InboxMessage, MessageDirection
from app.db.models.contact import ContactDetails
from app.db.models.sender_mailbox import SenderMailbox

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
    mailbox_id: Optional[int] = None,
    campaign_id: Optional[int] = None,
    is_read: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """List inbox threads, sorted by latest message."""
    # Get distinct thread_ids with filters, then fetch latest message per thread
    thread_query = db.query(
        InboxMessage.thread_id,
        func.max(InboxMessage.received_at).label("latest"),
    ).filter(InboxMessage.is_deleted == False)

    if category:
        thread_query = thread_query.filter(InboxMessage.category == category)
    if mailbox_id:
        thread_query = thread_query.filter(InboxMessage.mailbox_id == mailbox_id)
    if campaign_id:
        thread_query = thread_query.filter(InboxMessage.campaign_id == campaign_id)
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
        latest_msg = db.query(InboxMessage).filter(
            InboxMessage.thread_id == thread_id,
        ).order_by(InboxMessage.received_at.desc()).first()

        if not latest_msg:
            continue

        msg_count = db.query(InboxMessage).filter(
            InboxMessage.thread_id == thread_id
        ).count()

        unread_count = db.query(InboxMessage).filter(
            InboxMessage.thread_id == thread_id,
            InboxMessage.is_read == False,
        ).count()

        # Get contact info — try DB contact first, then infer from received messages
        contact_name = latest_msg.from_email
        if latest_msg.contact_id:
            contact = db.query(ContactDetails).filter(
                ContactDetails.contact_id == latest_msg.contact_id
            ).first()
            if contact:
                contact_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or latest_msg.from_email
        else:
            # For threads without contact_id, use the external email as contact identifier
            # Find the first received message to get the external sender's email
            received_msg = db.query(InboxMessage).filter(
                InboxMessage.thread_id == thread_id,
                InboxMessage.direction == MessageDirection.RECEIVED,
            ).first()
            if received_msg:
                contact_name = received_msg.from_email
            else:
                # Sent-only thread — use the recipient
                sent_msg = db.query(InboxMessage).filter(
                    InboxMessage.thread_id == thread_id,
                    InboxMessage.direction == MessageDirection.SENT,
                ).first()
                if sent_msg:
                    contact_name = sent_msg.to_email

        # Get category/sentiment/snippet from latest RECEIVED message (not sent)
        latest_received = db.query(InboxMessage).filter(
            InboxMessage.thread_id == thread_id,
            InboxMessage.direction == MessageDirection.RECEIVED,
        ).order_by(InboxMessage.received_at.desc()).first()

        thread_category = latest_received.category if latest_received else None
        thread_sentiment = latest_received.sentiment if latest_received else None
        snippet = (latest_received.body_text or "")[:120] if latest_received else ""

        # Use the first message's subject for the thread subject
        first_msg = db.query(InboxMessage).filter(
            InboxMessage.thread_id == thread_id,
        ).order_by(InboxMessage.received_at.asc()).first()

        result.append({
            "thread_id": thread_id,
            "subject": first_msg.subject if first_msg else latest_msg.subject,
            "latest_message_at": latest_at.isoformat() if latest_at else None,
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
):
    """Get all messages in a thread."""
    messages = db.query(InboxMessage).filter(
        InboxMessage.thread_id == thread_id,
        InboxMessage.is_deleted == False,
    ).order_by(InboxMessage.received_at.asc()).all()

    if not messages:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Get contact info
    contact_info = None
    contact_id = messages[0].contact_id
    if contact_id:
        contact = db.query(ContactDetails).filter(
            ContactDetails.contact_id == contact_id
        ).first()
        if contact:
            contact_info = {
                "contact_id": contact.contact_id,
                "name": f"{contact.first_name or ''} {contact.last_name or ''}".strip(),
                "email": contact.email,
                "title": contact.title,
                "company": contact.client_name,
                "phone": contact.phone,
            }

    return {
        "thread_id": thread_id,
        "contact": contact_info,
        "messages": [
            {
                "message_id": m.message_id,
                "direction": m.direction.value if m.direction else "sent",
                "from_email": m.from_email,
                "to_email": m.to_email,
                "subject": m.subject,
                "body_html": m.body_html,
                "body_text": m.body_text,
                "received_at": m.received_at.isoformat() if m.received_at else None,
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
):
    """Mark all messages in a thread as read."""
    updated = db.query(InboxMessage).filter(
        InboxMessage.thread_id == thread_id,
        InboxMessage.is_read == False,
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"marked_read": updated}


@router.put("/threads/{thread_id}/category")
def set_thread_category(
    thread_id: str,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Set category label for all messages in a thread."""
    updated = db.query(InboxMessage).filter(
        InboxMessage.thread_id == thread_id,
    ).update({"category": data.category}, synchronize_session=False)
    db.commit()
    return {"updated": updated, "category": data.category}


# ─── Delete ────────────────────────────────────────────────────────

@router.delete("/threads/{thread_id}")
def delete_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Soft-delete all messages in a thread."""
    now = datetime.utcnow()
    updated = db.query(InboxMessage).filter(
        InboxMessage.thread_id == thread_id,
        InboxMessage.is_deleted == False,
    ).update({"is_deleted": True, "deleted_at": now}, synchronize_session=False)
    db.commit()
    if not updated:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"deleted": updated, "thread_id": thread_id}


@router.post("/threads/bulk-delete")
def bulk_delete_threads(
    data: BulkDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Soft-delete multiple threads at once."""
    if not data.thread_ids:
        raise HTTPException(status_code=400, detail="No thread IDs provided")
    if len(data.thread_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 threads per request")

    now = datetime.utcnow()
    updated = db.query(InboxMessage).filter(
        InboxMessage.thread_id.in_(data.thread_ids),
        InboxMessage.is_deleted == False,
    ).update({"is_deleted": True, "deleted_at": now}, synchronize_session=False)
    db.commit()
    return {"deleted": updated, "thread_ids": data.thread_ids}


# ─── Reply ─────────────────────────────────────────────────────────

@router.post("/reply")
def send_reply(
    data: ReplyCompose,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Send a reply in a thread."""
    # Get thread context
    last_received = db.query(InboxMessage).filter(
        InboxMessage.thread_id == data.thread_id,
        InboxMessage.direction == MessageDirection.RECEIVED,
    ).order_by(InboxMessage.received_at.desc()).first()

    if not last_received:
        # Maybe replying to a sent-only thread
        last_msg = db.query(InboxMessage).filter(
            InboxMessage.thread_id == data.thread_id,
        ).order_by(InboxMessage.received_at.desc()).first()
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
    mailbox = db.query(SenderMailbox).filter(
        SenderMailbox.mailbox_id == data.mailbox_id
    ).first()
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
):
    """Generate an AI-suggested reply for a thread."""
    from app.db.models.campaign import Campaign

    messages = db.query(InboxMessage).filter(
        InboxMessage.thread_id == thread_id,
    ).order_by(InboxMessage.received_at.asc()).all()

    if not messages:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Look up contact and campaign from thread messages
    contact = None
    campaign = None
    for msg in messages:
        if msg.contact_id and not contact:
            contact = db.query(ContactDetails).filter(
                ContactDetails.contact_id == msg.contact_id
            ).first()
        if msg.campaign_id and not campaign:
            campaign = db.query(Campaign).filter(
                Campaign.campaign_id == msg.campaign_id
            ).first()
        if contact and campaign:
            break

    from app.services.ai_reply_agent import generate_reply_suggestion
    return generate_reply_suggestion(messages, contact, campaign, db)


# ─── Stats ─────────────────────────────────────────────────────────

@router.get("/stats")
def inbox_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Get inbox statistics."""
    total_threads = db.query(func.count(func.distinct(InboxMessage.thread_id))).filter(
        InboxMessage.is_deleted == False,
    ).scalar() or 0
    unread_count = db.query(func.count(func.distinct(InboxMessage.thread_id))).filter(
        InboxMessage.is_read == False,
        InboxMessage.is_deleted == False,
    ).scalar() or 0

    # Category breakdown
    categories = db.query(
        InboxMessage.category,
        func.count(func.distinct(InboxMessage.thread_id)),
    ).filter(InboxMessage.is_deleted == False).group_by(InboxMessage.category).all()

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
):
    """Trigger manual inbox sync."""
    from app.services.inbox_syncer import sync_inbox
    result = sync_inbox(db)
    return {"message": "Sync completed", "result": result}
