"""Link personal (non-auto_outbound) mailboxes to login User accounts.

RA / machine mailboxes (auto_outbound roles) have no login user. Personal mailboxes
(BDM/Recruiter/Admin/…) are tied 1:1 to a `User` so that person can sign in AND their
mailbox is usable for manual sends. This module maps an outreach role to a built-in RBAC
role and creates-or-links the login user.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.models.user import User, UserRole

# Outreach role name (lowercased) → built-in RBAC role for the linked login user.
# Unknown/custom roles fall back to the least-privileged built-in (recruiter).
_ROLE_MAP = {
    "admin": UserRole.ADMIN,
    "bd": UserRole.BDM,
    "bdm": UserRole.BDM,
    "business development": UserRole.BDM,
    "business development manager": UserRole.BDM,
    "recruiter": UserRole.RECRUITER,
    "ra": UserRole.RECRUITER,  # only reached if an RA-named role is non-auto_outbound
}


def map_outreach_role_to_rbac(role_name: Optional[str]) -> str:
    """Map an outreach role name to a built-in RBAC role value (never super_admin)."""
    if not role_name:
        return UserRole.RECRUITER.value
    return _ROLE_MAP.get(role_name.strip().lower(), UserRole.RECRUITER).value


class MailboxUserLinkError(ValueError):
    """Raised for invalid mailbox↔user linking (maps to HTTP 400)."""


def create_or_link_user(
    db: Session,
    *,
    email: str,
    full_name: Optional[str],
    login_password: Optional[str],
    tenant_id: Optional[int],
    rbac_role: str,
) -> User:
    """Return the login User for a personal mailbox.

    - If a user with this email already exists → link it (password unchanged).
    - Otherwise → create one (requires ``login_password``).
    Caller is responsible for committing. The returned user has a populated user_id.
    """
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return existing
    if not login_password or not login_password.strip():
        raise MailboxUserLinkError(
            "A login password is required to create a personal (non-RA) mailbox user."
        )
    user = User(
        email=email,
        password_hash=get_password_hash(login_password),
        full_name=full_name,
        role=rbac_role,
        tenant_id=tenant_id,
        is_active=True,
        is_verified=True,  # admin-created accounts are pre-verified
    )
    db.add(user)
    db.flush()  # populate user_id without committing
    return user
