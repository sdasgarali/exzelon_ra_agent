"""Tenant model for multi-tenant architecture."""
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship

from app.db.base import Base


class Tenant(Base):
    """Tenant model — each tenant is an isolated organization."""

    __tablename__ = "tenants"

    tenant_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    max_users = Column(Integer, default=10, nullable=False)
    max_mailboxes = Column(Integer, default=20, nullable=False)
    plan = Column(String(50), default="standard", nullable=False)  # free/standard/premium

    # Relationships
    users = relationship("User", back_populates="tenant", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Tenant(tenant_id={self.tenant_id}, name='{self.name}', slug='{self.slug}')>"
