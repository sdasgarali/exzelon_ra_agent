"""AI-powered natural language lead search endpoint."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.base import get_db
from app.api.deps.auth import get_current_user
from app.db.models.user import User

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
    )
