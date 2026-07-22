"""Super admin tenant management endpoints."""
import json as _json_admin
from datetime import timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.campaign import Campaign
from app.db.models.line_of_business import LineOfBusiness, LOBType, LOBStatus
from app.db.models.tenant_lob_assignment import TenantLOBAssignment
from app.api.deps.auth import require_role, UserRole
from app.core.security import create_access_token
from app.core.lob_defaults import LOB_DEFAULT_CONFIGS, LOB_TYPE_META, TENANT_PROMPT_PROFILES
from app.services.audit_helper import write_audit_log
from app.services.tenant_service import generate_unique_slug
from app.core.settings_resolver import get_tenant_setting_bool, set_tenant_setting

router = APIRouter(prefix="/admin/tenants", tags=["Admin - Tenants"])

# All routes require super_admin
super_admin_dep = require_role([UserRole.SUPER_ADMIN])


def _normalize_domain(d: Optional[str]) -> Optional[str]:
    """Normalize a registered domain so the SAME value links a tenant across systems
    (RA Agent ↔ Resource Pool). Strips scheme/www/path, lowercases."""
    if not d:
        return None
    import re
    clean = d.strip().lower()
    clean = re.sub(r"^https?://", "", clean)
    clean = re.sub(r"^www\.", "", clean)
    clean = clean.split("/")[0].strip()
    return clean or None


def _domain_taken(db: Session, domain: str, exclude_tenant_id: Optional[int] = None) -> bool:
    q = db.query(Tenant).filter(Tenant.domain == domain)
    if exclude_tenant_id is not None:
        q = q.filter(Tenant.tenant_id != exclude_tenant_id)
    return db.query(q.exists()).scalar()


class TenantSummary(BaseModel):
    tenant_id: int
    name: str
    slug: str
    domain: Optional[str] = None  # registered domain — cross-system link key (Resource Pool)
    plan: str
    is_active: bool
    website: Optional[str] = None
    industry: Optional[str] = None
    company_address: Optional[str] = None
    phone: Optional[str] = None
    contact_email: Optional[str] = None
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


