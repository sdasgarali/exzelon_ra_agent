"""Client management endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta

from app.api.deps import get_db, get_current_active_user
from app.db.models.user import User
from app.db.models.client import ClientInfo, ClientStatus, ClientCategory
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse

router = APIRouter(prefix="/clients", tags=["Clients"])


def compute_client_category(db: Session, client_name: str) -> ClientCategory:
    """Compute client category based on posting frequency in last 3 months."""
    three_months_ago = date.today() - timedelta(days=90)

    unique_dates = db.query(func.count(func.distinct(LeadDetails.posting_date))).filter(
        LeadDetails.client_name == client_name,
        LeadDetails.posting_date >= three_months_ago
    ).scalar() or 0

    if unique_dates > 3:
        return ClientCategory.REGULAR
    elif unique_dates > 0:
        return ClientCategory.OCCASIONAL
    else:
        return ClientCategory.PROSPECT


@router.get("")
async def list_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[ClientStatus] = None,
    category: Optional[ClientCategory] = None,
    search: Optional[str] = None,
    show_archived: bool = Query(False, description="Include archived clients"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List clients with filtering."""
    query = db.query(ClientInfo)

    if show_archived:
        query = query.filter(ClientInfo.is_archived == True)
    else:
        query = query.filter(ClientInfo.is_archived == False)

    if status:
        query = query.filter(ClientInfo.status == status)
    if category:
        query = query.filter(ClientInfo.client_category == category)
    if search:
        query = query.filter(ClientInfo.client_name.ilike(f"%{search}%"))

    total = query.count()
    clients = query.order_by(ClientInfo.client_name).offset(skip).limit(limit).all()

    return {
        "items": [ClientResponse.model_validate(c) for c in clients],
        "total": total
    }


@router.get("/stats", tags=["Clients"])
async def get_client_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get client statistics summary."""
    total = db.query(func.count(ClientInfo.client_id)).scalar() or 0

    by_status = db.query(
        ClientInfo.status,
        func.count(ClientInfo.client_id)
    ).group_by(ClientInfo.status).all()

    by_category = db.query(
        ClientInfo.client_category,
        func.count(ClientInfo.client_id)
    ).group_by(ClientInfo.client_category).all()

    return {
        "total": total,
        "by_status": {str(s): c for s, c in by_status if s},
        "by_category": {str(c): n for c, n in by_category if c}
    }


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get client by ID."""
    client = db.query(ClientInfo).filter(ClientInfo.client_id == client_id).first()
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
    current_user: User = Depends(get_current_active_user)
):
    """Create a new client."""
    existing = db.query(ClientInfo).filter(ClientInfo.client_name == client_in.client_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client with this name already exists"
        )

    client = ClientInfo(**client_in.model_dump())
    client.client_category = compute_client_category(db, client_in.client_name)
    db.add(client)
    db.commit()
    db.refresh(client)

    return ClientResponse.model_validate(client)


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    client_in: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update client."""
    client = db.query(ClientInfo).filter(ClientInfo.client_id == client_id).first()
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
    current_user: User = Depends(get_current_active_user)
):
    """Archive client (soft delete)."""
    client = db.query(ClientInfo).filter(ClientInfo.client_id == client_id).first()
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
    current_user: User = Depends(get_current_active_user)
):
    """Refresh client category based on current posting data."""
    client = db.query(ClientInfo).filter(ClientInfo.client_id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    client.client_category = compute_client_category(db, client.client_name)
    db.commit()
    db.refresh(client)

    return ClientResponse.model_validate(client)
