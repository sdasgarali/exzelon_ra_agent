"""Tenant-aware system/notification email sender.

System mail (email verification, password reset, deal notifications, invoices) is sent
from a per-tenant configurable sender stored in tenant settings, falling back to the
globally configured provider — Resend or SMTP, per `SYSTEM_MAIL_PROVIDER`.

The provider implementations live in `adapters/transactional/`; this module owns the
tenant-settings lookup and the call sites' best-effort contract.

Tenant setting keys (see settings_resolver):
  notification_sender_email / notification_sender_name
  notification_smtp_host / notification_smtp_port / notification_smtp_user
  notification_smtp_password_enc (Fernet)  /  notification_smtp_security ("starttls"|"ssl")
"""
from __future__ import annotations

from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_field
from app.core.settings_resolver import get_tenant_setting
from app.services.adapters.transactional import Attachment, SMTPMailer, resolve_sender

logger = structlog.get_logger()

# Tenant setting keys
K_EMAIL = "notification_sender_email"
K_NAME = "notification_sender_name"
K_HOST = "notification_smtp_host"
K_PORT = "notification_smtp_port"
K_USER = "notification_smtp_user"
K_PASSWORD_ENC = "notification_smtp_password_enc"
K_SECURITY = "notification_smtp_security"


def get_tenant_smtp_config(db: Session, tenant_id: Optional[int]) -> Optional[dict]:
    """The tenant's own SMTP sender, or None if they have not configured one.

    The plaintext password is under the private '_password' key for internal use only
    — never serialize it.
    """
    host = get_tenant_setting(db, K_HOST, tenant_id=tenant_id)
    user = get_tenant_setting(db, K_USER, tenant_id=tenant_id)
    pw_enc = get_tenant_setting(db, K_PASSWORD_ENC, tenant_id=tenant_id)
    if not (host and user and pw_enc):
        return None
    return {
        "host": host,
        "port": int(get_tenant_setting(db, K_PORT, tenant_id=tenant_id, default=587) or 587),
        "user": user,
        "security": (get_tenant_setting(db, K_SECURITY, tenant_id=tenant_id, default="starttls") or "starttls"),
        "sender_email": get_tenant_setting(db, K_EMAIL, tenant_id=tenant_id) or user,
        "sender_name": get_tenant_setting(db, K_NAME, tenant_id=tenant_id) or None,
        "_password": decrypt_field(pw_enc),
    }


def get_notification_sender(db: Session, tenant_id: Optional[int]) -> dict:
    """Resolved sender config for the UI and for callers that need to inspect it.

    Shape is kept backward compatible with the pre-Resend version — `source`, `host`,
    `port`, `user`, `security`, `sender_email`, `sender_name`, `password_set` — with
    `provider` added so the settings screen can say which service will actually send.
    """
    resolved = resolve_sender(db, tenant_id)
    if resolved["source"] == "none":
        return {"source": "none", "provider": resolved["provider"], "password_set": False}

    mailer = resolved["mailer"]
    out = {
        "source": resolved["source"],
        "provider": resolved["provider"],
        "sender_email": resolved["sender_email"],
        "sender_name": resolved["sender_name"],
        "password_set": True,
    }
    if isinstance(mailer, SMTPMailer):
        out.update(host=mailer.host, port=mailer.port, user=mailer.user,
                   security=mailer.security)
    return out


def send_system_email(
    db: Session,
    tenant_id: Optional[int],
    to_email: str,
    subject: str,
    html_body: str,
    attachments: Optional[list[Attachment]] = None,
    reply_to: Optional[str] = None,
) -> bool:
    """Send a system/notification email using the tenant's sender (or global fallback).

    Best-effort — never raises to the caller. Returns True on success. Callers treat a
    False as "the email did not go"; none of them roll back their own work over it,
    because a missed deal notification must not lose the deal.
    """
    if not to_email:
        return False

    resolved = resolve_sender(db, tenant_id)
    mailer = resolved["mailer"]
    if mailer is None:
        logger.warning("No notification sender configured (tenant or global) — skipping email",
                       tenant_id=tenant_id, to=to_email, provider=resolved["provider"])
        return False

    result = mailer.send(
        to_email=to_email, subject=subject, html_body=html_body,
        from_email=resolved["sender_email"], from_name=resolved["sender_name"],
        reply_to=reply_to, attachments=attachments,
    )
    if result.ok:
        logger.info("System email sent", tenant_id=tenant_id, to=to_email,
                    source=resolved["source"], provider=result.provider,
                    sender=resolved["sender_email"], message_id=result.message_id)
    else:
        logger.error("System email send failed", tenant_id=tenant_id, to=to_email,
                     source=resolved["source"], provider=result.provider,
                     error=result.detail)
    return result.ok


def send_test_email(db: Session, tenant_id: Optional[int], to_email: str,
                    override: Optional[dict] = None) -> tuple[bool, str]:
    """Send a test email, surfacing the provider's own error text to the UI.

    `override` (host/port/user/password/security/sender_email/name) validates SMTP
    credentials BEFORE they are saved, so a typo is caught at entry rather than
    discovered later by a password reset that never arrived.
    """
    subject = "NeuraLeads notification sender test"
    html = (
        "<div style=\"font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;\">"
        "<h2 style=\"color:#2563eb;\">It works ✅</h2>"
        "<p>This is a test of your NeuraLeads notification sender. If you received this, "
        "system emails (deal assignments, verification, password resets) will send from this address.</p>"
        "</div>"
    )

    if override and override.get("host") and override.get("user") and override.get("password"):
        mailer = SMTPMailer(
            host=override["host"], port=int(override.get("port") or 587),
            user=override["user"], password=override["password"],
            security=override.get("security") or "starttls",
        )
        result = mailer.send(
            to_email=to_email, subject=subject, html_body=html,
            from_email=override.get("sender_email") or override["user"],
            from_name=override.get("sender_name"),
        )
        return result.ok, (result.detail if not result.ok else "Test email sent.")

    resolved = resolve_sender(db, tenant_id)
    if resolved["mailer"] is None:
        return False, (
            "No sender configured. Fill in the SMTP fields, or set RESEND_API_KEY "
            "and RESEND_FROM_EMAIL for a global sender."
        )
    result = resolved["mailer"].send(
        to_email=to_email, subject=subject, html_body=html,
        from_email=resolved["sender_email"], from_name=resolved["sender_name"],
    )
    if result.ok:
        return True, (
            f"Test email sent via the {resolved['source']} {result.provider} sender "
            f"({resolved['sender_email']})."
        )
    return False, result.detail
