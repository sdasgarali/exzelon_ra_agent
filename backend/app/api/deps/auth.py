"""Authentication dependencies for FastAPI."""
import json
from typing import List
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.api.deps.database import get_db
from app.core.security import decode_access_token
from app.db.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """Get the current authenticated user."""
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
    tabs = ['job_sources', 'ai_llm', 'contacts', 'validation', 'outreach', 'business_rules']

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
