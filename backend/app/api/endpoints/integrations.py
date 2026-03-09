"""Integration endpoints for Zapier/Make and API key management."""
import json
import hashlib
import secrets
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role
from app.db.models.user import User, UserRole
from app.db.models.api_key import ApiKey
from app.db.models.webhook import Webhook

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ─── API Key Management ───────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str = Field(..., max_length=255)
    scopes: List[str] = ["read"]

class ApiKeyResponse(BaseModel):
    key_id: int
    name: str
    key_prefix: str
    scopes: List[str]
    is_active: bool
    last_used_at: Optional[str] = None
    created_at: Optional[str] = None


@router.post("/api-keys")
def create_api_key(
    data: ApiKeyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Create a new API key. The full key is returned only once."""
    raw_key = f"exz_{secrets.token_hex(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]

    api_key = ApiKey(
        name=data.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes_json=json.dumps(data.scopes),
        user_id=user.user_id,
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return {
        "key_id": api_key.key_id,
        "name": api_key.name,
        "key": raw_key,  # shown only once
        "key_prefix": key_prefix,
        "scopes": data.scopes,
        "message": "Save this key — it will not be shown again.",
    }


@router.get("/api-keys")
def list_api_keys(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    keys = db.query(ApiKey).filter(
        ApiKey.is_active == True,
        ApiKey.is_archived == False,
    ).all()
    return [
        {
            "key_id": k.key_id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "scopes": json.loads(k.scopes_json) if k.scopes_json else [],
            "is_active": k.is_active,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in keys
    ]


@router.delete("/api-keys/{key_id}")
def revoke_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    key = db.query(ApiKey).filter(ApiKey.key_id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.is_active = False
    db.commit()
    return {"message": "API key revoked"}


# ─── Zapier/Make Integration ──────────────────────────────────────

class ZapierSubscribe(BaseModel):
    hookUrl: str  # Zapier sends this
    event: str    # which event to subscribe to

class ZapierUnsubscribe(BaseModel):
    hookUrl: str


@router.post("/zapier/subscribe")
def zapier_subscribe(
    data: ZapierSubscribe,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    """REST hook subscription from Zapier."""
    webhook = Webhook(
        name=f"Zapier: {data.event}",
        url=data.hookUrl,
        events_json=json.dumps([data.event]),
        is_active=True,
        created_by=user.user_id,
    )
    db.add(webhook)
    db.commit()
    db.refresh(webhook)
    return {"webhook_id": webhook.webhook_id}


@router.delete("/zapier/subscribe/{hook_id}")
def zapier_unsubscribe(
    hook_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Unsubscribe a Zapier hook."""
    webhook = db.query(Webhook).filter(Webhook.webhook_id == hook_id).first()
    if webhook:
        webhook.is_active = False
        webhook.is_archived = True
        db.commit()
    return {"message": "Unsubscribed"}


@router.get("/zapier/sample/{event}")
def zapier_sample(event: str):
    """Return sample payload for Zapier field mapping."""
    samples = {
        "email.sent": {
            "event": "email.sent",
            "contact_email": "john@example.com",
            "contact_name": "John Doe",
            "subject": "Re: Your open position",
            "sent_at": "2026-01-15T10:30:00Z",
            "campaign_name": "Q1 Outreach",
        },
        "email.replied": {
            "event": "email.replied",
            "contact_email": "john@example.com",
            "contact_name": "John Doe",
            "subject": "Re: Your open position",
            "replied_at": "2026-01-16T14:00:00Z",
            "reply_body": "Thanks for reaching out...",
        },
        "lead.created": {
            "event": "lead.created",
            "lead_id": 123,
            "company": "Acme Corp",
            "job_title": "HR Manager",
            "state": "TX",
            "source": "linkedin",
        },
    }
    return [samples.get(event, {"event": event, "data": {}})]
