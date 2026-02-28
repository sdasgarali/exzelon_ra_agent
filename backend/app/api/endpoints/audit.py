"""Audit log endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.api.deps import get_db, get_current_active_user, require_role
from app.db.models.user import User, UserRole
from app.db.models.audit_log import AuditLog

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("")
async def list_audit_logs(
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    action: Optional[str] = None,
    changed_by: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """List audit logs with optional filters. Admin only."""
    query = db.query(AuditLog)

    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if changed_by:
        query = query.filter(AuditLog.changed_by == changed_by)

    total = query.count()
    logs = query.order_by(desc(AuditLog.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "log_id": log.log_id,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "action": log.action,
                "changed_fields": log.changed_fields,
                "changed_by": log.changed_by,
                "notes": log.notes,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }


@router.get("/lead/{lead_id}")
async def get_lead_audit_trail(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get audit trail for a specific lead."""
    logs = db.query(AuditLog).filter(
        AuditLog.entity_type == "lead",
        AuditLog.entity_id == lead_id
    ).order_by(desc(AuditLog.created_at)).all()

    return [
        {
            "log_id": log.log_id,
            "action": log.action,
            "changed_fields": log.changed_fields,
            "changed_by": log.changed_by,
            "notes": log.notes,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
