"""Super admin tenant management endpoints."""
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps.database import get_db
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.campaign import Campaign
from app.api.deps.auth import get_current_active_user, require_role, UserRole
from app.core.security import create_access_token
from app.core.config import settings
from app.services.audit_helper import write_audit_log
from app.core.settings_resolver import get_tenant_setting_bool, set_tenant_setting

router = APIRouter(prefix="/admin/tenants", tags=["Admin - Tenants"])

# All routes require super_admin
super_admin_dep = require_role([UserRole.SUPER_ADMIN])


class TenantSummary(BaseModel):
    tenant_id: int
    name: str
    slug: str
    plan: str
    is_active: bool
    website: Optional[str] = None
    industry: Optional[str] = None
    user_count: int
    lead_count: int
    contact_count: int
    mailbox_count: int
    campaign_count: int
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class TenantDetail(TenantSummary):
    domain: Optional[str] = None
    logo_url: Optional[str] = None
    max_users: int
    max_mailboxes: int
    max_contacts: int
    max_campaigns: int
    max_leads: int
    users: list = []


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None
    max_users: Optional[int] = None
    max_mailboxes: Optional[int] = None
    max_contacts: Optional[int] = None
    max_campaigns: Optional[int] = None
    max_leads: Optional[int] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    company_address: Optional[str] = None


@router.get("", response_model=List[TenantSummary])
async def list_tenants(
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
):
    """List all tenants with resource counts. Super admin only."""
    query = db.query(Tenant)
    if search:
        query = query.filter(
            (Tenant.name.ilike(f"%{search}%")) | (Tenant.slug.ilike(f"%{search}%"))
        )

    tenants = query.order_by(Tenant.tenant_id.asc()).offset(skip).limit(limit).all()

    result = []
    for t in tenants:
        result.append(TenantSummary(
            tenant_id=t.tenant_id,
            name=t.name,
            slug=t.slug,
            plan=t.plan.value if hasattr(t.plan, 'value') else str(t.plan),
            is_active=t.is_active,
            website=t.website,
            industry=t.industry,
            user_count=db.query(User).filter(User.tenant_id == t.tenant_id).count(),
            lead_count=db.query(LeadDetails).filter(LeadDetails.tenant_id == t.tenant_id).count(),
            contact_count=db.query(ContactDetails).filter(ContactDetails.tenant_id == t.tenant_id).count(),
            mailbox_count=db.query(SenderMailbox).filter(SenderMailbox.tenant_id == t.tenant_id).count(),
            campaign_count=db.query(Campaign).filter(Campaign.tenant_id == t.tenant_id).count(),
            created_at=t.created_at.isoformat() if hasattr(t, 'created_at') and t.created_at else None,
        ))

    return result


@router.get("/{tenant_id}", response_model=TenantDetail)
async def get_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Get tenant detail with users and resource counts. Super admin only."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    users = db.query(User).filter(User.tenant_id == tenant_id).all()
    user_list = [
        {
            "user_id": u.user_id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role.value if hasattr(u.role, 'value') else str(u.role),
            "is_active": u.is_active,
            "is_verified": u.is_verified,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        }
        for u in users
    ]

    return TenantDetail(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        slug=tenant.slug,
        plan=tenant.plan.value if hasattr(tenant.plan, 'value') else str(tenant.plan),
        is_active=tenant.is_active,
        website=tenant.website,
        industry=tenant.industry,
        domain=tenant.domain,
        logo_url=tenant.logo_url,
        max_users=tenant.max_users,
        max_mailboxes=tenant.max_mailboxes,
        max_contacts=tenant.max_contacts,
        max_campaigns=tenant.max_campaigns,
        max_leads=tenant.max_leads,
        user_count=len(users),
        lead_count=db.query(LeadDetails).filter(LeadDetails.tenant_id == tenant_id).count(),
        contact_count=db.query(ContactDetails).filter(ContactDetails.tenant_id == tenant_id).count(),
        mailbox_count=db.query(SenderMailbox).filter(SenderMailbox.tenant_id == tenant_id).count(),
        campaign_count=db.query(Campaign).filter(Campaign.tenant_id == tenant_id).count(),
        created_at=tenant.created_at.isoformat() if hasattr(tenant, 'created_at') and tenant.created_at else None,
        users=user_list,
    )


