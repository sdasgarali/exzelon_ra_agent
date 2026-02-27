"""Pipeline management endpoints."""
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, UploadFile, File, Body
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_active_user, require_role
from app.db.models.user import User, UserRole
from app.db.models.job_run import JobRun, JobStatus

router = APIRouter(prefix="/pipelines", tags=["Pipelines"])


def parse_counters(counters_json: str) -> dict:
    """Parse counters JSON and return standardized fields."""
    try:
        if counters_json:
            counters = json.loads(counters_json)
            # Map pipeline counters to frontend expected format
            # Lead sourcing uses: inserted, updated, skipped, errors
            # Contact enrichment uses: contacts_found, leads_enriched, skipped, errors
            # Email validation uses: validated, valid, invalid, errors
            inserted = counters.get("inserted", 0)
            updated = counters.get("updated", 0)
            skipped = counters.get("skipped", 0)
            errors = counters.get("errors", 0)
            contacts_found = counters.get("contacts_found", 0)
            leads_enriched = counters.get("leads_enriched", 0)
            validated = counters.get("validated", 0)
            valid_count = counters.get("valid", 0)
            invalid_count = counters.get("invalid", 0)

            # Calculate totals based on which pipeline ran
            if contacts_found > 0 or leads_enriched > 0:
                # Contact enrichment pipeline
                total = contacts_found + skipped + errors
                success = contacts_found
            elif validated > 0 or valid_count > 0 or invalid_count > 0:
                # Email validation pipeline
                total = validated or (valid_count + invalid_count + errors)
                success = valid_count or validated
            else:
                # Lead sourcing or other pipeline
                total = inserted + updated + skipped + errors
                success = inserted + updated

            contacts_reused = counters.get("contacts_reused", 0)
            api_calls_saved = counters.get("api_calls_saved", 0)

            return {
                "records_processed": total,
                "records_success": success,
                "records_failed": errors,
                "inserted": inserted,
                "updated": updated,
                "skipped": skipped,
                "errors": errors,
                "contacts_found": contacts_found,
                "leads_enriched": leads_enriched,
                "contacts_reused": contacts_reused,
                "api_calls_saved": api_calls_saved
            }
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        "records_processed": 0,
        "records_success": 0,
        "records_failed": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "contacts_found": 0,
        "leads_enriched": 0,
        "contacts_reused": 0,
        "api_calls_saved": 0
    }


@router.get("/runs")
async def list_job_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    pipeline_name: Optional[str] = None,
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List pipeline job runs."""
    query = db.query(JobRun)

    if pipeline_name:
        query = query.filter(JobRun.pipeline_name == pipeline_name)
    if status_filter:
        query = query.filter(JobRun.status == status_filter)

    runs = query.order_by(JobRun.started_at.desc()).offset(skip).limit(limit).all()

    results = []
    for r in runs:
        counters = parse_counters(r.counters_json)
        results.append({
            "run_id": r.run_id,
            "pipeline_name": r.pipeline_name,
            "started_at": r.started_at,
            "ended_at": r.ended_at,
            "status": r.status.value if r.status else None,
            "counters": r.counters_json,
            "records_processed": counters["records_processed"],
            "records_success": counters["records_success"],
            "records_failed": counters["records_failed"],
            "error_message": r.error_message,
            "triggered_by": r.triggered_by
        })
    return results


@router.get("/runs/{run_id}")
async def get_job_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get job run details."""
    run = db.query(JobRun).filter(JobRun.run_id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job run not found"
        )

    counters = parse_counters(run.counters_json)

    return {
        "run_id": run.run_id,
        "pipeline_name": run.pipeline_name,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "status": run.status.value if run.status else None,
        "counters": run.counters_json,
        "records_processed": counters["records_processed"],
        "records_success": counters["records_success"],
        "records_failed": counters["records_failed"],
        "logs_path": run.logs_path,
        "error_message": run.error_message,
        "triggered_by": run.triggered_by
    }


