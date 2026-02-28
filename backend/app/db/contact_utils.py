"""Utilities for contact-lead relationship queries using junction table."""
from typing import List, Set
from sqlalchemy.orm import Session
from app.db.models.contact import ContactDetails
from app.db.models.lead_contact import LeadContactAssociation


def get_contact_ids_for_lead(db: Session, lead_id: int) -> Set[int]:
    """Get all contact IDs associated with a lead via junction table + legacy FK.

    Returns deduplicated set of contact IDs from both relationship paths.
    """
    contact_ids = set()

    # Junction table
    for (cid,) in db.query(LeadContactAssociation.contact_id).filter(
        LeadContactAssociation.lead_id == lead_id
    ).all():
        contact_ids.add(cid)

    # Legacy FK
    for (cid,) in db.query(ContactDetails.contact_id).filter(
        ContactDetails.lead_id == lead_id
    ).all():
        contact_ids.add(cid)

    return contact_ids


def get_contacts_for_lead(db: Session, lead_id: int) -> List[ContactDetails]:
    """Get all contacts associated with a lead, deduplicated.

    Uses both junction table and legacy FK, returns unique contacts
    ordered by priority level and creation date.
    """
    contact_ids = get_contact_ids_for_lead(db, lead_id)

    if not contact_ids:
        return []

    return db.query(ContactDetails).filter(
        ContactDetails.contact_id.in_(list(contact_ids))
    ).order_by(
        ContactDetails.priority_level,
        ContactDetails.created_at
    ).all()


def get_lead_ids_for_contact(db: Session, contact_id: int) -> List[int]:
    """Get all lead IDs associated with a contact."""
    lead_ids = set()

    # Junction table
    for (lid,) in db.query(LeadContactAssociation.lead_id).filter(
        LeadContactAssociation.contact_id == contact_id
    ).all():
        lead_ids.add(lid)

    # Legacy FK
    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == contact_id
    ).first()
    if contact and contact.lead_id:
        lead_ids.add(contact.lead_id)

    return sorted(lead_ids)


def sync_lead_primary_contact(db: Session, lead_id: int) -> bool:
    """Sync denormalized contact fields on a lead from its primary contact.

    The primary contact is the first contact by priority level.
    Updates lead's first_name, last_name, contact_email, contact_title,
    contact_phone, and contact_source from the primary contact.

    Returns True if lead was updated, False otherwise.
    """
    from app.db.models.lead import LeadDetails

    contacts = get_contacts_for_lead(db, lead_id)
    if not contacts:
        return False

    lead = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id).first()
    if not lead:
        return False

    primary = contacts[0]  # First by priority_level, then created_at

    changed = False
    if lead.first_name != primary.first_name:
        lead.first_name = primary.first_name
        changed = True
    if lead.last_name != primary.last_name:
        lead.last_name = primary.last_name
        changed = True
    if lead.contact_email != primary.email:
        lead.contact_email = primary.email
        changed = True
    if lead.contact_title != primary.title:
        lead.contact_title = primary.title
        changed = True
    if lead.contact_phone != primary.phone:
        lead.contact_phone = primary.phone
        changed = True
    if lead.contact_source != primary.source:
        lead.contact_source = primary.source
        changed = True

    return changed
