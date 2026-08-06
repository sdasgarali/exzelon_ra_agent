"""Integration endpoints for Zapier/Make and API key management."""
import json
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.api.deps import get_db, get_current_active_user, require_role, get_current_tenant_id
from app.core.settings_resolver import get_tenant_setting
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


# ─── Resource Pool outcome webhooks → attribution (Phase 2) ───────

_RP_ATTR_EVENTS = {"offer.accepted", "placement.created", "invoice.paid"}


def _lead_id_from_external_ref(external_ref: Optional[str]) -> Optional[int]:
    """'ra-lead-42' or 'ra-t1-lead-42' -> 42. Delegates to the shared parser."""
    from app.services.integrations.resource_pool_client import parse_external_ref
    return parse_external_ref(external_ref)[1]


@router.post("/resource-pool/webhook")
async def resource_pool_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Resource Pool outcome webhooks (offer.accepted / placement.created /
    invoice.paid), verify the HMAC signature, and record an attribution row mapped
    back to the originating lead + source + campaign. Idempotent per RP entity.
    """
    raw = await request.body()
    provided_sig = request.headers.get("X-Exzelon-Signature", "")

    secret = (get_tenant_setting(db, "resourcepool_webhook_secret", tenant_id=1, default="") or "").strip()
    if not secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Webhook secret not configured (resourcepool_webhook_secret).")
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not (provided_sig and hmac.compare_digest(expected, provided_sig)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        envelope = json.loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON")

    event = envelope.get("event") or request.headers.get("X-Exzelon-Event", "")
    data = envelope.get("data") or {}
    if event not in _RP_ATTR_EVENTS:
        return {"ok": True, "ignored": event}  # ack unknown/unsubscribed events

    from app.db.models.resource_pool_attribution import ResourcePoolAttribution
    from app.db.models.lead import LeadDetails
    from app.db.models.outreach import OutreachEvent

    from app.services.integrations.resource_pool_client import parse_external_ref
    external_ref = data.get("externalRef")
    ref_tenant_id, lead_id = parse_external_ref(external_ref)

    # Resolve lead → tenant + source; and a best-effort originating campaign.
    # When the ref carries a tenant (ra-t<tenant>-lead-<id>), scope the lead
    # lookup by it so a lead_id shared across tenants maps to the RIGHT lead.
    tenant_id, source, campaign_id = ref_tenant_id or 1, None, None
    if lead_id is not None:
        lq = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id)
        if ref_tenant_id is not None:
            lq = lq.filter(LeadDetails.tenant_id == ref_tenant_id)
        lead = lq.first()
        if lead:
            tenant_id = lead.tenant_id or ref_tenant_id or 1
            source = lead.source
            oe = (db.query(OutreachEvent)
                  .filter(OutreachEvent.lead_id == lead_id, OutreachEvent.campaign_id.isnot(None))
                  .order_by(OutreachEvent.event_id.desc()).first())
            if oe:
                campaign_id = oe.campaign_id

    rp_entity_id = str(data.get("placementId") or data.get("offerId") or data.get("invoiceId") or "") or None
    amount = data.get("offerAmount")
    if amount is None:
        amount = data.get("amount")
    if amount is None:
        amount = data.get("billRate")

    occurred_at = None
    ca = envelope.get("createdAt")
    if ca:
        try:
            occurred_at = datetime.fromisoformat(str(ca).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            occurred_at = None

    # Idempotent upsert on (tenant_id, event_type, rp_entity_id).
    row = None
    if rp_entity_id:
        row = (db.query(ResourcePoolAttribution)
               .filter(ResourcePoolAttribution.tenant_id == tenant_id,
                       ResourcePoolAttribution.event_type == event,
                       ResourcePoolAttribution.rp_entity_id == rp_entity_id).first())
    if row is None:
        row = ResourcePoolAttribution(tenant_id=tenant_id, event_type=event, rp_entity_id=rp_entity_id)
        db.add(row)
    row.external_ref = external_ref
    row.lead_id = lead_id
    row.campaign_id = campaign_id
    row.source = source
    row.amount = amount
    row.currency = data.get("currency") or "USD"
    row.occurred_at = occurred_at
    row.raw_json = json.dumps(data)[:8000]
    db.commit()

    return {"ok": True, "event": event, "lead_id": lead_id, "attribution_id": row.attribution_id}


def _attribution_query(db: Session, tenant_id: Optional[int], start: Optional[str], end: Optional[str]):
    """Tenant- and date-range-filtered ResourcePoolAttribution query (end inclusive)."""
    from app.db.models.resource_pool_attribution import ResourcePoolAttribution as A
    q = db.query(A)
    if tenant_id is not None:
        q = q.filter(A.tenant_id == tenant_id)
    when = func.coalesce(A.occurred_at, A.created_at)
    if start:
        try:
            q = q.filter(when >= datetime.fromisoformat(start))
        except ValueError:
            pass
    if end:
        try:
            q = q.filter(when < datetime.fromisoformat(end) + timedelta(days=1))
        except ValueError:
            pass
    return q


@router.get("/resource-pool/attribution")
def resource_pool_attribution_summary(
    start: Optional[str] = Query(None, description="Inclusive start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="Inclusive end date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Campaign→placement→revenue attribution summary from Resource Pool outcomes.

    Optional ``start``/``end`` (YYYY-MM-DD) filter every aggregation by the outcome
    date (occurred_at, falling back to created_at); ``end`` is inclusive.
    """
    from app.db.models.resource_pool_attribution import ResourcePoolAttribution as A

    base = _attribution_query(db, tenant_id, start, end)

    by_event = dict(
        base.with_entities(A.event_type, func.count(A.attribution_id)).group_by(A.event_type).all()
    )
    by_source = [
        {"source": s or "unknown", "events": int(n or 0), "amount": float(amt or 0)}
        for s, n, amt in base.with_entities(A.source, func.count(A.attribution_id), func.sum(A.amount))
        .group_by(A.source).order_by(func.sum(A.amount).desc().nullslast()).all()
    ]
    placements = int(by_event.get("placement.created", 0))
    offers_accepted = int(by_event.get("offer.accepted", 0))
    revenue_paid = float(
        base.filter(A.event_type == "invoice.paid")
        .with_entities(func.coalesce(func.sum(A.amount), 0)).scalar() or 0
    )
    recent = [
        {
            "event_type": r.event_type,
            "source": r.source,
            "lead_id": r.lead_id,
            "external_ref": r.external_ref,
            "amount": float(r.amount) if r.amount is not None else None,
            "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
        }
        for r in base.order_by(A.attribution_id.desc()).limit(25).all()
    ]
    # Daily time series: revenue (paid invoices) + outcome count per day.
    _day = func.date(func.coalesce(A.occurred_at, A.created_at))
    timeseries = [
        {"date": str(d), "revenue": float(rev or 0), "outcomes": int(oc or 0)}
        for d, rev, oc in (
            base.with_entities(
                _day.label("d"),
                func.coalesce(func.sum(case((A.event_type == "invoice.paid", A.amount), else_=0)), 0),
                func.count(A.attribution_id),
            ).group_by(_day).order_by(_day).all()
        )
    ]
    return {
        "totals": {
            "offers_accepted": offers_accepted,
            "placements": placements,
            "invoices_paid": int(by_event.get("invoice.paid", 0)),
            "revenue_paid": revenue_paid,
        },
        "by_source": by_source,
        "by_event": {k: int(v) for k, v in by_event.items()},
        "recent": recent,
        "timeseries": timeseries,
    }


