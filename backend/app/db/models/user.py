"""User model with RBAC and multi-tenancy."""
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base


class UserRole(str, PyEnum):
    """Built-in user roles for RBAC.

    NOTE: `operator` was renamed to `bdm` and `viewer` to `recruiter`. Legacy
    values may still appear in old JWTs until they refresh; they are normalized
    via `LEGACY_ROLE_ALIASES` in `api/deps/auth.py`. Custom roles (settings-backed)
    are NOT members of this enum — `users.role` is a VARCHAR that can hold any
    registered role key.
    """
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    BDM = "bdm"
    RECRUITER = "recruiter"


class User(Base):
    """User model for authentication, RBAC, and multi-tenancy."""

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    # VARCHAR (not ENUM) so custom/settings-backed roles can be assigned alongside
    # the built-in UserRole values. Built-in constants still live in UserRole.
    role = Column(
        String(50),
        default=UserRole.RECRUITER.value,
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    # Account lockout
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)

    # Multi-tenancy
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True, index=True)

    # Email verification
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(512), nullable=True)
    verification_sent_at = Column(DateTime, nullable=True)

    # Password reset
    password_reset_token = Column(String(500), nullable=True)
    password_reset_sent_at = Column(DateTime, nullable=True)

    # Onboarding
    onboarding_dismissed_at = Column(DateTime, nullable=True)

    # Calendar link (Calendly/Cal.com)
    calendar_link = Column(String(500), nullable=True)

    # Relationship
    tenant = relationship("Tenant", backref="users")

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, email='{self.email}', role='{self.role}', tenant_id={self.tenant_id})>"
