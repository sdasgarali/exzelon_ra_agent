"""Contact business logic service."""
from typing import List, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.contact import ContactDetails
from app.db.models.lead_contact import LeadContactAssociation
from app.core.tenant_context import set_current_tenant_id, get_current_tenant_id
from app.db.query_helpers import tenant_query


def get_contact_stats(db: Session) -> dict:
    """Get contact statistics summary."""
    total = tenant_query(db, ContactDetails).with_entities(func.count(ContactDetails.contact_id)).scalar()

    by_priority = tenant_query(db, ContactDetails).with_entities(
        ContactDetails.priority_level,
        func.count(ContactDetails.contact_id)
    ).group_by(ContactDetails.priority_level).all()

    by_validation = tenant_query(db, ContactDetails).with_entities(
        ContactDetails.validation_status,
        func.count(ContactDetails.contact_id)
    ).group_by(ContactDetails.validation_status).all()

    with_lead = tenant_query(db, LeadContactAssociation).with_entities(func.count(func.distinct(LeadContactAssociation.contact_id))).scalar() or 0
    legacy_linked = tenant_query(db, ContactDetails).filter(
        ContactDetails.lead_id.isnot(None)
    ).with_entities(func.count(ContactDetails.contact_id)).scalar() or 0
    linked = max(with_lead, legacy_linked)

    return {
        "total": total,
        "linked_to_leads": linked,
        "unlinked": total - linked,
        "by_priority": {str(p): c for p, c in by_priority if p},
        "by_validation": {v: c for v, c in by_validation if v},
    }


def find_duplicate_contacts(db: Session) -> list:
    """Find contacts with duplicate email addresses."""
    dupes = tenant_query(db, ContactDetails, show_archived=False).with_entities(
        ContactDetails.email,
        func.count(ContactDetails.contact_id).label("count")
    ).filter(
        ContactDetails.email.isnot(None),
    ).group_by(ContactDetails.email).having(
        func.count(ContactDetails.contact_id) > 1
    ).all()

    results = []
    for email, count in dupes:
        contacts = tenant_query(db, ContactDetails, show_archived=False).filter(
            ContactDetails.email == email,
        ).order_by(ContactDetails.created_at).all()
        results.append({"email": email, "count": count, "contacts": contacts})

    return results


def bulk_archive_contacts(db: Session, contact_ids: List[int]) -> int:
    """Archive contacts by IDs. Returns count."""
    return tenant_query(db, ContactDetails).filter(
        ContactDetails.contact_id.in_(contact_ids)
    ).update({ContactDetails.is_archived: True}, synchronize_session=False)


def merge_contacts(db: Session, primary_id: int, merge_ids: List[int]) -> dict:
    """Merge duplicate contacts. Keep primary, archive others, transfer associations."""
    primary = tenant_query(db, ContactDetails).filter(ContactDetails.contact_id == primary_id).first()
    if not primary:
        return {"error": "Primary contact not found"}

    merged_count = 0
    associations_transferred = 0

    for cid in merge_ids:
        contact = tenant_query(db, ContactDetails).filter(ContactDetails.contact_id == cid).first()
        if not contact:
            continue

        assocs = tenant_query(db, LeadContactAssociation).filter(
            LeadContactAssociation.contact_id == cid
        ).all()
        for assoc in assocs:
            existing = tenant_query(db, LeadContactAssociation).filter(
                LeadContactAssociation.lead_id == assoc.lead_id,
                LeadContactAssociation.contact_id == primary_id
            ).first()
            if not existing:
                new_assoc = LeadContactAssociation(lead_id=assoc.lead_id, contact_id=primary_id)
                db.add(new_assoc)
                associations_transferred += 1
            db.delete(assoc)

        contact.is_archived = True
        merged_count += 1

    return {
        "primary_contact_id": primary_id,
        "merged_count": merged_count,
        "associations_transferred": associations_transferred,
    }
