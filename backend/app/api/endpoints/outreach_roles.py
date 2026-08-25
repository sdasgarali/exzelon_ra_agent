"""Outreach role management endpoints."""
import structlog
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db, require_role, get_current_tenant_id, ensure_tenant
from app.db.models.user import User, UserRole
from app.db.models.outreach_role import OutreachRole
from app.db.models.sender_mailbox import SenderMailbox
from app.db.query_helpers import tenant_filter

logger = structlog.get_logger()

router = APIRouter(prefix="/outreach-roles", tags=["Outreach Roles"])


# ── Schemas ──────────────────────────────────────────────────

class OutreachRoleCreate(BaseModel):
    role_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    purpose: Optional[str] = None
    auto_outbound: bool = False


class OutreachRoleUpdate(BaseModel):
    role_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    purpose: Optional[str] = None
    auto_outbound: Optional[bool] = None


class OutreachRoleResponse(BaseModel):
    role_id: int
    role_name: str
    description: Optional[str] = None
    purpose: Optional[str] = None
    is_system: bool = False
    # True → this role's mailboxes are auto-selected for cold outbound (machine sender,
    # no login user). False → personal/manual mailboxes tied to a login user.
    auto_outbound: bool = False
    mailbox_count: int = 0

    class Config:
        from_attributes = True


# ── Routes ───────────────────────────────────────────────────

@router.get("")
async def list_outreach_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM, UserRole.RECRUITER])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List outreach roles with mailbox counts."""
    query = tenant_filter(
        db.query(OutreachRole).filter(OutreachRole.is_archived == False),
        OutreachRole, tenant_id,
    )
    roles = query.order_by(OutreachRole.role_name).all()

    # Batch-load mailbox counts per role
    count_query = (
        db.query(SenderMailbox.outreach_role_id, func.count(SenderMailbox.mailbox_id))
        .filter(SenderMailbox.is_archived == False)
    )
    count_query = tenant_filter(count_query, SenderMailbox, tenant_id)
    count_rows = count_query.group_by(SenderMailbox.outreach_role_id).all()
    count_map = {role_id: cnt for role_id, cnt in count_rows if role_id is not None}

    return [
        OutreachRoleResponse(
            role_id=r.role_id,
            role_name=r.role_name,
            description=r.description,
            purpose=r.purpose,
            is_system=r.is_system,
            auto_outbound=r.auto_outbound,
            mailbox_count=count_map.get(r.role_id, 0),
        )
        for r in roles
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_outreach_role(
    body: OutreachRoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a new outreach role (Super Admin only)."""
    tid = ensure_tenant(tenant_id)
    existing = (
        db.query(OutreachRole)
        .filter(
            OutreachRole.tenant_id == tid,
            OutreachRole.role_name == body.role_name,
            OutreachRole.is_archived == False,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{body.role_name}' already exists",
        )

    role = OutreachRole(
        tenant_id=tid,
        role_name=body.role_name,
        description=body.description,
        purpose=body.purpose,
        is_system=False,
        auto_outbound=body.auto_outbound,
    )
    db.add(role)
    db.commit()
    db.refresh(role)

    return OutreachRoleResponse(
        role_id=role.role_id,
        role_name=role.role_name,
        description=role.description,
        purpose=role.purpose,
        is_system=role.is_system,
        auto_outbound=role.auto_outbound,
        mailbox_count=0,
    )


@router.put("/{role_id}")
async def update_outreach_role(
    role_id: int,
    body: OutreachRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update an outreach role (Super Admin only)."""
    query = db.query(OutreachRole).filter(OutreachRole.role_id == role_id)
    if tenant_id is not None:
        query = query.filter(OutreachRole.tenant_id == tenant_id)
    role = query.first()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if body.role_name is not None:
        # Check uniqueness within tenant
        dup = (
            db.query(OutreachRole)
            .filter(
                OutreachRole.tenant_id == role.tenant_id,
                OutreachRole.role_name == body.role_name,
                OutreachRole.role_id != role_id,
                OutreachRole.is_archived == False,
            )
            .first()
        )
        if dup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role '{body.role_name}' already exists",
            )
        role.role_name = body.role_name

    if body.description is not None:
        role.description = body.description

    if body.purpose is not None:
        role.purpose = body.purpose

    if body.auto_outbound is not None:
        role.auto_outbound = body.auto_outbound

    db.commit()
    db.refresh(role)

    # Get mailbox count
    count = (
        db.query(func.count(SenderMailbox.mailbox_id))
        .filter(SenderMailbox.outreach_role_id == role_id, SenderMailbox.is_archived == False)
        .scalar()
    )

    return OutreachRoleResponse(
        role_id=role.role_id,
        role_name=role.role_name,
        description=role.description,
        purpose=role.purpose,
        is_system=role.is_system,
        auto_outbound=role.auto_outbound,
        mailbox_count=count or 0,
    )


@router.delete("/{role_id}")
async def delete_outreach_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Soft-delete an outreach role (Super Admin only). Blocked for system roles."""
    query = db.query(OutreachRole).filter(OutreachRole.role_id == role_id)
    if tenant_id is not None:
        query = query.filter(OutreachRole.tenant_id == tenant_id)
    role = query.first()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System roles cannot be deleted",
        )

    # Nullify FK on mailboxes using this role
    mailboxes = (
        db.query(SenderMailbox)
        .filter(SenderMailbox.outreach_role_id == role_id)
        .all()
    )
    for mb in mailboxes:
        mb.outreach_role_id = None

    role.is_archived = True
    db.commit()

    return {"message": f"Role '{role.role_name}' deleted"}
