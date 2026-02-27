"""Contact schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from app.db.models.contact import PriorityLevel


class ContactBase(BaseModel):
    """Base contact schema."""
    lead_id: Optional[int] = None  # Legacy direct FK link
    client_name: str
    first_name: str
    last_name: str
    title: Optional[str] = None
    email: str  # Use str instead of EmailStr to avoid crashing on slightly malformed existing data
    location_state: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    priority_level: Optional[PriorityLevel] = None


class ContactCreate(ContactBase):
    """Schema for creating a contact."""
    email: EmailStr  # Validate email format on creation
    lead_ids: Optional[List[int]] = None  # Associate with multiple leads


class ContactUpdate(BaseModel):
    """Schema for updating a contact."""
    lead_id: Optional[int] = None
    client_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[EmailStr] = None
    location_state: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    priority_level: Optional[PriorityLevel] = None
    validation_status: Optional[str] = None
    last_outreach_date: Optional[str] = None


class ContactResponse(ContactBase):
    """Schema for contact response."""
    contact_id: int
    validation_status: Optional[str] = None
    last_outreach_date: Optional[str] = None
    lead_ids: List[int] = []  # All associated lead IDs via junction table
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContactListResponse(BaseModel):
    """Schema for paginated contact list response."""
    items: List[ContactResponse]
    total: int
    page: int
    page_size: int
    pages: int
