"""Outreach role model for categorizing sender mailboxes."""
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, UniqueConstraint

from app.db.base import Base


class OutreachRole(Base):
    """Tenant-scoped outreach role (e.g. RA, BDM, Recruiter)."""

    __tablename__ = "outreach_roles"

    role_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    role_name = Column(String(100), nullable=False)  # a.k.a. Role / Title
    description = Column(Text, nullable=True)
    purpose = Column(Text, nullable=True)  # what this role is used for in outreach
    is_system = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "role_name", name="uq_tenant_role_name"),
    )

    def __repr__(self):
        return f"<OutreachRole {self.role_name} (tenant={self.tenant_id})>"
