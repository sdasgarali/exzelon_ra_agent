"""Transactional mail — system email, deliberately separate from campaign sending.

Two kinds of email leave this platform and they must not share a path:

* **Campaign / cold outreach** — `adapters/email_sending/`. Goes out through the
  tenant's OWN mailboxes, because deliverability there depends on their domain
  reputation, their warmup history and the 30/day pacing the send gate enforces.
* **Transactional / system mail** — this package. Email verification, password
  resets, deal notifications, invoices. One sender, low volume, must arrive.

Routing cold outreach through a shared transactional provider would get that provider's
account terminated (Resend, Postmark and SendGrid all prohibit cold email in their
terms), and would put every tenant's sending behind one reputation. The split is
structural rather than a comment so it stays true.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Attachment:
    """A file to attach. `content` is the raw bytes; the adapter handles encoding."""

    filename: str
    content: bytes
    content_type: str = "application/pdf"


@dataclass
class MailResult:
    """Outcome of one send. `detail` is surfaced to the UI on the settings test button."""

    ok: bool
    detail: str = ""
    message_id: Optional[str] = None
    provider: str = ""


class TransactionalMailer(ABC):
    """One transactional send."""

    #: Short provider name, used in logs and in the settings test response.
    name: str = "base"

    @abstractmethod
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
        """Send one email. Must not raise — return `MailResult(ok=False, detail=...)`.

        System mail is best-effort at every call site: a failed deal notification must
        not roll back the deal, and a failed verification email must not 500 a signup.
        """
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has everything it needs to attempt a send."""
        ...
