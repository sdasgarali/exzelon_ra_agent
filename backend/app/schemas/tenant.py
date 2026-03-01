"""Tenant schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TenantBase(BaseModel):
    """Base tenant schema."""
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    is_active: bool = True
    max_users: int = Field(10, ge=1, le=1000)
    max_mailboxes: int = Field(20, ge=1, le=500)
    plan: str = Field("standard", pattern=r"^(free|standard|premium)$")


class TenantCreate(TenantBase):
    """Schema for creating a tenant."""
    pass


class TenantUpdate(BaseModel):
    """Schema for updating a tenant."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    max_users: Optional[int] = Field(None, ge=1, le=1000)
    max_mailboxes: Optional[int] = Field(None, ge=1, le=500)
    plan: Optional[str] = Field(None, pattern=r"^(free|standard|premium)$")


class TenantResponse(TenantBase):
    """Schema for tenant response."""
    tenant_id: int
    created_at: datetime
    updated_at: datetime
    is_archived: bool = False

    class Config:
        from_attributes = True


class TenantStatsResponse(TenantResponse):
    """Tenant response with stats."""
    user_count: int = 0
    lead_count: int = 0
    mailbox_count: int = 0
    contact_count: int = 0
