"""Tenant-aware system/notification email sender.

System mail (email verification, password reset, deal notifications) is sent from a
per-tenant configurable sender stored in tenant settings, falling back to the global
`settings.SMTP_*` env config. Basic SMTP auth (STARTTLS on 587 or implicit SSL on 465).

Tenant setting keys (see settings_resolver):
  notification_sender_email / notification_sender_name
  notification_smtp_host / notification_smtp_port / notification_smtp_user
  notification_smtp_password_enc (Fernet)  /  notification_smtp_security ("starttls"|"ssl")
"""
from __future__ import annotations

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import decrypt_field
from app.core.settings_resolver import get_tenant_setting

logger = structlog.get_logger()

# Tenant setting keys
K_EMAIL = "notification_sender_email"
K_NAME = "notification_sender_name"
K_HOST = "notification_smtp_host"
K_PORT = "notification_smtp_port"
K_USER = "notification_smtp_user"
K_PASSWORD_ENC = "notification_smtp_password_enc"
K_SECURITY = "notification_smtp_security"


def _smtp_send(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    security: str,
    from_email: str,
    from_name: Optional[str],
    to_email: str,
    subject: str,
    html_body: str,
) -> bool:
    """Low-level SMTP send. `security` = "ssl" (implicit TLS, e.g. 465) or "starttls" (e.g. 587)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()
    if (security or "").lower() == "ssl" or int(port) == 465:
        with smtplib.SMTP_SSL(host, int(port), timeout=30, context=context) as server:
            server.login(user, password)
            server.sendmail(from_email, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(host, int(port), timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(user, password)
            server.sendmail(from_email, [to_email], msg.as_string())
    return True


def get_notification_sender(db: Session, tenant_id: Optional[int]) -> dict:
    """Resolve the tenant's notification-sender config (falls back to global settings.SMTP_*).

    Returns a dict with: source ('tenant'|'global'|'none'), host, port, user, security,
    sender_email, sender_name, password_set (bool). The plaintext password is under
    the private '_password' key for internal use only — never serialize it.
    """
    host = get_tenant_setting(db, K_HOST, tenant_id=tenant_id)
    user = get_tenant_setting(db, K_USER, tenant_id=tenant_id)
    pw_enc = get_tenant_setting(db, K_PASSWORD_ENC, tenant_id=tenant_id)
    if host and user and pw_enc:
        return {
            "source": "tenant",
            "host": host,
            "port": int(get_tenant_setting(db, K_PORT, tenant_id=tenant_id, default=587) or 587),
            "user": user,
            "security": (get_tenant_setting(db, K_SECURITY, tenant_id=tenant_id, default="starttls") or "starttls"),
            "sender_email": get_tenant_setting(db, K_EMAIL, tenant_id=tenant_id) or user,
            "sender_name": get_tenant_setting(db, K_NAME, tenant_id=tenant_id) or None,
            "password_set": True,
            "_password": decrypt_field(pw_enc),
        }

    # Global fallback (env-configured transactional SMTP).
    if settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD:
        return {
            "source": "global",
            "host": settings.SMTP_HOST,
            "port": int(settings.SMTP_PORT or 587),
            "user": settings.SMTP_USER,
            "security": "ssl" if int(settings.SMTP_PORT or 587) == 465 else "starttls",
            "sender_email": settings.SMTP_USER,
            "sender_name": None,
            "password_set": True,
            "_password": settings.SMTP_PASSWORD,
        }

    return {"source": "none", "password_set": False}


def send_system_email(db: Session, tenant_id: Optional[int], to_email: str, subject: str, html_body: str) -> bool:
    """Send a system/notification email using the tenant's sender (or global fallback).

    Best-effort — never raises to the caller. Returns True on success.
    """
    if not to_email:
        return False
    cfg = get_notification_sender(db, tenant_id)
    if cfg.get("source") == "none":
        logger.warning("No notification sender configured (tenant or global) — skipping email",
                       tenant_id=tenant_id, to=to_email)
        return False
    try:
        _smtp_send(
            host=cfg["host"], port=cfg["port"], user=cfg["user"], password=cfg["_password"],
            security=cfg["security"], from_email=cfg["sender_email"], from_name=cfg.get("sender_name"),
            to_email=to_email, subject=subject, html_body=html_body,
        )
        logger.info("System email sent", tenant_id=tenant_id, to=to_email, source=cfg["source"], sender=cfg["sender_email"])
        return True
    except Exception as e:
        logger.error("System email send failed", tenant_id=tenant_id, to=to_email, source=cfg.get("source"), error=str(e))
        return False


def send_test_email(db: Session, tenant_id: Optional[int], to_email: str, override: Optional[dict] = None) -> tuple[bool, str]:
    """Send a test email. If `override` (host/port/user/password/security/sender_email/name) is
    given, use it directly (for validating before saving); otherwise use the saved config.
    Returns (ok, detail) with the SMTP error surfaced for the UI.
    """
    subject = "NeuraLeads notification sender test"
    html = (
        "<div style=\"font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;\">"
        "<h2 style=\"color:#2563eb;\">It works ✅</h2>"
        "<p>This is a test of your NeuraLeads notification sender. If you received this, "
        "system emails (deal assignments, verification, password resets) will send from this address.</p>"
        "</div>"
    )
    try:
        if override and override.get("host") and override.get("user") and override.get("password"):
            _smtp_send(
                host=override["host"], port=int(override.get("port") or 587), user=override["user"],
                password=override["password"], security=override.get("security") or "starttls",
                from_email=override.get("sender_email") or override["user"], from_name=override.get("sender_name"),
                to_email=to_email, subject=subject, html_body=html,
            )
            return True, "Test email sent."
        cfg = get_notification_sender(db, tenant_id)
        if cfg.get("source") == "none":
            return False, "No sender configured. Fill in the SMTP fields (or set a global SMTP) first."
        _smtp_send(
            host=cfg["host"], port=cfg["port"], user=cfg["user"], password=cfg["_password"],
            security=cfg["security"], from_email=cfg["sender_email"], from_name=cfg.get("sender_name"),
            to_email=to_email, subject=subject, html_body=html,
        )
        return True, f"Test email sent via the {cfg['source']} sender ({cfg['sender_email']})."
    except smtplib.SMTPAuthenticationError as e:
        return False, f"Authentication failed ({e.smtp_code}). Check the username/password — note Microsoft 365 blocks basic SMTP unless Authenticated SMTP is enabled."
    except Exception as e:
        return False, f"Send failed: {type(e).__name__}: {e}"
