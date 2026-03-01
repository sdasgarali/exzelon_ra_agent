"""Lead management endpoints."""
import csv
import io
from typing import Optional, List, Literal
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, asc, desc

from app.api.deps import get_db, get_current_active_user, require_role
from app.db.models.user import User, UserRole
from app.db.models.lead import LeadDetails, LeadStatus, CLOSED_STATUSES
from app.db.models.contact import ContactDetails
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.outreach import OutreachEvent
from app.schemas.lead import LeadCreate, LeadUpdate, LeadResponse, LeadListResponse
from app.schemas.contact import ContactResponse
from app.schemas.outreach import OutreachEventResponse
from app.core.state_machine import validate_transition, get_allowed_transitions
from app.db.models.audit_log import AuditLog
from app.schemas.pipeline import BulkLeadIdsRequest, BulkLeadStatusRequest, BulkEnrichRequest, BulkOutreachRequest, ManageContactsRequest
import json

router = APIRouter(prefix="/leads", tags=["Leads"])


def _audit(db: Session, entity_type: str, entity_id: int, action: str,
           changed_fields: dict | None = None, changed_by: str | None = None, notes: str | None = None):
    """Write an audit log entry."""
    log = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        changed_fields=json.dumps(changed_fields) if changed_fields else None,
        changed_by=changed_by,
        notes=notes,
    )
    db.add(log)

# Valid sort columns
SORT_COLUMNS = {
    "lead_id": LeadDetails.lead_id,
    "client_name": LeadDetails.client_name,
    "job_title": LeadDetails.job_title,
    "state": LeadDetails.state,
    "posting_date": LeadDetails.posting_date,
    "created_at": LeadDetails.created_at,
    "source": LeadDetails.source,
    "lead_status": LeadDetails.lead_status,
}


