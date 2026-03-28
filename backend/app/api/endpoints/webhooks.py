"""Webhook CRUD API endpoints."""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.db.models.webhook import Webhook, WebhookDelivery
from app.db.query_helpers import tenant_filter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

VALID_EVENTS = [
    "email.sent", "email.opened", "email.clicked", "email.replied",
    "email.bounced", "contact.unsubscribed", "campaign.completed", "lead.created",
    # Enhanced events (Phase 4.1)
    "contact.created", "contact.validated", "campaign.started", "campaign.paused",
    "deal.created", "deal.won", "deal.lost", "deal.stage_changed",
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    query = db.query(Webhook).filter(Webhook.is_archived == False)
    query = tenant_filter(query, Webhook, tenant_id)
    webhooks = query.all()
    return [_webhook_to_dict(w) for w in webhooks]


@router.post("")
def create_webhook(
    data: WebhookCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
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
        tenant_id=tenant_id or 1,
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    query = db.query(Webhook).filter(Webhook.webhook_id == webhook_id)
    query = tenant_filter(query, Webhook, tenant_id)
    webhook = query.first()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return _webhook_to_dict(webhook)


@router.put("/{webhook_id}")
def update_webhook(
    webhook_id: int,
    data: WebhookUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    query = db.query(Webhook).filter(Webhook.webhook_id == webhook_id)
    query = tenant_filter(query, Webhook, tenant_id)
    webhook = query.first()
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    query = db.query(Webhook).filter(Webhook.webhook_id == webhook_id)
    query = tenant_filter(query, Webhook, tenant_id)
    webhook = query.first()
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    # Verify tenant access to the parent webhook
    wh_query = db.query(Webhook).filter(Webhook.webhook_id == webhook_id)
    wh_query = tenant_filter(wh_query, Webhook, tenant_id)
    if not wh_query.first():
        raise HTTPException(status_code=404, detail="Webhook not found")

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
                "response_body": d.response_body[:200] if d.response_body else None,
                "success": d.success,
                "attempt_count": d.attempt_count,
                "next_retry_at": d.next_retry_at.isoformat() if d.next_retry_at else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/deliveries/all")
def list_all_deliveries(
    status: Optional[str] = Query(None, description="Filter: 'failed' or 'success'"),
    webhook_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List webhook deliveries with optional status filter."""
    query = db.query(WebhookDelivery)

    # Filter deliveries through parent Webhook tenant_id
    if tenant_id is not None:
        query = query.join(Webhook, WebhookDelivery.webhook_id == Webhook.webhook_id).filter(
            Webhook.tenant_id == tenant_id
        )

    if webhook_id:
        query = query.filter(WebhookDelivery.webhook_id == webhook_id)
    if status == "failed":
        query = query.filter(WebhookDelivery.success == False)
    elif status == "success":
        query = query.filter(WebhookDelivery.success == True)

    total = query.count()
    items = query.order_by(WebhookDelivery.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [
            {
                "delivery_id": d.delivery_id,
                "webhook_id": d.webhook_id,
                "event": d.event,
                "response_status": d.response_status,
                "response_body": d.response_body[:200] if d.response_body else None,
                "success": d.success,
                "attempt_count": d.attempt_count,
                "next_retry_at": d.next_retry_at.isoformat() if d.next_retry_at else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/deliveries/{delivery_id}/retry")
def retry_delivery(
    delivery_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Manually retry a failed webhook delivery."""
    delivery = db.query(WebhookDelivery).filter(
        WebhookDelivery.delivery_id == delivery_id
    ).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")

    wh_query = db.query(Webhook).filter(Webhook.webhook_id == delivery.webhook_id)
    wh_query = tenant_filter(wh_query, Webhook, tenant_id)
    webhook = wh_query.first()
    if not webhook:
        raise HTTPException(status_code=404, detail="Parent webhook not found")

    # Re-deliver
    from app.services.webhook_dispatcher import _deliver_webhook
    try:
        payload = json.loads(delivery.payload_json) if delivery.payload_json else {}
        event = delivery.event or "unknown"
        _deliver_webhook(webhook, event, payload.get("data", payload), db)
        return {"message": "Retry initiated", "delivery_id": delivery_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retry failed: {str(e)}")
