"""Pydantic schemas for pipeline endpoints."""
from typing import List, Optional
from pydantic import BaseModel, Field


class LeadIdsRequest(BaseModel):
    """Request body containing a list of lead IDs."""
    lead_ids: Optional[List[int]] = None


class ContactIdsRequest(BaseModel):
    """Request body containing a list of contact IDs."""
    contact_ids: List[int]


class BulkStatusRequest(BaseModel):
    """Request body for bulk status update."""
    lead_ids: List[int]
    new_status: str


class BulkArchiveRequest(BaseModel):
    """Request body for bulk archive."""
    lead_ids: List[int]


class BulkExportRequest(BaseModel):
    """Request body for bulk export."""
    lead_ids: List[int]
    format: str = "xlsx"


class BulkLeadIdsRequest(BaseModel):
    """Request body for bulk operations with lead IDs."""
    lead_ids: List[int]


class BulkLeadStatusRequest(BaseModel):
    """Request body for bulk status update."""
    lead_ids: List[int]
    status: str = Field(..., max_length=50)


class BulkEnrichRequest(BaseModel):
    """Request body for bulk enrichment."""
    lead_ids: List[int] = Field(..., max_length=200)


class BulkOutreachRequest(BaseModel):
    """Request body for bulk outreach."""
    lead_ids: List[int]
    dry_run: bool = True


class ManageContactsRequest(BaseModel):
    """Request body for managing lead contacts."""
    add_contact_ids: List[int] = []
    remove_contact_ids: List[int] = []


class BulkContactIdsRequest(BaseModel):
    """Request body for bulk contact operations."""
    contact_ids: List[int]
