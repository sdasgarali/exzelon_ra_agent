"""Deal task endpoints — task management for CRM deals."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.base import get_db
from app.api.deps.auth import get_current_user, get_current_tenant_id
from app.db.models.user import User
from app.db.models.deal_task import DealTask, TaskStatus, TaskPriority
from app.db.models.deal import Deal
from app.db.query_helpers import tenant_filter

router = APIRouter(prefix="", tags=["Deal Tasks"])


class CreateTaskRequest(BaseModel):
    title: str
    description: Optional[str] = None
    assigned_to: Optional[int] = None
    due_date: Optional[str] = None  # ISO format
    priority: str = "medium"  # low, medium, high


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_to: Optional[int] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None


@router.post("/deals/{deal_id}/tasks")
def create_deal_task(
    deal_id: int,
    body: CreateTaskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a task for a deal."""
    query = db.query(Deal).filter(Deal.deal_id == deal_id, Deal.is_archived == False)
    query = tenant_filter(query, Deal, tenant_id)
    deal = query.first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    due = None
    if body.due_date:
        try:
            due = datetime.fromisoformat(body.due_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid due_date format")

    priority = TaskPriority(body.priority) if body.priority in [e.value for e in TaskPriority] else TaskPriority.MEDIUM

    task = DealTask(
        deal_id=deal_id,
        title=body.title,
        description=body.description,
        assigned_to=body.assigned_to,
        due_date=due,
        priority=priority,
        created_by=current_user.user_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return _task_to_dict(task)


@router.get("/deals/{deal_id}/tasks")
def list_deal_tasks(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List tasks for a specific deal."""
    # Verify deal belongs to tenant
    deal_query = db.query(Deal).filter(Deal.deal_id == deal_id, Deal.is_archived == False)
    deal_query = tenant_filter(deal_query, Deal, tenant_id)
    if not deal_query.first():
        raise HTTPException(status_code=404, detail="Deal not found")

    tasks = db.query(DealTask).filter(
        DealTask.deal_id == deal_id,
        DealTask.is_archived == False,
    ).order_by(DealTask.due_date.asc().nullslast(), DealTask.created_at.desc()).all()

    return [_task_to_dict(t) for t in tasks]


@router.put("/tasks/{task_id}")
def update_task(
    task_id: int,
    body: UpdateTaskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update a deal task."""
    task = db.query(DealTask).filter(
        DealTask.task_id == task_id,
        DealTask.is_archived == False,
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Verify parent deal belongs to tenant
    if tenant_id is not None:
        deal = db.query(Deal).filter(Deal.deal_id == task.deal_id, Deal.tenant_id == tenant_id).first()
        if not deal:
            raise HTTPException(status_code=404, detail="Task not found")

    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.assigned_to is not None:
        task.assigned_to = body.assigned_to
    if body.due_date is not None:
        try:
            task.due_date = datetime.fromisoformat(body.due_date) if body.due_date else None
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid due_date format")
    if body.priority is not None and body.priority in [e.value for e in TaskPriority]:
        task.priority = TaskPriority(body.priority)
    if body.status is not None and body.status in [e.value for e in TaskStatus]:
        task.status = TaskStatus(body.status)
        if body.status == "completed":
            task.completed_at = datetime.utcnow()

    db.commit()
    return _task_to_dict(task)


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Mark a task as completed."""
    task = db.query(DealTask).filter(
        DealTask.task_id == task_id,
        DealTask.is_archived == False,
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Verify parent deal belongs to tenant
    if tenant_id is not None:
        deal = db.query(Deal).filter(Deal.deal_id == task.deal_id, Deal.tenant_id == tenant_id).first()
        if not deal:
            raise HTTPException(status_code=404, detail="Task not found")

    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.utcnow()
    db.commit()
    return _task_to_dict(task)


@router.delete("/tasks/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Delete a deal task (soft delete)."""
    task = db.query(DealTask).filter(
        DealTask.task_id == task_id,
        DealTask.is_archived == False,
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Verify parent deal belongs to tenant
    if tenant_id is not None:
        deal = db.query(Deal).filter(Deal.deal_id == task.deal_id, Deal.tenant_id == tenant_id).first()
        if not deal:
            raise HTTPException(status_code=404, detail="Task not found")

    task.is_archived = True
    db.commit()
    return {"message": "Deleted", "task_id": task_id}


@router.get("/tasks/my-tasks")
def my_tasks(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get current user's tasks across all deals."""
    q = db.query(DealTask).join(Deal, DealTask.deal_id == Deal.deal_id).filter(
        DealTask.assigned_to == current_user.user_id,
        DealTask.is_archived == False,
    )

    # Filter by tenant via parent Deal
    if tenant_id is not None:
        q = q.filter(Deal.tenant_id == tenant_id)

    if status and status in [e.value for e in TaskStatus]:
        q = q.filter(DealTask.status == TaskStatus(status))

    tasks = q.order_by(DealTask.due_date.asc().nullslast(), DealTask.created_at.desc()).all()
    return [_task_to_dict(t) for t in tasks]


def _task_to_dict(task: DealTask) -> dict:
    return {
        "task_id": task.task_id,
        "deal_id": task.deal_id,
        "title": task.title,
        "description": task.description,
        "assigned_to": task.assigned_to,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "status": task.status.value if task.status else "pending",
        "priority": task.priority.value if task.priority else "medium",
        "created_by": task.created_by,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }
