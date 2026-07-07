"""Pipeline management endpoints."""
import json
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, UploadFile, File, Body, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from datetime import timezone
from app.api.deps import get_db, get_current_tenant_id
from app.api.deps.auth import require_module_permission, require_module_tab_permission
from app.core.rate_limiter import limiter
from app.db.models.user import User
from app.db.models.job_run import JobRun, JobStatus
from app.db.query_helpers import tenant_filter
from app.schemas.pipeline import LeadIdsRequest, ContactIdsRequest


def _utc_iso(dt) -> str | None:
    """Convert naive datetime to UTC ISO string so JS parses it correctly."""
    if dt is None:
        return None
    # If naive, assume UTC (our DB stores UTC via datetime.utcnow)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

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
            auto_enriched_leads = counters.get("auto_enriched_leads", 0)

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
                "api_calls_saved": api_calls_saved,
                "auto_enriched_leads": auto_enriched_leads
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
        "api_calls_saved": 0,
        "auto_enriched_leads": 0
    }


@router.get("/runs")
async def list_job_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    pipeline_name: Optional[str] = None,
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_permission('pipelines', 'read')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List pipeline job runs."""
    query = db.query(JobRun)
    query = tenant_filter(query, JobRun, tenant_id)

    if pipeline_name:
        query = query.filter(JobRun.pipeline_name == pipeline_name)
    if status_filter:
        query = query.filter(JobRun.status == status_filter)

    runs = query.order_by(JobRun.started_at.desc()).offset(skip).limit(limit).all()

    results = []
    for r in runs:
        counters = parse_counters(r.counters_json)
        # Compute duration
        duration = None
        if r.started_at and r.ended_at:
            duration = round((r.ended_at - r.started_at).total_seconds(), 1)

        # Extract adapters used from lead_results
        adapters_used = None
        if r.lead_results_json:
            try:
                lr = json.loads(r.lead_results_json)
                adapters = set()
                for entry in lr:
                    if entry.get("adapter_used"):
                        for a in entry["adapter_used"].split(", "):
                            adapters.add(a)
                if adapters:
                    adapters_used = sorted(adapters)
            except (json.JSONDecodeError, TypeError):
                pass

        results.append({
            "run_id": r.run_id,
            "pipeline_name": r.pipeline_name,
            "started_at": _utc_iso(r.started_at),
            "ended_at": _utc_iso(r.ended_at),
            "status": r.status.value if r.status else None,
            "counters": r.counters_json,
            "records_processed": counters["records_processed"],
            "records_success": counters["records_success"],
            "records_failed": counters["records_failed"],
            "error_message": r.error_message,
            "triggered_by": r.triggered_by,
            "duration_seconds": duration,
            "adapters_used": adapters_used,
            "is_cancel_requested": bool(r.is_cancel_requested),
            "progress_pct": r.progress_pct or 0,
            "logs_path": r.logs_path,
        })
    return results


@router.get("/runs/{run_id}")
async def get_job_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_permission('pipelines', 'read')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get job run details."""
    query = db.query(JobRun).filter(JobRun.run_id == run_id)
    query = tenant_filter(query, JobRun, tenant_id)
    run = query.first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job run not found"
        )

    counters = parse_counters(run.counters_json)

    # Compute duration
    duration = None
    if run.started_at and run.ended_at:
        duration = round((run.ended_at - run.started_at).total_seconds(), 1)

    # Extract adapters used from lead_results
    adapters_used = None
    lead_results = None
    if run.lead_results_json:
        try:
            lead_results = json.loads(run.lead_results_json)
            adapters = set()
            for entry in lead_results:
                if entry.get("adapter_used"):
                    for a in entry["adapter_used"].split(", "):
                        adapters.add(a)
            if adapters:
                adapters_used = sorted(adapters)
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "run_id": run.run_id,
        "pipeline_name": run.pipeline_name,
        "started_at": _utc_iso(run.started_at),
        "ended_at": _utc_iso(run.ended_at),
        "status": run.status.value if run.status else None,
        "counters": run.counters_json,
        "records_processed": counters["records_processed"],
        "records_success": counters["records_success"],
        "records_failed": counters["records_failed"],
        "logs_path": run.logs_path,
        "error_message": run.error_message,
        "triggered_by": run.triggered_by,
        "duration_seconds": duration,
        "adapters_used": adapters_used,
        "lead_results": lead_results,
        "is_cancel_requested": bool(run.is_cancel_requested),
        "progress_pct": run.progress_pct or 0,
    }


