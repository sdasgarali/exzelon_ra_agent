"""Role management endpoints (super-admin only).

Lists built-in + custom (settings-backed, per-tenant) roles and lets a super admin
create/edit/delete CUSTOM roles. Built-in roles (super_admin/admin/bdm/recruiter)
are protected: their key + base_role are immutable and they cannot be deleted, though
their display label/description may be overridden per tenant.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role, get_current_tenant_id, require_tenant_id
from app.db.models.user import User, UserRole
from app.services import role_registry as reg
from app.services.audit_helper import write_audit_log

router = APIRouter(prefix="/roles", tags=["Roles"])


class RoleCreate(BaseModel):
    key: str = Field(..., description="Lowercase slug, e.g. 'bdm_lead'")
    label: str
    description: str = ""
    base_role: str = Field("recruiter", description="One of: admin, bdm, recruiter")


class RoleUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    base_role: Optional[str] = None


def _role_out(db: Session, tenant_id: Optional[int], r: dict) -> dict:
    """Attach a live in-use user count to a role dict."""
    return {**r, "user_count": reg.users_with_role(db, tenant_id, r["key"])}


@router.get("")
async def list_roles(
    db: Session = Depends(get_db),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """List built-in + custom roles for the current tenant context."""
    return {"roles": [_role_out(db, tenant_id, r) for r in reg.list_roles(db, tenant_id)]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """Create a custom role (requires an impersonated tenant)."""
    try:
        role = reg.create_role(
            db, tenant_id, key=body.key, label=body.label,
            description=body.description, base_role=body.base_role,
            updated_by=current_user.email,
        )
    except reg.RoleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    write_audit_log(db, tenant_id=tenant_id, entity_type="role", entity_id=0,
                    action="role_created", changed_by=current_user.email,
                    notes=f"key={role['key']}, base_role={role['base_role']}")
    db.commit()
    return _role_out(db, tenant_id, role)


@router.put("/{key}")
async def update_role(
    key: str,
    body: RoleUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """Update a role's label/description (and base_role for custom roles)."""
    if reg.get_role(db, tenant_id, key) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Role '{key}' not found")
    try:
        role = reg.update_role(
            db, tenant_id, key, label=body.label, description=body.description,
            base_role=body.base_role, updated_by=current_user.email,
        )
    except reg.RoleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    write_audit_log(db, tenant_id=tenant_id, entity_type="role", entity_id=0,
                    action="role_updated", changed_by=current_user.email, notes=f"key={key}")
    db.commit()
    return _role_out(db, tenant_id, role)


@router.delete("/{key}")
async def delete_role(
    key: str,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """Delete a custom role (blocked if it is built-in or assigned to any user)."""
    try:
        reg.delete_role(db, tenant_id, key, updated_by=current_user.email)
    except reg.RoleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    write_audit_log(db, tenant_id=tenant_id, entity_type="role", entity_id=0,
                    action="role_deleted", changed_by=current_user.email, notes=f"key={key}")
    db.commit()
    return {"success": True, "deleted": key}
