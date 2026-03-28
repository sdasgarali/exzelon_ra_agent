"""Authentication dependencies for FastAPI."""
import json
import hashlib
from datetime import datetime
from typing import List, Optional
from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.api.deps.database import get_db
from app.core.security import decode_access_token
from app.db.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> User:
    """Get the current authenticated user via JWT token or API key."""
    # Try API key first
    if x_api_key:
        from app.db.models.api_key import ApiKey
        key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
        api_key = db.query(ApiKey).filter(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True,
        ).first()
        if api_key:
            # Check expiry
            if api_key.expires_at and api_key.expires_at < datetime.utcnow():
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired")
            # Update last used
            api_key.last_used_at = datetime.utcnow()
            db.commit()
            # Return the user who owns this key
            user = db.query(User).filter(User.user_id == api_key.user_id).first()
            if user:
                return user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    # Fall back to JWT
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
    """Dependency factory to require specific roles.

    Super admins bypass all role checks automatically.
    """
    async def role_checker(
        current_user: User = Depends(get_current_active_user)
    ) -> User:
        # Super admin bypasses all role checks
        if current_user.role == UserRole.SUPER_ADMIN:
            return current_user
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in allowed_roles]}"
            )
        return current_user
    return role_checker


def get_user_settings_tab_access(db: Session, user: User, tab_key: str) -> str:
    """Returns the user's access level for a specific settings tab.

    Returns one of: 'full', 'read_write', 'read', 'no_access'.
    Super admins always get 'full'.
    """
    if user.role == UserRole.SUPER_ADMIN:
        return 'full'

    from app.db.models.settings import Settings
    role_perms_setting = db.query(Settings).filter(Settings.key == 'role_permissions').first()
    if not role_perms_setting or not role_perms_setting.value_json:
        return 'no_access'

    try:
        role_perms = json.loads(role_perms_setting.value_json)
    except (json.JSONDecodeError, TypeError):
        return 'no_access'

    role_name = user.role.value  # e.g. 'admin', 'operator', 'viewer'
    role_config = role_perms.get(role_name, {})
    settings_perm = role_config.get('settings')

    if settings_perm is None:
        return 'no_access'

    # Flat string: all tabs have the same permission
    if isinstance(settings_perm, str):
        return settings_perm

    # Nested object: per-tab permissions
    if isinstance(settings_perm, dict):
        return settings_perm.get(tab_key, 'no_access')

    return 'no_access'


def get_all_settings_tab_permissions(db: Session, user: User) -> dict:
    """Returns all settings tab permissions for the user.

    Returns a dict like {'job_sources': 'full', 'ai_llm': 'read', ...}
    """
    tabs = ['job_sources', 'ai_llm', 'contacts', 'validation', 'outreach', 'business_rules', 'automation']

    if user.role == UserRole.SUPER_ADMIN:
        return {tab: 'full' for tab in tabs}

    from app.db.models.settings import Settings
    role_perms_setting = db.query(Settings).filter(Settings.key == 'role_permissions').first()
    if not role_perms_setting or not role_perms_setting.value_json:
        return {tab: 'no_access' for tab in tabs}

    try:
        role_perms = json.loads(role_perms_setting.value_json)
    except (json.JSONDecodeError, TypeError):
        return {tab: 'no_access' for tab in tabs}

    role_name = user.role.value
    role_config = role_perms.get(role_name, {})
    settings_perm = role_config.get('settings')

    if settings_perm is None:
        return {tab: 'no_access' for tab in tabs}

    if isinstance(settings_perm, str):
        return {tab: settings_perm for tab in tabs}

    if isinstance(settings_perm, dict):
        return {tab: settings_perm.get(tab, 'no_access') for tab in tabs}

    return {tab: 'no_access' for tab in tabs}


def _extract_tenant_id(user: User, x_tenant_id: Optional[int] = None) -> Optional[int]:
    """Extract tenant_id from user context.

    - Super admin: returns None (all-tenant access) unless X-Tenant-ID header is set.
    - Regular user: always returns their own tenant_id (ignores header).

    Args:
        user: The authenticated User.
        x_tenant_id: Optional tenant ID from X-Tenant-ID header (super admin only).

    Returns:
        The tenant_id to scope queries to, or None for super admin global access.
    """
    if user.role == UserRole.SUPER_ADMIN:
        return x_tenant_id  # None = global, or specific tenant for impersonation
    return user.tenant_id


async def get_current_tenant_id(
    current_user: User = Depends(get_current_active_user),
    x_tenant_id: Optional[int] = Header(None, alias="X-Tenant-ID"),
) -> Optional[int]:
    """Dependency: get the tenant_id for scoping queries.

    - Super admin without X-Tenant-ID: returns None (sees all tenants).
    - Super admin with X-Tenant-ID: returns that tenant_id (impersonation).
    - Regular user: returns their tenant_id (always).
    - User without tenant: raises 403.
    """
    tid = _extract_tenant_id(current_user, x_tenant_id)
    if tid is None and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant assigned to this user",
        )
    return tid
