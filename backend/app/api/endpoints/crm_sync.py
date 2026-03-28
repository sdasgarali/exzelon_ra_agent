"""CRM sync endpoints — manual sync trigger and history."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.base import get_db
from app.api.deps.auth import get_current_user, require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.db.models.crm_sync_log import CRMSyncLog
from app.db.query_helpers import tenant_filter

router = APIRouter(prefix="/crm-sync", tags=["CRM Sync"])


class SyncRequest(BaseModel):
    crm_type: Optional[str] = None  # hubspot, salesforce, or None for all configured


@router.post("/run")
def trigger_crm_sync(
    body: SyncRequest = SyncRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Trigger manual CRM sync."""
    from app.services.crm_sync_engine import run_crm_sync, sync_contacts_from_crm, sync_deals_to_crm

    if body.crm_type:
        if body.crm_type not in ("hubspot", "salesforce"):
            raise HTTPException(status_code=400, detail="crm_type must be 'hubspot' or 'salesforce'")
        pull_result = sync_contacts_from_crm(body.crm_type, db)
        push_result = sync_deals_to_crm(body.crm_type, db)
        return {
            "crm_type": body.crm_type,
            "pull_contacts": pull_result,
            "push_deals": push_result,
        }

    # Sync all configured CRMs
    results = run_crm_sync(db)
    return results


@router.get("/history")
def sync_history(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get CRM sync history."""
    query = db.query(CRMSyncLog).filter(
        CRMSyncLog.is_archived == False,
    )
    query = tenant_filter(query, CRMSyncLog, tenant_id)
    logs = query.order_by(CRMSyncLog.started_at.desc()).limit(limit).all()

    return [
        {
            "sync_id": log.sync_id,
            "crm_type": log.crm_type,
            "direction": log.direction,
            "entity_type": log.entity_type,
            "records_synced": log.records_synced,
            "errors": log.errors,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
        }
        for log in logs
    ]
