"""Database backup management endpoints — super_admin only."""
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps.auth import get_current_active_user
from app.db.models.user import User, UserRole
from app.services import backup_service

logger = structlog.get_logger()

router = APIRouter(prefix="/backups", tags=["Backups"])


def _require_super_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Only super_admin can access backup endpoints."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can manage backups",
        )
    return current_user


@router.get("")
async def list_backups(current_user: User = Depends(_require_super_admin)):
    """List all available database backups."""
    return backup_service.list_backups()


@router.post("")
async def create_backup(current_user: User = Depends(_require_super_admin)):
    """Create a new database backup."""
    try:
        result = backup_service.create_backup()
        logger.info("Manual backup created", user=current_user.email, filename=result["filename"])
        return {**result, "message": "Backup created successfully"}
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{filename}/download")
async def download_backup(
    filename: str,
    current_user: User = Depends(_require_super_admin),
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


@router.delete("/{filename}")
async def delete_backup(
    filename: str,
    current_user: User = Depends(_require_super_admin),
):
    """Delete a specific backup file."""
    try:
        deleted = backup_service.delete_backup(filename)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file not found")

    logger.info("Backup deleted by user", user=current_user.email, filename=filename)
    return {"message": f"Backup '{filename}' deleted successfully"}
