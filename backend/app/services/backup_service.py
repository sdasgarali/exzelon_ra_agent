"""Database backup service — mysqldump + gzip with retention management."""
import os
import re
import subprocess
import gzip
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

# Integrity sanity floor for a dump (B3). Prod dumps are ~19 MB gzipped; anything
# under 1 MB means mysqldump stopped early or dumped an empty/wrong schema.
MIN_BACKUP_BYTES = 1024 * 1024
# Off-site objects older than this are deleted after each successful upload (B2).
OFFSITE_RETENTION_DAYS = 30


class BackupIntegrityError(RuntimeError):
    """A dump was written but failed verify_backup(); already alerted."""


def _mysql_env() -> dict:
    """Build a subprocess env dict with MYSQL_PWD set (avoids password in CLI args)."""
    env = os.environ.copy()
    if settings.DB_PASSWORD:
        env["MYSQL_PWD"] = settings.DB_PASSWORD
    return env


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


def _sha256_file(path: Path) -> str:
    """SHA-256 hex digest of a file (streamed)."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _upload_offsite(backup_path: Path, checksum: str) -> dict:
    """Upload a backup to S3 (optionally Fernet-encrypted), keyed with its checksum.

    Returns a status dict. Gated on ``BACKUP_S3_BUCKET`` — a no-op when unset so
    deployments without offsite storage keep working. A failure is logged at
    warning with ``backup_offsite_failed`` (wire an alert to that event). (ELR-018)
    """
    if not settings.BACKUP_S3_BUCKET:
        return {"status": "disabled"}
    try:
        data = backup_path.read_bytes()
        key_suffix = ""
        if settings.BACKUP_ENCRYPT and settings.ENCRYPTION_KEY:
            from cryptography.fernet import Fernet
            data = Fernet(settings.ENCRYPTION_KEY.encode()).encrypt(data)
            key_suffix = ".enc"

        key = f"{_offsite_prefix()}{backup_path.name}{key_suffix}"
        s3 = _s3_client()
        s3.put_object(
            Bucket=settings.BACKUP_S3_BUCKET,
            Key=key,
            Body=data,
            Metadata={"sha256": checksum, "encrypted": str(bool(key_suffix))},
        )
        logger.info("backup_offsite_uploaded", bucket=settings.BACKUP_S3_BUCKET,
                    key=key, encrypted=bool(key_suffix))
        pruned = _prune_offsite(s3)
        return {"status": "uploaded", "bucket": settings.BACKUP_S3_BUCKET,
                "key": key, "encrypted": bool(key_suffix), "pruned": pruned}
    except Exception as e:
        # Loud + alertable — an offsite backup that silently stops uploading is a
        # DR gap you only discover when you need to restore.
        logger.warning("backup_offsite_failed", error=str(e), filename=backup_path.name)
        from app.services.alerting import send_alert
        send_alert(
            "backup_offsite_failed",
            "Off-site backup upload failed",
            f"File: {backup_path.name}\nBucket: {settings.BACKUP_S3_BUCKET}\n"
            f"Endpoint: {settings.BACKUP_S3_ENDPOINT_URL or '(AWS default)'}\n"
            f"Error: {type(e).__name__}: {str(e)[:1000]}\n\n"
            "The local backup is intact; only the off-site copy is missing.",
        )
        return {"status": "failed", "error": str(e)}


def _offsite_prefix() -> str:
    prefix = (settings.BACKUP_S3_PREFIX or "").strip("/")
    return f"{prefix}/" if prefix else ""


def _region_from_endpoint(endpoint_url: str) -> Optional[str]:
    """Backblaze B2 / Wasabi-style endpoints embed the region:
    https://s3.us-west-004.backblazeb2.com -> us-west-004."""
    m = re.match(r"^https?://s3[.-]([a-z0-9-]+)\.(?:backblazeb2\.com|wasabisys\.com)", endpoint_url or "")
    return m.group(1) if m else None