class TenantCreate(BaseModel):
    name: str
    plan: str = "starter"
    domain: Optional[str] = None  # registered domain — unique link key across systems
    website: Optional[str] = None
    industry: Optional[str] = None
    company_address: Optional[str] = None
    phone: Optional[str] = None
    contact_email: Optional[str] = None
    max_users: int = 3
    max_mailboxes: int = 0
    max_contacts: int = 0
    max_campaigns: int = 0
    max_leads: int = 0


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    plan: Optional[str] = None
    domain: Optional[str] = None  # registered domain — unique link key across systems
    is_active: Optional[bool] = None
    max_users: Optional[int] = None
    max_mailboxes: Optional[int] = None
    max_contacts: Optional[int] = None
    max_campaigns: Optional[int] = None
    max_leads: Optional[int] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    company_address: Optional[str] = None
    phone: Optional[str] = None
    contact_email: Optional[str] = None


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
            domain=t.domain,
            plan=t.plan.value if hasattr(t.plan, 'value') else str(t.plan),
            is_active=t.is_active,
            website=t.website,
            industry=t.industry,
            company_address=t.company_address,
            phone=t.phone,
            contact_email=t.contact_email,
            user_count=db.query(User).filter(User.tenant_id == t.tenant_id).count(),
            lead_count=db.query(LeadDetails).filter(LeadDetails.tenant_id == t.tenant_id).count(),
            contact_count=db.query(ContactDetails).filter(ContactDetails.tenant_id == t.tenant_id).count(),
            mailbox_count=db.query(SenderMailbox).filter(SenderMailbox.tenant_id == t.tenant_id).count(),
            campaign_count=db.query(Campaign).filter(Campaign.tenant_id == t.tenant_id).count(),
            created_at=t.created_at.isoformat() if hasattr(t, 'created_at') and t.created_at else None,
        ))

    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    data: TenantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Create a new tenant. Super admin only."""
    if not data.name or not data.name.strip():
        raise HTTPException(status_code=400, detail="Tenant name is required")

    try:
        plan = TenantPlan(data.plan)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {data.plan}")

    slug = generate_unique_slug(data.name, db)

    domain = _normalize_domain(data.domain)
    if domain and _domain_taken(db, domain):
        raise HTTPException(status_code=409, detail="That registered domain is already linked to another tenant.")

    tenant = Tenant(
        name=data.name.strip(),
        slug=slug,
        plan=plan,
        domain=domain,
        website=data.website or None,
        industry=data.industry or None,
        company_address=data.company_address or None,
        phone=data.phone or None,
        contact_email=data.contact_email or None,
        max_users=data.max_users,
        max_mailboxes=data.max_mailboxes,
        max_contacts=data.max_contacts,
        max_campaigns=data.max_campaigns,
        max_leads=data.max_leads,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    write_audit_log(
        db, tenant_id=tenant.tenant_id, entity_type="tenant",
        entity_id=tenant.tenant_id, action="tenant_created",
        changed_by=current_user.email,
        notes=f"name={tenant.name}, plan={plan.value}",
    )
    db.commit()

    return {
        "message": f"Tenant '{tenant.name}' created",
        "tenant_id": tenant.tenant_id,
        "slug": tenant.slug,
        "plan": plan.value,
    }


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
        company_address=tenant.company_address,
        phone=tenant.phone,
        contact_email=tenant.contact_email,
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
    if data.domain is not None:
        norm = _normalize_domain(data.domain)
        if norm and _domain_taken(db, norm, exclude_tenant_id=tenant.tenant_id):
            raise HTTPException(status_code=409, detail="That registered domain is already linked to another tenant.")
        tenant.domain = norm
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
    if data.phone is not None:
        tenant.phone = data.phone
    if data.contact_email is not None:
        tenant.contact_email = data.contact_email

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
    feature_outreach_enabled: Optional[bool] = None
    feature_export_mailmerge_enabled: Optional[bool] = None


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
        "feature_outreach_enabled": get_tenant_setting_bool(
            db, "feature_outreach_enabled", tenant_id=tenant_id, default=True
        ),
        "feature_export_mailmerge_enabled": get_tenant_setting_bool(
            db, "feature_export_mailmerge_enabled", tenant_id=tenant_id, default=True
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

    if data.feature_outreach_enabled is not None:
        old_val = get_tenant_setting_bool(
            db, "feature_outreach_enabled", tenant_id=tenant_id, default=True
        )
        set_tenant_setting(
            db, "feature_outreach_enabled",
            data.feature_outreach_enabled,
            tenant_id=tenant_id,
            updated_by=current_user.email,
        )
        changes["feature_outreach_enabled"] = {
            "old": old_val, "new": data.feature_outreach_enabled,
        }

    if data.feature_export_mailmerge_enabled is not None:
        old_val = get_tenant_setting_bool(
            db, "feature_export_mailmerge_enabled", tenant_id=tenant_id, default=True
        )
        set_tenant_setting(
            db, "feature_export_mailmerge_enabled",
            data.feature_export_mailmerge_enabled,
            tenant_id=tenant_id,
            updated_by=current_user.email,
        )
        changes["feature_export_mailmerge_enabled"] = {
            "old": old_val, "new": data.feature_export_mailmerge_enabled,
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
        "feature_outreach_enabled": get_tenant_setting_bool(
            db, "feature_outreach_enabled", tenant_id=tenant_id, default=True
        ),
        "feature_export_mailmerge_enabled": get_tenant_setting_bool(
            db, "feature_export_mailmerge_enabled", tenant_id=tenant_id, default=True
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


# ─── LOB Assignments ─────────────────────────────────────────────

class LOBAssignmentUpdate(BaseModel):
    lob_types: List[str]


@router.get("/{tenant_id}/lob-assignments")
async def get_lob_assignments(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Get LOB type assignments for a tenant. Super admin only."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    assignments = (
        db.query(TenantLOBAssignment)
        .filter(
            TenantLOBAssignment.tenant_id == tenant_id,
            TenantLOBAssignment.is_archived == False,
        )
        .all()
    )

    valid_lob_types = [lt.value for lt in LOBType if lt != LOBType.CUSTOM]

    return {
        "tenant_id": tenant_id,
        "assigned_lob_types": [a.lob_type for a in assignments],
        "available_lob_types": valid_lob_types,
    }


def _slugify_lob(text: str) -> str:
    """Convert text to URL-friendly slug for LOB names."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


