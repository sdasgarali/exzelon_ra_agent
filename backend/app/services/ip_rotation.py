"""Server & IP Sharding and Rotation (SISR) for high-volume sending."""
import structlog
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox
from app.db.query_helpers import tenant_filter

logger = structlog.get_logger()


class IPRotationService:
    """Manage dedicated IP pools and rotation for email sending."""

    def get_available_ips(
        self,
        db: Session,
        tenant_id: int = None,
    ) -> list:
        """Get all active mailboxes with their SMTP configurations.

        Since dedicated_ip is not yet a column on SenderMailbox, this returns
        active mailboxes with their SMTP host info as a proxy for IP pool.

        Args:
            db: Database session.
            tenant_id: Optional tenant scope filter.

        Returns:
            List of dicts with mailbox info and SMTP host details.
        """
        q = db.query(SenderMailbox).filter(
            SenderMailbox.is_active == True,
        )
        if tenant_id:
            q = tenant_filter(q, SenderMailbox, tenant_id)

        mailboxes = q.all()
        return [
            {
                "mailbox_id": m.mailbox_id,
                "email": m.email,
                "smtp_host": m.smtp_host,
                "smtp_port": m.smtp_port,
                "warmup_status": (
                    m.warmup_status.value
                    if hasattr(m.warmup_status, "value")
                    else str(m.warmup_status)
                ),
                "emails_sent_today": m.emails_sent_today,
                "daily_send_limit": m.daily_send_limit,
                "remaining_quota": max(0, m.daily_send_limit - m.emails_sent_today),
            }
            for m in mailboxes
        ]

    def select_ip_for_send(
        self,
        db: Session,
        tenant_id: int,
    ) -> dict:
        """Select the best mailbox for sending based on quota and status.

        Args:
            db: Database session.
            tenant_id: Tenant scope.

        Returns:
            Dict with selected mailbox info and selection method.
        """
        ips = self.get_available_ips(db, tenant_id)
        if not ips:
            return {"ip": None, "method": "shared"}

        # Filter to mailboxes with remaining quota
        available = [ip for ip in ips if ip["remaining_quota"] > 0]
        if not available:
            return {"ip": None, "method": "quota_exhausted"}

        # Sort by remaining quota descending (most headroom first)
        available.sort(key=lambda x: x["remaining_quota"], reverse=True)
        selected = available[0]
        return {
            "ip": selected["smtp_host"],
            "mailbox_id": selected["mailbox_id"],
            "email": selected["email"],
            "remaining_quota": selected["remaining_quota"],
            "method": "dedicated",
        }

    def get_ip_stats(
        self,
        db: Session,
        tenant_id: int,
    ) -> dict:
        """Get IP pool statistics.

        Args:
            db: Database session.
            tenant_id: Tenant scope.

        Returns:
            Dict with pool stats including total IPs, avg quota, and per-IP details.
        """
        ips = self.get_available_ips(db, tenant_id)
        total_remaining = sum(ip["remaining_quota"] for ip in ips)
        total_capacity = sum(ip["daily_send_limit"] for ip in ips)

        return {
            "total_mailboxes": len(ips),
            "total_daily_capacity": total_capacity,
            "total_remaining_today": total_remaining,
            "avg_remaining_quota": (
                total_remaining / len(ips) if ips else 0
            ),
            "mailboxes": ips,
        }