def _s3_client():
    """boto3 S3 client that also works against S3-compatible stores (Backblaze B2).

    Credentials come from the standard boto3 chain — ``AWS_ACCESS_KEY_ID`` /
    ``AWS_SECRET_ACCESS_KEY`` (in the .env as ``PROD_AWS_*``; env_loader strips the
    prefix). For B2 the SigV4 region must match the endpoint, so it is derived from
    the endpoint host unless ``AWS_DEFAULT_REGION`` is set. boto3 >= 1.36 sends
    CRC32 checksum headers by default that several S3-compatible stores reject, so
    checksums are limited to "when_required" on a custom endpoint.
    """
    import boto3
    from botocore.config import Config

    kwargs: dict = {}
    endpoint = settings.BACKUP_S3_ENDPOINT_URL
    if endpoint:
        kwargs["endpoint_url"] = endpoint
        region = os.environ.get("AWS_DEFAULT_REGION") or _region_from_endpoint(endpoint)
        if region:
            kwargs["region_name"] = region
        try:
            kwargs["config"] = Config(
                signature_version="s3v4",
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            )
        except TypeError:  # botocore < 1.36 has neither option (nor the problem)
            kwargs["config"] = Config(signature_version="s3v4")
    return boto3.client("s3", **kwargs)


def _prune_offsite(s3, retention_days: int = OFFSITE_RETENTION_DAYS) -> int:
    """Delete off-site backup objects older than ``retention_days``. Best-effort —
    a prune failure never fails the upload. Only touches objects under the backup
    prefix whose name is a backup file. Returns the number deleted."""
    from datetime import timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    prefix = _offsite_prefix()
    deleted = 0
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.BACKUP_S3_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                name = obj["Key"][len(prefix):]
                if name.endswith(".enc"):
                    name = name[:-4]
                if not FILENAME_PATTERN.match(name):
                    continue
                if obj["LastModified"] < cutoff:
                    s3.delete_object(Bucket=settings.BACKUP_S3_BUCKET, Key=obj["Key"])
                    deleted += 1
                    logger.info("backup_offsite_pruned", key=obj["Key"])
    except Exception as e:
        logger.warning("backup_offsite_prune_failed", error=str(e))
    return deleted


def verify_backup(path: Path, min_bytes: int = MIN_BACKUP_BYTES) -> tuple[bool, str]:
    """Integrity check for a gzipped mysqldump (B3).

    Streams the whole file through gzip (equivalent to ``gzip -t`` — a truncated or
    corrupt stream raises), and checks: file size >= ``min_bytes``, at least one
    ``CREATE TABLE``, and mysqldump's trailing ``-- Dump completed`` marker (absent
    when the dump was cut short). Returns ``(ok, reason)``.
    """
    try:
        size = path.stat().st_size
    except OSError as e:
        return False, f"cannot stat backup: {e}"
    if size < min_bytes:
        return False, f"backup too small: {size} bytes (< {min_bytes})"
    has_create = False
    tail = b""
    try:
        with gzip.open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                window = tail + chunk
                if not has_create and b"CREATE TABLE" in window:
                    has_create = True
                tail = window[-4096:]
    except Exception as e:
        return False, f"gzip stream invalid: {type(e).__name__}: {e}"
    if not has_create:
        return False, "no CREATE TABLE statement in dump"
    if b"-- Dump completed" not in tail:
        return False, "dump is missing the '-- Dump completed' trailer (truncated?)"
    return True, "ok"


def effective_retention_days(setting_value) -> int:
    """Local retention = max(admin setting ``backup_retention_days``,
    ``BACKUP_LOCAL_RETENTION_DAYS``). The config value is a floor so a low UI
    setting (default 3) can never shrink the DR window below it (B1)."""
    try:
        configured = int(setting_value)
    except (TypeError, ValueError):
        configured = 0
    return max(configured, int(settings.BACKUP_LOCAL_RETENTION_DAYS or 0), 1)


def latest_backup_time() -> Optional[datetime]:
    """Local time of the newest valid local backup (from its filename), or None."""
    newest = None
    for p in BACKUP_DIR.glob("exzelon_ra_agent_*.sql.gz"):
        if not FILENAME_PATTERN.match(p.name):
            continue
        ts = _parse_timestamp_from_filename(p.name)
        if ts and (newest is None or ts > newest):
            newest = ts
    return newest