@router.get("", response_model=LeadListResponse)
async def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    limit: Optional[int] = Query(None, ge=1, le=500),
    status: Optional[LeadStatus] = None,
    source: Optional[str] = None,
    state: Optional[str] = None,
    client_name: Optional[str] = None,
    job_title: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = Query("created_at", description="Column to sort by"),
    sort_order: Optional[Literal["asc", "desc"]] = Query("desc", description="Sort direction"),
    show_archived: bool = Query(False, description="Include archived leads"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List leads with filtering, sorting, and pagination."""
    if limit:
        page_size = limit

    query = db.query(LeadDetails)

    if show_archived:
        query = query.filter(LeadDetails.is_archived == True)
    else:
        query = query.filter(LeadDetails.is_archived == False)

    if status:
        query = query.filter(LeadDetails.lead_status == status)
    if source:
        query = query.filter(LeadDetails.source == source)
    if state:
        query = query.filter(LeadDetails.state == state)
    if client_name:
        query = query.filter(LeadDetails.client_name.ilike(f"%{client_name}%"))
    if job_title:
        query = query.filter(LeadDetails.job_title.ilike(f"%{job_title}%"))
    if from_date:
        query = query.filter(LeadDetails.posting_date >= from_date)
    if to_date:
        query = query.filter(LeadDetails.posting_date <= to_date)
    if search:
        # Support searching by numeric ID (e.g. "42" or "#42")
        search_stripped = search.lstrip('#').strip()
        if search_stripped.isdigit():
            query = query.filter(LeadDetails.lead_id == int(search_stripped))
        else:
            query = query.filter(
                (LeadDetails.client_name.ilike(f"%{search}%")) |
                (LeadDetails.job_title.ilike(f"%{search}%")) |
                (LeadDetails.state.ilike(f"%{search}%"))
            )

    total = query.count()

    if sort_by == "contact_count":
        # Subquery: count distinct contacts per lead from junction table
        count_sub = db.query(
            LeadContactAssociation.lead_id.label("lead_id"),
            func.count(func.distinct(LeadContactAssociation.contact_id)).label("cnt")
        ).group_by(LeadContactAssociation.lead_id).subquery()

        query = query.outerjoin(count_sub, LeadDetails.lead_id == count_sub.c.lead_id)
        count_expr = func.coalesce(count_sub.c.cnt, 0)

        if sort_order == "asc":
            query = query.order_by(asc(count_expr))
        else:
            query = query.order_by(desc(count_expr))
    else:
        sort_column = SORT_COLUMNS.get(sort_by, LeadDetails.created_at)
        if sort_order == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

    offset = (page - 1) * page_size
    leads = query.offset(offset).limit(page_size).all()

    pages = (total + page_size - 1) // page_size

    # Batch fetch contact counts via junction table + legacy FK
    lead_ids = [lead.lead_id for lead in leads]
    contact_counts = {}
    if lead_ids:
        # Junction table counts
        junc_counts = db.query(LeadContactAssociation).with_entities(
            LeadContactAssociation.lead_id,
            func.count(func.distinct(LeadContactAssociation.contact_id))
        ).filter(
            LeadContactAssociation.lead_id.in_(lead_ids)
        ).group_by(LeadContactAssociation.lead_id).all()
        for lid, cnt in junc_counts:
            contact_counts[lid] = cnt

        # Legacy FK counts (for leads not in junction table yet)
        legacy_counts = db.query(ContactDetails).with_entities(
            ContactDetails.lead_id,
            func.count(ContactDetails.contact_id)
        ).filter(
            ContactDetails.lead_id.in_(lead_ids)
        ).group_by(ContactDetails.lead_id).all()
        for lid, cnt in legacy_counts:
            contact_counts[lid] = max(contact_counts.get(lid, 0), cnt)

    lead_responses = []
    for lead in leads:
        lead_dict = LeadResponse.model_validate(lead).model_dump()
        lead_dict['contact_count'] = contact_counts.get(lead.lead_id, 0)
        lead_responses.append(lead_dict)

    return {
        "items": lead_responses,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages
    }


@router.get("/stats", tags=["Leads"])
async def get_lead_stats(
    show_archived: bool = Query(False, description="Include archived leads"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get lead statistics summary."""
    stats_base = db.query(LeadDetails)
    if show_archived:
        stats_base = stats_base.filter(LeadDetails.is_archived == True)
    else:
        stats_base = stats_base.filter(LeadDetails.is_archived == False)
    total = stats_base.count()

    by_status = stats_base.with_entities(
        LeadDetails.lead_status,
        func.count(LeadDetails.lead_id)
    ).group_by(LeadDetails.lead_status).all()

    by_source = stats_base.with_entities(
        LeadDetails.source,
        func.count(LeadDetails.lead_id)
    ).group_by(LeadDetails.source).all()

    return {
        "total": total,
        "by_status": {s.value: c for s, c in by_status if s},
        "by_source": {s: c for s, c in by_source if s}
    }



@router.get("/status-transitions")
async def get_status_transitions(
    current_status: Optional[LeadStatus] = None,
    current_user: User = Depends(get_current_active_user)
):
    """Get allowed status transitions. If current_status provided, returns allowed next statuses."""
    if current_status:
        return {
            "current": current_status.value,
            "allowed": get_allowed_transitions(current_status),
        }
    # Return full transition map
    from app.core.state_machine import LEAD_STATUS_TRANSITIONS
    return {
        s.value: sorted([t.value for t in targets])
        for s, targets in LEAD_STATUS_TRANSITIONS.items()
    }


@router.get("/export/csv")
async def export_leads_csv(
    lead_status: Optional[LeadStatus] = Query(None, alias="status"),
    source: Optional[str] = None,
    state: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    search: Optional[str] = None,
    show_archived: bool = Query(False, description="Include archived leads"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Export leads to CSV file."""
    query = db.query(LeadDetails)

    if show_archived:
        query = query.filter(LeadDetails.is_archived == True)
    else:
        query = query.filter(LeadDetails.is_archived == False)

    if lead_status:
        query = query.filter(LeadDetails.lead_status == lead_status)
    if source:
        query = query.filter(LeadDetails.source == source)
    if state:
        query = query.filter(LeadDetails.state == state)
    if from_date:
        query = query.filter(LeadDetails.posting_date >= from_date)
    if to_date:
        query = query.filter(LeadDetails.posting_date <= to_date)
    if search:
        query = query.filter(
            (LeadDetails.client_name.ilike(f"%{search}%")) |
            (LeadDetails.job_title.ilike(f"%{search}%"))
        )

    def generate_csv():
        """Stream CSV data in batches to avoid loading all records into memory."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "Lead ID", "Company Name", "Job Title", "State", "Posting Date",
            "Job Link", "Source", "Status", "Salary Min", "Salary Max",
            "Contact Email", "Created At"
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        # Stream data in batches
        batch_size = 1000
        offset = 0
        ordered_query = query.order_by(LeadDetails.created_at.desc())
        while True:
            batch = ordered_query.offset(offset).limit(batch_size).all()
            if not batch:
                break
            for lead in batch:
                writer.writerow([
                    lead.lead_id,
                    lead.client_name,
                    lead.job_title,
                    lead.state,
                    lead.posting_date.isoformat() if lead.posting_date else "",
                    lead.job_link,
                    lead.source,
                    lead.lead_status.value if lead.lead_status else "",
                    lead.salary_min,
                    lead.salary_max,
                    lead.contact_email,
                    lead.created_at.isoformat() if lead.created_at else ""
                ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
            offset += batch_size

    filename = f"leads_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/import/preview")
async def preview_csv_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Preview CSV import: show first 10 rows, total count, and duplicate count."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    decoded = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))

    rows = list(reader)
    total_rows = len(rows)

    # Check for duplicates
    existing_links = {
        link for (link,) in db.query(LeadDetails).with_entities(
            LeadDetails.job_link
        ).filter(
            LeadDetails.job_link.isnot(None)
        ).all()
    }

    duplicate_count = 0
    preview_rows = []
    for i, row in enumerate(rows):
        row_lower = {k.lower().strip(): v for k, v in row.items()}
        job_link = (row_lower.get('job link') or row_lower.get('job_link') or
                    row_lower.get('link') or row_lower.get('url') or "").strip()

        is_duplicate = bool(job_link and job_link in existing_links)
        if is_duplicate:
            duplicate_count += 1

        if i < 10:
            preview_rows.append({
                "row_number": i + 2,
                "company_name": (row_lower.get('company name') or row_lower.get('client_name') or
                                row_lower.get('company') or "").strip(),
                "job_title": (row_lower.get('job title') or row_lower.get('job_title') or
                             row_lower.get('title') or "").strip(),
                "state": (row_lower.get('state') or "").strip(),
                "source": (row_lower.get('source') or "import").strip(),
                "is_duplicate": is_duplicate,
            })

    return {
        "filename": file.filename,
        "total_rows": total_rows,
        "duplicate_count": duplicate_count,
        "new_count": total_rows - duplicate_count,
        "preview": preview_rows,
        "columns": list(rows[0].keys()) if rows else [],
    }


@router.post("/import/csv")
async def import_leads_csv(
    file: UploadFile = File(...),
    skip_duplicates: bool = Query(True, description="Skip leads with duplicate job_link"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Import leads from CSV file."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV"
        )

    content = await file.read()
    decoded = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))

    imported = 0
    skipped = 0
    errors = []

    # Pre-load existing job_links to avoid N+1 queries
    existing_links = set()
    if skip_duplicates:
        existing_links = {
            link for (link,) in db.query(LeadDetails).with_entities(
                LeadDetails.job_link
            ).filter(
                LeadDetails.job_link.isnot(None)
            ).all()
        }

    for row_num, row in enumerate(reader, start=2):
        try:
            row_lower = {k.lower().strip(): v for k, v in row.items()}

            client_name = (
                row_lower.get('company name') or
                row_lower.get('client_name') or
                row_lower.get('company') or ""
            ).strip()

            job_title = (
                row_lower.get('job title') or
                row_lower.get('job_title') or
                row_lower.get('title') or ""
            ).strip()

            if not client_name or not job_title:
                errors.append(f"Row {row_num}: Missing company name or job title")
                skipped += 1
                continue

            job_link = (
                row_lower.get('job link') or
                row_lower.get('job_link') or
                row_lower.get('link') or
                row_lower.get('url') or ""
            ).strip()

            if skip_duplicates and job_link:
                if job_link in existing_links:
                    skipped += 1
                    continue
                existing_links.add(job_link)  # Track new imports too

            posting_date_str = (
                row_lower.get('posting date') or
                row_lower.get('posting_date') or
                row_lower.get('date') or ""
            ).strip()
            posting_date = None
            if posting_date_str:
                try:
                    posting_date = datetime.strptime(posting_date_str, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        posting_date = datetime.strptime(posting_date_str, "%m/%d/%Y").date()
                    except ValueError:
                        posting_date = date.today()

            status_str = (
                row_lower.get('status') or
                row_lower.get('lead_status') or "open"
            ).strip().lower()
            lead_status_val = LeadStatus.OPEN
            status_map = {
                'open': LeadStatus.OPEN,
                'hunting': LeadStatus.HUNTING,
                'closed_hired': LeadStatus.CLOSED_HIRED,
                'closed-hired': LeadStatus.CLOSED_HIRED,
                'closed_not_hired': LeadStatus.CLOSED_NOT_HIRED,
                'closed-not-hired': LeadStatus.CLOSED_NOT_HIRED,
                'new': LeadStatus.OPEN,
                'closed_test': LeadStatus.CLOSED_TEST,
                'closed-test': LeadStatus.CLOSED_TEST,
            }
            lead_status_val = status_map.get(status_str, LeadStatus.OPEN)

            salary_min = None
            salary_max = None
            try:
                salary_min_str = row_lower.get('salary min') or row_lower.get('salary_min') or ""
                if salary_min_str:
                    salary_min = float(salary_min_str.replace(',', '').replace('$', ''))
            except ValueError:
                pass
            try:
                salary_max_str = row_lower.get('salary max') or row_lower.get('salary_max') or ""
                if salary_max_str:
                    salary_max = float(salary_max_str.replace(',', '').replace('$', ''))
            except ValueError:
                pass

            lead = LeadDetails(
                client_name=client_name,
                job_title=job_title,
                state=(row_lower.get('state') or "").strip()[:2].upper(),
                posting_date=posting_date or date.today(),
                job_link=job_link or None,
                source=(row_lower.get('source') or "import").strip(),
                lead_status=lead_status_val,
                salary_min=salary_min,
                salary_max=salary_max,
                contact_email=(row_lower.get('contact email') or row_lower.get('email') or "").strip() or None,
            )
            db.add(lead)
            imported += 1

        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
            skipped += 1

    db.commit()

    return {
        "message": f"Import complete: {imported} leads imported, {skipped} skipped",
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:10] if errors else []
    }



@router.delete("/bulk")
async def bulk_delete_leads(
    request: BulkLeadIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Archive multiple leads by IDs (soft delete). Admin only."""
    lead_ids = request.lead_ids
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")

    leads = db.query(LeadDetails).filter(
        LeadDetails.lead_id.in_(lead_ids)
    ).all()

    if not leads:
        raise HTTPException(status_code=404, detail="No leads found with provided IDs")

    found_ids = [l.lead_id for l in leads]

    try:
        # Soft delete: archive leads instead of hard deleting
        archived_count = db.query(LeadDetails).filter(
            LeadDetails.lead_id.in_(found_ids)
        ).update({LeadDetails.is_archived: True}, synchronize_session=False)

        # Also archive linked contacts
        linked_contacts = db.query(ContactDetails).filter(
            ContactDetails.lead_id.in_(found_ids)
        ).all()
        contact_ids = [c.contact_id for c in linked_contacts]
        contacts_archived = 0
        if contact_ids:
            contacts_archived = db.query(ContactDetails).filter(
                ContactDetails.contact_id.in_(contact_ids)
            ).update({ContactDetails.is_archived: True}, synchronize_session=False)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bulk delete failed: {str(e)}")

    return {
        "message": f"Successfully archived {archived_count} lead(s) and {contacts_archived} linked contact(s)",
        "archived_count": archived_count,
        "contacts_archived": contacts_archived,
        "archived_ids": found_ids
    }

@router.put('/bulk/unarchive', tags=['Leads'])
async def bulk_unarchive_leads(
    request: BulkLeadIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Restore archived leads (unarchive)."""
    lead_ids = request.lead_ids
    if not lead_ids:
        raise HTTPException(status_code=400, detail='No lead IDs provided')

    try:
        restored_count = db.query(LeadDetails).filter(
            LeadDetails.lead_id.in_(lead_ids),
            LeadDetails.is_archived == True
        ).update({LeadDetails.is_archived: False}, synchronize_session=False)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bulk unarchive failed: {str(e)}")

    return {
        'message': f'Successfully restored {restored_count} lead(s)',
        'restored_count': restored_count,
        'restored_ids': lead_ids
    }






@router.put("/bulk/status")
async def bulk_update_status(
    request: BulkLeadStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Update status of multiple leads at once. Admin/Operator only."""
    lead_ids = request.lead_ids
    new_status = request.status

    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")
    if not new_status:
        raise HTTPException(status_code=400, detail="No status provided")

    # Validate status
    try:
        status_enum = LeadStatus(new_status)
    except ValueError:
        valid = [s.value for s in LeadStatus]
        raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {valid}")

    # Validate transitions per lead and audit
    leads = db.query(LeadDetails).filter(LeadDetails.lead_id.in_(lead_ids)).all()
    updated = 0
    rejected = []
    for lead in leads:
        if not validate_transition(lead.lead_status, status_enum):
            rejected.append({
                "lead_id": lead.lead_id,
                "current": lead.lead_status.value,
                "requested": new_status,
                "allowed": get_allowed_transitions(lead.lead_status),
            })
            continue
        old_status = lead.lead_status.value
        lead.lead_status = status_enum
        _audit(db, "lead", lead.lead_id, "status_change",
               {"lead_status": {"old": old_status, "new": new_status}},
               changed_by=current_user.email)
        updated += 1
    db.commit()

    result = {
        "message": f"Updated {updated} lead(s) to status '{new_status}'",
        "updated_count": updated,
        "status": new_status,
    }
    if rejected:
        result["rejected"] = rejected
        result["message"] += f"; {len(rejected)} rejected (invalid transition)"
    return result


@router.post("/bulk/enrich/preview")
async def preview_bulk_enrichment(
    request: BulkLeadIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Preview enrichment plan: show leads, existing contacts, reusable contacts, API needs."""
    lead_ids = request.lead_ids
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")

    from app.core.config import settings as app_settings
    max_contacts = app_settings.MAX_CONTACTS_PER_COMPANY_PER_JOB

    previews = []
    summary = {
        "total_leads": len(lead_ids),
        "will_enrich": 0,
        "will_skip": 0,
        "contacts_from_cache": 0,
        "leads_needing_api": 0
    }

    for lid in lead_ids:
        lead = db.query(LeadDetails).filter(LeadDetails.lead_id == lid).first()
        if not lead:
            previews.append({"lead_id": lid, "error": "Lead not found", "status": "skip", "skip_reason": "Not found"})
            summary["will_skip"] += 1
            continue

        # Count existing contacts for this lead (junction + FK)
        existing_cids = set()
        for row in db.query(LeadContactAssociation).with_entities(
            LeadContactAssociation.contact_id
        ).filter(
            LeadContactAssociation.lead_id == lid
        ).all():
            existing_cids.add(row[0])
        for c in db.query(ContactDetails).with_entities(
            ContactDetails.contact_id
        ).filter(
            ContactDetails.lead_id == lid
        ).all():
            existing_cids.add(c[0])
        current_contacts = len(existing_cids)

        if current_contacts >= max_contacts:
            previews.append({
                "lead_id": lid, "client_name": lead.client_name, "job_title": lead.job_title,
                "current_contacts": current_contacts, "reusable_count": 0, "api_needed": 0,
                "status": "skip", "skip_reason": f"Already has {current_contacts}/{max_contacts} contacts"
            })
            summary["will_skip"] += 1
            continue

        # Count reusable contacts at same company not linked to this lead
        reusable_q = db.query(ContactDetails).filter(
            ContactDetails.client_name == lead.client_name
        )
        if existing_cids:
            reusable_q = reusable_q.filter(~ContactDetails.contact_id.in_(list(existing_cids)))
        reusable_count = reusable_q.count()

        needed = max_contacts - current_contacts
        from_cache = min(reusable_count, needed)
        api_needed = max(0, needed - from_cache)

        previews.append({
            "lead_id": lid, "client_name": lead.client_name, "job_title": lead.job_title,
            "current_contacts": current_contacts, "reusable_count": from_cache,
            "api_needed": api_needed, "status": "enrich", "skip_reason": None
        })
        summary["will_enrich"] += 1
        summary["contacts_from_cache"] += from_cache
        if api_needed > 0:
            summary["leads_needing_api"] += 1

    # Auto-enrich sibling preview: find other unenriched leads at the same companies
    enriching_companies = set()
    for p in previews:
        if p.get("status") == "enrich" and p.get("client_name"):
            enriching_companies.add(p["client_name"])

    selected_id_set = set(lead_ids)
    auto_enrich_previews = []
    for company in enriching_companies:
        siblings = db.query(LeadDetails).filter(
            LeadDetails.client_name == company,
            LeadDetails.first_name.is_(None),
            ~LeadDetails.lead_status.in_(CLOSED_STATUSES),
            LeadDetails.is_archived == False,
            ~LeadDetails.lead_id.in_(list(selected_id_set))
        ).all()
        for sib in siblings:
            # Check if there are reusable contacts at this company
            sib_existing_cids = set()
            for row in db.query(LeadContactAssociation).with_entities(
                LeadContactAssociation.contact_id
            ).filter(
                LeadContactAssociation.lead_id == sib.lead_id
            ).all():
                sib_existing_cids.add(row[0])
            for c in db.query(ContactDetails).with_entities(
                ContactDetails.contact_id
            ).filter(
                ContactDetails.lead_id == sib.lead_id
            ).all():
                sib_existing_cids.add(c[0])

            sib_reusable_q = db.query(ContactDetails).filter(
                ContactDetails.client_name == company
            )
            if sib_existing_cids:
                sib_reusable_q = sib_reusable_q.filter(~ContactDetails.contact_id.in_(list(sib_existing_cids)))
            reusable_count = sib_reusable_q.count()

            if reusable_count > 0:
                auto_enrich_previews.append({
                    "lead_id": sib.lead_id,
                    "client_name": sib.client_name,
                    "job_title": sib.job_title,
                    "reusable_count": min(reusable_count, max_contacts - len(sib_existing_cids)),
                })

    summary["auto_enrich_siblings"] = len(auto_enrich_previews)

    return {"previews": previews, "summary": summary, "auto_enrich_previews": auto_enrich_previews}


@router.post("/bulk/enrich")
async def bulk_enrich_leads(
    request: BulkEnrichRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Trigger contact enrichment for selected leads (runs in background)."""
    lead_ids = request.lead_ids
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")
    if len(lead_ids) > 200:
        raise HTTPException(status_code=400, detail="Maximum 200 leads per batch")

    from app.services.pipelines.contact_enrichment import run_contact_enrichment_pipeline
    from app.db.models.job_run import JobRun, JobStatus

    # Pre-create job run so we can return run_id immediately
    job_run = JobRun(
        pipeline_name="contact_enrichment",
        status=JobStatus.PENDING,
        triggered_by=current_user.email,
    )
    db.add(job_run)
    db.commit()
    db.refresh(job_run)
    created_run_id = job_run.run_id

    background_tasks.add_task(
        run_contact_enrichment_pipeline,
        triggered_by=current_user.email,
        lead_ids=lead_ids,
        run_id=created_run_id,
    )

    return {
        "message": f"Contact enrichment started for {len(lead_ids)} lead(s)",
        "status": "processing",
        "lead_count": len(lead_ids),
        "run_id": created_run_id
    }


@router.post("/bulk/outreach/preview")
async def preview_bulk_outreach(
    request: BulkLeadIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Preview outreach plan: show leads, contacts, eligibility, and sender assignments."""
    lead_ids = request.lead_ids
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")

    from app.db.models.sender_mailbox import SenderMailbox
    from app.services.pipelines.outreach import check_send_eligibility

    # Get available Cold Ready / Active mailboxes, least loaded first
    available_mailboxes = db.query(SenderMailbox).filter(
        SenderMailbox.is_active == True,
        SenderMailbox.warmup_status.in_(["cold_ready", "active"]),
        SenderMailbox.emails_sent_today < SenderMailbox.daily_send_limit
    ).order_by(SenderMailbox.emails_sent_today.asc()).all()

    mailbox_list = [
        {"mailbox_id": m.mailbox_id, "email": m.email, "display_name": m.display_name,
         "warmup_status": m.warmup_status.value if hasattr(m.warmup_status, 'value') else str(m.warmup_status),
         "sent_today": m.emails_sent_today, "daily_limit": m.daily_send_limit}
        for m in available_mailboxes
    ]

    assignments = []
    mailbox_idx = 0

    for lid in lead_ids:
        lead = db.query(LeadDetails).filter(LeadDetails.lead_id == lid).first()
        if not lead:
            assignments.append({"lead_id": lid, "error": "Lead not found", "contacts": [], "sender": None})
            continue

        # Get contacts
        junction_cids = [row[0] for row in db.query(LeadContactAssociation).with_entities(
            LeadContactAssociation.contact_id
        ).filter(
            LeadContactAssociation.lead_id == lid
        ).all()]

        if junction_cids:
            contacts = db.query(ContactDetails).filter(
                (ContactDetails.lead_id == lid) | (ContactDetails.contact_id.in_(junction_cids))
            ).all()
        else:
            contacts = db.query(ContactDetails).filter(ContactDetails.lead_id == lid).all()

        contact_previews = []
        eligible_count = 0
        for c in contacts:
            eligible, reason = check_send_eligibility(db, c)
            contact_previews.append({
                "contact_id": c.contact_id,
                "name": f"{c.first_name} {c.last_name}".strip(),
                "email": c.email,
                "validation_status": c.validation_status,
                "eligible": eligible,
                "skip_reason": reason if not eligible else None
            })
            if eligible:
                eligible_count += 1

        # Round-robin mailbox assignment for this lead
        sender = None
        if eligible_count > 0 and available_mailboxes:
            mb = available_mailboxes[mailbox_idx % len(available_mailboxes)]
            sender = {"mailbox_id": mb.mailbox_id, "email": mb.email, "display_name": mb.display_name}
            mailbox_idx += 1

        assignments.append({
            "lead_id": lid,
            "client_name": lead.client_name,
            "job_title": lead.job_title,
            "contacts": contact_previews,
            "eligible_count": eligible_count,
            "sender": sender
        })

    return {
        "assignments": assignments,
        "available_mailboxes": mailbox_list,
        "total_leads": len(lead_ids)
    }


@router.post("/bulk/outreach")
async def bulk_outreach_leads(
    request: BulkOutreachRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Trigger outreach for contacts of multiple leads."""
    lead_ids = request.lead_ids
    dry_run = request.dry_run

    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")
    if len(lead_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 leads per batch")

    from app.services.pipelines.outreach import run_outreach_for_lead as _run

    results = []
    total_sent = 0
    total_skipped = 0
    total_errors = 0

    for lid in lead_ids:
        try:
            result = _run(lead_id=lid, dry_run=dry_run, triggered_by=current_user.email)
            sent = result.get("sent", 0)
            skipped = result.get("skipped", 0)
            errors = result.get("errors", 0)
            entry = {"lead_id": lid, "sent": sent, "skipped": skipped, "errors": errors}
            if "error" in result:
                entry["error"] = result["error"]
            if "message" in result:
                entry["message"] = result["message"]
            results.append(entry)
            total_sent += sent
            total_skipped += skipped
            total_errors += errors
        except Exception as e:
            results.append({"lead_id": lid, "error": str(e), "sent": 0, "skipped": 0, "errors": 1})
            total_errors += 1

    return {
        "total_leads": len(lead_ids),
        "results": results,
        "summary": {"total_sent": total_sent, "total_skipped": total_skipped, "total_errors": total_errors},
        "dry_run": dry_run
    }


@router.get("/{lead_id}/detail")
async def get_lead_detail(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get detailed lead info including contacts and outreach events."""
    lead = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )

    # Get contacts via junction table + legacy FK
    junction_cids = [row[0] for row in db.query(LeadContactAssociation).with_entities(
        LeadContactAssociation.contact_id
    ).filter(
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

    # Get outreach events for this lead
    outreach_events = db.query(OutreachEvent).filter(
        OutreachEvent.lead_id == lead_id
    ).order_by(OutreachEvent.sent_at.desc()).all()

    # Build lookup dicts for enrichment
    contact_lookup = {c.contact_id: c for c in contacts}
    # Fetch any additional contacts referenced by events but not in junction
    event_contact_ids = {e.contact_id for e in outreach_events if e.contact_id not in contact_lookup}
    if event_contact_ids:
        extra_contacts = db.query(ContactDetails).filter(
            ContactDetails.contact_id.in_(list(event_contact_ids))
        ).all()
        for c in extra_contacts:
            contact_lookup[c.contact_id] = c

    # Sender mailbox lookup
    from app.db.models.sender_mailbox import SenderMailbox
    mailbox_ids = {e.sender_mailbox_id for e in outreach_events if e.sender_mailbox_id}
    mailbox_lookup = {}
    if mailbox_ids:
        mailboxes = db.query(SenderMailbox).filter(
            SenderMailbox.mailbox_id.in_(list(mailbox_ids))
        ).all()
        mailbox_lookup = {m.mailbox_id: m for m in mailboxes}

    # Enrich events
    enriched_events = []
    for e in outreach_events:
        evt = OutreachEventResponse.model_validate(e).model_dump()
        contact = contact_lookup.get(e.contact_id)
        if contact:
            evt["contact_name"] = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or None
            evt["contact_email"] = contact.email
        else:
            evt["contact_name"] = None
            evt["contact_email"] = None
        mailbox = mailbox_lookup.get(e.sender_mailbox_id) if e.sender_mailbox_id else None
        if mailbox:
            evt["sender_email"] = mailbox.email
            evt["sender_name"] = mailbox.display_name or mailbox.email
        else:
            evt["sender_email"] = None
            evt["sender_name"] = None
        enriched_events.append(evt)

    lead_dict = LeadResponse.model_validate(lead).model_dump()
    lead_dict['contact_count'] = len(contacts)
    lead_dict['contacts'] = [ContactResponse.model_validate(c).model_dump() for c in contacts]
    lead_dict['outreach_events'] = enriched_events

    return lead_dict



@router.post("/{lead_id}/contacts")
async def manage_lead_contacts(
    lead_id: int,
    request: ManageContactsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Add or remove contact associations for a lead."""
    lead = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )

    add_ids = request.add_contact_ids
    remove_ids = request.remove_contact_ids

    added = 0
    removed = 0

    for cid in add_ids:
        contact = db.query(ContactDetails).filter(ContactDetails.contact_id == cid).first()
        if not contact:
            continue
        existing = db.query(LeadContactAssociation).filter(
            LeadContactAssociation.lead_id == lead_id,
            LeadContactAssociation.contact_id == cid
        ).first()
        if not existing:
            assoc = LeadContactAssociation(lead_id=lead_id, contact_id=cid)
            db.add(assoc)
            added += 1

    for cid in remove_ids:
        deleted = db.query(LeadContactAssociation).filter(
            LeadContactAssociation.lead_id == lead_id,
            LeadContactAssociation.contact_id == cid
        ).delete(synchronize_session=False)
        removed += deleted

    db.commit()

    return {
        "message": f"Added {added}, removed {removed} contact associations",
        "added": added,
        "removed": removed,
        "lead_id": lead_id
    }


@router.post("/{lead_id}/outreach")
async def run_outreach_for_lead(
    lead_id: int,
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Trigger outreach for contacts of a specific lead."""
    lead = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )

    from app.services.pipelines.outreach import run_outreach_for_lead as _run
    result = _run(lead_id=lead_id, dry_run=dry_run, triggered_by=current_user.email)

    return result


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get lead by ID."""
    lead = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    return LeadResponse.model_validate(lead)


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    lead_in: LeadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new lead."""
    if lead_in.job_link:
        existing = db.query(LeadDetails).filter(LeadDetails.job_link == lead_in.job_link).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead with this job link already exists"
            )

    lead = LeadDetails(**lead_in.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)

    return LeadResponse.model_validate(lead)


@router.put("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    lead_in: LeadUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update lead."""
    lead = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )

    update_data = lead_in.model_dump(exclude_unset=True)

    # Validate status transition if status is changing
    if "lead_status" in update_data and update_data["lead_status"] != lead.lead_status:
        new_status = update_data["lead_status"]
        if isinstance(new_status, str):
            new_status = LeadStatus(new_status)
        if not validate_transition(lead.lead_status, new_status):
            allowed = get_allowed_transitions(lead.lead_status)
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from '{lead.lead_status.value}' to '{new_status.value}'. Allowed: {allowed}"
            )

    # Track changes for audit
    changes = {}
    for field, value in update_data.items():
        old_val = getattr(lead, field, None)
        if old_val != value:
            old_str = old_val.value if hasattr(old_val, 'value') else str(old_val) if old_val is not None else None
            new_str = value.value if hasattr(value, 'value') else str(value) if value is not None else None
            changes[field] = {"old": old_str, "new": new_str}
        setattr(lead, field, value)

    if changes:
        _audit(db, "lead", lead.lead_id, "update", changes, changed_by=current_user.email)

    db.commit()
    db.refresh(lead)

    return LeadResponse.model_validate(lead)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Archive lead (soft delete)."""
    lead = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )

    # Soft delete: archive instead of hard deleting
    lead.is_archived = True
    _audit(db, "lead", lead.lead_id, "archive",
           {"is_archived": {"old": False, "new": True}},
           changed_by=current_user.email)
    db.commit()