@router.put("/{tenant_id}")
async def update_tenant(
    tenant_id: int,
    data: TenantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Update tenant plan, limits, or status. Super admin only."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if data.name is not None:
        tenant.name = data.name
    if data.plan is not None:
        try:
            tenant.plan = TenantPlan(data.plan)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid plan: {data.plan}")
    if data.is_active is not None:
        tenant.is_active = data.is_active
    if data.max_users is not None:
        tenant.max_users = data.max_users
    if data.max_mailboxes is not None:
        tenant.max_mailboxes = data.max_mailboxes
    if data.max_contacts is not None:
        tenant.max_contacts = data.max_contacts
    if data.max_campaigns is not None:
        tenant.max_campaigns = data.max_campaigns
    if data.max_leads is not None:
        tenant.max_leads = data.max_leads
    if data.website is not None:
        tenant.website = data.website
    if data.industry is not None:
        tenant.industry = data.industry
    if data.company_address is not None:
        tenant.company_address = data.company_address

    db.commit()
    db.refresh(tenant)

    return {
        "message": "Tenant updated",
        "tenant_id": tenant.tenant_id,
        "plan": tenant.plan.value if hasattr(tenant.plan, 'value') else str(tenant.plan),
    }


@router.delete("/{tenant_id}")
async def deactivate_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Soft-delete (deactivate) a tenant. Super admin only."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Don't allow deactivating Tenant #1 (system tenant)
    if tenant.tenant_id == 1:
        raise HTTPException(status_code=400, detail="Cannot deactivate the system tenant")

    tenant.is_active = False
    # Also deactivate all users in this tenant
    db.query(User).filter(User.tenant_id == tenant_id).update({"is_active": False})
    db.commit()

    return {"message": f"Tenant '{tenant.name}' deactivated", "tenant_id": tenant_id}


@router.post("/{tenant_id}/impersonate")
async def impersonate_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Get a token scoped to a specific tenant for impersonation. Super admin only."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    token_data = {
        "sub": current_user.email,
        "role": current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role),
        "tenant_id": tenant_id,
        "plan": tenant.plan.value if hasattr(tenant.plan, 'value') else str(tenant.plan),
        "impersonating": True,
    }

    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(hours=2),  # Short-lived impersonation token
    )

    write_audit_log(db, tenant_id=0, entity_type="auth",
                    entity_id=current_user.user_id, action="impersonation_start",
                    changed_by=current_user.email,
                    notes=f"target_tenant={tenant_id} ({tenant.name})")
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "tenant_name": tenant.name,
        "tenant_id": tenant_id,
        "expires_in": 7200,
    }


# ─── White-Label Branding ─────────────────────────────────────────

class BrandingUpdate(BaseModel):
    brand_name: Optional[str] = None
    brand_logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None  # #hex
    brand_secondary_color: Optional[str] = None
    custom_domain: Optional[str] = None
    agency_mode: Optional[bool] = None


