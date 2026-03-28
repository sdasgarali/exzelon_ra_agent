"""Email validation endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db, get_current_active_user, get_current_tenant_id
from app.db.models.user import User
from app.db.models.email_validation import EmailValidationResult, ValidationStatus
from app.db.models.contact import ContactDetails
from app.db.query_helpers import tenant_filter
from app.schemas.validation import ValidationResult, ValidationBulkRequest

router = APIRouter(prefix="/validation", tags=["Email Validation"])


@router.get("/results", response_model=List[ValidationResult])
async def list_validation_results(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status_filter: Optional[ValidationStatus] = Query(None, alias="status"),
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """List email validation results."""
    query = db.query(EmailValidationResult)

    if status_filter:
        query = query.filter(EmailValidationResult.status == status_filter)
    if provider:
        query = query.filter(EmailValidationResult.provider == provider)

    results = query.order_by(EmailValidationResult.validated_at.desc()).offset(skip).limit(limit).all()
    return [ValidationResult.model_validate(r) for r in results]


@router.get("/results/{email}")
async def get_validation_result(
    email: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Get validation result for a specific email."""
    result = db.query(EmailValidationResult).filter(
        EmailValidationResult.email == email.lower()
    ).order_by(EmailValidationResult.validated_at.desc()).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Validation result not found"
        )

    return ValidationResult.model_validate(result)


@router.post("/validate-bulk")
async def validate_bulk(
    request: ValidationBulkRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Run bulk email validation (async)."""
    from app.services.pipelines.email_validation import run_email_validation_pipeline

    # Start validation in background
    background_tasks.add_task(
        run_email_validation_pipeline,
        emails=[str(e) for e in request.emails],
        provider=request.provider,
        triggered_by=current_user.email
    )

    return {
        "message": f"Bulk validation started for {len(request.emails)} emails",
        "status": "processing"
    }


@router.post("/validate-pending-contacts")
async def validate_pending_contacts(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Validate all contacts without validation status."""
    # Get unvalidated contact emails
    query = db.query(ContactDetails).filter(
        ContactDetails.validation_status.is_(None)
    )
    query = tenant_filter(query, ContactDetails, tenant_id)
    contacts = query.all()

    if not contacts:
        return {"message": "No pending contacts to validate", "count": 0}

    emails = [c.email for c in contacts]

    from app.services.pipelines.email_validation import run_email_validation_pipeline

    background_tasks.add_task(
        run_email_validation_pipeline,
        emails=emails,
        provider=None,
        triggered_by=current_user.email
    )

    return {
        "message": f"Validation started for {len(emails)} contacts",
        "status": "processing"
    }


@router.get("/stats/summary")
async def get_validation_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Get validation statistics summary."""
    base = db.query(EmailValidationResult)
    total = base.count()

    by_status = base.with_entities(
        EmailValidationResult.status,
        func.count(EmailValidationResult.validation_id)
    ).group_by(EmailValidationResult.status).all()

    valid_count = next((c for s, c in by_status if s == ValidationStatus.VALID), 0)
    invalid_count = next((c for s, c in by_status if s == ValidationStatus.INVALID), 0)

    bounce_rate = (invalid_count / total * 100) if total > 0 else 0

    return {
        "total_validated": total,
        "by_status": {str(s): c for s, c in by_status if s},
        "estimated_bounce_rate": round(bounce_rate, 2)
    }
