"""Lead business logic service."""
import csv
import io
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.contact import ContactDetails
from app.db.models.lead_contact import LeadContactAssociation
from app.db.contact_utils import get_contacts_for_lead, get_contact_ids_for_lead


def get_lead_stats(db: Session, show_archived: bool = False) -> dict:
    """Get lead statistics summary."""
    query = db.query(LeadDetails)
    if show_archived:
        query = query.filter(LeadDetails.is_archived == True)
    else:
        query = query.filter(LeadDetails.is_archived == False)

    total = query.count()
    by_status = query.with_entities(
        LeadDetails.lead_status, func.count(LeadDetails.lead_id)
    ).group_by(LeadDetails.lead_status).all()
    by_source = query.with_entities(
        LeadDetails.source, func.count(LeadDetails.lead_id)
    ).group_by(LeadDetails.source).all()

    return {
        "total": total,
        "by_status": {s.value: c for s, c in by_status if s},
        "by_source": {s: c for s, c in by_source if s},
    }


def bulk_archive_leads(db: Session, lead_ids: List[int]) -> dict:
    """Archive leads and their linked contacts. Returns counts."""
    leads = db.query(LeadDetails).filter(LeadDetails.lead_id.in_(lead_ids)).all()
    if not leads:
        return {"archived_count": 0, "contacts_archived": 0, "archived_ids": []}

    found_ids = [l.lead_id for l in leads]
    archived_count = db.query(LeadDetails).filter(
        LeadDetails.lead_id.in_(found_ids)
    ).update({LeadDetails.is_archived: True}, synchronize_session=False)

    linked_contacts = db.query(ContactDetails).filter(
        ContactDetails.lead_id.in_(found_ids)
    ).all()
    contact_ids = [c.contact_id for c in linked_contacts]
    contacts_archived = 0
    if contact_ids:
        contacts_archived = db.query(ContactDetails).filter(
            ContactDetails.contact_id.in_(contact_ids)
        ).update({ContactDetails.is_archived: True}, synchronize_session=False)

    return {
        "archived_count": archived_count,
        "contacts_archived": contacts_archived,
        "archived_ids": found_ids,
    }


def bulk_unarchive_leads(db: Session, lead_ids: List[int]) -> int:
    """Unarchive leads. Returns count of restored leads."""
    return db.query(LeadDetails).filter(
        LeadDetails.lead_id.in_(lead_ids),
        LeadDetails.is_archived == True
    ).update({LeadDetails.is_archived: False}, synchronize_session=False)


def generate_csv_stream(db: Session, query):
    """Generate CSV data as a streaming generator."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Lead ID", "Company Name", "Job Title", "State", "Posting Date",
        "Job Link", "Source", "Status", "Salary Min", "Salary Max",
        "Contact Email", "Created At",
    ])
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    batch_size = 1000
    offset = 0
    ordered = query.order_by(LeadDetails.created_at.desc())
    while True:
        batch = ordered.offset(offset).limit(batch_size).all()
        if not batch:
            break
        for lead in batch:
            writer.writerow([
                lead.lead_id, lead.client_name, lead.job_title, lead.state,
                lead.posting_date.isoformat() if lead.posting_date else "",
                lead.job_link, lead.source,
                lead.lead_status.value if lead.lead_status else "",
                lead.salary_min, lead.salary_max, lead.contact_email,
                lead.created_at.isoformat() if lead.created_at else "",
            ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        offset += batch_size
