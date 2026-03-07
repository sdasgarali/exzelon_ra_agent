"""Client schemas."""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel
from app.db.models.client import ClientStatus, ClientCategory


class ClientBase(BaseModel):
    """Base client schema."""
    client_name: str
    status: ClientStatus = ClientStatus.ACTIVE
    industry: Optional[str] = None
    company_size: Optional[str] = None
    location_state: Optional[str] = None


class ClientCreate(ClientBase):
    """Schema for creating a client."""
    pass


class ClientUpdate(BaseModel):
    """Schema for updating a client."""
    client_name: Optional[str] = None
    status: Optional[ClientStatus] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    client_category: Optional[ClientCategory] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    location_state: Optional[str] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    domain: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    employee_count: Optional[int] = None
    founded_year: Optional[int] = None
    headquarters: Optional[str] = None
    phone: Optional[str] = None


class ClientResponse(ClientBase):
    """Schema for client response."""
    client_id: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    client_category: ClientCategory
    service_count: int
    is_archived: bool = False
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    domain: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    employee_count: Optional[int] = None
    founded_year: Optional[int] = None
    headquarters: Optional[str] = None
    phone: Optional[str] = None
    enrichment_source: Optional[str] = None
    enriched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
