"""Centralized tenant-aware settings resolver.

Resolution order (highest to lowest priority):
1. TenantSettings[tenant_id, key]   <- per-tenant override
2. Settings[key]                    <- global DB default
3. config.py / .env                 <- environment variable (not checked here)
4. Caller-supplied default          <- hardcoded fallback
"""
import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.settings import Settings
from app.db.models.tenant_settings import TenantSettings

logger = logging.getLogger(__name__)


def get_tenant_setting(
    db: Session,
    key: str,
    tenant_id: Optional[int] = None,
    default: Any = None,
) -> Any:
    """Get a setting value with 4-layer resolution.

    1. If tenant_id is provided, check tenant_settings first.
    2. Fall back to global settings table.
    3. Return caller default if nothing found.
    """
    # Layer 1: tenant override
    if tenant_id is not None:
        ts = (
            db.query(TenantSettings)
            .filter(
                TenantSettings.tenant_id == tenant_id,
                TenantSettings.key == key,
            )
            .first()
        )
        if ts and ts.value_json is not None:
            try:
                return json.loads(ts.value_json)
            except (json.JSONDecodeError, TypeError):
                return ts.value_json

    # Layer 2: global DB default
    gs = db.query(Settings).filter(Settings.key == key).first()
    if gs and gs.value_json is not None:
        try:
            return json.loads(gs.value_json)
        except (json.JSONDecodeError, TypeError):
            return gs.value_json

    # Layer 3/4: caller default
    return default


def get_tenant_setting_bool(
    db: Session,
    key: str,
    tenant_id: Optional[int] = None,
    default: bool = False,
) -> bool:
    """Convenience wrapper that coerces the result to bool."""
    val = get_tenant_setting(db, key, tenant_id=tenant_id, default=default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    try:
        return bool(val)
    except (TypeError, ValueError):
        return default


def set_tenant_setting(
    db: Session,
    key: str,
    value: Any,
    tenant_id: Optional[int] = None,
    updated_by: Optional[str] = None,
) -> None:
    """Write a setting value.

    - If tenant_id is provided: upsert into tenant_settings.
    - If tenant_id is None: upsert into global settings.
    """
    value_json = json.dumps(value)

    if tenant_id is not None:
        ts = (
            db.query(TenantSettings)
            .filter(
                TenantSettings.tenant_id == tenant_id,
                TenantSettings.key == key,
            )
            .first()
        )
        if ts:
            ts.value_json = value_json
            if updated_by:
                ts.updated_by = updated_by
        else:
            ts = TenantSettings(
                tenant_id=tenant_id,
                key=key,
                value_json=value_json,
                updated_by=updated_by,
            )
            db.add(ts)
    else:
        gs = db.query(Settings).filter(Settings.key == key).first()
        if gs:
            gs.value_json = value_json
            if updated_by:
                gs.updated_by = updated_by
        else:
            gs = Settings(
                key=key,
                value_json=value_json,
                type="string",
                description=f"Setting: {key}",
                updated_by=updated_by,
            )
            db.add(gs)

    db.flush()


def delete_tenant_setting(
    db: Session,
    key: str,
    tenant_id: int,
) -> bool:
    """Remove a tenant override so it reverts to global default.

    Returns True if a row was deleted, False if nothing existed.
    """
    count = (
        db.query(TenantSettings)
        .filter(
            TenantSettings.tenant_id == tenant_id,
            TenantSettings.key == key,
        )
        .delete()
    )
    db.flush()
    return count > 0


def get_tenant_overrides(
    db: Session,
    tenant_id: int,
) -> Dict[str, Any]:
    """Return dict of keys that the tenant has explicitly overridden."""
    rows = (
        db.query(TenantSettings)
        .filter(TenantSettings.tenant_id == tenant_id)
        .all()
    )
    result: Dict[str, Any] = {}
    for row in rows:
        try:
            result[row.key] = json.loads(row.value_json) if row.value_json is not None else None
        except (json.JSONDecodeError, TypeError):
            result[row.key] = row.value_json
    return result


def get_all_tenant_settings(
    db: Session,
    tenant_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Return merged dict of all settings (global + tenant overrides).

    Each value is the resolved value after applying tenant overrides.
    """
    # Start with global settings
    merged: Dict[str, Any] = {}
    for gs in db.query(Settings).all():
        try:
            merged[gs.key] = json.loads(gs.value_json) if gs.value_json is not None else None
        except (json.JSONDecodeError, TypeError):
            merged[gs.key] = gs.value_json

    # Overlay tenant overrides
    if tenant_id is not None:
        for ts in db.query(TenantSettings).filter(TenantSettings.tenant_id == tenant_id).all():
            try:
                merged[ts.key] = json.loads(ts.value_json) if ts.value_json is not None else None
            except (json.JSONDecodeError, TypeError):
                merged[ts.key] = ts.value_json

    return merged
