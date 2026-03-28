"""User schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.db.models.user import UserRole


class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole = UserRole.VIEWER
    is_active: bool = True


class UserCreate(UserBase):
    """Schema for creating a user (admin-created, within tenant)."""
    password: str


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class TenantInfo(BaseModel):
    """Minimal tenant info in user response."""
    tenant_id: int
    name: str
    slug: str
    plan: str

    class Config:
        from_attributes = True


class UserResponse(UserBase):
    """Schema for user response."""
    user_id: int
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    is_verified: bool = True
    tenant_id: Optional[int] = None
    tenant: Optional[TenantInfo] = None

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
