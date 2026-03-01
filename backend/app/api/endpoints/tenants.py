"""Tenant management endpoints — Global Super Admin only."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_active_user, require_role
from app.core.constants import MASTER_TENANT_ID
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.db.models.sender_mailbox import SenderMailbox
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, TenantStatsResponse
from app.core.security import create_access_token
from app.core.config import settings

router = APIRouter(prefix="/tenants", tags=["Tenants"])


def _require_global_super_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require Global Super Admin (super_admin role + master tenant)."""
    if current_user.role != UserRole.SUPER_ADMIN or current_user.tenant_id != MASTER_TENANT_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Global Super Admin access required"
        )
    return current_user


@router.get("", response_model=list[TenantStatsResponse])
async def list_tenants(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_global_super_admin),
):
    """List all tenants with stats. Super Admin only."""
    query = db.query(Tenant)
    if is_active is not None:
        query = query.filter(Tenant.is_active == is_active)
    query = query.filter(Tenant.is_archived == False)
    tenants = query.order_by(Tenant.tenant_id).offset(skip).limit(limit).all()

    results = []
    for t in tenants:
        user_count = db.query(func.count(User.user_id)).filter(User.tenant_id == t.tenant_id).scalar() or 0
        lead_count = db.query(func.count(LeadDetails.lead_id)).filter(
            LeadDetails.tenant_id == t.tenant_id, LeadDetails.is_archived == False
        ).scalar() or 0
        mailbox_count = db.query(func.count(SenderMailbox.mailbox_id)).filter(
            SenderMailbox.tenant_id == t.tenant_id, SenderMailbox.is_archived == False
        ).scalar() or 0
        contact_count = db.query(func.count(ContactDetails.contact_id)).filter(
            ContactDetails.tenant_id == t.tenant_id, ContactDetails.is_archived == False
        ).scalar() or 0

        results.append(TenantStatsResponse(
            tenant_id=t.tenant_id,
            name=t.name,
            slug=t.slug,
            is_active=t.is_active,
            max_users=t.max_users,
            max_mailboxes=t.max_mailboxes,
            plan=t.plan,
            created_at=t.created_at,
            updated_at=t.updated_at,
            is_archived=t.is_archived,
            user_count=user_count,
            lead_count=lead_count,
            mailbox_count=mailbox_count,
            contact_count=contact_count,
        ))
    return results


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant(
    tenant_in: TenantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_global_super_admin),
):
    """Create a new tenant. Super Admin only."""
    # Check unique name
    existing = db.query(Tenant).filter(Tenant.name == tenant_in.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tenant name already exists")
    # Check unique slug
    existing_slug = db.query(Tenant).filter(Tenant.slug == tenant_in.slug).first()
    if existing_slug:
        raise HTTPException(status_code=400, detail="Tenant slug already exists")

    tenant = Tenant(**tenant_in.model_dump())
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return TenantResponse.model_validate(tenant)


@router.get("/{tenant_id}", response_model=TenantStatsResponse)
async def get_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get tenant details. Super Admin or own tenant admin."""
    if current_user.role != UserRole.SUPER_ADMIN and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    user_count = db.query(func.count(User.user_id)).filter(User.tenant_id == tenant_id).scalar() or 0
    lead_count = db.query(func.count(LeadDetails.lead_id)).filter(
        LeadDetails.tenant_id == tenant_id, LeadDetails.is_archived == False
    ).scalar() or 0
    mailbox_count = db.query(func.count(SenderMailbox.mailbox_id)).filter(
        SenderMailbox.tenant_id == tenant_id, SenderMailbox.is_archived == False
    ).scalar() or 0
    contact_count = db.query(func.count(ContactDetails.contact_id)).filter(
        ContactDetails.tenant_id == tenant_id, ContactDetails.is_archived == False
    ).scalar() or 0

    return TenantStatsResponse(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        slug=tenant.slug,
        is_active=tenant.is_active,
        max_users=tenant.max_users,
        max_mailboxes=tenant.max_mailboxes,
        plan=tenant.plan,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        is_archived=tenant.is_archived,
        user_count=user_count,
        lead_count=lead_count,
        mailbox_count=mailbox_count,
        contact_count=contact_count,
    )


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: int,
    tenant_in: TenantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_global_super_admin),
):
    """Update a tenant. Super Admin only."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = tenant_in.model_dump(exclude_unset=True)
    # Check unique constraints if changing name/slug
    if "name" in update_data and update_data["name"] != tenant.name:
        existing = db.query(Tenant).filter(Tenant.name == update_data["name"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="Tenant name already exists")
    if "slug" in update_data and update_data["slug"] != tenant.slug:
        existing = db.query(Tenant).filter(Tenant.slug == update_data["slug"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="Tenant slug already exists")

    for key, value in update_data.items():
        setattr(tenant, key, value)

    db.commit()
    db.refresh(tenant)
    return TenantResponse.model_validate(tenant)


@router.delete("/{tenant_id}")
async def delete_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_global_super_admin),
):
    """Soft-delete (archive) a tenant. Super Admin only."""
    if tenant_id == 1:
        raise HTTPException(status_code=400, detail="Cannot delete the primary tenant")

    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.is_archived = True
    tenant.is_active = False
    db.commit()
    return {"message": f"Tenant '{tenant.name}' archived", "tenant_id": tenant_id}


@router.post("/{tenant_id}/switch")
async def switch_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_global_super_admin),
):
    """Switch active tenant context (returns new JWT). Super Admin only."""
    tenant = db.query(Tenant).filter(
        Tenant.tenant_id == tenant_id, Tenant.is_active == True
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Active tenant not found")

    from datetime import timedelta
    access_token = create_access_token(
        data={
            "sub": current_user.email,
            "tenant_id": tenant_id,
            "role": current_user.role.value,
        },
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
    }
