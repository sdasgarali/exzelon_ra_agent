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
    """Search B2B contact database via Apollo adapter."""
    job_title = data.get("job_title", "")
    company = data.get("company", "")
    location = data.get("location", "")
    limit = min(data.get("limit", 25), 100)

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
        return {"results": results, "count": len(results)}
    except Exception as e:
        logger.warning("database_search_failed", error=str(e))
        return {"results": [], "count": 0, "error": str(e)}
