"""Transactional mail provider selection.

Resolution order, highest priority first:

1. **The tenant's own SMTP**, when they have configured one. A tenant that has set up
   their own notification sender did so to have system mail come from their domain —
   silently routing it through our shared provider would undo that, and would put their
   mail under our reputation instead of theirs.
2. **The global provider** chosen by `SYSTEM_MAIL_PROVIDER`:
   - `auto` (default) — Resend when an API key is set, otherwise global SMTP.
   - `resend` / `smtp` — force one, and fail loudly rather than quietly falling back,
     so a misconfiguration surfaces instead of mail silently changing sender.
   - `none` — disable global system mail entirely.
3. **Nothing**, in which case callers log and move on. System mail is best-effort at
   every call site.
"""
from __future__ import annotations

from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.adapters.transactional.base import (
    Attachment, MailResult, TransactionalMailer,
)
from app.services.adapters.transactional.resend_mailer import ResendMailer
from app.services.adapters.transactional.smtp_mailer import SMTPMailer

logger = structlog.get_logger()

__all__ = [
    "Attachment", "MailResult", "TransactionalMailer",
    "ResendMailer", "SMTPMailer",
    "get_mailer", "resolve_sender",
]


def _global_smtp() -> Optional[SMTPMailer]:
    if not (settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD):
        return None
    port = int(settings.SMTP_PORT or 587)
    return SMTPMailer(
        host=settings.SMTP_HOST, port=port, user=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        security="ssl" if port == 465 else "starttls",
    )


def _global_resend() -> Optional[ResendMailer]:
    mailer = ResendMailer()
    return mailer if mailer.is_configured() else None


def resolve_sender(db: Optional[Session], tenant_id: Optional[int]) -> dict:
    """Which provider will handle this tenant's system mail, and from what address.

    Returns `{source, provider, mailer, sender_email, sender_name}` where `source` is
    'tenant' | 'global' | 'none'. `mailer` is None when nothing is configured.
    """
    # 1. Tenant-configured SMTP wins.
    if db is not None:
        from app.services.system_mailer import get_tenant_smtp_config
        cfg = get_tenant_smtp_config(db, tenant_id)
        if cfg:
            return {
                "source": "tenant",
                "provider": "smtp",
                "mailer": SMTPMailer(
                    host=cfg["host"], port=cfg["port"], user=cfg["user"],
                    password=cfg["_password"], security=cfg["security"],
                ),
                "sender_email": cfg["sender_email"],
                "sender_name": cfg.get("sender_name"),
            }

    # 2. The configured global provider.
    choice = (settings.SYSTEM_MAIL_PROVIDER or "auto").lower()
    if choice == "none":
        return {"source": "none", "provider": "none", "mailer": None,
                "sender_email": None, "sender_name": None}

    if choice in ("auto", "resend"):
        resend = _global_resend()
        if resend:
            return {
                "source": "global", "provider": "resend", "mailer": resend,
                "sender_email": settings.RESEND_FROM_EMAIL,
                "sender_name": settings.RESEND_FROM_NAME or None,
            }
        if choice == "resend":
            # Explicitly asked for Resend and it is not usable — do NOT silently fall
            # back to SMTP. Mail arriving from an unexpected sender is harder to
            # diagnose than mail that does not arrive.
            logger.warning("SYSTEM_MAIL_PROVIDER=resend but RESEND_API_KEY/FROM_EMAIL are unset")
            return {"source": "none", "provider": "resend", "mailer": None,
                    "sender_email": None, "sender_name": None}

    if choice in ("auto", "smtp"):
        smtp = _global_smtp()
        if smtp:
            return {
                "source": "global", "provider": "smtp", "mailer": smtp,
                "sender_email": settings.SMTP_USER, "sender_name": None,
            }

    return {"source": "none", "provider": "none", "mailer": None,
            "sender_email": None, "sender_name": None}


def get_mailer(db: Optional[Session] = None,
               tenant_id: Optional[int] = None) -> Optional[TransactionalMailer]:
    """The mailer for this tenant, or None when nothing is configured."""
    return resolve_sender(db, tenant_id)["mailer"]
