"""Lead schemas."""
import json
from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, field_validator, model_validator
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
    employment_type: Optional[str] = None
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
    employment_type: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    contact_title: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_source: Optional[str] = None
    lead_status: Optional[LeadStatus] = None
    data_type: Optional[str] = None
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
    employment_type: Optional[str] = None
    lead_status: LeadStatus
    data_type: Optional[str] = "prod"
    skip_reason: Optional[str] = None
    contact_count: Optional[int] = 0
    industry: Optional[str] = None
    company_size: Optional[str] = None
    employer_website: Optional[str] = None
    run_id: Optional[int] = None
    lob_id: Optional[int] = None
    # Campaign / mailing state (derived from campaign_contacts → campaigns).
    # Must be declared here or FastAPI's response_model strips them from the payload.
    campaign_status: Optional[str] = None
    campaign_id: Optional[int] = None
    mailing_status: Optional[str] = None
    metadata: Optional[dict] = None
    intent_score: Optional[int] = None
    intent_signals: Optional[List[str]] = None
    intent_tier: Optional[str] = None
    is_archived: bool = False
    downloaded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_metadata(cls, v):
        """Ignore SQLAlchemy MetaData objects that collide with this field name."""
        if v is None or isinstance(v, dict):
            return v
        return None

    @model_validator(mode="before")
    @classmethod
    def extract_intent_from_metadata(cls, data):
        """Extract intent data from metadata_json if present."""
        if hasattr(data, "__dict__"):
            # ORM model — read metadata_json attribute
            metadata_json = getattr(data, "metadata_json", None)
            if metadata_json:
                try:
                    meta = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                    intent = meta.get("intent", {}) if isinstance(meta, dict) else {}
                    if intent:
                        # Set as attributes on the ORM object for serialization
                        object.__setattr__(data, "intent_score", intent.get("intent_score"))
                        object.__setattr__(data, "intent_signals", intent.get("signals"))
                        object.__setattr__(data, "intent_tier", intent.get("tier"))
                except (json.JSONDecodeError, TypeError, AttributeError):
                    pass
        elif isinstance(data, dict):
            metadata_json = data.get("metadata_json")
            if metadata_json:
                try:
                    meta = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                    intent = meta.get("intent", {}) if isinstance(meta, dict) else {}
                    if intent:
                        data.setdefault("intent_score", intent.get("intent_score"))
                        data.setdefault("intent_signals", intent.get("signals"))
                        data.setdefault("intent_tier", intent.get("tier"))
                except (json.JSONDecodeError, TypeError):
                    pass
        return data

    class Config:
        from_attributes = True


class LeadListResponse(BaseModel):
    """Schema for paginated lead list response."""
    items: List[LeadResponse]
    total: int
    total_contact_associations: int = 0
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
