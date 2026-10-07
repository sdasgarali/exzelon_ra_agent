"""Mailboxes, warmup and deliverability tools.

Several backend ``/warmup/*`` routes look mailboxes up by id without a tenant
check, so every tool that passes a mailbox id to one of them first confirms
the mailbox belongs to the caller via the tenant-scoped ``GET /mailboxes/{id}``.
"""
from __future__ import annotations

from typing import Literal, Optional

from mcp.server.mcpserver import Context, MCPServer

from neuraleads_mcp.runtime import (
    EXTERNAL, READ, WRITE, WRITE_IDEMPOTENT, Runtime, confirmation_required, pick, pick_list,
)

MAILBOX_FIELDS = (
    "mailbox_id", "email", "display_name", "provider", "warmup_status", "is_active", "can_send",
    "daily_send_limit", "emails_sent_today", "remaining_daily_quota", "total_emails_sent",
    "bounce_count", "reply_count", "complaint_count", "connection_status", "connection_error",
    "warmup_days_completed", "outreach_role_name", "last_sent_at",
)
WarmupStatus = Literal["warming_up", "cold_ready", "active", "paused", "inactive", "blacklisted"]


def register(mcp: MCPServer, rt: Runtime) -> None:
    write = not rt.settings.read_only

    async def owned_mailbox(ctx: Context, mailbox_id: int) -> dict:
        """Tenant-scoped lookup; raises a tool error if the mailbox isn't the caller's."""
        return await rt.get(ctx, f"/mailboxes/{int(mailbox_id)}")

    async def owned_mailbox_ids(ctx: Context) -> set:
        data = await rt.get(ctx, "/mailboxes")
        return {m.get("mailbox_id") for m in (data.get("items") or [])}

    # ── mailboxes ───────────────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def list_mailboxes(
        ctx: Context,
        warmup_status: Optional[Literal["warming_up", "cold_ready", "active", "paused", "inactive",
                                        "blacklisted", "recovering"]] = None,
        provider: Optional[Literal["microsoft_365", "gmail", "smtp", "other"]] = None,
        is_active: Optional[bool] = None,
        archived: bool = False,
    ) -> dict:
        """List sender mailboxes with warmup status, send capacity left today, and bounce/reply counts.
        `archived=true` returns only archived mailboxes."""
        data = await rt.get(ctx, "/mailboxes", status=warmup_status, provider=provider,
                            is_active=is_active, show_archived=archived)
        return pick_list(data, MAILBOX_FIELDS)

    @mcp.tool(annotations=READ)
    async def get_mailbox_stats(ctx: Context) -> dict:
        """Totals across all mailboxes: how many are active/ready/warming, daily capacity, used and
        available sends today, lifetime sent, bounces and replies."""
        return await rt.get(ctx, "/mailboxes/stats")

    @mcp.tool(annotations=READ)
    async def get_mailbox(ctx: Context, mailbox_id: int) -> dict:
        """One mailbox in depth: settings, outreach stats, campaigns using it, and the last 30 days of
        warmup logs."""
        data = await rt.get(ctx, f"/mailboxes/{mailbox_id}/detail")
        if isinstance(data, dict) and isinstance(data.get("mailbox"), dict):
            data["mailbox"] = pick(data["mailbox"], MAILBOX_FIELDS + (
                "sender_first_name", "sender_last_name", "smtp_host", "smtp_port", "imap_host",
                "imap_port", "auth_method", "oauth_connected", "warmup_started_at",
                "warmup_completed_at", "notes", "created_at"))
        return data

    if write:
        @mcp.tool(annotations=EXTERNAL)
        async def test_mailbox_connection(ctx: Context, mailbox_id: int) -> dict:
            """Live SMTP + IMAP login test for a mailbox (takes up to ~30s). Updates its connection status."""
            return await rt.post(ctx, f"/mailboxes/{mailbox_id}/test-connection")

        @mcp.tool(annotations=WRITE)
        async def set_mailbox_status(ctx: Context, mailbox_id: int, new_status: WarmupStatus,
                                     confirm: bool = False) -> dict:
            """Change a mailbox's warmup/sending status (e.g. pause a mailbox that is bouncing, or mark a
            warmed mailbox `cold_ready`). Requires confirm=true."""
            mb = await owned_mailbox(ctx, mailbox_id)
            if not confirm:
                return confirmation_required("set_mailbox_status", {
                    "mailbox": mb.get("email"), "from": mb.get("warmup_status"), "to": new_status})
            return await rt.post(ctx, f"/mailboxes/{mailbox_id}/update-status", new_status=new_status)

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def update_mailbox_settings(
            ctx: Context, mailbox_id: int,
            daily_send_limit: Optional[int] = None, display_name: Optional[str] = None,
            sender_first_name: Optional[str] = None, sender_last_name: Optional[str] = None,
            is_active: Optional[bool] = None, notes: Optional[str] = None,
        ) -> dict:
            """Update a mailbox's sending settings. Only the fields you pass change. Credentials and
            server settings can't be changed here — do that in the NeuraLeads UI."""
            body = {k: v for k, v in {
                "daily_send_limit": daily_send_limit, "display_name": display_name,
                "sender_first_name": sender_first_name, "sender_last_name": sender_last_name,
                "is_active": is_active, "notes": notes}.items() if v is not None}
            if not body:
                return {"status": "no_change", "message": "Pass at least one field to update."}
            if daily_send_limit is not None and not (1 <= daily_send_limit <= 500):
                return {"status": "rejected", "message": "daily_send_limit must be between 1 and 500."}
            return pick(await rt.put(ctx, f"/mailboxes/{mailbox_id}", json=body), MAILBOX_FIELDS)

    # ── warmup ──────────────────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def get_warmup_overview(ctx: Context) -> dict:
        """Warmup dashboard: every connected mailbox's warmup day/phase, health score, daily limit, and
        bounce/reply/complaint rates, plus counts per status and average health."""
        return await rt.get(ctx, "/warmup/status")

    @mcp.tool(annotations=READ)
    async def get_warmup_health_scores(ctx: Context) -> dict:
        """Health score breakdown per mailbox (bounce, reply, complaint and account-age components)."""
        return await rt.get(ctx, "/warmup/health-scores")

    @mcp.tool(annotations=READ)
    async def get_warmup_schedule(ctx: Context) -> dict:
        """The warmup ramp: phases, days and recommended emails per day."""
        return await rt.get(ctx, "/warmup/schedule")

    @mcp.tool(annotations=READ)
    async def get_mailbox_warmup_history(ctx: Context, mailbox_id: int, days: int = 30) -> dict:
        """Daily warmup log for one mailbox (sent, received, opens, replies, bounces, health)."""
        await owned_mailbox(ctx, mailbox_id)
        return await rt.get(ctx, "/warmup/analytics", mailbox_id=mailbox_id, days=max(1, min(days, 365)))

    @mcp.tool(annotations=READ)
    async def list_warmup_alerts(ctx: Context,
                                 severity: Optional[Literal["info", "warning", "critical"]] = None,
                                 unread_only: bool = False, limit: int = 50) -> dict:
        """Warmup alerts (blacklistings, health drops, auto-pauses, DNS issues, warmup complete) for your
        mailboxes."""
        mine = await owned_mailbox_ids(ctx)
        data = await rt.get(ctx, "/warmup/alerts", severity=severity,
                            is_read=False if unread_only else None, limit=200)
        items = [a for a in (data.get("items") or []) if a.get("mailbox_id") in mine]
        items = items[: max(1, min(limit, 200))]
        return {"items": items, "count": len(items),
                "unread_count": sum(1 for a in items if not a.get("is_read"))}

    @mcp.tool(annotations=READ)
    async def get_mailbox_dns_status(ctx: Context, mailbox_id: int) -> dict:
        """Latest stored SPF / DKIM / DMARC / MX check for a mailbox's domain."""
        await owned_mailbox(ctx, mailbox_id)
        return await rt.get(ctx, f"/warmup/dns/{mailbox_id}")

    @mcp.tool(annotations=READ)
    async def get_mailbox_blacklist_status(ctx: Context, mailbox_id: int) -> dict:
        """Latest stored blacklist (DNSBL) check for a mailbox."""
        await owned_mailbox(ctx, mailbox_id)
        return await rt.get(ctx, f"/warmup/blacklist/{mailbox_id}")

    @mcp.tool(annotations=READ)
    async def list_warmup_profiles(ctx: Context) -> dict:
        """Available warmup profiles (ramp presets) that can be applied to a mailbox."""
        return await rt.get(ctx, "/warmup/profiles")

    if write:
        @mcp.tool(annotations=EXTERNAL)
        async def run_dns_check(ctx: Context, mailbox_id: Optional[int] = None) -> dict:
            """Run a live SPF/DKIM/DMARC/MX check for one mailbox, or all connected mailboxes if no id."""
            if mailbox_id is not None:
                await owned_mailbox(ctx, mailbox_id)
            return await rt.post(ctx, "/warmup/dns-check", mailbox_id=mailbox_id)

        @mcp.tool(annotations=EXTERNAL)
        async def run_blacklist_check(ctx: Context, mailbox_id: Optional[int] = None) -> dict:
            """Run a live blacklist check for one mailbox, or all connected mailboxes if no id. A listed
            mailbox may be auto-paused (status `blacklisted`)."""
            if mailbox_id is not None:
                await owned_mailbox(ctx, mailbox_id)
            return await rt.post(ctx, "/warmup/blacklist-check", mailbox_id=mailbox_id)

        @mcp.tool(annotations=WRITE)
        async def assess_mailbox_warmup(ctx: Context, mailbox_id: int) -> dict:
            """Re-score one mailbox's warmup now; may promote it, change its daily limit, or auto-pause it."""
            await owned_mailbox(ctx, mailbox_id)
            return await rt.post(ctx, f"/warmup/assess/{mailbox_id}")

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def apply_warmup_profile(ctx: Context, profile_id: int, mailbox_id: int) -> dict:
            """Assign a warmup profile (see list_warmup_profiles) to a mailbox."""
            await owned_mailbox(ctx, mailbox_id)
            return await rt.post(ctx, f"/warmup/profiles/{profile_id}/apply/{mailbox_id}")

    # ── deliverability ──────────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def get_deliverability_summary(ctx: Context) -> dict:
        """Workspace deliverability: average health, DNS issues, bounce/complaint rates and trend,
        send-gate blocks today."""
        return await rt.get(ctx, "/deliverability/health-summary")

    @mcp.tool(annotations=READ)
    async def get_mailbox_deliverability(ctx: Context, mailbox_id: int) -> dict:
        """One mailbox's deliverability grade (A–F), rates and detected ISP."""
        return await rt.get(ctx, f"/deliverability/mailbox/{mailbox_id}/health")

    @mcp.tool(annotations=READ)
    async def check_spam_score(ctx: Context, subject: str, body_html: str) -> dict:
        """Score an email draft for spam triggers (0–100, grade, flagged words). Nothing is sent."""
        return await rt.post(ctx, "/spam-check", json={"subject": subject, "body_html": body_html})
