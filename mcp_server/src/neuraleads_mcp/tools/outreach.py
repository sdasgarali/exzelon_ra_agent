"""Direct outreach (lead-by-lead sends), the outreach event log, reply checks and warmup-wide actions.

Direct sends bypass campaigns but not the safety rules: every email still passes the backend's
eligibility checks (valid email only, cooldown, unsubscribes/suppression, excluded companies,
mailbox daily limits). Each tool that sends or changes mailbox state is confirmation-gated, and
every mailbox id is checked against the caller's workspace first.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from mcp.server.mcpserver import Context, MCPServer

from neuraleads_mcp.runtime import (
    EXTERNAL, READ, WRITE, Runtime, as_items, clamp_limit, confirmation_required, pick,
)

EVENT_FIELDS = ("event_id", "contact_id", "lead_id", "sender_mailbox_id", "sent_at", "channel", "status",
                "subject", "template_id", "bounce_reason", "reply_detected_at", "reply_subject", "skip_reason")
MAX_OUTREACH_LEADS = 100


def _status_key(raw) -> str:
    """'OutreachStatus.SENT' / 'SENT' / 'sent' → 'sent'."""
    return str(raw).rsplit(".", 1)[-1].strip().lower()


def register(mcp: MCPServer, rt: Runtime) -> None:
    write = not rt.settings.read_only

    async def own_mailbox_ids(ctx: Context) -> set:
        data = await rt.get(ctx, "/mailboxes")
        return {m.get("mailbox_id") for m in (data.get("items") or [])}

    async def outreach_preview(ctx: Context, lead_ids: list) -> dict:
        data = await rt.post(ctx, "/leads/bulk/outreach/preview", json={"lead_ids": lead_ids})
        mine = await own_mailbox_ids(ctx)
        # Defence in depth: never show another workspace's mailboxes.
        mailboxes = [m for m in (data.get("available_mailboxes") or []) if m.get("mailbox_id") in mine]
        assignments = []
        for a in data.get("assignments") or []:
            sender = a.get("sender")
            if isinstance(sender, dict) and sender.get("mailbox_id") not in mine:
                sender = None
            assignments.append({**pick(a, ("lead_id", "client_name", "job_title", "eligible_count", "error")),
                                "sender": sender,
                                "contacts": [pick(c, ("contact_id", "name", "email", "validation_status",
                                                      "eligible", "skip_reason"))
                                             for c in a.get("contacts") or []]})
        return {"total_leads": data.get("total_leads", len(lead_ids)),
                "eligible_contacts": sum(a.get("eligible_count") or 0 for a in assignments),
                "available_mailboxes": mailboxes, "assignments": assignments}

    # ── event log & stats ───────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def list_outreach_events(
        ctx: Context, status: Optional[Literal["sent", "replied", "bounced", "skipped"]] = None,
        channel: Optional[Literal["mailmerge", "smtp", "m365", "gmail", "api"]] = None,
        from_date: Optional[datetime] = None, to_date: Optional[datetime] = None,
        offset: int = 0, limit: int = 25,
    ) -> dict:
        """The outreach log: every email sent (or skipped) with status, subject, sender mailbox,
        bounce reason and reply time, newest first."""
        rows = await rt.get(ctx, "/outreach/events", status=status, channel=channel,
                            from_date=from_date.isoformat() if from_date else None,
                            to_date=to_date.isoformat() if to_date else None,
                            skip=max(0, offset), limit=clamp_limit(limit))
        return as_items(rows, EVENT_FIELDS)

    @mcp.tool(annotations=READ)
    async def get_outreach_stats(ctx: Context) -> dict:
        """Outreach totals by status (sent, replied, bounced, skipped) with bounce and reply rates."""
        data = await rt.get(ctx, "/outreach/stats/summary")
        if isinstance(data, dict) and isinstance(data.get("by_status"), dict):
            by_status: dict = {}
            for k, v in data["by_status"].items():
                key = _status_key(k)
                by_status[key] = by_status.get(key, 0) + (v or 0)
            data["by_status"] = by_status
        return data

    @mcp.tool(annotations=READ)
    async def preview_lead_outreach(ctx: Context, lead_ids: list[int]) -> dict:
        """Dry run for emailing leads' contacts directly (up to 100 leads): which contacts are
        eligible, why others are skipped, and which mailbox would send. Sends nothing."""
        ids = list(dict.fromkeys(lead_ids))[:MAX_OUTREACH_LEADS]
        if not ids:
            return {"status": "no_change", "message": "lead_ids is empty."}
        return await outreach_preview(ctx, ids)

    if not write:
        return

    @mcp.tool(annotations=EXTERNAL)
    async def send_lead_outreach(ctx: Context, lead_ids: list[int], confirm: bool = False) -> dict:
        """Email the eligible contacts of up to 100 leads right now, outside any campaign, using the
        active outreach template. Ineligible contacts (not valid, cooling down, unsubscribed,
        excluded) are skipped. Without confirm=true it only returns the preview."""
        ids = list(dict.fromkeys(lead_ids))
        if not ids:
            return {"status": "no_change", "message": "lead_ids is empty."}
        if len(ids) > MAX_OUTREACH_LEADS:
            return {"status": "rejected", "message": f"At most {MAX_OUTREACH_LEADS} leads per call."}
        if not confirm:
            preview = await outreach_preview(ctx, ids)
            return confirmation_required("send_lead_outreach", {
                "lead_count": len(ids), "eligible_contacts": preview["eligible_contacts"],
                "note": "Emails go out immediately from the assigned mailboxes."}, preview=preview)
        return await rt.post(ctx, "/leads/bulk/outreach", json={"lead_ids": ids, "dry_run": False})

    @mcp.tool(annotations=WRITE)
    async def check_replies(ctx: Context) -> dict:
        """Check your mailboxes for new replies and bounces now (normally automatic). Runs in the
        background; new replies appear in list_inbox_threads."""
        return await rt.post(ctx, "/outreach/check-replies")

    @mcp.tool(annotations=WRITE)
    async def start_warmup_recovery(ctx: Context, mailbox_id: int, confirm: bool = False) -> dict:
        """Put a paused or blacklisted mailbox into recovery: a slow re-warmup at a reduced daily limit
        (status `recovering`). Needs the warmup-settings 'full' permission (super admins by default).
        Requires confirm=true."""
        mb = await rt.get(ctx, f"/mailboxes/{int(mailbox_id)}")  # workspace check
        if not confirm:
            return confirmation_required("start_warmup_recovery", {
                "mailbox": mb.get("email"), "warmup_status": mb.get("warmup_status"),
                "daily_send_limit": mb.get("daily_send_limit"),
                "note": "Sending volume is cut back while the mailbox recovers."})
        return await rt.post(ctx, f"/warmup/recovery/{int(mailbox_id)}/start")

    @mcp.tool(annotations=WRITE)
    async def assess_all_warmup(ctx: Context, confirm: bool = False) -> dict:
        """Re-score warmup for every mailbox in the workspace now (normally scheduled). Mailboxes may
        be promoted, have daily limits changed, or be auto-paused. Requires confirm=true."""
        if not confirm:
            data = await rt.get(ctx, "/mailboxes")
            return confirmation_required("assess_all_warmup", {
                "mailboxes": len(data.get("items") or []),
                "note": "Statuses and daily limits may change; unhealthy mailboxes may be paused."})
        return await rt.post(ctx, "/warmup/assess")
