"""IMAP read emulation for warmup — marks warmup emails as read to simulate human behavior."""
import imaplib
import random
import time
from datetime import datetime
from typing import Dict, Any
import structlog

from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus

logger = structlog.get_logger()

# Default IMAP settings per provider
IMAP_DEFAULTS = {
    "microsoft_365": {"host": "outlook.office365.com", "port": 993},
    "gmail": {"host": "imap.gmail.com", "port": 993},
    "smtp": {"host": None, "port": 993},
    "other": {"host": None, "port": 993},
}


def run_imap_read_cycle(db: Session) -> Dict[str, Any]:
    """For each warmup-active mailbox, connect via IMAP and mark warmup emails as read.

    This simulates human email reading behavior to improve warmup effectiveness.
    ISPs track whether emails are read, so marking warmup emails as read
    improves sender reputation.

    Returns: {mailboxes_processed: int, emails_marked: int, errors: int}
    """
    result = {"mailboxes_processed": 0, "emails_marked": 0, "errors": 0}

    mailboxes = db.query(SenderMailbox).filter(
        SenderMailbox.warmup_status.in_([WarmupStatus.WARMING_UP, WarmupStatus.ACTIVE]),
        SenderMailbox.is_active == True,
        SenderMailbox.connection_status == "successful",
    ).all()

    # Get all warmup mailbox emails for matching
    all_warmup_emails = set(
        m.email.lower() for m in db.query(SenderMailbox).filter(
            SenderMailbox.warmup_status.in_([WarmupStatus.WARMING_UP, WarmupStatus.ACTIVE]),
            SenderMailbox.is_active == True,
        ).all()
    )

    for mailbox in mailboxes:
        try:
            marked = _process_mailbox_imap(mailbox, all_warmup_emails, db)
            result["mailboxes_processed"] += 1
            result["emails_marked"] += marked
        except Exception as e:
            logger.warning("IMAP read cycle failed for mailbox",
                           mailbox=mailbox.email, error=str(e))
            result["errors"] += 1

        # Random delay between mailboxes (5-15 seconds)
        time.sleep(random.uniform(5, 15))

    return result


def _process_mailbox_imap(
    mailbox: SenderMailbox,
    warmup_peer_emails: set,
    db: Session,
) -> int:
    """Connect to a single mailbox via IMAP and mark unread warmup emails as read.

    Returns: number of emails marked as read.
    """
    imap_host = mailbox.imap_host
    imap_port = mailbox.imap_port or 993

    # Determine IMAP host from provider if not explicitly set
    if not imap_host:
        provider = mailbox.provider.value if mailbox.provider else "smtp"
        defaults = IMAP_DEFAULTS.get(provider, IMAP_DEFAULTS["other"])
        imap_host = defaults["host"]
        if not imap_host:
            logger.debug("No IMAP host for mailbox", mailbox=mailbox.email)
            return 0

    # Decrypt password if needed
    password = mailbox.password
    if password:
        try:
            from app.core.encryption import decrypt_field, is_encrypted
            if is_encrypted(password):
                password = decrypt_field(password)
        except Exception:
            pass

    # For OAuth2 mailboxes, use access token
    use_oauth = mailbox.auth_method == "oauth2" and mailbox.oauth_access_token

    marked_count = 0

    try:
        imap = imaplib.IMAP4_SSL(imap_host, imap_port)

        if use_oauth:
            # XOAUTH2 authentication
            auth_string = f"user={mailbox.email}\x01auth=Bearer {mailbox.oauth_access_token}\x01\x01"
            imap.authenticate("XOAUTH2", lambda x: auth_string.encode())
        else:
            if not password:
                logger.debug("No password for IMAP login", mailbox=mailbox.email)
                return 0
            imap.login(mailbox.email, password)

        imap.select("INBOX")

        # Search for unread messages
        status, messages = imap.search(None, "UNSEEN")
        if status != "OK":
            imap.logout()
            return 0

        message_ids = messages[0].split() if messages[0] else []

        for msg_id in message_ids:
            try:
                # Fetch sender (FROM header only — lightweight)
                status, data = imap.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM)])")
                if status != "OK" or not data or not data[0]:
                    continue

                header = data[0][1].decode("utf-8", errors="ignore") if isinstance(data[0], tuple) and len(data[0]) > 1 else ""

                # Check if sender is a warmup peer
                sender_is_peer = any(peer_email in header.lower() for peer_email in warmup_peer_emails)

                if sender_is_peer:
                    # Random delay to simulate human reading (5-30 seconds wait would be
                    # ideal but we just add a small randomized delay here)
                    time.sleep(random.uniform(0.5, 3))

                    # Mark as read
                    imap.store(msg_id, "+FLAGS", "\\Seen")
                    marked_count += 1

            except Exception as e:
                logger.debug("Error processing IMAP message", error=str(e))

        imap.logout()

        # Update warmup opens counter
        if marked_count > 0:
            mailbox.warmup_opens = (mailbox.warmup_opens or 0) + marked_count

    except imaplib.IMAP4.error as e:
        logger.warning("IMAP connection failed", mailbox=mailbox.email, error=str(e))
        raise
    except Exception as e:
        logger.warning("IMAP read cycle error", mailbox=mailbox.email, error=str(e))
        raise

    return marked_count
