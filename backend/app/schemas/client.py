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


class ClientResponse(ClientBase):
    """Schema for client response."""
    client_id: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    client_category: ClientCategory
    service_count: int
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
