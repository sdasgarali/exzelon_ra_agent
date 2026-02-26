"""Email template schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.db.models.email_template import TemplateStatus


class EmailTemplateCreate(BaseModel):
    """Schema for creating an email template."""
    name: str = Field(..., min_length=1, max_length=255)
    subject: str = Field(..., min_length=1, max_length=500)
    body_html: str = Field(..., min_length=1)
    body_text: Optional[str] = None
    description: Optional[str] = None
    status: TemplateStatus = TemplateStatus.INACTIVE


class EmailTemplateUpdate(BaseModel):
    """Schema for updating an email template."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    subject: Optional[str] = Field(None, min_length=1, max_length=500)
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TemplateStatus] = None


class EmailTemplateResponse(BaseModel):
    """Schema for email template response."""
    template_id: int
    name: str
    subject: str
    body_html: str
    body_text: Optional[str] = None
    status: TemplateStatus
    is_default: bool
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmailTemplateListResponse(BaseModel):
    """Schema for listing email templates."""
    items: List[EmailTemplateResponse]
    total: int
    active_template_id: Optional[int] = None
