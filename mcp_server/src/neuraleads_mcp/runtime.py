"""Per-process runtime shared by all tools: settings, REST client, auth, output shaping."""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from neuraleads_mcp.client import NeuraLeadsClient, NeuraLeadsError
from neuraleads_mcp.config import Settings

logger = logging.getLogger("neuraleads_mcp")

# Tool annotation presets (hints for the client UI and the model).
READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
WRITE_IDEMPOTENT = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
# Reaches the outside world: sends email, calls paid data providers, etc.
EXTERNAL = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True)

# Keys whose values must never reach the model, whatever the backend returns.
_SECRET_KEY = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|refresh|credential|smtp_pass|imap_pass|oauth)",
    re.IGNORECASE,
)
# Fields that are *about* secrets but are safe booleans/labels.
_SECRET_KEY_ALLOW = re.compile(r"(_set|_configured|_present|_connected|_enabled|_status|_type|_provider|_expires_at|key_prefix)$|^(has|is)_",
                               re.IGNORECASE)

MAX_LIST_ITEMS = 100


def sanitize(value: Any, _depth: int = 0) -> Any:
    """Recursively remove credential-like fields (defence in depth)."""
    if _depth > 12:
        return value
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and _SECRET_KEY.search(k) and not _SECRET_KEY_ALLOW.search(k):
                continue
            out[k] = sanitize(v, _depth + 1)
        return out
    if isinstance(value, list):
        return [sanitize(v, _depth + 1) for v in value]
    return value


def clamp_limit(limit: Optional[int], default: int = 25) -> int:
    if limit is None:
        return default
    return max(1, min(int(limit), MAX_LIST_ITEMS))


class Runtime:
    def __init__(self, settings: Settings, client: Optional[NeuraLeadsClient] = None, *, hosted: bool = False):
        self.settings = settings
        self.hosted = hosted
        self.client = client or NeuraLeadsClient(
            settings.api_url, timeout=settings.timeout_seconds, max_retries=settings.max_retries)

    # ── auth ────────────────────────────────────────────────────────────
    def api_key_for(self, ctx: Optional[Context]) -> str:
        """The caller's key: from request headers (hosted) or the environment (local).

        In hosted mode a server-wide key is never used, so one user can never act
        with another user's credentials.
        """
        headers: Mapping[str, str] = {}
        if ctx is not None:
            try:
                headers = ctx.headers or {}
            except ValueError:
                headers = {}
        lower = {k.lower(): v for k, v in headers.items()}
        auth = lower.get("authorization", "")
        if auth.lower().startswith("bearer ") and auth[7:].strip():
            return auth[7:].strip()
        if lower.get("x-api-key"):
            return lower["x-api-key"].strip()
        if self.hosted:
            raise ToolError("Missing API key. Send it as 'Authorization: Bearer <key>' when connecting "
                            "to the NeuraLeads MCP endpoint.")
        if not self.settings.api_key:
            raise ToolError("NEURALEADS_API_KEY is not set. Create a key in NeuraLeads → Settings → "
                            "API Keys & MCP and add it to this MCP server's environment.")
        return self.settings.api_key

    # ── calls ───────────────────────────────────────────────────────────
    async def call(self, ctx: Optional[Context], method: str, path: str, *,
                   params: Optional[Mapping[str, Any]] = None, json: Any = None) -> Any:
        key = self.api_key_for(ctx)
        try:
            result = await self.client.request(key, method, path, params=params, json=json)
        except NeuraLeadsError as exc:
            raise ToolError(str(exc)) from exc
        return sanitize(result)

    async def get(self, ctx, path, **params):
        return await self.call(ctx, "GET", path, params=params)

    async def post(self, ctx, path, json=None, **params):
        return await self.call(ctx, "POST", path, params=params, json=json)

    async def put(self, ctx, path, json=None, **params):
        return await self.call(ctx, "PUT", path, params=params, json=json)

    async def delete(self, ctx, path, json=None, **params):
        return await self.call(ctx, "DELETE", path, params=params, json=json)


def confirmation_required(action: str, details: Mapping[str, Any], preview: Any = None) -> dict:
    """Result returned by high-impact tools when called without ``confirm=True``."""
    out = {
        "status": "confirmation_required",
        "action": action,
        "details": dict(details),
        "next_step": "Nothing was changed. Show this to the user and, once they agree, "
                     "call the same tool again with confirm=true.",
    }
    if preview is not None:
        out["preview"] = preview
    return out


def pick(item: Any, fields: tuple) -> Any:
    """Keep only ``fields`` of a dict (missing ones skipped) to save the model's context."""
    if not isinstance(item, dict):
        return item
    return {f: item[f] for f in fields if f in item}


def pick_list(payload: Any, fields: tuple, list_keys: tuple = ("items", "data", "results")) -> Any:
    """Slim the item list inside a paginated payload (or a bare list), keeping pagination keys."""
    if isinstance(payload, list):
        return [pick(i, fields) for i in payload]
    if isinstance(payload, dict):
        for key in list_keys:
            if isinstance(payload.get(key), list):
                return {**payload, key: [pick(i, fields) for i in payload[key]]}
    return payload
