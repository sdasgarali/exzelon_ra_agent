"""Lead schemas."""
from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel
from app.db.models.lead import LeadStatus


class LeadBase(BaseModel):
    """Base lead schema."""
    client_name: str
    job_title: str
    state: Optional[str] = None
    posting_date: Optional[date] = None
    job_link: Optional[str] = None
    salary_min: Optional[Decimal] = None
    salary_max: Optional[Decimal] = None
    source: Optional[str] = None
    ra_name: Optional[str] = None


class LeadCreate(LeadBase):
    """Schema for creating a lead."""
    pass


class LeadUpdate(BaseModel):
    """Schema for updating a lead."""
    client_name: Optional[str] = None
    job_title: Optional[str] = None
    state: Optional[str] = None
    posting_date: Optional[date] = None
    job_link: Optional[str] = None
    salary_min: Optional[Decimal] = None
    salary_max: Optional[Decimal] = None
    source: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    contact_title: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_source: Optional[str] = None
    lead_status: Optional[LeadStatus] = None
    skip_reason: Optional[str] = None
    ra_name: Optional[str] = None


class LeadResponse(LeadBase):
    """Schema for lead response."""
    lead_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    contact_title: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_source: Optional[str] = None
    lead_status: LeadStatus
    skip_reason: Optional[str] = None
    contact_count: Optional[int] = 0
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LeadListResponse(BaseModel):
    """Schema for paginated lead list response."""
    items: List[LeadResponse]
    total: int
    page: int
    page_size: int
    pages: int


class LeadDetailResponse(LeadResponse):
    """Schema for detailed lead response including contacts and outreach events."""
    contacts: List[dict] = []
    outreach_events: List[dict] = []


class LeadContactsManageRequest(BaseModel):
    """Schema for managing lead-contact associations."""
    add_contact_ids: Optional[List[int]] = None
    remove_contact_ids: Optional[List[int]] = None
