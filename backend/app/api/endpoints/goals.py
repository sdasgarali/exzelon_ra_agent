"""Goal/target tracking endpoints for KPIs."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel

from app.db.base import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id
from app.db.query_helpers import tenant_filter
from app.db.models.user import User, UserRole
from app.db.models.goal_target import GoalTarget

router = APIRouter(prefix="/goals", tags=["Goals"])


class GoalCreate(BaseModel):
    user_id: Optional[int] = None  # None = team-wide goal
    metric: str  # leads_sourced/emails_sent/deals_won/revenue
    target_value: float
    current_value: float = 0.0
    period: str = "monthly"  # weekly/monthly/quarterly
    period_start: Optional[str] = None  # YYYY-MM-DD
    period_end: Optional[str] = None


class GoalUpdate(BaseModel):
    user_id: Optional[int] = None
    metric: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    period: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None


def _goal_to_dict(g: GoalTarget) -> dict:
    target = g.target_value or 0
    current = g.current_value or 0
    progress = round(current / target * 100, 1) if target > 0 else 0.0
    return {
        "goal_id": g.goal_id,
        "tenant_id": g.tenant_id,
        "user_id": g.user_id,
        "metric": g.metric,
        "target_value": g.target_value,
        "current_value": g.current_value,
        "period": g.period,
        "period_start": g.period_start,
        "period_end": g.period_end,
        "progress_percent": progress,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }


@router.get("")
def list_goals(
    metric: Optional[str] = None,
    period: Optional[str] = None,
    user_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List goals with optional filters."""
    q = db.query(GoalTarget).filter(GoalTarget.is_archived == False)
    q = tenant_filter(q, GoalTarget, tenant_id)

    if metric:
        q = q.filter(GoalTarget.metric == metric)
    if period:
        q = q.filter(GoalTarget.period == period)
    if user_id is not None:
        q = q.filter(GoalTarget.user_id == user_id)

    total = q.count()
    items = q.order_by(desc(GoalTarget.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [_goal_to_dict(g) for g in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("")
def create_goal(
    body: GoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a new goal/target."""
    goal = GoalTarget(
        tenant_id=tenant_id or 1,
        user_id=body.user_id,
        metric=body.metric,
        target_value=body.target_value,
        current_value=body.current_value,
        period=body.period,
        period_start=body.period_start,
        period_end=body.period_end,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _goal_to_dict(goal)


@router.put("/{goal_id}")
def update_goal(
    goal_id: int,
    body: GoalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update a goal."""
    q = db.query(GoalTarget).filter(
        GoalTarget.goal_id == goal_id,
        GoalTarget.is_archived == False,
    )
    q = tenant_filter(q, GoalTarget, tenant_id)
    goal = q.first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    if body.user_id is not None:
        goal.user_id = body.user_id
    if body.metric is not None:
        goal.metric = body.metric
    if body.target_value is not None:
        goal.target_value = body.target_value
    if body.current_value is not None:
        goal.current_value = body.current_value
    if body.period is not None:
        goal.period = body.period
    if body.period_start is not None:
        goal.period_start = body.period_start
    if body.period_end is not None:
        goal.period_end = body.period_end

    db.commit()
    db.refresh(goal)
    return _goal_to_dict(goal)


@router.delete("/{goal_id}")
def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Soft-delete a goal."""
    q = db.query(GoalTarget).filter(
        GoalTarget.goal_id == goal_id,
        GoalTarget.is_archived == False,
    )
    q = tenant_filter(q, GoalTarget, tenant_id)
    goal = q.first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    goal.is_archived = True
    db.commit()
    return {"ok": True, "goal_id": goal_id}


@router.get("/progress")
def goals_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get all active goals with current progress percentages."""
    q = db.query(GoalTarget).filter(GoalTarget.is_archived == False)
    q = tenant_filter(q, GoalTarget, tenant_id)
    goals = q.order_by(GoalTarget.metric, GoalTarget.period).all()

    return {
        "goals": [_goal_to_dict(g) for g in goals],
        "total": len(goals),
    }