# ─── Candidate match summary feed (Phase 3) ───────────────────────

@router.get("/resource-pool/match-summary/{lead_id}")
def resource_pool_match_summary(
    lead_id: int,
    threshold: int = Query(80, ge=0, le=100, description="Minimum fit %"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Candidate match summary for a lead's job (count of candidates ≥ threshold% fit
    + top anonymized matches), fetched from Resource Pool — powers the outreach pitch.
    """
    from app.services.integrations.resource_pool_client import ResourcePoolClient, build_external_ref
    client = ResourcePoolClient.from_settings(db, tenant_id=tenant_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Resource Pool integration not configured (set resourcepool_api_url + resourcepool_api_key).")
    external_ref = build_external_ref(lead_id, tenant_id)
    try:
        summary = client.get_match_summary(external_ref, threshold=threshold)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 502
        if code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Lead {lead_id} not found in Resource Pool (push it first).")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Resource Pool match-summary failed (HTTP {code}).")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Could not reach Resource Pool: {e}")
    return {"ok": True, "lead_id": lead_id, **summary}


@router.get("/resource-pool/attribution/export")
def resource_pool_attribution_export(
    start: Optional[str] = Query(None, description="Inclusive start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="Inclusive end date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """CSV export of the (date-range-filtered) attribution rows."""
    import csv
    import io
    from fastapi.responses import StreamingResponse
    from app.db.models.resource_pool_attribution import ResourcePoolAttribution as A

    q = _attribution_query(db, tenant_id, start, end).order_by(A.attribution_id.desc())
    cols = ["attribution_id", "event_type", "source", "lead_id", "external_ref",
            "campaign_id", "amount", "currency", "occurred_at", "created_at", "rp_entity_id"]

    def _iter():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for r in q.yield_per(500):
            w.writerow([
                r.attribution_id, r.event_type, r.source or "", r.lead_id or "",
                r.external_ref or "", r.campaign_id or "",
                float(r.amount) if r.amount is not None else "", r.currency or "",
                r.occurred_at.isoformat() if r.occurred_at else "",
                r.created_at.isoformat() if getattr(r, "created_at", None) else "",
                r.rp_entity_id or "",
            ])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    fname = f"attribution_{start or 'all'}_{end or 'all'}.csv"
    return StreamingResponse(_iter(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ─── Resource Pool export (pull side of RP's "Import from NeuraLeads") ──────────

def _export_contact(c) -> dict:
    """Serialize a ContactDetails to the RP import contact shape."""
    name = " ".join([p for p in [(c.first_name or "").strip(), (c.last_name or "").strip()] if p]).strip()
    return {
        "name": name or (getattr(c, "client_name", None) or "Contact"),
        "email": (c.email or None),
        "phone": (getattr(c, "phone", None) or None),
        "title": (getattr(c, "title", None) or None),
        "priority": getattr(c, "priority_level", None),
        "validationStatus": getattr(c, "validation_status", None),
    }


@router.get("/export/leads")
def export_leads_for_resource_pool(
    limit: int = Query(50, ge=1, le=200),
    since_id: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Export this tenant's leads (company + job + FULL contact list + opportunity)
    so Resource Pool can PULL them via its "Import from NeuraLeads" button.

    Auth: standard user auth — accepts ``X-API-Key`` (tenant-scoped), so an RP-held
    NeuraLeads key only ever sees its own tenant's leads. Only leads with at least
    one contact are returned. Page forward with ``since_id`` = the previous
    response's ``nextSinceId``.
    """
    from app.db.models.lead import LeadDetails
    from app.db.models.client import ClientInfo
    from app.db.models.contact import ContactDetails
    from app.services.integrations.resource_pool_client import build_lead_payload, _tenant_domain

    lq = tenant_filter(db.query(LeadDetails), LeadDetails, tenant_id)
    if since_id:
        lq = lq.filter(LeadDetails.lead_id > since_id)
    leads = lq.order_by(LeadDetails.lead_id.asc()).limit(limit).all()

    tenant_domain = _tenant_domain(db, tenant_id)
    out: List[dict] = []
    for lead in leads:
        contacts = tenant_filter(
            db.query(ContactDetails).filter(ContactDetails.lead_id == lead.lead_id),
            ContactDetails, tenant_id,
        ).all()
        if not contacts:
            continue  # nothing to hand off without a client contact
        company = None
        if lead.client_name:
            company = tenant_filter(
                db.query(ClientInfo).filter(ClientInfo.client_name == lead.client_name),
                ClientInfo, tenant_id,
            ).first()
        payload = build_lead_payload(lead, company=company, contact=None, stage="LEAD",
                                     tenant_domain=tenant_domain, tenant_id=tenant_id)
        payload["contacts"] = [_export_contact(c) for c in contacts]
        out.append(payload)

    next_since_id = leads[-1].lead_id if leads else since_id
    return {"leads": out, "count": len(out), "nextSinceId": next_since_id}
