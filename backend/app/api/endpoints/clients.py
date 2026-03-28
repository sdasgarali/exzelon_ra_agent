"""Client management endpoints."""
import csv
import io
import json
from typing import List, Optional, Literal
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, asc, desc
from pydantic import BaseModel

from app.api.deps import get_db, get_current_active_user, require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.db.models.client import ClientInfo, ClientStatus, ClientCategory
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.db.models.settings import Settings as SettingsModel
from app.db.query_helpers import active_query, tenant_filter
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse
from app.services.company_enrichment import enrich_client, bulk_enrich_clients

router = APIRouter(prefix="/clients", tags=["Clients"])

# Valid sort columns
SORT_COLUMNS = {
    "client_id": ClientInfo.client_id,
    "client_name": ClientInfo.client_name,
    "status": ClientInfo.status,
    "client_category": ClientInfo.client_category,
    "industry": ClientInfo.industry,
    "company_size": ClientInfo.company_size,
    "location_state": ClientInfo.location_state,
    "created_at": ClientInfo.created_at,
}


class BulkClientIdsRequest(BaseModel):
    """Request body for bulk operations with client IDs."""
    client_ids: List[int]


def _get_setting(db: Session, key: str, default=None):
    """Read a single setting from the DB; return default if missing."""
    row = db.query(SettingsModel).filter(SettingsModel.key == key).first()
    if row and row.value_json:
        try:
            return json.loads(row.value_json)
        except Exception:
            return row.value_json
    return default


def compute_client_category(db: Session, client_name: str, tenant_id: Optional[int] = None) -> ClientCategory:
    """Compute client category based on posting frequency.

    Thresholds are read from the settings table:
      - category_window_days  (default 90)
      - category_regular_threshold  (default 3)  — unique posting dates > this → Regular
      - category_occasional_threshold (default 0) — unique posting dates > this → Occasional
    """
    window_days = int(_get_setting(db, "category_window_days", 90))
    regular_threshold = int(_get_setting(db, "category_regular_threshold", 3))
    occasional_threshold = int(_get_setting(db, "category_occasional_threshold", 0))

    cutoff = date.today() - timedelta(days=window_days)

    lead_query = db.query(LeadDetails).filter(
        LeadDetails.client_name == client_name,
        LeadDetails.posting_date >= cutoff
    )
    lead_query = tenant_filter(lead_query, LeadDetails, tenant_id)
    unique_dates = lead_query.with_entities(func.count(func.distinct(LeadDetails.posting_date))).scalar() or 0

    if unique_dates > regular_threshold:
        return ClientCategory.REGULAR
    elif unique_dates > occasional_threshold:
        return ClientCategory.OCCASIONAL
    else:
        return ClientCategory.PROSPECT


