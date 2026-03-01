"""User model with RBAC."""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base


class UserRole(str, PyEnum):
    """User roles for RBAC."""
    SUPER_ADMIN = "super_admin"
    TENANT_ADMIN = "tenant_admin"
    ADMIN = "admin"          # Legacy — treated as TENANT_ADMIN
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(Base):
    """User model for authentication and RBAC."""

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x]),
        default=UserRole.VIEWER,
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    # Multi-tenant: NULL for SUPER_ADMIN (system-level), set for all other users
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    tenant = relationship("Tenant", back_populates="users")

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    @property
    def effective_role(self) -> str:
        """Return effective role (maps legacy ADMIN to TENANT_ADMIN)."""
        if self.role == UserRole.ADMIN:
            return UserRole.TENANT_ADMIN
        return self.role

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, email='{self.email}', role='{self.role}', tenant_id={self.tenant_id})>"