def create_backup() -> dict:
    """Create a full database backup using mysqldump + gzip.

    Returns dict with {filename, size_bytes, size_human, created_at}.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"exzelon_ra_agent_{timestamp}.sql.gz"
    backup_path = BACKUP_DIR / filename

    # Build mysqldump command (password via env var, not CLI arg)
    cmd = [
        "mysqldump",
        "--single-transaction",
        # ra_user has no PROCESS privilege; MySQL 8.0.21+ mysqldump aborts on the
        # tablespace query without this flag (same flag the pre-deploy dump uses).
        "--no-tablespaces",
        "--routines",
        "--triggers",
        "--events",
        f"--host={settings.DB_HOST}",
        f"--port={settings.DB_PORT}",
        f"--user={settings.DB_USER}",
        settings.DB_NAME,
    ]
    env = _mysql_env()

    logger.info("Creating database backup", filename=filename)

    try:
        # Run mysqldump and capture output
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=300,  # 5 min timeout
            env=env,
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

        # Integrity check (B3). A bad dump is renamed out of the backup set so it
        # neither counts as "latest successful backup" for /ready nor gets restored.
        ok, reason = verify_backup(backup_path)
        if not ok:
            bad = backup_path.with_name(backup_path.name + ".failed")
            try:
                os.replace(backup_path, bad)
            except OSError:
                pass
            logger.error("backup_integrity_failed", filename=filename, reason=reason,
                         size_bytes=size_bytes)
            from app.services.alerting import send_alert
            send_alert(
                "backup_failed",
                "Database backup failed its integrity check",
                f"File: {filename} (kept as {bad.name})\nSize: {size_bytes} bytes\n"
                f"Reason: {reason}",
            )
            raise BackupIntegrityError(f"Backup integrity check failed: {reason}")

        # Integrity checksum (detects silent corruption / partial writes).
        checksum = _sha256_file(backup_path)

        logger.info("Backup created", filename=filename, size_bytes=size_bytes, sha256=checksum)

        # Offsite copy (disaster recovery) — a local-only backup on the same VPS
        # is lost with the VPS. Best-effort: a failure is logged loudly (alertable)
        # but does not fail the local backup. (ELR-018)
        offsite = _upload_offsite(backup_path, checksum)

        return {
            "filename": filename,
            "size_bytes": size_bytes,
            "size_human": _format_size(size_bytes),
            "created_at": created_at,
            "sha256": checksum,
            "offsite": offsite,
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


def restore_backup(filename: str) -> dict:
    """Restore database from a backup file.

    1. Validates filename
    2. Creates a pre-restore snapshot (best-effort)
    3. Decompresses .sql.gz and pipes SQL to mysql CLI
    Returns dict with {success, filename, pre_restore_backup, message, details}.
    """
    path = get_backup_path(filename)
    if not path.exists():
        raise FileNotFoundError(f"Backup file not found: {filename}")

    # Pre-restore snapshot (best-effort)
    pre_restore_backup = None
    try:
        snapshot = create_backup()
        pre_restore_backup = snapshot["filename"]
        logger.info("Pre-restore snapshot created", filename=pre_restore_backup)
    except Exception as e:
        logger.warning("Pre-restore snapshot failed (continuing)", error=str(e))

    # Decompress
    logger.info("Restoring database from backup", filename=filename)
    try:
        with gzip.open(path, "rb") as f:
            sql_data = f.read()
    except Exception as e:
        raise RuntimeError(f"Failed to decompress backup: {e}")

    if not sql_data:
        raise RuntimeError("Backup file is empty after decompression")

    # Build mysql command (password via env var)
    cmd = [
        "mysql",
        f"--host={settings.DB_HOST}",
        f"--port={settings.DB_PORT}",
        f"--user={settings.DB_USER}",
        settings.DB_NAME,
    ]
    env = _mysql_env()

    try:
        result = subprocess.run(
            cmd,
            input=sql_data,
            capture_output=True,
            timeout=600,  # 10 min timeout for restore
            env=env,
        )

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            logger.error("mysql restore failed", returncode=result.returncode, stderr=stderr)
            raise RuntimeError(f"mysql restore failed (exit {result.returncode}): {stderr[:500]}")

        logger.info("Database restored successfully", filename=filename)
        return {
            "success": True,
            "filename": filename,
            "pre_restore_backup": pre_restore_backup,
            "message": "Database restored successfully",
        }

    except subprocess.TimeoutExpired:
        raise RuntimeError("mysql restore timed out after 600 seconds")


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
    # Dumps that failed the integrity check are kept for inspection, then aged out.
    for p in BACKUP_DIR.glob("exzelon_ra_agent_*.sql.gz.failed"):
        ts = _parse_timestamp_from_filename(p.name)
        if ts and ts < cutoff:
            p.unlink(missing_ok=True)
            deleted += 1
            logger.info("Old failed backup cleaned up", filename=p.name)
    return deleted
