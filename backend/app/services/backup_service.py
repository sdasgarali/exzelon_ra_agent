"""Database backup service — mysqldump + gzip with retention management."""
import re
import subprocess
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import structlog

from app.core.config import settings

logger = structlog.get_logger()

# Backup directory: backend/data/backups/
BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Filename pattern for validation (prevents path traversal)
FILENAME_PATTERN = re.compile(r"^exzelon_ra_agent_\d{8}_\d{6}\.sql\.gz$")


def _format_size(size_bytes: int) -> str:
    """Format byte count to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _parse_timestamp_from_filename(filename: str) -> Optional[datetime]:
    """Extract datetime from backup filename like exzelon_ra_agent_20260301_143000.sql.gz."""
    match = re.search(r"(\d{8})_(\d{6})", filename)
    if not match:
        return None
    try:
        return datetime.strptime(f"{match.group(1)}_{match.group(2)}", "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def create_backup() -> dict:
    """Create a full database backup using mysqldump + gzip.

    Returns dict with {filename, size_bytes, size_human, created_at}.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"exzelon_ra_agent_{timestamp}.sql.gz"
    backup_path = BACKUP_DIR / filename

    # Build mysqldump command
    cmd = [
        "mysqldump",
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        f"--host={settings.DB_HOST}",
        f"--port={settings.DB_PORT}",
        f"--user={settings.DB_USER}",
    ]
    if settings.DB_PASSWORD:
        cmd.append(f"--password={settings.DB_PASSWORD}")
    cmd.append(settings.DB_NAME)

    logger.info("Creating database backup", filename=filename)

    try:
        # Run mysqldump and capture output
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=300,  # 5 min timeout
        )

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            logger.error("mysqldump failed", returncode=result.returncode, stderr=stderr)
            raise RuntimeError(f"mysqldump failed (exit {result.returncode}): {stderr[:500]}")

        sql_data = result.stdout
        if not sql_data:
            raise RuntimeError("mysqldump produced empty output")

        # Compress with gzip
        with gzip.open(backup_path, "wb") as f:
            f.write(sql_data)

        size_bytes = backup_path.stat().st_size
        created_at = datetime.now().isoformat()

        logger.info("Backup created", filename=filename, size_bytes=size_bytes)

        return {
            "filename": filename,
            "size_bytes": size_bytes,
            "size_human": _format_size(size_bytes),
            "created_at": created_at,
        }

    except subprocess.TimeoutExpired:
        # Clean up partial file
        backup_path.unlink(missing_ok=True)
        raise RuntimeError("mysqldump timed out after 300 seconds")
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise


def list_backups() -> list[dict]:
    """List all backup files, sorted newest first."""
    backups = []
    for p in BACKUP_DIR.glob("exzelon_ra_agent_*.sql.gz"):
        if not FILENAME_PATTERN.match(p.name):
            continue
        ts = _parse_timestamp_from_filename(p.name)
        backups.append({
            "filename": p.name,
            "size_bytes": p.stat().st_size,
            "size_human": _format_size(p.stat().st_size),
            "created_at": ts.isoformat() if ts else p.stat().st_mtime,
        })
    backups.sort(key=lambda b: b["filename"], reverse=True)
    return backups


def get_backup_path(filename: str) -> Path:
    """Return the full path for a backup file after validating the filename."""
    if not FILENAME_PATTERN.match(filename):
        raise ValueError(f"Invalid backup filename: {filename}")
    path = BACKUP_DIR / filename
    # Extra safety: ensure resolved path is still inside BACKUP_DIR
    if not path.resolve().is_relative_to(BACKUP_DIR.resolve()):
        raise ValueError("Path traversal detected")
    return path


def delete_backup(filename: str) -> bool:
    """Delete a specific backup file. Returns True if deleted."""
    path = get_backup_path(filename)
    if not path.exists():
        return False
    path.unlink()
    logger.info("Backup deleted", filename=filename)
    return True


def cleanup_old_backups(retention_days: int) -> int:
    """Delete backups older than retention_days. Returns count of deleted files."""
    cutoff = datetime.now() - timedelta(days=retention_days)
    deleted = 0
    for p in BACKUP_DIR.glob("exzelon_ra_agent_*.sql.gz"):
        if not FILENAME_PATTERN.match(p.name):
            continue
        ts = _parse_timestamp_from_filename(p.name)
        if ts and ts < cutoff:
            p.unlink()
            deleted += 1
            logger.info("Old backup cleaned up", filename=p.name)
    return deleted
