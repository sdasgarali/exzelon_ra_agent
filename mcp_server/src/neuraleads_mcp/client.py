"""Async REST client for the NeuraLeads API (``/api/v1``).

Everything the MCP tools do goes through here, authenticated with the caller's
API key. The backend enforces RBAC, tenant isolation, plan features, credits,
send limits and key scopes, so this client never re-implements those rules;
it only turns their failures into messages an AI model can act on.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping, Optional

import httpx

logger = logging.getLogger("neuraleads_mcp.client")

_SAFE_TO_RETRY = {"GET", "HEAD", "OPTIONS"}
_RETRY_STATUSES = {502, 503, 504}


class NeuraLeadsError(Exception):
    """A failed API call, with a message written for the model and the user."""

    def __init__(self, message: str, status: Optional[int] = None, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


def _detail_text(detail: Any) -> str:
    if detail is None:
        return ""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):  # FastAPI 422 validation errors
        parts = []
        for err in detail[:5]:
            if isinstance(err, dict):
                loc = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query"))
                parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
            else:
                parts.append(str(err))
        return "; ".join(parts)
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("detail") or detail)
    return str(detail)


def explain_error(status: int, detail: Any) -> str:
    """Map an HTTP failure to an actionable message."""
    text = _detail_text(detail)
    if status == 401:
        return ("NeuraLeads rejected the API key (missing, invalid, revoked or expired). "
                "Create a new key in NeuraLeads → Settings → API Keys & MCP.")
    if status == 402:
        code = detail.get("code") if isinstance(detail, dict) else None
        if code == "feature_not_in_plan":
            plan = detail.get("required_plan")
            return f"This feature is not included in the workspace's plan{f' (needs {plan})' if plan else ''}. {text}".strip()
        return f"Not enough credits or send quota for this action. {text}".strip()
    if status == 403:
        return f"Permission denied. {text}".strip()
    if status == 404:
        return f"Not found. {text}".strip()
    if status == 409:
        return f"Conflict. {text}".strip()
    if status in (400, 422):
        return f"Invalid request. {text}".strip()
    if status == 429:
        return f"Rate limited by NeuraLeads; wait a moment and try again. {text}".strip()
    if status >= 500:
        return f"NeuraLeads had a server error ({status}). Try again shortly. {text}".strip()
    return f"Request failed ({status}). {text}".strip()


class NeuraLeadsClient:
    """Thin wrapper around a shared ``httpx.AsyncClient``.

    The API key is passed per call so that one process can serve many users
    in hosted (HTTP) mode without ever storing their keys.
    """

    def __init__(self, base_url: str, timeout: float = 60.0, max_retries: int = 2,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
            transport=transport,
            headers={"User-Agent": "neuraleads-mcp/0.1", "Accept": "application/json"},
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(self, api_key: str, method: str, path: str, *,
                      params: Optional[Mapping[str, Any]] = None,
                      json: Any = None, tenant_id: Optional[int] = None) -> Any:
        """Call the API as ``api_key``. ``tenant_id`` is sent as ``X-Tenant-ID``: it selects the
        workspace for super-admin keys and is ignored by the backend for everyone else."""
        if not api_key:
            raise NeuraLeadsError(explain_error(401, None), status=401)
        method = method.upper()
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {"X-API-Key": api_key}
        if tenant_id is not None:
            headers["X-Tenant-ID"] = str(int(tenant_id))

        # Only idempotent reads are retried: a POST that sends email or spends
        # credits must never run twice because a response got lost.
        attempts = 1 + (self._max_retries if method in _SAFE_TO_RETRY else 0)
        last_exc: Optional[Exception] = None
        for attempt in range(attempts):
            try:
                resp = await self._http.request(method, path, params=clean_params, json=json, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning("NeuraLeads %s %s transport error (attempt %d/%d): %s",
                               method, path, attempt + 1, attempts, type(exc).__name__)
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.5 * 2 ** attempt)
                    continue
                raise NeuraLeadsError(
                    f"Could not reach NeuraLeads ({type(exc).__name__}). "
                    + ("" if method in _SAFE_TO_RETRY else
                       "The action may or may not have run — check before retrying."),
                ) from exc

            if resp.status_code in _RETRY_STATUSES and attempt + 1 < attempts:
                await asyncio.sleep(0.5 * 2 ** attempt)
                continue
            return self._handle(resp, method, path)
        raise NeuraLeadsError(f"Could not reach NeuraLeads: {last_exc}")  # pragma: no cover

    @staticmethod
    def _handle(resp: httpx.Response, method: str, path: str) -> Any:
        if resp.status_code == 204 or not resp.content:
            if resp.is_success:
                return {"ok": True}
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.is_success:
            return body if body is not None else {"ok": True, "content": resp.text[:2000]}
        detail = body.get("detail", body) if isinstance(body, dict) else (resp.text[:500] or None)
        logger.info("NeuraLeads %s %s -> %s", method, path, resp.status_code)
        raise NeuraLeadsError(explain_error(resp.status_code, detail), status=resp.status_code, detail=detail)
