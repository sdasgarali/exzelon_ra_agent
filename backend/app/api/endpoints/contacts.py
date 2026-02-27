"""Contact management endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db, get_current_active_user, require_role
from app.db.models.user import User, UserRole
from app.db.models.contact import ContactDetails, PriorityLevel
from app.db.models.lead_contact import LeadContactAssociation
from app.schemas.contact import ContactCreate, ContactUpdate, ContactResponse

router = APIRouter(prefix="/contacts", tags=["Contacts"])


def _enrich_contact_with_lead_ids(db: Session, contact) -> ContactResponse:
    """Convert a ContactDetails to a response with lead_ids from junction table."""
    assoc_lead_ids = db.query(LeadContactAssociation.lead_id).filter(
        LeadContactAssociation.contact_id == contact.contact_id
    ).all()
    lead_ids = [row[0] for row in assoc_lead_ids]

    if contact.lead_id and contact.lead_id not in lead_ids:
        lead_ids.insert(0, contact.lead_id)

    response = ContactResponse.model_validate(contact)
    response.lead_ids = lead_ids
    return response


@router.get("")
async def list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    lead_id: Optional[int] = None,
    client_name: Optional[str] = None,
    priority_level: Optional[PriorityLevel] = None,
    validation_status: Optional[str] = None,
    source: Optional[str] = None,
    state: Optional[str] = None,
    search: Optional[str] = None,
    show_archived: bool = Query(False, description="Include archived contacts"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List contacts with filtering."""
    query = db.query(ContactDetails)

    if not show_archived:
        query = query.filter(ContactDetails.is_archived == False)

    if lead_id:
        junction_cids = [row[0] for row in db.query(LeadContactAssociation.contact_id).filter(
            LeadContactAssociation.lead_id == lead_id
        ).all()]
        if junction_cids:
            query = query.filter(
                (ContactDetails.lead_id == lead_id) |
                (ContactDetails.contact_id.in_(junction_cids))
            )
        else:
            query = query.filter(ContactDetails.lead_id == lead_id)
    if client_name:
        query = query.filter(ContactDetails.client_name.ilike(f"%{client_name}%"))
    if priority_level:
        query = query.filter(ContactDetails.priority_level == priority_level)
    if validation_status:
        query = query.filter(ContactDetails.validation_status == validation_status)
    if source:
        query = query.filter(ContactDetails.source == source)
    if state:
        query = query.filter(ContactDetails.location_state == state)
    if search:
        query = query.filter(
            (ContactDetails.first_name.ilike(f"%{search}%")) |
            (ContactDetails.last_name.ilike(f"%{search}%")) |
            (ContactDetails.email.ilike(f"%{search}%"))
        )

    total = query.count()
    offset = (page - 1) * page_size
    contacts = query.order_by(ContactDetails.created_at.desc()).offset(offset).limit(page_size).all()
    pages = (total + page_size - 1) // page_size

    # Batch fetch lead_ids from junction table
    contact_ids = [c.contact_id for c in contacts]
    lead_id_map = {}
    if contact_ids:
        assocs = db.query(
            LeadContactAssociation.contact_id,
            LeadContactAssociation.lead_id
        ).filter(
            LeadContactAssociation.contact_id.in_(contact_ids)
        ).all()
        for cid, lid in assocs:
            lead_id_map.setdefault(cid, []).append(lid)

    items = []
    for c in contacts:
        resp = ContactResponse.model_validate(c)
        junction_leads = lead_id_map.get(c.contact_id, [])
        all_leads = list(junction_leads)
        if c.lead_id and c.lead_id not in all_leads:
            all_leads.insert(0, c.lead_id)
        resp.lead_ids = all_leads
        items.append(resp)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages
    }


