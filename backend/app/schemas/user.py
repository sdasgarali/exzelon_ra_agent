"""User schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
from app.db.models.user import UserRole

# Roles renamed 2026-08-13; normalize legacy inbound values on the schema boundary.
_LEGACY_ROLE_ALIASES = {"operator": UserRole.BDM.value, "viewer": UserRole.RECRUITER.value}


def _normalize_role(v):
    """Map legacy role values to their new keys; pass any other value through.

    ``role`` is a free-form str (not the UserRole enum) so custom, settings-backed
    role keys are accepted. Validity against the role registry is enforced in the
    endpoints, not here.
    """
    if isinstance(v, str):
        return _LEGACY_ROLE_ALIASES.get(v, v)
    return v


class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    full_name: Optional[str] = None
    role: str = UserRole.RECRUITER.value
    is_active: bool = True

    @field_validator("role", mode="before")
    @classmethod
    def _norm_role(cls, v):
        return _normalize_role(v)


class UserCreate(UserBase):
    """Schema for creating a user (admin-created, within tenant)."""
    password: str
    # Target tenant. Honored only for super_admin callers; regular admins always
    # create within their own tenant. Ignored/forced NULL for super_admin-role users.
    tenant_id: Optional[int] = None


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    # Only a super_admin may reassign a user's tenant; ignored for regular admins.
    tenant_id: Optional[int] = None

    @field_validator("role", mode="before")
    @classmethod
    def _norm_role(cls, v):
        return _normalize_role(v)


class TenantInfo(BaseModel):
    """Minimal tenant info in user response."""
    tenant_id: int
    name: str
    slug: str
    plan: str
    industry: Optional[str] = None
    website: Optional[str] = None
    company_address: Optional[str] = None
    logo_url: Optional[str] = None

    class Config:
        from_attributes = True


class UserResponse(UserBase):
    """Schema for user response."""
    user_id: int
    # Built-in role this (possibly custom) role resolves to, for coarse UI gating.
    base_role: Optional[str] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    is_verified: bool = True
    tenant_id: Optional[int] = None
    tenant: Optional[TenantInfo] = None
    locked_until: Optional[datetime] = None
    failed_login_count: Optional[int] = None

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    user: UserResponse


class ForgotPasswordRequest(BaseModel):
    """Schema for forgot password request."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Schema for password reset."""
    token: str
    new_password: str
