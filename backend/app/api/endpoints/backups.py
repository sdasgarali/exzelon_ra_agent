"""Database backup management endpoints.

RBAC:
- List / Create / Download: Admin+ (super_admin bypasses via require_role)
- Delete / Restore: Super Admin only
"""
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.db.models.user import User, UserRole
from app.db.models.audit_log import AuditLog
from app.services import backup_service

logger = structlog.get_logger()

router = APIRouter(prefix="/backups", tags=["Backups"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _audit_backup(db: Session, action: str, changed_by: str, filename: str,
                  outcome: str, details: str = ""):
    """Write an audit log entry for a backup operation."""
    db.add(AuditLog(
        tenant_id=1,
        entity_type="backup",
        entity_id=0,
        action=action,
        changed_by=changed_by,
        notes=json.dumps({"filename": filename, "outcome": outcome, "details": details}),
    ))
    db.commit()


class RestoreRequest(BaseModel):
    confirm: bool


# ---------------------------------------------------------------------------
# Endpoints — Admin+ (list, create, download)
# ---------------------------------------------------------------------------

@router.get("")
async def list_backups(current_user: User = Depends(require_role([UserRole.ADMIN]))):
    """List all available database backups."""
    return backup_service.list_backups()


@router.post("")
async def create_backup(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Create a new database backup."""
    try:
        result = backup_service.create_backup()
        logger.info("Manual backup created", user=current_user.email, filename=result["filename"])
        _audit_backup(db, "backup_create", current_user.email, result["filename"], "success")
        return {**result, "message": "Backup created successfully"}
    except RuntimeError as e:
        _audit_backup(db, "backup_create", current_user.email, "N/A", "failure", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{filename}/download")
async def download_backup(
    filename: str,
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Download a specific backup file."""
    try:
        path = backup_service.get_backup_path(filename)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file not found")

    return FileResponse(
        path=str(path),
        media_type="application/gzip",
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Endpoints — Super Admin only (delete, restore)
# ---------------------------------------------------------------------------

@router.delete("/{filename}")
async def delete_backup(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """Delete a specific backup file. Super Admin only."""
    try:
        deleted = backup_service.delete_backup(filename)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file not found")

    logger.info("Backup deleted by user", user=current_user.email, filename=filename)
    _audit_backup(db, "backup_delete", current_user.email, filename, "success")
    return {"message": f"Backup '{filename}' deleted successfully"}


@router.post("/{filename}/restore")
async def restore_backup(
    filename: str,
    body: RestoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """Restore database from a backup file. Super Admin only.

    Requires `{"confirm": true}` in request body.
    """
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Restore requires explicit confirmation (confirm=true)",
        )

    # Validate filename
    try:
        path = backup_service.get_backup_path(filename)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file not found")

    try:
        result = backup_service.restore_backup(filename)
        logger.info("Database restored", user=current_user.email, filename=filename)
        _audit_backup(db, "backup_restore", current_user.email, filename, "success",
                      f"Pre-restore snapshot: {result.get('pre_restore_backup', 'N/A')}")
        return result
    except (RuntimeError, FileNotFoundError) as e:
        _audit_backup(db, "backup_restore", current_user.email, filename, "failure", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
