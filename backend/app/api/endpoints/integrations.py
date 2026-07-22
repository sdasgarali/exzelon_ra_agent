"""Integration endpoints for Zapier/Make and API key management."""
import json
import hashlib
import logging
import secrets
from datetime import datetime
from typing import Optional, List
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_active_user, require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.db.models.api_key import ApiKey
from app.db.models.webhook import Webhook
from app.db.query_helpers import tenant_filter

logger = logging.getLogger(__name__)

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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
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
        tenant_id=tenant_id or 1,
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    query = db.query(ApiKey).filter(
        ApiKey.is_active == True,
        ApiKey.is_archived == False,
    )
    query = tenant_filter(query, ApiKey, tenant_id)
    keys = query.all()
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    query = db.query(ApiKey).filter(ApiKey.key_id == key_id)
    query = tenant_filter(query, ApiKey, tenant_id)
    key = query.first()
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """REST hook subscription from Zapier."""
    webhook = Webhook(
        name=f"Zapier: {data.event}",
        url=data.hookUrl,
        events_json=json.dumps([data.event]),
        is_active=True,
        created_by=user.user_id,
        tenant_id=tenant_id or 1,
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Unsubscribe a Zapier hook."""
    query = db.query(Webhook).filter(Webhook.webhook_id == hook_id)
    query = tenant_filter(query, Webhook, tenant_id)
    webhook = query.first()
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


# ─── Zapier Inbound Actions ──────────────────────────────────────

class ZapierAddContact(BaseModel):
    email: str
    first_name: str
    last_name: str
    company: Optional[str] = None
    title: Optional[str] = None
    phone: Optional[str] = None


class ZapierEnrollCampaign(BaseModel):
    contact_id: int
    campaign_id: int


class ZapierCreateDeal(BaseModel):
    title: str
    value: Optional[float] = None
    contact_id: Optional[int] = None
    client_id: Optional[int] = None


@router.post("/zapier/actions/add-contact")
def zapier_add_contact(
    data: ZapierAddContact,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a contact from Zapier webhook."""
    from app.db.models.contact import ContactDetails
    contact = ContactDetails(
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        client_name=data.company or "",
        title=data.title,
        phone=data.phone,
        source="zapier",
        tenant_id=tenant_id or 1,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return {"contact_id": contact.contact_id, "email": contact.email, "status": "created"}


@router.post("/zapier/actions/enroll-campaign")
def zapier_enroll_campaign(
    data: ZapierEnrollCampaign,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Enroll a contact in a campaign from Zapier."""
    from app.db.models.campaign import Campaign, CampaignContact, CampaignContactStatus
    campaign = db.query(Campaign).filter(Campaign.campaign_id == data.campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    existing = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == data.campaign_id,
        CampaignContact.contact_id == data.contact_id,
    ).first()
    if existing:
        return {"status": "already_enrolled", "id": existing.id}

    cc = CampaignContact(
        campaign_id=data.campaign_id,
        contact_id=data.contact_id,
        status=CampaignContactStatus.ACTIVE,
        current_step=1,
        enrolled_at=datetime.utcnow(),
    )
    db.add(cc)
    campaign.total_contacts = (campaign.total_contacts or 0) + 1
    db.commit()
    return {"status": "enrolled", "id": cc.id}


@router.post("/zapier/actions/create-deal")
def zapier_create_deal(
    data: ZapierCreateDeal,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a CRM deal from Zapier."""
    from app.db.models.deal import Deal, DealStage
    # Get first stage
    first_stage = db.query(DealStage).filter(
        DealStage.stage_order == 1,
    ).first()
    deal = Deal(
        title=data.title,
        value=data.value or 0,
        contact_id=data.contact_id,
        client_id=data.client_id,
        stage_id=first_stage.stage_id if first_stage else None,
        probability=10,
        tenant_id=tenant_id or 1,
    )
    db.add(deal)
    db.commit()
    db.refresh(deal)
    return {"deal_id": deal.deal_id, "title": deal.title, "status": "created"}


# ─── Resource Pool ATS hand-off (Phase 1) ─────────────────────────

@router.post("/resource-pool/push-lead/{lead_id}")
def push_lead_to_resource_pool(
    lead_id: int,
    stage: str = Query("LEAD", description="Opportunity stage: LEAD or QUALIFIED"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Push a qualified lead (Job + Company + Contact + Opportunity) to Resource Pool.

    Idempotent: Resource Pool upserts on ``externalRef = ra-lead-<lead_id>``.
    """
    from app.services.integrations.resource_pool_client import push_lead_by_id
    try:
        rp = push_lead_by_id(db, lead_id, tenant_id=tenant_id, stage=stage)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else "??"
        body = e.response.text[:500] if e.response is not None else ""
        logger.warning("Resource Pool push failed (HTTP %s) for lead %s", code, lead_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Resource Pool rejected the lead (HTTP {code}): {body}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Could not reach Resource Pool: {e}")

    if rp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resource Pool integration not configured (set resourcepool_api_url + resourcepool_api_key).",
        )
    return {"ok": True, "lead_id": lead_id, "resource_pool": rp}
