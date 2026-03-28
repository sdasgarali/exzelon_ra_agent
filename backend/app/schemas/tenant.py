"""Tenant schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re


class TenantResponse(BaseModel):
    """Schema for tenant in API responses."""
    tenant_id: int
    name: str
    slug: str
    plan: str
    is_active: bool
    max_users: int
    max_mailboxes: int
    max_contacts: int
    max_campaigns: int
    max_leads: int
    created_at: datetime

    class Config:
        from_attributes = True


class TenantBrief(BaseModel):
    """Minimal tenant info embedded in user responses."""
    tenant_id: int
    name: str
    slug: str
    plan: str

    class Config:
        from_attributes = True


class SignupRequest(BaseModel):
    """Schema for self-service signup."""
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 chars, 1 uppercase, 1 number)")
    full_name: str = Field(..., min_length=1, max_length=255, description="Full name")
    company_name: str = Field(..., min_length=1, max_length=255, description="Company/organization name")

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v

    @staticmethod
    def slugify(name: str) -> str:
        """Convert company name to URL-safe slug."""
        slug = name.lower().strip()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'[\s-]+', '-', slug)
        slug = slug.strip('-')
        return slug[:100] if slug else "org"


class SignupResponse(BaseModel):
    """Response after successful signup."""
    message: str
    user_id: int


class VerifyResponse(BaseModel):
    """Response after email verification."""
    message: str
    verified: bool