@router.get("/stats", tags=["Contacts"])
async def get_contact_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get contact statistics summary."""
    total = db.query(func.count(ContactDetails.contact_id)).scalar()

    by_priority = db.query(
        ContactDetails.priority_level,
        func.count(ContactDetails.contact_id)
    ).group_by(ContactDetails.priority_level).all()

    by_validation = db.query(
        ContactDetails.validation_status,
        func.count(ContactDetails.contact_id)
    ).group_by(ContactDetails.validation_status).all()

    with_lead = db.query(func.count(func.distinct(LeadContactAssociation.contact_id))).scalar() or 0
    legacy_linked = db.query(func.count(ContactDetails.contact_id)).filter(
        ContactDetails.lead_id.isnot(None)
    ).scalar() or 0
    linked = max(with_lead, legacy_linked)

    return {
        "total": total,
        "linked_to_leads": linked,
        "unlinked": total - linked,
        "by_priority": {str(p): c for p, c in by_priority if p},
        "by_validation": {v: c for v, c in by_validation if v}
    }


@router.get("/by-lead/{lead_id}", tags=["Contacts"])
async def get_contacts_for_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all contacts linked to a specific lead."""
    junction_cids = [row[0] for row in db.query(LeadContactAssociation.contact_id).filter(
        LeadContactAssociation.lead_id == lead_id
    ).all()]

    if junction_cids:
        contacts = db.query(ContactDetails).filter(
            (ContactDetails.lead_id == lead_id) |
            (ContactDetails.contact_id.in_(junction_cids))
        ).order_by(ContactDetails.priority_level, ContactDetails.created_at).all()
    else:
        contacts = db.query(ContactDetails).filter(
            ContactDetails.lead_id == lead_id
        ).order_by(ContactDetails.priority_level, ContactDetails.created_at).all()

    return {
        "lead_id": lead_id,
        "contacts": [ContactResponse.model_validate(c) for c in contacts],
        "total": len(contacts)
    }


@router.delete("/bulk")
async def bulk_delete_contacts(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Archive multiple contacts by IDs (soft delete). Admin only."""
    contact_ids = request.get("contact_ids", [])
    if not contact_ids:
        raise HTTPException(status_code=400, detail="No contact IDs provided")

    contacts = db.query(ContactDetails).filter(
        ContactDetails.contact_id.in_(contact_ids)
    ).all()

    if not contacts:
        raise HTTPException(status_code=404, detail="No contacts found with provided IDs")

    emails = [c.email for c in contacts if c.email]
    found_ids = [c.contact_id for c in contacts]

    # Soft delete: archive contacts instead of hard deleting
    archived_count = db.query(ContactDetails).filter(
        ContactDetails.contact_id.in_(found_ids)
    ).update({ContactDetails.is_archived: True}, synchronize_session=False)

    db.commit()

    return {
        "message": f"Successfully archived {archived_count} contact(s)",
        "archived_count": archived_count,
        "archived_ids": found_ids
    }


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get contact by ID."""
    contact = db.query(ContactDetails).filter(ContactDetails.contact_id == contact_id).first()
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )
    return _enrich_contact_with_lead_ids(db, contact)


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact_in: ContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new contact."""
    existing = db.query(ContactDetails).filter(ContactDetails.email == contact_in.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact with this email already exists"
        )

    lead_ids = contact_in.lead_ids
    contact_data = contact_in.model_dump(exclude={"lead_ids"})
    contact = ContactDetails(**contact_data)
    db.add(contact)
    db.flush()

    if lead_ids:
        for lid in lead_ids:
            assoc = LeadContactAssociation(lead_id=lid, contact_id=contact.contact_id)
            db.add(assoc)

    db.commit()
    db.refresh(contact)
    return _enrich_contact_with_lead_ids(db, contact)


@router.put("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: int,
    contact_in: ContactUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update contact."""
    contact = db.query(ContactDetails).filter(ContactDetails.contact_id == contact_id).first()
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    update_data = contact_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contact, field, value)

    db.commit()
    db.refresh(contact)
    return _enrich_contact_with_lead_ids(db, contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Archive contact (soft delete)."""
    contact = db.query(ContactDetails).filter(ContactDetails.contact_id == contact_id).first()
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    # Soft delete: archive instead of hard deleting
    contact.is_archived = True
    db.commit()
