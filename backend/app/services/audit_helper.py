"""Shared audit logging helpers."""
import json
from fastapi import Request
from sqlalchemy.orm import Session
from app.db.models.audit_log import AuditLog


def write_audit_log(
    db: Session,
    *,
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    action: str,
    changed_by: str,
    changed_fields: dict = None,
    notes: str = None,
):
    """Write an audit log entry."""
    audit = AuditLog(
        tenant_id=tenant_id or 0,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        changed_by=changed_by,
        changed_fields=json.dumps(changed_fields) if changed_fields else None,
        notes=notes,
    )
    db.add(audit)


def get_client_ip(request: Request) -> str:
    """Extract client IP handling X-Forwarded-For from nginx proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"