@router.put("/{tenant_id}/branding")
async def update_branding(
    tenant_id: int,
    data: BrandingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Update tenant branding for white-label. Super admin only."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    changes = {}

    if data.brand_name is not None:
        changes["brand_name"] = {"old": tenant.brand_name, "new": data.brand_name}
        tenant.brand_name = data.brand_name
    if data.brand_logo_url is not None:
        changes["brand_logo_url"] = {"old": tenant.brand_logo_url, "new": data.brand_logo_url}
        tenant.brand_logo_url = data.brand_logo_url
    if data.brand_primary_color is not None:
        # Validate hex color format
        color = data.brand_primary_color
        if color and not (color.startswith("#") and len(color) == 7):
            raise HTTPException(status_code=400, detail="brand_primary_color must be in #RRGGBB format")
        changes["brand_primary_color"] = {"old": tenant.brand_primary_color, "new": color}
        tenant.brand_primary_color = color
    if data.brand_secondary_color is not None:
        color = data.brand_secondary_color
        if color and not (color.startswith("#") and len(color) == 7):
            raise HTTPException(status_code=400, detail="brand_secondary_color must be in #RRGGBB format")
        changes["brand_secondary_color"] = {"old": tenant.brand_secondary_color, "new": color}
        tenant.brand_secondary_color = color
    if data.custom_domain is not None:
        changes["custom_domain"] = {"old": tenant.custom_domain, "new": data.custom_domain}
        tenant.custom_domain = data.custom_domain
    if data.agency_mode is not None:
        changes["agency_mode"] = {"old": tenant.agency_mode, "new": data.agency_mode}
        tenant.agency_mode = data.agency_mode

    if changes:
        write_audit_log(
            db,
            tenant_id=tenant_id,
            entity_type="tenant",
            entity_id=tenant_id,
            action="branding_update",
            changed_by=current_user.email,
            changed_fields=changes,
        )

    db.commit()
    db.refresh(tenant)

    return {
        "message": "Branding updated",
        "tenant_id": tenant.tenant_id,
        "branding": {
            "brand_name": tenant.brand_name,
            "brand_logo_url": tenant.brand_logo_url,
            "brand_primary_color": tenant.brand_primary_color,
            "brand_secondary_color": tenant.brand_secondary_color,
            "custom_domain": tenant.custom_domain,
            "agency_mode": tenant.agency_mode,
        },
    }


class FeatureFlagsUpdate(BaseModel):
    feature_email_validation_enabled: Optional[bool] = None
    feature_campaigns_enabled: Optional[bool] = None


@router.get("/{tenant_id}/features")
async def get_tenant_features(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Get feature flags for a tenant. Super admin only."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "tenant_id": tenant_id,
        "feature_email_validation_enabled": get_tenant_setting_bool(
            db, "feature_email_validation_enabled", tenant_id=tenant_id, default=True
        ),
        "feature_campaigns_enabled": get_tenant_setting_bool(
            db, "feature_campaigns_enabled", tenant_id=tenant_id, default=True
        ),
    }


@router.put("/{tenant_id}/features")
async def update_tenant_features(
    tenant_id: int,
    data: FeatureFlagsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Update feature flags for a tenant. Super admin only."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    changes = {}
    if data.feature_email_validation_enabled is not None:
        old_val = get_tenant_setting_bool(
            db, "feature_email_validation_enabled", tenant_id=tenant_id, default=True
        )
        set_tenant_setting(
            db, "feature_email_validation_enabled",
            data.feature_email_validation_enabled,
            tenant_id=tenant_id,
            updated_by=current_user.email,
        )
        changes["feature_email_validation_enabled"] = {
            "old": old_val, "new": data.feature_email_validation_enabled,
        }

    if data.feature_campaigns_enabled is not None:
        old_val = get_tenant_setting_bool(
            db, "feature_campaigns_enabled", tenant_id=tenant_id, default=True
        )
        set_tenant_setting(
            db, "feature_campaigns_enabled",
            data.feature_campaigns_enabled,
            tenant_id=tenant_id,
            updated_by=current_user.email,
        )
        changes["feature_campaigns_enabled"] = {
            "old": old_val, "new": data.feature_campaigns_enabled,
        }

    if changes:
        write_audit_log(
            db,
            tenant_id=tenant_id,
            entity_type="tenant",
            entity_id=tenant_id,
            action="feature_flags_update",
            changed_by=current_user.email,
            changed_fields=changes,
        )

    db.commit()

    return {
        "message": "Feature flags updated",
        "tenant_id": tenant_id,
        "feature_email_validation_enabled": get_tenant_setting_bool(
            db, "feature_email_validation_enabled", tenant_id=tenant_id, default=True
        ),
        "feature_campaigns_enabled": get_tenant_setting_bool(
            db, "feature_campaigns_enabled", tenant_id=tenant_id, default=True
        ),
    }


@router.get("/{tenant_id}/branding")
async def get_branding(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Get tenant branding configuration. Super admin only."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "tenant_id": tenant.tenant_id,
        "brand_name": tenant.brand_name,
        "brand_logo_url": tenant.brand_logo_url,
        "brand_primary_color": tenant.brand_primary_color,
        "brand_secondary_color": tenant.brand_secondary_color,
        "custom_domain": tenant.custom_domain,
        "agency_mode": tenant.agency_mode,
    }
