"""Server & IP Sharding and Rotation (SISR) for high-volume sending."""
import socket
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox
from app.db.query_helpers import tenant_filter

logger = structlog.get_logger()


class IPRotationService:
    """Manage dedicated IP pools and rotation for email sending."""

    # Class-level round-robin counter for IP group rotation
    _rr_index: int = 0

    def get_available_ips(
        self,
        db: Session,
        tenant_id: int = None,
    ) -> list:
        """Get all active mailboxes with their SMTP and IP configurations.

        Returns active mailboxes with their SMTP host info and dedicated IP
        addresses for IP pool management.

        Args:
            db: Database session.
            tenant_id: Optional tenant scope filter.

        Returns:
            List of dicts with mailbox info, SMTP host, and dedicated IP details.
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
                "dedicated_ip": m.dedicated_ip,
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

    def resolve_and_store_ip(
        self,
        db: Session,
        mailbox_id: int,
    ) -> Optional[str]:
        """Resolve a mailbox's SMTP host to an IP address and store it.

        Uses ``socket.getaddrinfo()`` to resolve the SMTP host to an IP and
        stores the result in the ``dedicated_ip`` column on SenderMailbox.

        Args:
            db: Database session.
            mailbox_id: The mailbox whose SMTP host should be resolved.

        Returns:
            The resolved IP address string, or None if resolution fails.
        """
        mailbox = db.query(SenderMailbox).filter(
            SenderMailbox.mailbox_id == mailbox_id,
        ).first()

        if not mailbox:
            logger.warning("resolve_ip_mailbox_not_found", mailbox_id=mailbox_id)
            return None

        if not mailbox.smtp_host:
            logger.warning(
                "resolve_ip_no_smtp_host",
                mailbox_id=mailbox_id,
                email=mailbox.email,
            )
            return None

        try:
            # Resolve SMTP host to IP (AF_INET for IPv4)
            addr_info = socket.getaddrinfo(
                mailbox.smtp_host,
                mailbox.smtp_port or 587,
                socket.AF_INET,
                socket.SOCK_STREAM,
            )
            if not addr_info:
                logger.warning(
                    "resolve_ip_no_results",
                    mailbox_id=mailbox_id,
                    smtp_host=mailbox.smtp_host,
                )
                return None

            # addr_info[0][4][0] is the IP address from the first result
            resolved_ip = addr_info[0][4][0]

            mailbox.dedicated_ip = resolved_ip
            db.flush()

            logger.info(
                "ip_resolved_and_stored",
                mailbox_id=mailbox_id,
                email=mailbox.email,
                smtp_host=mailbox.smtp_host,
                dedicated_ip=resolved_ip,
            )
            return resolved_ip

        except (socket.gaierror, socket.herror, OSError) as exc:
            logger.error(
                "resolve_ip_failed",
                mailbox_id=mailbox_id,
                smtp_host=mailbox.smtp_host,
                error=str(exc),
            )
            return None

    def select_ip_round_robin(
        self,
        db: Session,
        tenant_id: int,
    ) -> Optional[dict]:
        """Select a mailbox using round-robin rotation across IP groups.

        Groups active mailboxes by their ``dedicated_ip`` (falling back to
        ``smtp_host`` when no dedicated IP is set). Within each group, only
        mailboxes with remaining daily quota are considered. The method
        rotates across groups using a class-level ``_rr_index`` counter.

        Args:
            db: Database session.
            tenant_id: Tenant scope.

        Returns:
            Dict with selected mailbox info and selection method, or None
            if no mailbox with remaining quota is available.
        """
        ips = self.get_available_ips(db, tenant_id)

        # Filter to mailboxes with remaining quota
        available = [ip for ip in ips if ip["remaining_quota"] > 0]
        if not available:
            logger.warning(
                "round_robin_no_available_ips",
                tenant_id=tenant_id,
            )
            return None

        # Group by dedicated_ip (or smtp_host as fallback)
        groups: dict[str, list[dict]] = {}
        for entry in available:
            group_key = entry["dedicated_ip"] or entry["smtp_host"] or "unknown"
            groups.setdefault(group_key, []).append(entry)

        if not groups:
            return None

        # Sort group keys for deterministic ordering
        sorted_keys = sorted(groups.keys())

        # Round-robin across groups
        idx = IPRotationService._rr_index % len(sorted_keys)
        IPRotationService._rr_index += 1

        selected_group_key = sorted_keys[idx]
        group_mailboxes = groups[selected_group_key]

        # Within the group, pick the mailbox with the most remaining quota
        group_mailboxes.sort(key=lambda x: x["remaining_quota"], reverse=True)
        selected = group_mailboxes[0]

        logger.info(
            "round_robin_ip_selected",
            tenant_id=tenant_id,
            ip_group=selected_group_key,
            mailbox_id=selected["mailbox_id"],
            email=selected["email"],
            remaining_quota=selected["remaining_quota"],
            rr_index=IPRotationService._rr_index,
            total_groups=len(sorted_keys),
        )

        return {
            "ip": selected_group_key,
            "dedicated_ip": selected["dedicated_ip"],
            "mailbox_id": selected["mailbox_id"],
            "email": selected["email"],
            "remaining_quota": selected["remaining_quota"],
            "method": "round_robin",
        }
