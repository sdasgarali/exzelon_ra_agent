"""SMTP transactional mail adapter.

Wraps the existing send path so SMTP and Resend are interchangeable behind one
interface. Handles both implicit TLS (465) and STARTTLS (587).
"""
from __future__ import annotations

import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional

import structlog

from app.services.adapters.transactional.base import (
    Attachment, MailResult, TransactionalMailer,
)

logger = structlog.get_logger()


class SMTPMailer(TransactionalMailer):
    name = "smtp"

    def __init__(self, host: str, port: int, user: str, password: str,
                 security: str = "starttls"):
        self.host = host
        self.port = int(port or 587)
        self.user = user
        self.password = password
        self.security = (security or "starttls").lower()

    def is_configured(self) -> bool:
        return bool(self.host and self.user and self.password)

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
        if not self.is_configured():
            return MailResult(False, "SMTP is not configured.", provider=self.name)

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
        msg["To"] = to_email
        if reply_to:
            msg["Reply-To"] = reply_to

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(html_body, "html"))
        msg.attach(alt)

        for a in attachments or []:
            part = MIMEApplication(a.content, _subtype=a.content_type.split("/")[-1])
            part.add_header("Content-Disposition", "attachment", filename=a.filename)
            msg.attach(part)

        try:
            context = ssl.create_default_context()
            if self.security == "ssl" or self.port == 465:
                with smtplib.SMTP_SSL(self.host, self.port, timeout=30, context=context) as server:
                    server.login(self.user, self.password)
                    server.sendmail(from_email, [to_email], msg.as_string())
            else:
                with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(self.user, self.password)
                    server.sendmail(from_email, [to_email], msg.as_string())
            return MailResult(True, "Sent.", provider=self.name)

        except smtplib.SMTPAuthenticationError as e:
            # Worth calling out by name: it is the single most common failure here, and
            # the generic "authentication failed" sends people hunting for a typo in a
            # password that is perfectly correct.
            return MailResult(
                False,
                f"Authentication failed ({e.smtp_code}). Check the username and password — "
                "note that Microsoft 365 blocks basic SMTP unless Authenticated SMTP is "
                "enabled on the mailbox.",
                provider=self.name,
            )
        except Exception as e:  # noqa: BLE001 — system mail is best-effort
            logger.error("smtp_send_failed", to=to_email, error=str(e))
            return MailResult(False, f"Send failed: {type(e).__name__}: {e}", provider=self.name)