@router.get("")
async def list_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[ClientStatus] = None,
    category: Optional[ClientCategory] = None,
    industry: Optional[str] = None,
    company_size: Optional[str] = None,
    location_state: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = Query("client_name", description="Column to sort by"),
    sort_order: Optional[Literal["asc", "desc"]] = Query("asc", description="Sort direction"),
    show_archived: bool = Query(False, description="Include archived clients"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List clients with filtering and sorting."""
    query = active_query(db, ClientInfo, show_archived=show_archived)
    query = tenant_filter(query, ClientInfo, tenant_id)

    if status:
        query = query.filter(ClientInfo.status == status)
    if category:
        query = query.filter(ClientInfo.client_category == category)
    if industry:
        query = query.filter(ClientInfo.industry == industry)
    if company_size:
        query = query.filter(ClientInfo.company_size == company_size)
    if location_state:
        query = query.filter(ClientInfo.location_state == location_state)
    if search:
        search_stripped = search.lstrip('#').strip()
        if search_stripped.isdigit():
            query = query.filter(ClientInfo.client_id == int(search_stripped))
        else:
            query = query.filter(
                (ClientInfo.client_name.ilike(f"%{search}%")) |
                (ClientInfo.industry.ilike(f"%{search}%")) |
                (ClientInfo.location_state.ilike(f"%{search}%"))
            )

    total = query.count()

    sort_column = SORT_COLUMNS.get(sort_by, ClientInfo.client_name)
    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))

    clients = query.offset(skip).limit(limit).all()

    return {
        "items": [ClientResponse.model_validate(c) for c in clients],
        "total": total
    }


@router.get("/stats", tags=["Clients"])
async def get_client_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get client statistics summary."""
    total_query = tenant_filter(db.query(ClientInfo), ClientInfo, tenant_id)
    total = total_query.with_entities(
        func.count(ClientInfo.client_id)
    ).scalar() or 0

    status_query = tenant_filter(db.query(ClientInfo), ClientInfo, tenant_id)
    by_status = status_query.with_entities(
        ClientInfo.status,
        func.count(ClientInfo.client_id)
    ).group_by(ClientInfo.status).all()

    category_query = tenant_filter(db.query(ClientInfo), ClientInfo, tenant_id)
    by_category = category_query.with_entities(
        ClientInfo.client_category,
        func.count(ClientInfo.client_id)
    ).group_by(ClientInfo.client_category).all()

    return {
        "total": total,
        "by_status": {str(s): c for s, c in by_status if s},
        "by_category": {str(c): n for c, n in by_category if c}
    }


@router.get("/export/csv")
async def export_clients_csv(
    status: Optional[ClientStatus] = None,
    category: Optional[ClientCategory] = None,
    search: Optional[str] = None,
    show_archived: bool = Query(False, description="Include archived clients"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Export clients to CSV file."""
    query = active_query(db, ClientInfo, show_archived=show_archived)
    query = tenant_filter(query, ClientInfo, tenant_id)

    if status:
        query = query.filter(ClientInfo.status == status)
    if category:
        query = query.filter(ClientInfo.client_category == category)
    if search:
        query = query.filter(
            (ClientInfo.client_name.ilike(f"%{search}%")) |
            (ClientInfo.industry.ilike(f"%{search}%"))
        )

    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "ID", "Client Name", "Industry", "Size", "Status",
            "Category", "Services", "Location", "Created"
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        batch_size = 1000
        offset = 0
        ordered_query = query.order_by(ClientInfo.client_name)
        while True:
            batch = ordered_query.offset(offset).limit(batch_size).all()
            if not batch:
                break
            for client in batch:
                writer.writerow([
                    client.client_id,
                    client.client_name,
                    client.industry or "",
                    client.company_size or "",
                    client.status.value if client.status else "",
                    client.client_category.value if client.client_category else "",
                    client.service_count or 0,
                    client.location_state or "",
                    client.created_at.isoformat() if client.created_at else ""
                ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
            offset += batch_size

    filename = f"clients_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/filter-options")
async def get_client_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get distinct values for client filter dropdowns."""
    ind_query = tenant_filter(db.query(ClientInfo.industry).filter(
        ClientInfo.industry.isnot(None), ClientInfo.industry != ""
    ), ClientInfo, tenant_id)
    industries = [r[0] for r in ind_query.distinct().order_by(ClientInfo.industry).all()]

    size_query = tenant_filter(db.query(ClientInfo.company_size).filter(
        ClientInfo.company_size.isnot(None), ClientInfo.company_size != ""
    ), ClientInfo, tenant_id)
    sizes = [r[0] for r in size_query.distinct().order_by(ClientInfo.company_size).all()]

    state_query = tenant_filter(db.query(ClientInfo.location_state).filter(
        ClientInfo.location_state.isnot(None), ClientInfo.location_state != ""
    ), ClientInfo, tenant_id)
    states = [r[0] for r in state_query.distinct().order_by(ClientInfo.location_state).all()]

    return {
        "industries": industries,
        "company_sizes": sizes,
        "location_states": states,
    }


@router.delete("/bulk")
async def bulk_delete_clients(
    request: BulkClientIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Archive multiple clients by IDs (soft delete). Admin/Operator only."""
    client_ids = request.client_ids
    if not client_ids:
        raise HTTPException(status_code=400, detail="No client IDs provided")

    query = db.query(ClientInfo).filter(
        ClientInfo.client_id.in_(client_ids)
    )
    query = tenant_filter(query, ClientInfo, tenant_id)
    clients = query.all()

    if not clients:
        raise HTTPException(status_code=404, detail="No clients found with provided IDs")

    found_ids = [c.client_id for c in clients]

    try:
        archive_query = db.query(ClientInfo).filter(
            ClientInfo.client_id.in_(found_ids)
        )
        archive_query = tenant_filter(archive_query, ClientInfo, tenant_id)
        archived_count = archive_query.update({ClientInfo.is_archived: True}, synchronize_session=False)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bulk delete failed: {str(e)}")

    return {
        "message": f"Successfully archived {archived_count} client(s)",
        "archived_count": archived_count,
        "archived_ids": found_ids
    }


@router.post("/bulk/enrich")
async def bulk_enrich(
    request: BulkClientIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Enrich multiple clients with data aggregated from leads."""
    client_ids = request.client_ids
    if not client_ids:
        raise HTTPException(status_code=400, detail="No client IDs provided")
    if len(client_ids) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 clients per batch")

    # Filter client IDs to only those belonging to this tenant
    query = db.query(ClientInfo.client_id).filter(ClientInfo.client_id.in_(client_ids))
    query = tenant_filter(query, ClientInfo, tenant_id)
    valid_ids = [r[0] for r in query.all()]

    if not valid_ids:
        raise HTTPException(status_code=404, detail="No clients found with provided IDs")

    result = bulk_enrich_clients(db, valid_ids)
    return result


@router.post("/{client_id}/enrich")
async def enrich_single_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Enrich a single client with data aggregated from leads."""
    query = db.query(ClientInfo).filter(ClientInfo.client_id == client_id)
    if tenant_id is not None:
        query = query.filter(ClientInfo.tenant_id == tenant_id)
    client = query.first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    result = enrich_client(db, client)
    db.commit()
    return result


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get client by ID."""
    query = db.query(ClientInfo).filter(ClientInfo.client_id == client_id)
    if tenant_id is not None:
        query = query.filter(ClientInfo.tenant_id == tenant_id)
    client = query.first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    return ClientResponse.model_validate(client)


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    client_in: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a new client."""
    dup_query = db.query(ClientInfo).filter(ClientInfo.client_name == client_in.client_name)
    if tenant_id is not None:
        dup_query = dup_query.filter(ClientInfo.tenant_id == tenant_id)
    existing = dup_query.first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client with this name already exists"
        )

    client = ClientInfo(**client_in.model_dump())
    client.tenant_id = tenant_id or 1
    client.client_category = compute_client_category(db, client_in.client_name, tenant_id=tenant_id)
    db.add(client)
    db.commit()
    db.refresh(client)

    return ClientResponse.model_validate(client)


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    client_in: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update client."""
    query = db.query(ClientInfo).filter(ClientInfo.client_id == client_id)
    if tenant_id is not None:
        query = query.filter(ClientInfo.tenant_id == tenant_id)
    client = query.first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    update_data = client_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)

    return ClientResponse.model_validate(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Archive client (soft delete)."""
    query = db.query(ClientInfo).filter(ClientInfo.client_id == client_id)
    if tenant_id is not None:
        query = query.filter(ClientInfo.tenant_id == tenant_id)
    client = query.first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    # Soft delete: archive client and cascade to linked contacts
    client.is_archived = True
    # Archive all contacts belonging to this company
    db.query(ContactDetails).filter(
        ContactDetails.company_name == client.company_name
    ).update({ContactDetails.is_archived: True}, synchronize_session=False)
    db.commit()


@router.post("/{client_id}/refresh-category", response_model=ClientResponse)
async def refresh_client_category(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Refresh client category based on current posting data."""
    query = db.query(ClientInfo).filter(ClientInfo.client_id == client_id)
    if tenant_id is not None:
        query = query.filter(ClientInfo.tenant_id == tenant_id)
    client = query.first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    client.client_category = compute_client_category(db, client.client_name, tenant_id=tenant_id)
    db.commit()
    db.refresh(client)

    return ClientResponse.model_validate(client)
