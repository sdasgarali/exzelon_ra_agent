"""Contact management endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db, get_current_active_user, require_role, get_current_tenant_id
from app.api.deps.plan_limits import check_plan_limit
from app.db.models.user import User, UserRole
from app.db.models.contact import ContactDetails, PriorityLevel, OutreachStatus as ContactOutreachStatus
from app.db.models.client import ClientInfo
from app.db.models.lead_contact import LeadContactAssociation
from app.db.query_helpers import active_query, tenant_filter
from app.schemas.contact import ContactCreate, ContactUpdate, ContactResponse
from app.schemas.pipeline import BulkContactIdsRequest
from app.services.timezone_resolver import resolve_contact_timezone

import structlog
_logger = structlog.get_logger()

router = APIRouter(prefix="/contacts", tags=["Contacts"])


def _enrich_contact_with_lead_ids(db: Session, contact) -> ContactResponse:
    """Convert a ContactDetails to a response with lead_ids from junction table."""
    assoc_lead_ids = db.query(LeadContactAssociation).with_entities(
        LeadContactAssociation.lead_id
    ).filter(
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
    outreach_status: Optional[str] = None,
    data_type: Optional[str] = None,
    show_archived: bool = Query(False, description="Include archived contacts"),
    sort_by: Optional[str] = Query(None, description="Column to sort by"),
    sort_order: Optional[str] = Query("desc", description="Sort order: asc or desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List contacts with filtering."""
    query = active_query(db, ContactDetails, show_archived=show_archived)
    query = tenant_filter(query, ContactDetails, tenant_id)

    if lead_id:
        junction_cids = [row[0] for row in db.query(LeadContactAssociation).with_entities(
            LeadContactAssociation.contact_id
        ).filter(
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
    if outreach_status:
        query = query.filter(ContactDetails.outreach_status == outreach_status)
    if data_type:
        query = query.filter(ContactDetails.data_type == data_type)
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

    # Sortable columns mapping
    sort_columns = {
        "name": ContactDetails.first_name,
        "company": ContactDetails.client_name,
        "email": ContactDetails.email,
        "phone": ContactDetails.phone,
        "priority": ContactDetails.priority_level,
        "validation": ContactDetails.validation_status,
        "lead_id": ContactDetails.lead_id,
        "source": ContactDetails.source,
        "status": ContactDetails.outreach_status,
        "unsubscribed_at": ContactDetails.unsubscribed_at,
        "timezone": ContactDetails.timezone,
    }
    order_col = sort_columns.get(sort_by, ContactDetails.created_at)
    if sort_order == "asc":
        query = query.order_by(order_col.asc())
    else:
        query = query.order_by(order_col.desc())

    contacts = query.offset(offset).limit(page_size).all()
    pages = (total + page_size - 1) // page_size

    # Batch fetch lead_ids from junction table
    contact_ids = [c.contact_id for c in contacts]
    lead_id_map = {}
    if contact_ids:
        assocs = db.query(LeadContactAssociation).with_entities(
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
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get contact statistics summary."""
    base_query = tenant_filter(db.query(ContactDetails), ContactDetails, tenant_id)

    total = base_query.with_entities(
        func.count(ContactDetails.contact_id)
    ).scalar()

    by_priority = base_query.with_entities(
        ContactDetails.priority_level,
        func.count(ContactDetails.contact_id)
    ).group_by(ContactDetails.priority_level).all()

    by_validation = base_query.with_entities(
        ContactDetails.validation_status,
        func.count(ContactDetails.contact_id)
    ).group_by(ContactDetails.validation_status).all()

    with_lead = db.query(LeadContactAssociation).with_entities(
        func.count(func.distinct(LeadContactAssociation.contact_id))
    ).scalar() or 0
    legacy_linked = base_query.with_entities(
        func.count(ContactDetails.contact_id)
    ).filter(
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
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get all contacts linked to a specific lead."""
    junction_cids = [row[0] for row in db.query(LeadContactAssociation).with_entities(
        LeadContactAssociation.contact_id
    ).filter(
        LeadContactAssociation.lead_id == lead_id
    ).all()]

    if junction_cids:
        query = db.query(ContactDetails).filter(
            (ContactDetails.lead_id == lead_id) |
            (ContactDetails.contact_id.in_(junction_cids))
        )
    else:
        query = db.query(ContactDetails).filter(
            ContactDetails.lead_id == lead_id
        )
    query = tenant_filter(query, ContactDetails, tenant_id)
    contacts = query.order_by(ContactDetails.priority_level, ContactDetails.created_at).all()

    return {
        "lead_id": lead_id,
        "contacts": [ContactResponse.model_validate(c) for c in contacts],
        "total": len(contacts)
    }


@router.delete("/bulk")
async def bulk_delete_contacts(
    request: BulkContactIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Archive multiple contacts by IDs (soft delete). Admin only."""
    contact_ids = request.contact_ids
    if not contact_ids:
        raise HTTPException(status_code=400, detail="No contact IDs provided")

    query = db.query(ContactDetails).filter(
        ContactDetails.contact_id.in_(contact_ids)
    )
    query = tenant_filter(query, ContactDetails, tenant_id)
    contacts = query.all()

    if not contacts:
        raise HTTPException(status_code=404, detail="No contacts found with provided IDs")

    emails = [c.email for c in contacts if c.email]
    found_ids = [c.contact_id for c in contacts]

    try:
        # Soft delete: archive contacts instead of hard deleting
        archive_query = db.query(ContactDetails).filter(
            ContactDetails.contact_id.in_(found_ids)
        )
        archive_query = tenant_filter(archive_query, ContactDetails, tenant_id)
        archived_count = archive_query.update({ContactDetails.is_archived: True}, synchronize_session=False)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bulk delete failed: {str(e)}")

    return {
        "message": f"Successfully archived {archived_count} contact(s)",
        "archived_count": archived_count,
        "archived_ids": found_ids
    }


@router.put("/bulk/restore")
async def bulk_restore_contacts(
    request: BulkContactIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Restore archived contacts (unarchive). Admin only."""
    contact_ids = request.contact_ids
    if not contact_ids:
        raise HTTPException(status_code=400, detail="No contact IDs provided")

    query = db.query(ContactDetails).filter(
        ContactDetails.contact_id.in_(contact_ids),
        ContactDetails.is_archived == True,
    )
    query = tenant_filter(query, ContactDetails, tenant_id)

    try:
        restored_count = query.update({ContactDetails.is_archived: False}, synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bulk restore failed: {str(e)}")

    return {
        "message": f"Successfully restored {restored_count} contact(s)",
        "restored_count": restored_count,
    }


@router.put("/bulk/update")
async def bulk_update_contacts(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Bulk update multiple contacts. Super Admin only.

    Body: { "contact_ids": [...], "updates": { "field": "value", ... } }
    Only non-null fields in updates are applied.
    """
    contact_ids = request.get("contact_ids", [])
    updates = request.get("updates", {})

    if not contact_ids:
        raise HTTPException(status_code=400, detail="No contact IDs provided")
    if not updates:
        raise HTTPException(status_code=400, detail="No update fields provided")

    ALLOWED_FIELDS = {
        "data_type", "first_name", "last_name", "client_name", "email",
        "phone", "timezone", "lead_id", "outreach_status", "validation_status",
        "priority_level", "is_test",
    }
    filtered = {k: v for k, v in updates.items() if k in ALLOWED_FIELDS and v is not None and v != ""}

    if not filtered:
        raise HTTPException(status_code=400, detail="No valid update fields provided")

    query = db.query(ContactDetails).filter(ContactDetails.contact_id.in_(contact_ids))
    query = tenant_filter(query, ContactDetails, tenant_id)
    contacts = query.all()

    if not contacts:
        raise HTTPException(status_code=404, detail="No contacts found with provided IDs")

    try:
        for contact in contacts:
            for field, value in filtered.items():
                if field == "priority_level":
                    setattr(contact, field, PriorityLevel(value))
                elif field == "lead_id":
                    setattr(contact, field, int(value))
                else:
                    setattr(contact, field, value)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bulk update failed: {str(e)}")

    return {"message": f"Updated {len(contacts)} contact(s)", "updated_count": len(contacts)}


@router.post("/reset-test-data", tags=["Contacts"])
async def reset_test_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Reset outreach history for all test contacts. Super Admin only.

    Deletes OutreachEvent and CampaignContact records for is_test=True contacts,
    resets their last_outreach_date and outreach_status, and removes suppression entries.
    """
    from app.db.models.outreach import OutreachEvent
    from app.db.models.campaign import CampaignContact
    from app.db.models.suppression import SuppressionList

    query = tenant_filter(
        db.query(ContactDetails).filter(ContactDetails.is_test == True),
        ContactDetails, tenant_id,
    )
    test_contacts = query.all()

    if not test_contacts:
        return {"reset_count": 0, "events_deleted": 0, "enrollments_deleted": 0, "suppressions_removed": 0}

    test_ids = [c.contact_id for c in test_contacts]
    test_emails = [c.email.lower() for c in test_contacts if c.email]

    # Delete outreach events
    events_deleted = db.query(OutreachEvent).filter(
        OutreachEvent.contact_id.in_(test_ids),
    ).delete(synchronize_session=False)

    # Delete campaign enrollments
    enrollments_deleted = db.query(CampaignContact).filter(
        CampaignContact.contact_id.in_(test_ids),
    ).delete(synchronize_session=False)

    # Remove from suppression list
    suppressions_removed = 0
    if test_emails:
        suppressions_removed = db.query(SuppressionList).filter(
            SuppressionList.email.in_(test_emails),
        ).delete(synchronize_session=False)

    # Reset contact fields
    for contact in test_contacts:
        contact.last_outreach_date = None
        contact.outreach_status = ContactOutreachStatus.ACTIVE

    db.commit()
    _logger.info(
        "reset_test_data",
        tenant_id=tenant_id,
        reset_count=len(test_contacts),
        events_deleted=events_deleted,
        enrollments_deleted=enrollments_deleted,
        suppressions_removed=suppressions_removed,
    )

    return {
        "reset_count": len(test_contacts),
        "events_deleted": events_deleted,
        "enrollments_deleted": enrollments_deleted,
        "suppressions_removed": suppressions_removed,
    }


@router.get("/duplicates", tags=["Contacts"])
async def find_duplicate_contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Find contacts with duplicate email addresses."""
    from sqlalchemy import func as sa_func

    # Find emails that appear more than once
    base_query = active_query(db, ContactDetails, show_archived=False)
    base_query = tenant_filter(base_query, ContactDetails, tenant_id)
    dupes = base_query.with_entities(
        ContactDetails.email,
        sa_func.count(ContactDetails.contact_id).label("count")
    ).filter(
        ContactDetails.email.isnot(None),
    ).group_by(ContactDetails.email).having(
        sa_func.count(ContactDetails.contact_id) > 1
    ).all()

    results = []
    for email, count in dupes:
        detail_query = active_query(db, ContactDetails, show_archived=False)
        detail_query = tenant_filter(detail_query, ContactDetails, tenant_id)
        contacts = detail_query.filter(
            ContactDetails.email == email,
        ).order_by(ContactDetails.created_at).all()
        results.append({
            "email": email,
            "count": count,
            "contacts": [ContactResponse.model_validate(c) for c in contacts]
        })

    return {"duplicates": results, "total_groups": len(results)}


@router.post("/merge", tags=["Contacts"])
async def merge_contacts(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Merge duplicate contacts. Keep primary, archive others and transfer associations."""
    primary_id = request.get("primary_contact_id")
    merge_ids = request.get("merge_contact_ids", [])

    if not primary_id or not merge_ids:
        raise HTTPException(status_code=400, detail="primary_contact_id and merge_contact_ids required")

    if primary_id in merge_ids:
        raise HTTPException(status_code=400, detail="primary_contact_id cannot be in merge_contact_ids")

    query = db.query(ContactDetails).filter(ContactDetails.contact_id == primary_id)
    if tenant_id is not None:
        query = query.filter(ContactDetails.tenant_id == tenant_id)
    primary = query.first()
    if not primary:
        raise HTTPException(status_code=404, detail="Primary contact not found")

    merged_count = 0
    associations_transferred = 0

    for cid in merge_ids:
        merge_query = db.query(ContactDetails).filter(ContactDetails.contact_id == cid)
        if tenant_id is not None:
            merge_query = merge_query.filter(ContactDetails.tenant_id == tenant_id)
        contact = merge_query.first()
        if not contact:
            continue

        # Transfer junction table associations to primary
        assocs = db.query(LeadContactAssociation).filter(
            LeadContactAssociation.contact_id == cid
        ).all()
        for assoc in assocs:
            existing = db.query(LeadContactAssociation).filter(
                LeadContactAssociation.lead_id == assoc.lead_id,
                LeadContactAssociation.contact_id == primary_id
            ).first()
            if not existing:
                new_assoc = LeadContactAssociation(
                    lead_id=assoc.lead_id,
                    contact_id=primary_id,
                )
                db.add(new_assoc)
                associations_transferred += 1
            db.delete(assoc)

        # Archive the merged contact
        contact.is_archived = True
        merged_count += 1

    db.commit()

    return {
        "message": f"Merged {merged_count} contacts into contact {primary_id}",
        "primary_contact_id": primary_id,
        "merged_count": merged_count,
        "associations_transferred": associations_transferred
    }


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get contact by ID."""
    query = db.query(ContactDetails).filter(ContactDetails.contact_id == contact_id)
    if tenant_id is not None:
        query = query.filter(ContactDetails.tenant_id == tenant_id)
    contact = query.first()
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
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a new contact."""
    check_plan_limit(db, tenant_id, "contacts")

    dup_query = tenant_filter(
        db.query(ContactDetails).filter(ContactDetails.email == contact_in.email),
        ContactDetails, tenant_id
    )
    existing = dup_query.first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact with this email already exists"
        )

    lead_ids = contact_in.lead_ids
    contact_data = contact_in.model_dump(exclude={"lead_ids"})
    contact = ContactDetails(**contact_data)
    contact.tenant_id = tenant_id or 1

    # Auto-resolve timezone: prefer contact's own state, fall back to client's timezone
    if contact.location_state:
        contact.timezone = resolve_contact_timezone(contact.location_state)
    elif contact.client_name:
        client = db.query(ClientInfo).filter(
            ClientInfo.client_name == contact.client_name,
            ClientInfo.tenant_id == (tenant_id or 1),
        ).first()
        if client and client.timezone:
            contact.timezone = client.timezone

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
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update contact."""
    query = db.query(ContactDetails).filter(ContactDetails.contact_id == contact_id)
    if tenant_id is not None:
        query = query.filter(ContactDetails.tenant_id == tenant_id)
    contact = query.first()
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    update_data = contact_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contact, field, value)

    # Auto-resolve timezone when location_state changes
    if "location_state" in update_data and contact.location_state:
        contact.timezone = resolve_contact_timezone(contact.location_state)

    db.commit()
    db.refresh(contact)
    return _enrich_contact_with_lead_ids(db, contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Archive contact (soft delete)."""
    query = db.query(ContactDetails).filter(ContactDetails.contact_id == contact_id)
    if tenant_id is not None:
        query = query.filter(ContactDetails.tenant_id == tenant_id)
    contact = query.first()
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    # Soft delete: archive instead of hard deleting
    contact.is_archived = True
    db.commit()


@router.get("/{contact_id}/reply-prediction")
def get_reply_prediction(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get statistical reply prediction for a contact."""
    from app.services.reply_predictor import predict_reply_likelihood

    query = db.query(ContactDetails).filter(ContactDetails.contact_id == contact_id)
    if tenant_id is not None:
        query = query.filter(ContactDetails.tenant_id == tenant_id)
    if not query.first():
        raise HTTPException(status_code=404, detail="Contact not found")

    return predict_reply_likelihood(contact_id, db)