@router.get("/runs/{run_id}/download")
async def download_run_export(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_permission('pipelines', 'read')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Download the export file (CSV) for a completed pipeline run."""
    query = db.query(JobRun).filter(JobRun.run_id == run_id)
    query = tenant_filter(query, JobRun, tenant_id)
    run = query.first()
    if not run:
        raise HTTPException(status_code=404, detail="Job run not found")

    if not run.logs_path:
        raise HTTPException(status_code=404, detail="No export file for this run")

    if not os.path.isfile(run.logs_path):
        raise HTTPException(status_code=404, detail="Export file not found on disk")

    filename = os.path.basename(run.logs_path)
    return FileResponse(run.logs_path, media_type="text/csv", filename=filename)


@router.get("/runs/{run_id}/summary")
async def get_run_summary(
    run_id: int,
    regenerate: bool = Query(False, description="Force re-generation of summary report"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_permission('pipelines', 'read')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get or generate an AI-powered summary report for a completed pipeline run.

    Pass ?regenerate=true to force fresh generation (ignores cache).
    Old-format cached summaries (missing source_breakdown) are auto-regenerated.
    """
    query = db.query(JobRun).filter(JobRun.run_id == run_id)
    query = tenant_filter(query, JobRun, tenant_id)
    run = query.first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job run not found")

    terminal_statuses = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
    if run.status not in terminal_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Summary is only available for completed, failed, or cancelled runs. Current status: {run.status.value}"
        )

    # Return cached summary if available (skip if regenerate=True)
    if not regenerate and run.summary_json:
        try:
            cached = json.loads(run.summary_json)
            # Auto-regenerate if old format (missing source_breakdown)
            if "source_breakdown" in cached:
                return cached
        except (json.JSONDecodeError, TypeError):
            pass

    # Generate new summary
    from app.services.pipeline_summary import generate_pipeline_summary
    summary = generate_pipeline_summary(db, run)

    # Cache it
    run.summary_json = json.dumps(summary)
    db.commit()

    return summary


@router.post("/jobs/{run_id}/cancel")
async def cancel_job_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_permission('pipelines', 'read_write')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Request cancellation of a running pipeline job."""
    query = db.query(JobRun).filter(JobRun.run_id == run_id)
    query = tenant_filter(query, JobRun, tenant_id)
    run = query.first()
    if not run:
        raise HTTPException(status_code=404, detail="Job run not found")
    if run.status != JobStatus.RUNNING:
        raise HTTPException(status_code=400, detail=f"Cannot cancel job in '{run.status.value}' state")
    run.is_cancel_requested = 1
    db.commit()
    return {"message": f"Cancellation requested for job {run_id}", "run_id": run_id}


@router.post("/lead-sourcing/run")
@limiter.limit("5/hour")
async def run_lead_sourcing(
    request: Request,
    background_tasks: BackgroundTasks,
    sources: List[str] = Query(default=["linkedin", "indeed"]),
    lob_id: Optional[int] = Query(default=None, description="LOB to scope lead sources"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_tab_permission('pipelines', 'lead_sourcing', 'read_write')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Run lead sourcing pipeline."""
    from app.services.pipelines.lead_sourcing import run_lead_sourcing_pipeline

    background_tasks.add_task(
        run_lead_sourcing_pipeline,
        sources=sources,
        triggered_by=current_user.email,
        tenant_id=tenant_id,
        lob_id=lob_id,
    )

    return {
        "message": f"Lead sourcing started for sources: {sources}",
        "status": "processing",
        "lob_id": lob_id,
    }