@router.post("/lead-sourcing/run")
async def run_lead_sourcing(
    background_tasks: BackgroundTasks,
    sources: List[str] = Query(default=["linkedin", "indeed"]),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Run lead sourcing pipeline."""
    from app.services.pipelines.lead_sourcing import run_lead_sourcing_pipeline

    background_tasks.add_task(
        run_lead_sourcing_pipeline,
        sources=sources,
        triggered_by=current_user.email
    )

    return {
        "message": f"Lead sourcing started for sources: {sources}",
        "status": "processing"
    }


@router.post("/lead-sourcing/upload")
async def upload_leads_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Upload leads from XLSX file."""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be .xlsx or .xls format"
        )

    from app.services.pipelines.lead_sourcing import import_leads_from_file
    import os
    from app.core.config import settings

    # Save uploaded file
    os.makedirs(settings.EXPORT_PATH, exist_ok=True)
    file_path = os.path.join(settings.EXPORT_PATH, f"upload_{file.filename}")

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Import leads
    result = import_leads_from_file(file_path, triggered_by=current_user.email)

    return result


@router.post("/contact-enrichment/run")
async def run_contact_enrichment(
    background_tasks: BackgroundTasks,
    request: Optional[dict] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Run contact enrichment pipeline. Optionally pass lead_ids to enrich specific leads."""
    from app.services.pipelines.contact_enrichment import run_contact_enrichment_pipeline

    lead_ids = None
    if request and isinstance(request, dict):
        lead_ids = request.get("lead_ids")

    background_tasks.add_task(
        run_contact_enrichment_pipeline,
        triggered_by=current_user.email,
        lead_ids=lead_ids
    )

    msg = "Contact enrichment started" + (f" for {len(lead_ids)} selected leads" if lead_ids else "")
    return {
        "message": msg,
        "status": "processing"
    }


@router.post("/email-validation/run")
async def run_email_validation(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Run email validation pipeline."""
    from app.services.pipelines.email_validation import run_email_validation_pipeline

    background_tasks.add_task(
        run_email_validation_pipeline,
        emails=None,  # Will validate all unvalidated contacts
        provider=None,
        triggered_by=current_user.email
    )

    return {
        "message": "Email validation started",
        "status": "processing"
    }




@router.post("/email-validation/run-selected")
async def run_email_validation_selected(
    request: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Run email validation for selected contact IDs."""
    from app.services.pipelines.email_validation import run_email_validation_pipeline
    from app.db.models.contact import ContactDetails

    contact_ids = request.get("contact_ids", [])
    if not contact_ids:
        raise HTTPException(status_code=400, detail="No contact IDs provided")

    contacts = db.query(ContactDetails).filter(
        ContactDetails.contact_id.in_(contact_ids)
    ).all()
    emails = [c.email for c in contacts if c.email]

    if not emails:
        raise HTTPException(status_code=400, detail="No valid emails found for selected contacts")

    background_tasks.add_task(
        run_email_validation_pipeline,
        emails=emails,
        provider=None,
        triggered_by=current_user.email
    )

    return {
        "message": f"Email validation started for {len(emails)} contacts",
        "status": "processing",
        "count": len(emails)
    }


@router.post("/outreach/run")
async def run_outreach(
    background_tasks: BackgroundTasks,
    mode: str = Query("mailmerge", description="Send mode: mailmerge or send"),
    dry_run: bool = Query(True),
    request: Optional[dict] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Run outreach pipeline. Optionally pass lead_ids to target specific leads."""
    lead_ids = None
    if request and isinstance(request, dict):
        lead_ids = request.get("lead_ids")

    if lead_ids:
        from app.services.pipelines.outreach import run_outreach_for_lead
        for lid in lead_ids:
            background_tasks.add_task(run_outreach_for_lead, lead_id=lid, dry_run=dry_run, triggered_by=current_user.email)
        return {
            "message": f"Outreach started for {len(lead_ids)} selected leads (dry_run={dry_run})",
            "status": "processing"
        }

    if mode == "mailmerge":
        from app.services.pipelines.outreach import run_outreach_mailmerge_pipeline
        background_tasks.add_task(
            run_outreach_mailmerge_pipeline,
            triggered_by=current_user.email
        )
    else:
        from app.services.pipelines.outreach import run_outreach_send_pipeline
        background_tasks.add_task(
            run_outreach_send_pipeline,
            dry_run=dry_run,
            limit=30,
            triggered_by=current_user.email
        )

    return {
        "message": f"Outreach pipeline started (mode={mode}, dry_run={dry_run})",
        "status": "processing"
    }
