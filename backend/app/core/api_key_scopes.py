"""API-key scope enforcement.

API keys authenticate as their owner user, so RBAC, tenant isolation, plan
gates and credit gates already apply. Scopes narrow that further, per key:

- ``read``  — safe methods only (GET/HEAD/OPTIONS), plus a short list of
  POST endpoints that only compute or preview and never change data.
- ``write`` — everything except DELETE, and never account administration
  (users, roles, billing, tenants, auth, API keys, GDPR, backups).
- ``admin`` — everything the owner user may do.

API-key management itself is never reachable with an API key (other than
listing): a leaked key must not be able to mint a stronger one.
"""
import json
import re
from typing import Iterable, Optional, Tuple

VALID_SCOPES = ("read", "write", "admin")

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# POST endpoints that only read/compute — allowed for read-scoped keys.
# Matched as path suffixes under /api/v1.
_READ_ONLY_POST_SUFFIXES = (
    "/leads/ai-search",
    "/leads/database-search",
    "/leads/bulk/enrich/preview",
    "/leads/bulk/outreach/preview",
    "/enrollment-preview",
    "/campaigns/compare",
    "/spam-check",                       # /spam-check and /email-preview/spam-check
    "/suggest-reply",                    # /inbox/threads/{id}/suggest-reply
    "/ai-suggest-subjects",              # /campaigns/{id}/ai-suggest-subjects
    "/templates/score",
    "/templates/fixes",
    "/templates/apply-fixes",            # returns fixed text; the template is not saved
    "/leads/import/google-sheet/preview",
)

# Compute-only POSTs whose path has an id in the middle; matched against the full path.
_READ_ONLY_POST_PATTERNS = (
    re.compile(r"^/api/v1/templates/\d+/preview$"),
    # Not /saved-searches/{id}/execute yet: it saves nothing, but its natural-language
    # path searches every tenant's leads (no tenant_id passed). Add it once that is fixed.
)

# Account administration — off-limits to write-scoped keys.
_ADMIN_ONLY_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/users",
    "/api/v1/roles",
    "/api/v1/admin",
    "/api/v1/billing",
    "/api/v1/integrations/api-keys",
    "/api/v1/gdpr",
    "/api/v1/backups",
    "/api/v1/activity",
)

_KEY_MANAGEMENT_PREFIX = "/api/v1/integrations/api-keys"


def normalize_scopes(scopes: Optional[Iterable[str]]) -> set:
    """Return the set of recognised scopes. Unknown values are dropped."""
    if not scopes:
        return set()
    return {s.strip().lower() for s in scopes if isinstance(s, str)} & set(VALID_SCOPES)


def parse_scopes_json(raw: Optional[str]) -> list:
    """Decode ``api_keys.scopes_json``; anything malformed yields ``[]`` (= read-only)."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [s for s in value if isinstance(s, str)] if isinstance(value, list) else []


def _is_read_only_post(path: str) -> bool:
    return path.endswith(_READ_ONLY_POST_SUFFIXES) or any(p.match(path) for p in _READ_ONLY_POST_PATTERNS)


def check_scope(scopes: Optional[Iterable[str]], method: str, path: str) -> Tuple[bool, str]:
    """Decide whether a key with ``scopes`` may call ``method path``.

    Returns ``(allowed, reason)``; ``reason`` is a user-facing message when denied.
    A key with no recognised scope is treated as read-only (least privilege).
    """
    method = (method or "").upper()
    path = (path or "").rstrip("/") or "/"
    granted = normalize_scopes(scopes) or {"read"}

    if method in _SAFE_METHODS:
        return True, ""

    if path.startswith(_KEY_MANAGEMENT_PREFIX):
        return False, "API keys cannot create or revoke API keys. Sign in to NeuraLeads to manage keys."

    if "admin" in granted:
        return True, ""

    if "write" in granted:
        if method == "DELETE":
            return False, "This API key has 'write' scope, which cannot delete data. Use an 'admin' key."
        if path.startswith(_ADMIN_ONLY_PREFIXES):
            return False, "This API key has 'write' scope, which cannot manage account settings, users, roles or billing."
        return True, ""

    # read-only
    if method == "POST" and _is_read_only_post(path):
        return True, ""
    return False, "This API key is read-only. Create a key with 'write' scope to make changes."
