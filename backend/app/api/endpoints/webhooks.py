"""Webhook CRUD API endpoints."""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import require_role
from app.db.models.user import User, UserRole
from app.db.models.webhook import Webhook, WebhookDelivery

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

VALID_EVENTS = [
    "email.sent", "email.opened", "email.clicked", "email.replied",
    "email.bounced", "contact.unsubscribed", "campaign.completed", "lead.created",
]


class WebhookCreate(BaseModel):
    name: str = Field(..., max_length=255)
    url: str = Field(..., max_length=1000)
    secret: Optional[str] = None
    events: List[str]
    is_active: bool = True

class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


def _webhook_to_dict(w: Webhook) -> dict:
    return {
        "webhook_id": w.webhook_id,
        "name": w.name,
        "url": w.url,
        "events": json.loads(w.events_json) if w.events_json else [],
        "is_active": w.is_active,
        "last_triggered_at": w.last_triggered_at.isoformat() if w.last_triggered_at else None,
        "total_deliveries": w.total_deliveries,
        "total_failures": w.total_failures,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


@router.get("")
def list_webhooks(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    webhooks = db.query(Webhook).filter(Webhook.is_archived == False).all()
    return [_webhook_to_dict(w) for w in webhooks]


@router.post("")
def create_webhook(
    data: WebhookCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    for event in data.events:
        if event not in VALID_EVENTS:
            raise HTTPException(status_code=400, detail=f"Invalid event: {event}")

    import secrets
    webhook = Webhook(
        name=data.name,
        url=data.url,
        secret=data.secret or secrets.token_hex(32),
        events_json=json.dumps(data.events),
        is_active=data.is_active,
        created_by=user.user_id,
    )
    db.add(webhook)
    db.commit()
    db.refresh(webhook)
    result = _webhook_to_dict(webhook)
    result["secret"] = webhook.secret  # show secret on creation only
    return result


@router.get("/{webhook_id}")
def get_webhook(
    webhook_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    webhook = db.query(Webhook).filter(Webhook.webhook_id == webhook_id).first()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return _webhook_to_dict(webhook)


@router.put("/{webhook_id}")
def update_webhook(
    webhook_id: int,
    data: WebhookUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    webhook = db.query(Webhook).filter(Webhook.webhook_id == webhook_id).first()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if data.name is not None:
        webhook.name = data.name
    if data.url is not None:
        webhook.url = data.url
    if data.secret is not None:
        webhook.secret = data.secret
    if data.events is not None:
        for event in data.events:
            if event not in VALID_EVENTS:
                raise HTTPException(status_code=400, detail=f"Invalid event: {event}")
        webhook.events_json = json.dumps(data.events)
    if data.is_active is not None:
        webhook.is_active = data.is_active

    db.commit()
    db.refresh(webhook)
    return _webhook_to_dict(webhook)


@router.delete("/{webhook_id}")
def delete_webhook(
    webhook_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    webhook = db.query(Webhook).filter(Webhook.webhook_id == webhook_id).first()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    webhook.is_archived = True
    webhook.is_active = False
    db.commit()
    return {"message": "Webhook deleted"}


@router.get("/{webhook_id}/deliveries")
def list_deliveries(
    webhook_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    query = db.query(WebhookDelivery).filter(
        WebhookDelivery.webhook_id == webhook_id
    )
    total = query.count()
    items = query.order_by(WebhookDelivery.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [
            {
                "delivery_id": d.delivery_id,
                "event": d.event,
                "response_status": d.response_status,
                "success": d.success,
                "attempt_count": d.attempt_count,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
