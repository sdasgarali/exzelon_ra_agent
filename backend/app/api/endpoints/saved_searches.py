"""Saved searches / smart lists CRUD endpoints."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.db.base import get_db
from app.api.deps.auth import get_current_user
from app.db.models.user import User
from app.db.models.saved_search import SavedSearch

router = APIRouter(prefix="/saved-searches", tags=["Saved Searches"])


class CreateSavedSearch(BaseModel):
    name: str
    description: Optional[str] = None
    filters_json: str  # JSON string of filter criteria
    is_shared: bool = False


class UpdateSavedSearch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    filters_json: Optional[str] = None
    is_shared: Optional[bool] = None


@router.post("")
def create_saved_search(
    body: CreateSavedSearch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save current lead filters as a named search."""
    # Validate JSON
    try:
        json.loads(body.filters_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="filters_json must be valid JSON")

    search = SavedSearch(
        name=body.name,
        description=body.description,
        filters_json=body.filters_json,
        is_shared=body.is_shared,
        user_id=current_user.user_id,
    )
    db.add(search)
    db.commit()
    db.refresh(search)

    return {
        "search_id": search.search_id,
        "name": search.name,
        "description": search.description,
        "filters_json": search.filters_json,
        "is_shared": search.is_shared,
        "created_at": search.created_at.isoformat() if search.created_at else None,
    }


@router.get("")
def list_saved_searches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List current user's saved searches + shared ones."""
    searches = db.query(SavedSearch).filter(
        SavedSearch.is_archived == False,
        ((SavedSearch.user_id == current_user.user_id) | (SavedSearch.is_shared == True)),
    ).order_by(SavedSearch.created_at.desc()).all()

    return [
        {
            "search_id": s.search_id,
            "name": s.name,
            "description": s.description,
            "filters_json": s.filters_json,
            "is_shared": s.is_shared,
            "user_id": s.user_id,
            "is_own": s.user_id == current_user.user_id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in searches
    ]


@router.post("/{search_id}/execute")
def execute_saved_search(
    search_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute a saved search and return matching leads."""
    search = db.query(SavedSearch).filter(
        SavedSearch.search_id == search_id,
        SavedSearch.is_archived == False,
    ).first()
    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found")

    # Check access
    if not search.is_shared and search.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        filters = json.loads(search.filters_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid saved search filters")

    from app.services.ai_lead_search import execute_ai_search
    # If the saved filter has a "query" key, use AI search
    if "query" in filters:
        return execute_ai_search(query=filters["query"], db=db, limit=limit, offset=offset)

    # Otherwise apply filters directly
    from app.db.models.lead import LeadDetails
    from sqlalchemy import func, or_
    from datetime import datetime, timedelta

    q = db.query(LeadDetails).filter(LeadDetails.is_archived == False)

    if filters.get("state"):
        q = q.filter(func.upper(LeadDetails.state) == filters["state"].upper())
    if filters.get("city"):
        q = q.filter(LeadDetails.city.ilike(f"%{filters['city']}%"))
    if filters.get("industry"):
        q = q.filter(LeadDetails.industry.ilike(f"%{filters['industry']}%"))
    if filters.get("industries"):
        industry_filters = [LeadDetails.industry.ilike(f"%{i}%") for i in filters["industries"]]
        q = q.filter(or_(*industry_filters))
    if filters.get("job_title"):
        q = q.filter(LeadDetails.job_title.ilike(f"%{filters['job_title']}%"))
    if filters.get("salary_min"):
        q = q.filter(LeadDetails.salary_min >= int(filters["salary_min"]))
    if filters.get("status"):
        q = q.filter(LeadDetails.status == filters["status"])
    if filters.get("source"):
        q = q.filter(LeadDetails.source.ilike(f"%{filters['source']}%"))
    if filters.get("days_ago"):
        cutoff = datetime.utcnow() - timedelta(days=int(filters["days_ago"]))
        q = q.filter(LeadDetails.created_at >= cutoff)

    total = q.count()
    results = q.order_by(LeadDetails.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "search_name": search.name,
        "filters_applied": filters,
        "total": total,
        "results": [
            {
                "lead_id": r.lead_id,
                "company_name": r.company_name,
                "job_title": r.job_title,
                "state": r.state,
                "city": getattr(r, "city", None),
                "industry": r.industry,
                "salary_min": r.salary_min,
                "salary_max": r.salary_max,
                "status": r.status,
                "source": r.source,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ],
    }


@router.put("/{search_id}")
def update_saved_search(
    search_id: int,
    body: UpdateSavedSearch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a saved search."""
    search = db.query(SavedSearch).filter(
        SavedSearch.search_id == search_id,
        SavedSearch.user_id == current_user.user_id,
        SavedSearch.is_archived == False,
    ).first()
    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found or not owned by you")

    if body.name is not None:
        search.name = body.name
    if body.description is not None:
        search.description = body.description
    if body.filters_json is not None:
        try:
            json.loads(body.filters_json)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=400, detail="filters_json must be valid JSON")
        search.filters_json = body.filters_json
    if body.is_shared is not None:
        search.is_shared = body.is_shared

    db.commit()
    return {"message": "Updated", "search_id": search.search_id}


@router.delete("/{search_id}")
def delete_saved_search(
    search_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a saved search (soft delete)."""
    search = db.query(SavedSearch).filter(
        SavedSearch.search_id == search_id,
        SavedSearch.user_id == current_user.user_id,
        SavedSearch.is_archived == False,
    ).first()
    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found or not owned by you")

    search.is_archived = True
    db.commit()
    return {"message": "Deleted", "search_id": search.search_id}