@router.get("/lead-sourcing/lob-sources")
async def list_lob_lead_sources(
    lob_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_tab_permission('pipelines', 'lead_sourcing', 'read')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List available LOB-specific lead sources for a given LOB."""
    from app.services.pipelines.lead_sourcing import _default_sources_for_lob_type
    from app.core.settings_resolver import get_lob_config

    all_sources = {
        "npi_registry": {"name": "NPI Registry", "description": "Healthcare provider/practice directory (free)", "lobs": ["rcm"]},
        "google_business": {"name": "Google Business", "description": "Local business listings via Google Places", "lobs": ["rcm", "digital_marketing"]},
        "crunchbase": {"name": "Crunchbase", "description": "Company profiles, funding, and growth data", "lobs": ["software_dev", "ai_services"]},
        "builtwith": {"name": "BuiltWith", "description": "Website technology stack analysis", "lobs": ["software_dev", "digital_marketing"]},
        "pagespeed": {"name": "PageSpeed Insights", "description": "Website performance audit scores (free)", "lobs": ["digital_marketing"]},
        "github_org": {"name": "GitHub Organizations", "description": "Software organizations and repos (free)", "lobs": ["software_dev", "ai_services"]},
    }

    if lob_id:
        from app.db.models.line_of_business import LineOfBusiness
        lob = db.query(LineOfBusiness).filter(LineOfBusiness.lob_id == lob_id).first()
        if lob:
            config = get_lob_config(db, lob_id, "lead_source_config") or {}
            enabled = config.get("enabled_sources", _default_sources_for_lob_type(lob.lob_type))
            for key, info in all_sources.items():
                info["enabled"] = key in enabled
                info["recommended"] = lob.lob_type in info["lobs"]
            return {"lob_type": lob.lob_type, "sources": all_sources}

    return {"lob_type": None, "sources": all_sources}


@router.post("/lead-sourcing/upload")
@limiter.limit("10/hour")
async def upload_leads_file(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_tab_permission('pipelines', 'lead_sourcing', 'read_write')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
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
    result = import_leads_from_file(file_path, triggered_by=current_user.email, tenant_id=tenant_id)

    return result


@router.get("/contact-enrichment/estimate")
async def estimate_contact_enrichment(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_tab_permission('pipelines', 'contact_enrichment', 'read')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Estimate API calls for a contact enrichment run (read-only, no side effects)."""
    from app.db.models.lead import LeadDetails, LeadStatus
    from app.db.models.contact import ContactDetails
    from app.db.models.lead_contact import LeadContactAssociation
    from app.core.config import settings as app_settings
    from app.core.settings_resolver import get_tenant_setting
    from app.services.pipelines.contact_enrichment import get_contact_discovery_adapters

    _mc = get_tenant_setting(db, "max_contacts_per_company_job", tenant_id=tenant_id, default=None)
    max_contacts = int(_mc) if _mc is not None else app_settings.MAX_CONTACTS_PER_COMPANY_PER_JOB

    # Same lead selection query as the actual pipeline
    q = db.query(LeadDetails).filter(
        LeadDetails.first_name.is_(None),
        LeadDetails.lead_status == LeadStatus.NEW,
        LeadDetails.is_archived == False,
    )
    if tenant_id is not None:
        q = q.filter(LeadDetails.tenant_id == tenant_id)
    leads = q.limit(100).all()
    total_leads = len(leads)

    # Count how many can be satisfied from company cache vs need API
    from_cache = 0
    needs_api = 0
    for lead in leads:
        # Count existing contacts linked to this lead
        existing = db.query(ContactDetails).filter(
            ContactDetails.lead_id == lead.lead_id
        ).count()
        if existing >= max_contacts:
            from_cache += 1
            continue
        # Check reusable contacts at the same company
        existing_cids = set()
        for row in db.query(LeadContactAssociation).filter(
            LeadContactAssociation.lead_id == lead.lead_id
        ).with_entities(LeadContactAssociation.contact_id).all():
            existing_cids.add(row[0])
        for c in db.query(ContactDetails).filter(
            ContactDetails.lead_id == lead.lead_id
        ).with_entities(ContactDetails.contact_id).all():
            existing_cids.add(c[0])

        reusable_q = db.query(ContactDetails).filter(
            ContactDetails.client_name == lead.client_name,
        )
        if existing_cids:
            reusable_q = reusable_q.filter(~ContactDetails.contact_id.in_(list(existing_cids)))
        reusable_count = reusable_q.limit(max_contacts - existing).count()

        if existing + reusable_count >= max_contacts:
            from_cache += 1
        else:
            needs_api += 1

    # Get configured providers
    adapters = get_contact_discovery_adapters(db, tenant_id=tenant_id)
    provider_names = [a[0] for a in adapters]
    num_providers = len(provider_names)

    # Estimate: min = needs_api * 1 (first adapter succeeds), max = needs_api * num_providers
    return {
        "total_leads_eligible": total_leads,
        "batch_size": 100,
        "from_company_cache": from_cache,
        "needs_api_calls": needs_api,
        "estimated_api_calls_min": needs_api,
        "estimated_api_calls_max": needs_api * max(num_providers, 1),
        "configured_providers": provider_names,
        "max_contacts_per_job": max_contacts,
    }


@router.post("/contact-enrichment/run")
@limiter.limit("5/hour")
async def run_contact_enrichment(
    request: Request,
    background_tasks: BackgroundTasks,
    body: Optional[LeadIdsRequest] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_tab_permission('pipelines', 'contact_enrichment', 'read_write')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Run contact enrichment pipeline. Optionally pass lead_ids to enrich specific leads."""
    from app.services.pipelines.contact_enrichment import run_contact_enrichment_pipeline

    lead_ids = body.lead_ids if body else None

    background_tasks.add_task(
        run_contact_enrichment_pipeline,
        triggered_by=current_user.email,
        lead_ids=lead_ids,
        tenant_id=tenant_id,
    )

    msg = "Contact enrichment started" + (f" for {len(lead_ids)} selected leads" if lead_ids else "")
    return {
        "message": msg,
        "status": "processing"
    }


@router.get("/feature-status")
async def get_feature_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_permission('pipelines', 'read')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get feature flags for the current tenant."""
    from app.core.settings_resolver import get_tenant_setting_bool
    return {
        "email_validation_enabled": get_tenant_setting_bool(
            db, "feature_email_validation_enabled", tenant_id=tenant_id, default=True
        ),
        "campaigns_enabled": get_tenant_setting_bool(
            db, "feature_campaigns_enabled", tenant_id=tenant_id, default=True
        ),
        "outreach_enabled": get_tenant_setting_bool(
            db, "feature_outreach_enabled", tenant_id=tenant_id, default=True
        ),
        "export_mailmerge_enabled": get_tenant_setting_bool(
            db, "feature_export_mailmerge_enabled", tenant_id=tenant_id, default=True
        ),
    }


@router.get("/business-rules")
async def get_business_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_permission('pipelines', 'read')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get resolved business rules for the current tenant (read from DB settings)."""
    from app.services.pipelines.outreach import resolve_business_rules
    from app.core.settings_resolver import get_tenant_setting
    rules = resolve_business_rules(db, tenant_id=tenant_id)
    bounce_target = get_tenant_setting(db, "warmup_bounce_rate_good", tenant_id=tenant_id, default="2.0")
    rules["warmup_bounce_rate_good"] = float(bounce_target)
    return rules


@router.post("/email-validation/run")
@limiter.limit("5/hour")
async def run_email_validation(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_tab_permission('pipelines', 'email_validation', 'read_write')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Run email validation pipeline."""
    from app.core.settings_resolver import get_tenant_setting_bool
    if not get_tenant_setting_bool(db, "feature_email_validation_enabled", tenant_id=tenant_id, default=True):
        raise HTTPException(status_code=403, detail="Email validation is disabled for your organization")

    from app.services.pipelines.email_validation import run_email_validation_pipeline

    background_tasks.add_task(
        run_email_validation_pipeline,
        emails=None,  # Will validate all unvalidated contacts
        provider=None,
        triggered_by=current_user.email,
        tenant_id=tenant_id,
    )

    return {
        "message": "Email validation started",
        "status": "processing"
    }




@router.post("/email-validation/run-selected")
@limiter.limit("10/hour")
async def run_email_validation_selected(
    request: Request,
    background_tasks: BackgroundTasks,
    body: ContactIdsRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_tab_permission('pipelines', 'email_validation', 'read_write')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Run email validation for selected contact IDs."""
    from app.core.settings_resolver import get_tenant_setting_bool
    if not get_tenant_setting_bool(db, "feature_email_validation_enabled", tenant_id=tenant_id, default=True):
        raise HTTPException(status_code=403, detail="Email validation is disabled for your organization")

    from app.services.pipelines.email_validation import run_email_validation_pipeline
    from app.db.models.contact import ContactDetails

    contact_ids = body.contact_ids
    if not contact_ids:
        raise HTTPException(status_code=400, detail="No contact IDs provided")

    q = db.query(ContactDetails).filter(
        ContactDetails.contact_id.in_(contact_ids)
    )
    if tenant_id is not None:
        q = q.filter(ContactDetails.tenant_id == tenant_id)
    contacts = q.all()
    emails = [c.email for c in contacts if c.email]

    if not emails:
        raise HTTPException(status_code=400, detail="No valid emails found for selected contacts")

    background_tasks.add_task(
        run_email_validation_pipeline,
        emails=emails,
        provider=None,
        triggered_by=current_user.email,
    )

    return {
        "message": f"Email validation started for {len(emails)} contacts",
        "status": "processing",
        "count": len(emails)
    }


@router.post("/outreach/run")
@limiter.limit("5/hour")
async def run_outreach(
    request: Request,
    background_tasks: BackgroundTasks,
    mode: str = Query("mailmerge", description="Send mode: mailmerge or send"),
    dry_run: bool = Query(True),
    body: Optional[LeadIdsRequest] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module_tab_permission('pipelines', 'outreach', 'read_write')),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Run outreach pipeline. Optionally pass lead_ids to target specific leads."""
    from app.core.settings_resolver import get_tenant_setting_bool

    if mode == "mailmerge":
        if not get_tenant_setting_bool(db, "feature_export_mailmerge_enabled", tenant_id=tenant_id, default=True):
            raise HTTPException(status_code=403, detail="Export mailmerge is disabled for your organization")
    else:
        if not get_tenant_setting_bool(db, "feature_outreach_enabled", tenant_id=tenant_id, default=True):
            raise HTTPException(status_code=403, detail="Outreach is disabled for your organization")

    lead_ids = body.lead_ids if body else None

    if mode == "mailmerge":
        from app.services.pipelines.outreach import run_outreach_mailmerge_pipeline
        # Create JobRun eagerly so we can return run_id for polling/download
        job_run = JobRun(
            tenant_id=tenant_id or 1,
            pipeline_name="outreach_mailmerge",
            status=JobStatus.RUNNING,
            triggered_by=current_user.email,
        )
        db.add(job_run)
        db.commit()
        db.refresh(job_run)
        run_id = job_run.run_id

        background_tasks.add_task(
            run_outreach_mailmerge_pipeline,
            triggered_by=current_user.email,
            tenant_id=tenant_id,
            lead_ids=lead_ids,
            existing_run_id=run_id,
        )
        return {
            "message": f"Mailmerge export started{f' for {len(lead_ids)} selected leads' if lead_ids else ''}",
            "status": "processing",
            "run_id": run_id,
        }

    if lead_ids:
        from app.services.pipelines.outreach import run_outreach_for_lead
        for lid in lead_ids:
            background_tasks.add_task(run_outreach_for_lead, lead_id=lid, dry_run=dry_run, triggered_by=current_user.email, tenant_id=tenant_id)
        return {
            "message": f"Outreach started for {len(lead_ids)} selected leads (dry_run={dry_run})",
            "status": "processing"
        }

    from app.services.pipelines.outreach import run_outreach_send_pipeline
    background_tasks.add_task(
        run_outreach_send_pipeline,
        dry_run=dry_run,
        limit=30,
        triggered_by=current_user.email,
        tenant_id=tenant_id,
    )

    return {
        "message": f"Outreach pipeline started (mode={mode}, dry_run={dry_run})",
        "status": "processing"
    }
