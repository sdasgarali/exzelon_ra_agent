"""Permission and RolePermission models for RBAC (wired in Phase 5)."""
from sqlalchemy import Column, Integer, String, Boolean, UniqueConstraint

from app.db.base import Base


class Permission(Base):
    """Permission definition — maps a module + action pair."""

    __tablename__ = "permissions"

    permission_id = Column(Integer, primary_key=True, autoincrement=True)
    module = Column(String(50), nullable=False)   # leads, contacts, outreach, mailboxes, templates, pipelines, settings, users, tenants
    action = Column(String(50), nullable=False)    # read, write, delete
    description = Column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("module", "action", name="uq_permission_module_action"),
    )

    def __repr__(self) -> str:
        return f"<Permission(module='{self.module}', action='{self.action}')>"


class RolePermission(Base):
    """Maps a role string to a permission — defines what each role can do."""

    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String(50), nullable=False, index=True)  # SUPER_ADMIN, TENANT_ADMIN, OPERATOR, VIEWER
    permission_id = Column(Integer, nullable=False, index=True)
    is_allowed = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("role", "permission_id", name="uq_role_permission"),
    )

    def __repr__(self) -> str:
        return f"<RolePermission(role='{self.role}', permission_id={self.permission_id})>"
