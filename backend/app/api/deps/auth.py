"""Authentication dependencies for FastAPI."""
from typing import Optional, List
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.api.deps.database import get_db
from app.core.security import decode_access_token
from app.core.constants import MASTER_TENANT_ID
from app.core.tenant_context import (
    set_current_tenant_id, set_is_super_admin, set_is_global_super_admin,
)
from app.db.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """Get the current authenticated user and set tenant context."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    email: str = payload.get("sub")
    if email is None:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception

    # Set tenant context for this request
    is_sa = user.role == UserRole.SUPER_ADMIN
    is_gsa = is_sa and user.tenant_id == MASTER_TENANT_ID
    set_is_super_admin(is_sa)
    set_is_global_super_admin(is_gsa)

    if is_gsa:
        # Global Super Admin: X-Tenant-Id header for tenant switching
        header_tenant = request.headers.get("X-Tenant-Id")
        if header_tenant:
            try:
                set_current_tenant_id(int(header_tenant))
            except (ValueError, TypeError):
                set_current_tenant_id(None)
        else:
            set_current_tenant_id(None)  # No filter — sees all tenants
    else:
        # Tenant Super Admin + all other roles: scoped to own tenant
        set_current_tenant_id(user.tenant_id)

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get the current active user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


def require_role(allowed_roles: List[UserRole]):
    """Dependency factory to require specific roles."""
    async def role_checker(
        current_user: User = Depends(get_current_active_user)
    ) -> User:
        # SUPER_ADMIN always passes role checks
        if current_user.role == UserRole.SUPER_ADMIN:
            return current_user
        # Legacy ADMIN is treated as TENANT_ADMIN
        effective_role = current_user.role
        if effective_role == UserRole.ADMIN:
            effective_role = UserRole.TENANT_ADMIN
        # Check both the user's role and TENANT_ADMIN mapping
        allowed_effective = set(allowed_roles)
        if UserRole.ADMIN in allowed_effective:
            allowed_effective.add(UserRole.TENANT_ADMIN)
        if UserRole.TENANT_ADMIN in allowed_effective:
            allowed_effective.add(UserRole.ADMIN)
        if effective_role not in allowed_effective and current_user.role not in allowed_effective:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in allowed_roles]}"
            )
        return current_user
    return role_checker
