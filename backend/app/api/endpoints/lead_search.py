"""AI-powered natural language lead search endpoint."""
import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.base import get_db
from app.api.deps.auth import get_current_user, get_current_tenant_id, require_role
from app.db.models.user import User, UserRole
from app.core.rate_limiter import limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/leads", tags=["Lead Search"])


class AISearchRequest(BaseModel):
    query: str
    limit: int = 50
    offset: int = 0


@router.post("/ai-search")
def ai_search_leads(
    body: AISearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Search leads using natural language queries.

    Examples:
    - "tech companies in Texas hiring HR managers 80k+"
    - "manufacturing in Ohio"
    - "recent leads from last 7 days"
    """
    from app.services.ai_lead_search import execute_ai_search
    return execute_ai_search(
        query=body.query,
        db=db,
        limit=body.limit,
        offset=body.offset,
        tenant_id=tenant_id,
    )


@router.post("/database-search")
@limiter.limit("10/hour")
def database_search_contacts(
    request: Request,
    data: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Search B2B contact database via Apollo adapter.

    Paid: each returned contact is metered as ``contact_enriched`` (the platform's
    Apollo key pays for it). A tenant is required; a super admin without a tenant
    selected may search unmetered (internal use).
    """
    from fastapi import HTTPException, status as http_status
    from app.core.credit_costs import cost_for
    from app.db.models.tenant import Tenant
    from app.services.credit_metering import check_credit_budget, meter

    job_title = data.get("job_title", "")
    company = data.get("company", "")
    location = data.get("location", "")
    try:
        limit = int(data.get("limit", 25))
    except (TypeError, ValueError):
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="limit must be an integer")
    limit = max(1, min(limit, 100))

    if tenant_id is None:
        if user.role != UserRole.SUPER_ADMIN:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Select a tenant first — database search is billed to a tenant.",
            )
    else:
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if tenant is not None and getattr(tenant, "billing_suspended", False):
            raise HTTPException(
                status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
                detail="Account suspended for non-payment. Please settle outstanding invoices to resume.",
            )
        # Pre-flight on the worst case (every requested row returned).
        check_credit_budget(db, tenant_id, credits_needed=limit * cost_for("contact_enriched", db=db))

    # Exclusion gate — do not spend Apollo credits on out-of-scope companies.
    # Name-based rules apply here (placeholder / blacklist / keyword); industry
    # and size are unknown for a free-typed company name so they don't gate.
    from app.services.lead_eligibility import check_lead_eligibility
    eligible, reason = check_lead_eligibility(
        db, {"client_name": company, "job_title": job_title}, tenant_id=tenant_id
    )
    if not eligible:
        logger.info("database_search blocked by exclusion gate", company=company, reason=reason)
        return {"results": [], "count": 0, "excluded": True, "reason": reason}

    try:
        from app.services.adapters.contact_discovery.apollo import ApolloAdapter
        adapter = ApolloAdapter()
        # Map the request params to what Apollo adapter accepts
        results = adapter.search_contacts(
            company_name=company,
            job_title=job_title,
            state=location,  # location maps to state param
            limit=limit,
        )
        results = list(results or [])[:limit]
    except Exception as e:
        logger.warning("database_search_failed", error=str(e))
        return {"results": [], "count": 0, "error": str(e)}

    if results and tenant_id is not None:
        meter(db, tenant_id, "contact_enriched", quantity=len(results),
              user_id=getattr(user, "user_id", None),
              description=f"Database search: {len(results)} contact(s)")
        db.commit()  # get_db closes without committing; persist the charge
    return {"results": results, "count": len(results)}