@router.put("/{tenant_id}/lob-assignments")
async def update_lob_assignments(
    tenant_id: int,
    data: LOBAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Update LOB type assignments for a tenant. Super admin only.

    Accepts the desired set of lob_types. Auto-provisions or archives
    LOB instances when assignments change.
    """
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    valid_lob_values = {lt.value for lt in LOBType if lt != LOBType.CUSTOM}
    invalid = set(data.lob_types) - valid_lob_values
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid LOB types: {', '.join(sorted(invalid))}",
        )

    if not data.lob_types:
        raise HTTPException(status_code=400, detail="At least one LOB type is required")

    desired = set(data.lob_types)

    # Current assignments
    current_assignments = (
        db.query(TenantLOBAssignment)
        .filter(
            TenantLOBAssignment.tenant_id == tenant_id,
            TenantLOBAssignment.is_archived == False,
        )
        .all()
    )
    current_types = {a.lob_type for a in current_assignments}

    to_add = desired - current_types
    to_remove = current_types - desired

    added = []
    removed = []

    # Add new assignments + auto-provision LOB instances
    for lob_type_str in to_add:
        # Check if an archived assignment exists -> unarchive
        archived_assignment = (
            db.query(TenantLOBAssignment)
            .filter(
                TenantLOBAssignment.tenant_id == tenant_id,
                TenantLOBAssignment.lob_type == lob_type_str,
                TenantLOBAssignment.is_archived == True,
            )
            .first()
        )
        if archived_assignment:
            archived_assignment.is_archived = False
            archived_assignment.assigned_by = current_user.email
        else:
            db.add(TenantLOBAssignment(
                tenant_id=tenant_id,
                lob_type=lob_type_str,
                assigned_by=current_user.email,
            ))

        # Auto-provision LOB instance: check for archived first -> unarchive, else create
        lob_type_enum = LOBType(lob_type_str)
        existing_lob = (
            db.query(LineOfBusiness)
            .filter(
                LineOfBusiness.tenant_id == tenant_id,
                LineOfBusiness.lob_type == lob_type_enum,
            )
            .first()
        )
        if existing_lob:
            if existing_lob.is_archived:
                existing_lob.is_archived = False
                existing_lob.status = LOBStatus.ACTIVE
        else:
            # Create new LOB instance with defaults
            meta = LOB_TYPE_META.get(lob_type_str, {})
            defaults = LOB_DEFAULT_CONFIGS.get(lob_type_str, {})
            tenant_profiles = TENANT_PROMPT_PROFILES.get(tenant.slug, {})
            prompt_profile = None
            if lob_type_str in tenant_profiles:
                prompt_profile = _json_admin.dumps(tenant_profiles[lob_type_str])

            lob = LineOfBusiness(
                tenant_id=tenant_id,
                name=meta.get("label", lob_type_str.replace("_", " ").title()),
                slug=_slugify_lob(meta.get("label", lob_type_str)),
                lob_type=lob_type_enum,
                description=meta.get("description", ""),
                is_default=False,
                color=meta.get("default_color", "#8B5CF6"),
                icon=meta.get("default_icon", "settings"),
                lead_source_config=_json_admin.dumps(defaults.get("lead_source_config")) if defaults.get("lead_source_config") else None,
                icp_config=_json_admin.dumps(defaults.get("icp_config")) if defaults.get("icp_config") else None,
                business_rules=_json_admin.dumps(defaults.get("business_rules")) if defaults.get("business_rules") else None,
                prompt_profile=prompt_profile,
            )
            db.add(lob)

        added.append(lob_type_str)

    # Remove assignments + archive LOB instances
    for lob_type_str in to_remove:
        assignment = next(
            (a for a in current_assignments if a.lob_type == lob_type_str), None
        )
        if assignment:
            assignment.is_archived = True

        # Archive the LOB instance (soft-delete preserves FK refs)
        lob_type_enum = LOBType(lob_type_str)
        lob = (
            db.query(LineOfBusiness)
            .filter(
                LineOfBusiness.tenant_id == tenant_id,
                LineOfBusiness.lob_type == lob_type_enum,
                LineOfBusiness.is_archived == False,
            )
            .first()
        )
        if lob:
            lob.is_archived = True
            lob.status = LOBStatus.PAUSED

        removed.append(lob_type_str)

    # Ensure at least one LOB remains as is_default
    remaining_lobs = (
        db.query(LineOfBusiness)
        .filter(
            LineOfBusiness.tenant_id == tenant_id,
            LineOfBusiness.is_archived == False,
        )
        .all()
    )
    if remaining_lobs and not any(l.is_default for l in remaining_lobs):
        remaining_lobs[0].is_default = True

    # Audit log
    if added or removed:
        write_audit_log(
            db,
            tenant_id=tenant_id,
            entity_type="tenant",
            entity_id=tenant_id,
            action="lob_assignments_update",
            changed_by=current_user.email,
            notes=f"added={added}, removed={removed}",
        )

    db.commit()

    # Re-query final state
    final_assignments = (
        db.query(TenantLOBAssignment)
        .filter(
            TenantLOBAssignment.tenant_id == tenant_id,
            TenantLOBAssignment.is_archived == False,
        )
        .all()
    )

    return {
        "message": "LOB assignments updated",
        "tenant_id": tenant_id,
        "assigned_lob_types": [a.lob_type for a in final_assignments],
        "added": added,
        "removed": removed,
    }
