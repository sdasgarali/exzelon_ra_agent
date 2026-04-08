"""DKIM Signer — optional DKIM signing for custom SMTP setups.

O365 and Gmail sign emails automatically via their gateways, so DKIM signing
is only needed for custom/self-hosted SMTP relays. This module gracefully
degrades when the ``dkim`` library is not installed.

Usage:
    if should_sign_dkim(mailbox):
        signed_bytes = sign_email_dkim(
            msg_bytes=raw_email,
            domain="example.com",
            selector="mail",
            private_key=mailbox.dkim_private_key,
        )
"""
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()

# Providers that sign DKIM automatically — no need to double-sign
PROVIDER_SIGNED_HOSTS = frozenset({
    "office365.com",
    "smtp.office365.com",
    "outlook.office365.com",
    "smtp.gmail.com",
    "smtp.google.com",
    "smtp-relay.gmail.com",
    "smtp.googlemail.com",
})

# Attempt to import dkim — purely optional
try:
    import dkim as _dkim_lib
    _DKIM_AVAILABLE = True
except ImportError:
    _dkim_lib = None
    _DKIM_AVAILABLE = False
    logger.info("dkim_library_not_installed", note="DKIM signing disabled — install 'dkim' package to enable")


def should_sign_dkim(mailbox: Any) -> bool:
    """Return True if the mailbox should have its emails DKIM-signed.

    Criteria:
    - The mailbox has a ``dkim_private_key`` attribute that is non-empty.
    - The mailbox's ``smtp_host`` is NOT in the list of providers that
      automatically sign outbound email.

    Args:
        mailbox: A SenderMailbox model instance (or any object with
                 ``dkim_private_key`` and ``smtp_host`` attributes).

    Returns:
        True if the caller should DKIM-sign the message.
    """
    private_key = getattr(mailbox, "dkim_private_key", None)
    if not private_key:
        return False

    smtp_host = (getattr(mailbox, "smtp_host", "") or "").lower().strip()
    if smtp_host in PROVIDER_SIGNED_HOSTS:
        logger.debug(
            "dkim_skip_provider_signed",
            smtp_host=smtp_host,
            email=getattr(mailbox, "email", "?"),
        )
        return False

    return True


def sign_email_dkim(
    msg_bytes: bytes,
    domain: str,
    selector: str,
    private_key: str,
) -> bytes:
    """Sign an email message with DKIM.

    Attempts to sign the raw email bytes using the ``dkim`` library. If the
    library is not installed or signing fails for any reason, the original
    unsigned bytes are returned with a warning log.

    Args:
        msg_bytes: Raw RFC-5322 email message bytes.
        domain: The signing domain (e.g., ``example.com``).
        selector: DKIM selector (e.g., ``mail``, ``s1``).
        private_key: RSA private key in PEM format (string).

    Returns:
        Signed email bytes (DKIM-Signature header prepended), or original
        bytes if signing is unavailable or fails.
    """
    if not _DKIM_AVAILABLE:
        logger.warning(
            "dkim_sign_skipped",
            reason="dkim library not installed",
            domain=domain,
        )
        return msg_bytes

    if not all([msg_bytes, domain, selector, private_key]):
        logger.warning(
            "dkim_sign_skipped",
            reason="missing required parameters",
            domain=domain,
            has_selector=bool(selector),
            has_key=bool(private_key),
        )
        return msg_bytes

    try:
        # Encode private key to bytes if it's a string
        key_bytes = private_key.encode("utf-8") if isinstance(private_key, str) else private_key

        signed = _dkim_lib.sign(
            message=msg_bytes,
            selector=selector.encode("utf-8"),
            domain=domain.encode("utf-8"),
            privkey=key_bytes,
            include_headers=[
                b"From",
                b"To",
                b"Subject",
                b"Date",
                b"Message-ID",
                b"MIME-Version",
                b"Content-Type",
            ],
        )

        logger.info(
            "dkim_sign_success",
            domain=domain,
            selector=selector,
            original_size=len(msg_bytes),
            signed_size=len(signed),
        )
        return signed

    except Exception as e:
        logger.error(
            "dkim_sign_failed",
            domain=domain,
            selector=selector,
            error=str(e),
            error_type=type(e).__name__,
        )
        return msg_bytes


def get_dkim_config(db: Any, mailbox_id: int) -> Dict[str, Any]:
    """Retrieve DKIM configuration for a mailbox.

    Looks up the mailbox and extracts DKIM-related settings.

    Args:
        db: SQLAlchemy Session.
        mailbox_id: Primary key of the SenderMailbox.

    Returns:
        Dict with keys: enabled (bool), domain (str), selector (str),
        has_private_key (bool). Returns {enabled: False} if no DKIM config
        or mailbox not found.
    """
    try:
        from app.db.models.sender_mailbox import SenderMailbox

        mailbox = db.query(SenderMailbox).filter(
            SenderMailbox.mailbox_id == mailbox_id
        ).first()

        if not mailbox:
            logger.debug("dkim_config_not_found", mailbox_id=mailbox_id)
            return {"enabled": False, "domain": "", "selector": "", "has_private_key": False}

        private_key = getattr(mailbox, "dkim_private_key", None)
        dkim_selector = getattr(mailbox, "dkim_selector", None) or "mail"
        domain = mailbox.email.split("@")[1] if "@" in mailbox.email else ""

        enabled = bool(private_key) and should_sign_dkim(mailbox)

        return {
            "enabled": enabled,
            "domain": domain,
            "selector": dkim_selector,
            "has_private_key": bool(private_key),
        }

    except Exception as e:
        logger.error("dkim_config_error", mailbox_id=mailbox_id, error=str(e))
        return {"enabled": False, "domain": "", "selector": "", "has_private_key": False}
