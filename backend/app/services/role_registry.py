"""Role registry — built-in + custom (settings-backed, per-tenant) RBAC roles.

Built-in roles (``super_admin``, ``admin``, ``bdm``, ``recruiter``) are immutable
keys defined in code. Their display label/description may be overridden per-tenant
via the ``role_label_overrides`` setting. Custom roles are stored per-tenant in the
``custom_roles`` setting and MUST declare a ``base_role`` (one of admin/bdm/recruiter)
so coarse ``require_role`` checks and nav can resolve them to a built-in for
enforcement, while the fine-grained ``role_permissions`` matrix can further restrict.
"""
import re
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.settings_resolver import get_tenant_setting, set_tenant_setting
from app.db.models.user import User

CUSTOM_ROLES_KEY = "custom_roles"
LABEL_OVERRIDES_KEY = "role_label_overrides"

# Built-in roles (base_role == own key). Order is display order.
BUILTIN_ROLES: List[dict] = [
    {"key": "super_admin", "label": "Super Admin",
     "description": "Full system access. Cannot be restricted.",
     "base_role": "super_admin", "builtin": True, "static": True},
    {"key": "admin", "label": "Admin",
     "description": "Manage operations, users, and settings.",
     "base_role": "admin", "builtin": True},
    {"key": "bdm", "label": "BDM",
     "description": "Business Development Manager — day-to-day lead management and outreach.",
     "base_role": "bdm", "builtin": True},
    {"key": "recruiter", "label": "Recruiter",
     "description": "Read-only access to data.",
     "base_role": "recruiter", "builtin": True},
]
BUILTIN_KEYS = {r["key"] for r in BUILTIN_ROLES}
# super_admin is never a valid base for a custom role (would bypass all checks).
VALID_BASE_ROLES = {"admin", "bdm", "recruiter"}
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class RoleError(ValueError):
    """Raised for invalid role-registry operations (maps to HTTP 400/409)."""


# ─── Read ────────────────────────────────────────────────────────────────────

def _load_custom(db: Session, tenant_id: Optional[int]) -> List[dict]:
    raw = get_tenant_setting(db, CUSTOM_ROLES_KEY, tenant_id=tenant_id, default=None)
    return list(raw) if isinstance(raw, list) else []


def _load_overrides(db: Session, tenant_id: Optional[int]) -> dict:
    raw = get_tenant_setting(db, LABEL_OVERRIDES_KEY, tenant_id=tenant_id, default=None)
    return dict(raw) if isinstance(raw, dict) else {}


def _shape_custom(r: dict) -> dict:
    base = r.get("base_role")
    if base not in VALID_BASE_ROLES:
        base = "recruiter"
    return {
        "key": r.get("key"),
        "label": r.get("label") or r.get("key"),
        "description": r.get("description", ""),
        "base_role": base,
        "builtin": False,
    }


def list_roles(db: Session, tenant_id: Optional[int]) -> List[dict]:
    """Return built-in (with any per-tenant label overrides) + custom roles."""
    overrides = _load_overrides(db, tenant_id)
    result: List[dict] = []
    for r in BUILTIN_ROLES:
        merged = dict(r)
        ov = overrides.get(r["key"])
        if isinstance(ov, dict):
            if ov.get("label"):
                merged["label"] = ov["label"]
            if ov.get("description") is not None:
                merged["description"] = ov["description"]
        result.append(merged)
    for r in _load_custom(db, tenant_id):
        if r.get("key"):
            result.append(_shape_custom(r))
    return result


def get_role(db: Session, tenant_id: Optional[int], key: str) -> Optional[dict]:
    return next((r for r in list_roles(db, tenant_id) if r["key"] == key), None)


def resolve_base_role(db: Session, tenant_id: Optional[int], key: str) -> str:
    """Resolve any role key to a built-in base role for coarse checks.

    Built-in keys map to themselves. Unknown/custom keys resolve to their declared
    ``base_role`` (default ``recruiter`` — the least-privileged built-in).
    """
    if key in BUILTIN_KEYS:
        return key
    for r in _load_custom(db, tenant_id):
        if r.get("key") == key:
            base = r.get("base_role")
            return base if base in VALID_BASE_ROLES else "recruiter"
    return "recruiter"


def is_builtin(key: str) -> bool:
    return key in BUILTIN_KEYS


def users_with_role(db: Session, tenant_id: Optional[int], key: str) -> int:
    """Count users currently assigned this role key within the tenant."""
    q = db.query(User).filter(User.role == key)
    if tenant_id is not None:
        q = q.filter(User.tenant_id == tenant_id)
    return q.count()


# ─── Write ───────────────────────────────────────────────────────────────────

