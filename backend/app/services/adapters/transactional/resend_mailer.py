"""Resend transactional mail adapter.

Uses the REST API over `httpx` (already a dependency) rather than the `resend` SDK —
one POST against a stable endpoint does not justify another package to keep patched.

Sender domain: Resend will only accept a `from` address on a domain verified in the
account. `onboarding@resend.dev` is their shared test sender and delivers ONLY to the
account owner's own address, so it is fine for a smoke test and useless in production —
set `RESEND_FROM_EMAIL` to an address on a verified domain before relying on this.
"""
from __future__ import annotations

import base64
from typing import Optional

import httpx
import structlog

from app.core.config import settings
from app.services.adapters.transactional.base import (
    Attachment, MailResult, TransactionalMailer,
)

logger = structlog.get_logger()

API_URL = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 20


class ResendMailer(TransactionalMailer):
    name = "resend"

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_from_email: Optional[str] = None,
        default_from_name: Optional[str] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.RESEND_API_KEY
        self.default_from_email = default_from_email or settings.RESEND_FROM_EMAIL
        self.default_from_name = default_from_name or settings.RESEND_FROM_NAME

    def is_configured(self) -> bool:
        return bool(self.api_key and self.default_from_email)

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        html_body: str,
        from_email: str,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[list[Attachment]] = None,
    ) -> MailResult:
        if not self.api_key:
            return MailResult(False, "RESEND_API_KEY is not set.", provider=self.name)

        sender = from_email or self.default_from_email
        if not sender:
            return MailResult(False, "No sender address configured.", provider=self.name)
        display = from_name or self.default_from_name
        payload = {
            "from": f"{display} <{sender}>" if display else sender,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }
        if reply_to:
            payload["reply_to"] = reply_to
        if attachments:
            payload["attachments"] = [
                {
                    "filename": a.filename,
                    "content": base64.b64encode(a.content).decode("ascii"),
                }
                for a in attachments
            ]

        try:
            resp = httpx.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )
        except Exception as e:  # noqa: BLE001 — system mail is best-effort everywhere
            logger.error("resend_send_failed", to=to_email, error=str(e))
            return MailResult(False, f"Could not reach Resend: {e}", provider=self.name)

        if resp.status_code in (200, 201):
            message_id = (resp.json() or {}).get("id")
            logger.info("resend_sent", to=to_email, message_id=message_id)
            return MailResult(True, "Sent.", message_id=message_id, provider=self.name)

        # Resend's errors are specific and worth surfacing verbatim to the settings UI —
        # "domain is not verified" and "restricted API key" are both self-explanatory
        # and both unfixable without the message.
        detail = _explain(resp)
        logger.error("resend_rejected", to=to_email, status=resp.status_code, detail=detail)
        return MailResult(False, detail, provider=self.name)


def _explain(resp: httpx.Response) -> str:
    """Turn a Resend error body into something actionable."""
    try:
        body = resp.json()
        message = body.get("message") or body.get("error") or resp.text
        name = body.get("name", "")
    except Exception:  # noqa: BLE001 - non-JSON error body
        return f"Resend returned HTTP {resp.status_code}: {resp.text[:200]}"

    hints = {
        "restricted_api_key": " (this key is send-only, which is fine for sending)",
        "validation_error": " — check the from address is on a domain verified in Resend.",
        "missing_api_key": " — set RESEND_API_KEY.",
    }
    return f"Resend: {message}{hints.get(name, '')}"
