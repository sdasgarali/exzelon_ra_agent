"""User management endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role, get_current_tenant_id
from app.core.security import get_password_hash
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.audit_helper import write_audit_log

router = APIRouter(prefix="/users", tags=["Users"])


def _is_super_admin(user: User) -> bool:
    return user.role == UserRole.SUPER_ADMIN


def _validate_tenant(db: Session, tenant_id: int) -> None:
    """Raise 400 if the tenant does not exist."""
    if not db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant not found")


def _caller_tenant_id(current_user: User) -> int:
    """Tenant a non-super-admin caller is scoped to. Raises 400 if unset.

    Guards against the NULL==NULL edge case: a non-super-admin with tenant_id=NULL
    must never resolve to 'all global users'.
    """
    if current_user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account is not assigned to a tenant.",
        )
    return current_user.tenant_id


def _can_access_user(current_user: User, target: User) -> bool:
    """Whether the caller may view/modify the target user (tenant isolation)."""
    if _is_super_admin(current_user):
        return True
    return current_user.tenant_id is not None and target.tenant_id == current_user.tenant_id


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    tenant_id: Optional[int] = Query(None, description="Super-admin only: filter by tenant"),
    impersonated_tenant_id: Optional[int] = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """List users. Admin+ only. Regular admins see only their own tenant's users;
    super admins see all tenants, scoped to the selected/impersonated tenant when one
    is active (X-Tenant-ID header) and overridable by an explicit `tenant_id` filter."""
    query = db.query(User)

    # Tenant isolation: non-super-admins are restricted to their own tenant.
    if not _is_super_admin(current_user):
        query = query.filter(User.tenant_id == _caller_tenant_id(current_user))
    else:
        # Super admin: explicit ?tenant_id filter wins; otherwise honor the selected
        # (impersonated) tenant from X-Tenant-ID so "select a tenant" scopes the list.
        effective_tenant_id = tenant_id if tenant_id is not None else impersonated_tenant_id
        if effective_tenant_id is not None:
            query = query.filter(User.tenant_id == effective_tenant_id)

    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) | (User.full_name.ilike(f"%{search}%"))
        )

    users = query.order_by(User.user_id).offset(skip).limit(limit).all()
    return [UserResponse.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Get user by ID. Admin+ only (own tenant unless super admin)."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user or not _can_access_user(current_user, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Create a new user. Admin+ only.

    Only super_admin can assign the super_admin role.
    """
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Only super_admin can create super_admin users
    if user_in.role == UserRole.SUPER_ADMIN and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can assign the super_admin role"
        )

    # Resolve tenant assignment (every user is bound to exactly one tenant, except
    # super_admins which are global / cross-tenant).
    if user_in.role == UserRole.SUPER_ADMIN:
        target_tenant_id = None
    elif _is_super_admin(current_user):
        # Super admin explicitly chooses the tenant for the new user.
        if user_in.tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select a tenant for this user.",
            )
        _validate_tenant(db, user_in.tenant_id)
        target_tenant_id = user_in.tenant_id
    else:
        # Regular admins can only create users inside their own tenant.
        target_tenant_id = current_user.tenant_id
        if target_tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your account is not assigned to a tenant.",
            )

    user = User(
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role,
        is_active=user_in.is_active,
        tenant_id=target_tenant_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    write_audit_log(db, tenant_id=current_user.tenant_id or 0, entity_type="user",
                    entity_id=user.user_id, action="user_created",
                    changed_by=current_user.email,
                    notes=f"email={user.email}, role={user.role.value if hasattr(user.role, 'value') else user.role}")
    db.commit()

    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Update user. Admin+ only.

    Only super_admin can modify super_admin users.
    Cannot demote the last super_admin.
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user or not _can_access_user(current_user, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Only super_admin can modify super_admin users
    if user.role == UserRole.SUPER_ADMIN and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can modify super_admin users"
        )

    # Only super_admin can promote to super_admin
    if user_in.role == UserRole.SUPER_ADMIN and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can assign the super_admin role"
        )

    # Prevent demoting the last super_admin
    if (
        user.role == UserRole.SUPER_ADMIN
        and user_in.role is not None
        and user_in.role != UserRole.SUPER_ADMIN
    ):
        super_admin_count = db.query(User).filter(
            User.role == UserRole.SUPER_ADMIN,
            User.is_active == True,
        ).count()
        if super_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last super admin"
            )

    update_data = user_in.model_dump(exclude_unset=True)

    # ── Tenant reassignment rules ──────────────────────────────────────────────
    # Only super_admin may move a user between tenants. super_admin-role users are
    # always global (NULL); a user leaving the super_admin role must get a tenant.
    requested_tenant = update_data.pop("tenant_id", "UNSET")
    effective_role = update_data.get("role", user.role)
    if effective_role == UserRole.SUPER_ADMIN:
        if user.tenant_id is not None:
            update_data["tenant_id"] = None
    elif _is_super_admin(current_user):
        if requested_tenant != "UNSET" and requested_tenant is not None:
            _validate_tenant(db, requested_tenant)
            update_data["tenant_id"] = requested_tenant
        elif requested_tenant is None or user.tenant_id is None:
            # Explicit null, or a user leaving super_admin with no tenant yet:
            # a non-super-admin user must have a tenant.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select a tenant for this user.",
            )
    # Regular admins: any requested tenant change is dropped (cannot reassign).

    # Capture old values for audit
    changed_fields = {}
    for field, new_val in update_data.items():
        if field == "password":
            changed_fields["password"] = {"old": "***", "new": "***"}
            continue
        old_val = getattr(user, field, None)
        if hasattr(old_val, "value"):
            old_val = old_val.value
        new_display = new_val.value if hasattr(new_val, "value") else new_val
        if str(old_val) != str(new_display):
            changed_fields[field] = {"old": str(old_val), "new": str(new_display)}

    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(user, field, value)

    if changed_fields:
        write_audit_log(db, tenant_id=current_user.tenant_id or 0, entity_type="user",
                        entity_id=user.user_id, action="user_updated",
                        changed_by=current_user.email, changed_fields=changed_fields)

    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Delete user. Admin+ only.

    Only super_admin can delete super_admin users.
    Cannot delete the last super_admin.
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user or not _can_access_user(current_user, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.user_id == current_user.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")

    # Only super_admin can delete super_admin users
    if user.role == UserRole.SUPER_ADMIN and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can delete super_admin users"
        )

    # Prevent deleting the last super_admin
    if user.role == UserRole.SUPER_ADMIN:
        super_admin_count = db.query(User).filter(
            User.role == UserRole.SUPER_ADMIN,
            User.is_active == True,
        ).count()
        if super_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the last super admin"
            )

    write_audit_log(db, tenant_id=current_user.tenant_id or 0, entity_type="user",
                    entity_id=user.user_id, action="user_deleted",
                    changed_by=current_user.email,
                    notes=f"email={user.email}")
    db.delete(user)
    db.commit()
