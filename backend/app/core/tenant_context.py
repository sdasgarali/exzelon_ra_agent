"""Tenant context management using ContextVars.

Provides thread-safe, async-safe tenant context that is automatically
set by the auth dependency and consumed by tenant_query().
"""
from contextvars import ContextVar

_current_tenant_id: ContextVar[int | None] = ContextVar("current_tenant_id", default=None)
_is_super_admin: ContextVar[bool] = ContextVar("is_super_admin", default=False)
_is_global_super_admin: ContextVar[bool] = ContextVar("is_global_super_admin", default=False)


def get_current_tenant_id() -> int | None:
    """Get the current tenant_id from context."""
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: int | None) -> None:
    """Set the current tenant_id in context."""
    _current_tenant_id.set(tenant_id)


def get_is_super_admin() -> bool:
    """Check if the current user is a super admin (either GSA or TSA)."""
    return _is_super_admin.get()


def set_is_super_admin(val: bool) -> None:
    """Set whether the current user is a super admin."""
    _is_super_admin.set(val)


def get_is_global_super_admin() -> bool:
    """Check if the current user is a Global Super Admin (SA + master tenant)."""
    return _is_global_super_admin.get()


def set_is_global_super_admin(val: bool) -> None:
    """Set whether the current user is a Global Super Admin."""
    _is_global_super_admin.set(val)