def create_role(db: Session, tenant_id: Optional[int], *, key: str, label: str,
                description: str = "", base_role: str = "recruiter",
                updated_by: Optional[str] = None) -> dict:
    key = (key or "").strip().lower()
    label = (label or "").strip()
    if not KEY_RE.match(key):
        raise RoleError("Role key must be lowercase letters/numbers/underscore, 2-40 chars, starting with a letter.")
    if key in BUILTIN_KEYS:
        raise RoleError(f"'{key}' is a reserved built-in role.")
    if not label:
        raise RoleError("Label is required.")
    if base_role not in VALID_BASE_ROLES:
        raise RoleError(f"base_role must be one of {sorted(VALID_BASE_ROLES)}.")
    custom = _load_custom(db, tenant_id)
    if any(r.get("key") == key for r in custom):
        raise RoleError(f"A custom role '{key}' already exists.")
    custom.append({"key": key, "label": label, "description": description, "base_role": base_role})
    set_tenant_setting(db, CUSTOM_ROLES_KEY, custom, tenant_id=tenant_id, updated_by=updated_by)
    _seed_matrix_row(db, tenant_id, key, base_role, updated_by)
    return _shape_custom(custom[-1])


def update_role(db: Session, tenant_id: Optional[int], key: str, *,
                label: Optional[str] = None, description: Optional[str] = None,
                base_role: Optional[str] = None, updated_by: Optional[str] = None) -> dict:
    if key in BUILTIN_KEYS:
        # Built-ins: only label/description are editable (key + base immutable).
        if base_role is not None and base_role != key:
            raise RoleError("Cannot change the base role of a built-in role.")
        overrides = _load_overrides(db, tenant_id)
        ov = dict(overrides.get(key, {}))
        if label is not None:
            if not label.strip():
                raise RoleError("Label is required.")
            ov["label"] = label.strip()
        if description is not None:
            ov["description"] = description
        overrides[key] = ov
        set_tenant_setting(db, LABEL_OVERRIDES_KEY, overrides, tenant_id=tenant_id, updated_by=updated_by)
        return get_role(db, tenant_id, key)

    custom = _load_custom(db, tenant_id)
    row = next((r for r in custom if r.get("key") == key), None)
    if row is None:
        raise RoleError(f"Role '{key}' not found.")
    if label is not None:
        if not label.strip():
            raise RoleError("Label is required.")
        row["label"] = label.strip()
    if description is not None:
        row["description"] = description
    if base_role is not None:
        if base_role not in VALID_BASE_ROLES:
            raise RoleError(f"base_role must be one of {sorted(VALID_BASE_ROLES)}.")
        row["base_role"] = base_role
    set_tenant_setting(db, CUSTOM_ROLES_KEY, custom, tenant_id=tenant_id, updated_by=updated_by)
    return _shape_custom(row)


def delete_role(db: Session, tenant_id: Optional[int], key: str,
                updated_by: Optional[str] = None) -> None:
    if key in BUILTIN_KEYS:
        raise RoleError("Built-in roles cannot be deleted.")
    custom = _load_custom(db, tenant_id)
    if not any(r.get("key") == key for r in custom):
        raise RoleError(f"Role '{key}' not found.")
    in_use = users_with_role(db, tenant_id, key)
    if in_use:
        raise RoleError(f"Cannot delete: {in_use} user(s) are assigned this role. Reassign them first.")
    custom = [r for r in custom if r.get("key") != key]
    set_tenant_setting(db, CUSTOM_ROLES_KEY, custom, tenant_id=tenant_id, updated_by=updated_by)
    _remove_matrix_row(db, tenant_id, key, updated_by)


# ─── Permission-matrix helpers ───────────────────────────────────────────────

def _seed_matrix_row(db: Session, tenant_id: Optional[int], key: str, base_role: str,
                     updated_by: Optional[str]) -> None:
    """Copy the base_role's permission-matrix row onto the new custom role so it
    is immediately enforceable (admin can then refine it on the Permissions tab)."""
    matrix = get_tenant_setting(db, "role_permissions", tenant_id=tenant_id, default=None)
    if not isinstance(matrix, dict):
        return
    base_cfg = matrix.get(base_role)
    if base_cfg is not None and key not in matrix:
        import copy
        matrix[key] = copy.deepcopy(base_cfg)
        set_tenant_setting(db, "role_permissions", matrix, tenant_id=tenant_id, updated_by=updated_by)


def _remove_matrix_row(db: Session, tenant_id: Optional[int], key: str,
                       updated_by: Optional[str]) -> None:
    matrix = get_tenant_setting(db, "role_permissions", tenant_id=tenant_id, default=None)
    if isinstance(matrix, dict) and key in matrix:
        matrix.pop(key, None)
        set_tenant_setting(db, "role_permissions", matrix, tenant_id=tenant_id, updated_by=updated_by)
