"""User management endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_active_user, require_role
from app.core.security import get_password_hash
from app.core.tenant_context import get_is_global_super_admin
from app.db.models.user import User, UserRole
from app.db.query_helpers import tenant_query
from app.schemas.user import UserCreate, UserUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    tenant_id: Optional[int] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """List users. Super Admin sees all; Tenant Admin sees own tenant."""
    if get_is_global_super_admin():
        query = db.query(User)
        if tenant_id is not None:
            query = query.filter(User.tenant_id == tenant_id)
    else:
        query = db.query(User).filter(User.tenant_id == current_user.tenant_id)

    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) | (User.full_name.ilike(f"%{search}%"))
        )

    total = query.count()
    users = query.order_by(User.user_id).offset(skip).limit(limit).all()
    return [UserResponse.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Get user by ID. Super Admin sees any; Tenant Admin sees own tenant."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not get_is_global_super_admin() and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Create a new user. Super Admin can assign any tenant; Tenant Admin assigns own."""
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Determine tenant_id for new user
    if get_is_global_super_admin():
        assigned_tenant_id = user_in.tenant_id  # Super Admin can set any tenant
    else:
        assigned_tenant_id = current_user.tenant_id  # Tenant Admin forces own tenant

    # Tenant Admin cannot create Super Admin users
    if not get_is_global_super_admin() and user_in.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create Super Admin users")

    user = User(
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role,
        is_active=user_in.is_active,
        tenant_id=assigned_tenant_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Update user. Super Admin can update any; Tenant Admin updates own tenant."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not get_is_global_super_admin() and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = user_in.model_dump(exclude_unset=True)

    # Tenant Admin cannot escalate to Super Admin
    if not get_is_global_super_admin() and update_data.get("role") == UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign Super Admin role")

    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))

    # Tenant Admin cannot change tenant_id
    if not get_is_global_super_admin():
        update_data.pop("tenant_id", None)

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Delete user. Super Admin can delete any; Tenant Admin deletes own tenant."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not get_is_global_super_admin() and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.user_id == current_user.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")

    # Cannot delete a Super Admin
    if user.role == UserRole.SUPER_ADMIN and not get_is_global_super_admin():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete Super Admin users")

    db.delete(user)
    db.commit()
