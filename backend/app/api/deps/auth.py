"""Authentication dependencies for FastAPI."""
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


def get_module_tab_access(db: Session, user: User, module_key: str, tab_key: str) -> str:
    """Returns the user's access level for a specific tab within any module.

    Works for settings, warmup, pipelines, or any future independentTabs module.
    Returns one of: 'full', 'read_write', 'read', 'no_access'.
    Super admins always get 'full'.
    """
    if user.role == UserRole.SUPER_ADMIN:
        return 'full'

    from app.core.settings_resolver import get_tenant_setting
    role_perms = get_tenant_setting(db, 'role_permissions', tenant_id=user.tenant_id, default=None)
    if not role_perms or not isinstance(role_perms, dict):
        return 'no_access'

    role_config = role_perms.get(user.role.value, {})
    module_perm = role_config.get(module_key)

    if module_perm is None:
        return 'no_access'

    # Flat string: all tabs inherit the same permission
    if isinstance(module_perm, str):
        return module_perm

    # Nested object: per-tab permissions
    if isinstance(module_perm, dict):
        return module_perm.get(tab_key, 'no_access')

    return 'no_access'


def get_user_settings_tab_access(db: Session, user: User, tab_key: str) -> str:
    """Returns the user's access level for a specific settings tab.

    Thin wrapper around get_module_tab_access for backward compatibility.
    """
    return get_module_tab_access(db, user, 'settings', tab_key)


def get_all_settings_tab_permissions(db: Session, user: User) -> dict:
    """Returns all settings tab permissions for the user.

    Returns a dict like {'job_source_apis': 'full', 'ai_llm': 'read', ...}
    """
    tabs = ['job_filters', 'job_source_apis', 'ai_llm', 'contacts', 'validation', 'outreach', 'business_rules', 'deliverability', 'lob_lead_sources', 'automation', 'source_tuning']

    if user.role == UserRole.SUPER_ADMIN:
        return {tab: 'full' for tab in tabs}

    from app.core.settings_resolver import get_tenant_setting
    role_perms = get_tenant_setting(db, 'role_permissions', tenant_id=user.tenant_id, default=None)
    if not role_perms or not isinstance(role_perms, dict):
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


PERMISSION_LEVELS = ['no_access', 'read', 'read_write', 'full']


def get_module_permission(db: Session, user: User, module_key: str) -> str:
    """Returns the user's effective permission level for any module.

    Resolves through 3 layers (highest priority wins):
      Layer 3: User-specific overrides
      Layer 2: Role-based permissions (from settings)
      Layer 1: Defaults (super_admin=full, viewer=no_access, etc.)

    Returns one of: 'full', 'read_write', 'read', 'no_access'.
    """
    if user.role == UserRole.SUPER_ADMIN:
        return 'full'

    from app.core.settings_resolver import get_tenant_setting

    # Layer 3: User-specific overrides
    user_overrides = get_tenant_setting(db, 'user_permission_overrides', tenant_id=user.tenant_id, default=None)
    if user_overrides and isinstance(user_overrides, dict):
        user_key = f"user_{user.user_id}"
        override = user_overrides.get(user_key, {})
        if isinstance(override, dict) and module_key in override:
            return override[module_key]

    # Layer 2: Role-based permissions
    role_perms = get_tenant_setting(db, 'role_permissions', tenant_id=user.tenant_id, default=None)
    if role_perms and isinstance(role_perms, dict):
        role_config = role_perms.get(user.role.value, {})
        if module_key in role_config:
            perm = role_config[module_key]
            # Could be a string or a dict (for modules with independent tabs)
            if isinstance(perm, str):
                return perm
            if isinstance(perm, dict):
                # Independent tabs: return highest access as aggregate
                levels = [perm.get(k, 'no_access') for k in perm]
                if levels:
                    max_idx = max(
                        PERMISSION_LEVELS.index(l) for l in levels if l in PERMISSION_LEVELS
                    ) if any(l in PERMISSION_LEVELS for l in levels) else 0
                    return PERMISSION_LEVELS[max_idx]

    # Layer 1: Safe defaults
    defaults = {
        'admin': 'full',
        'operator': 'read_write',
        'viewer': 'read',
    }
    return defaults.get(user.role.value, 'no_access')


def require_module_permission(module_key: str, min_level: str):
    """Dependency factory to enforce minimum permission level for a module.

    Usage: current_user = Depends(require_module_permission('warmup', 'read_write'))
    """
    min_idx = PERMISSION_LEVELS.index(min_level)

    async def permission_checker(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role == UserRole.SUPER_ADMIN:
            return current_user
        level = get_module_permission(db, current_user, module_key)
        level_idx = PERMISSION_LEVELS.index(level) if level in PERMISSION_LEVELS else 0
        if level_idx < min_idx:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permission for {module_key}. Required: {min_level}, yours: {level}"
            )
        return current_user
    return permission_checker


def require_module_tab_permission(module_key: str, tab_key: str, min_level: str):
    """Dependency factory to enforce minimum permission level for a specific tab within a module.

    Usage: current_user = Depends(require_module_tab_permission('warmup', 'overview', 'read'))
    """
    min_idx = PERMISSION_LEVELS.index(min_level)

    async def tab_permission_checker(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role == UserRole.SUPER_ADMIN:
            return current_user
        level = get_module_tab_access(db, current_user, module_key, tab_key)
        level_idx = PERMISSION_LEVELS.index(level) if level in PERMISSION_LEVELS else 0
        if level_idx < min_idx:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permission for {module_key}/{tab_key}. Required: {min_level}, yours: {level}"
            )
        return current_user
    return tab_permission_checker


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
