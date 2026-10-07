"""Outreach campaign tools.

Campaign email is sent by NeuraLeads' scheduler (every ~2 minutes, inside the
campaign's send window), which applies the send limits, cooldown, suppression
and valid-email rules. These tools never send email directly.
"""
from __future__ import annotations

import asyncio
from typing import Literal, Optional

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from neuraleads_mcp.runtime import (
    EXTERNAL, READ, WRITE, WRITE_IDEMPOTENT, Runtime, clamp_limit, confirmation_required, pick,
    pick_list,
)

CAMPAIGN_FIELDS = ("campaign_id", "name", "description", "status", "timezone", "send_window_start",
                   "send_window_end", "send_days", "mailbox_ids", "daily_limit", "total_contacts",
                   "total_sent", "total_opened", "total_replied", "total_bounced", "health_score",
                   "sending_speed", "scheduled_send_at", "auto_pause_reason", "created_at")
STEP_FIELDS = ("step_id", "step_order", "step_type", "subject", "body_html", "body_text", "template_id",
               "delay_days", "delay_hours", "reply_to_thread", "total_sent", "total_replied")
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
StepType = Literal["email", "wait"]
MAX_ENROLL = 200


def register(mcp: MCPServer, rt: Runtime) -> None:
    write = not rt.settings.read_only

    async def campaign(ctx: Context, campaign_id: int) -> dict:
        return await rt.get(ctx, f"/campaigns/{campaign_id}")

    @mcp.tool(annotations=READ)
    async def list_campaigns(ctx: Context,
                             status: Optional[Literal["draft", "active", "paused", "completed"]] = None,
                             page: int = 1, page_size: int = 20) -> dict:
        """Outreach campaigns with status and send/open/reply/bounce totals, newest first."""
        data = await rt.get(ctx, "/campaigns", status=status, page=max(1, page), page_size=clamp_limit(page_size, 20))
        return pick_list(data, CAMPAIGN_FIELDS)

    @mcp.tool(annotations=READ)
    async def get_campaign(ctx: Context, campaign_id: int) -> dict:
        """A campaign's settings, sequence steps (subject/body/delays) and schedules."""
        data = await campaign(ctx, campaign_id)
        out = pick(data, CAMPAIGN_FIELDS)
        out["steps"] = [pick(s, STEP_FIELDS) for s in (data.get("steps") or [])]
        out["schedules"] = data.get("schedules") or []
        return out

    @mcp.tool(annotations=READ)
    async def get_campaign_analytics(ctx: Context, campaign_id: int, date_from: Optional[str] = None,
                                     date_to: Optional[str] = None) -> dict:
        """Campaign results overall and per step (incl. A/B variants), plus the step funnel.
        Dates are YYYY-MM-DD."""
        return await rt.get(ctx, f"/campaigns/{campaign_id}/analytics", date_from=date_from, date_to=date_to)

    @mcp.tool(annotations=READ)
    async def get_campaign_health(ctx: Context, campaign_id: int) -> dict:
        """Campaign health score (deliverability, engagement, volume) with recommendations."""
        return await rt.get(ctx, f"/campaigns/{campaign_id}/health")

    @mcp.tool(annotations=READ)
    async def get_campaign_mailbox_stats(ctx: Context, campaign_id: int) -> list:
        """Per sender mailbox results for a campaign (sent, opens, replies, bounces and rates)."""
        return await rt.get(ctx, f"/campaigns/{campaign_id}/mailbox-stats")

    @mcp.tool(annotations=READ)
    async def list_campaign_contacts(
        ctx: Context, campaign_id: int,
        status: Optional[Literal["active", "completed", "replied", "bounced", "unsubscribed", "paused"]] = None,
        page: int = 1, page_size: int = 25,
    ) -> dict:
        """Contacts enrolled in a campaign with their step, next send time and status."""
        data = await rt.get(ctx, f"/campaigns/{campaign_id}/contacts", status=status, page=max(1, page),
                            page_size=clamp_limit(page_size))
        return pick_list(data, ("contact_id", "contact_name", "contact_email", "contact_title",
                                "contact_company", "lead_id", "lead_title", "status", "current_step",
                                "next_send_at", "enrolled_at", "completed_at"))

    @mcp.tool(annotations=READ)
    async def list_campaign_ready_leads(
        ctx: Context, search: Optional[str] = None, states: Optional[list[str]] = None,
        industries: Optional[list[str]] = None, titles: Optional[list[str]] = None,
        days: int = 7, page: int = 1, page_size: int = 25,
    ) -> dict:
        """Leads posted in the last `days` that have contacts and are not already in an active or draft
        campaign — the pool for create_campaign_from_leads."""
        return await rt.get(ctx, "/campaigns/available-leads", search=search, state=states, industry=industries,
                            title=titles, days=max(1, min(days, 365)), page=max(1, page),
                            page_size=clamp_limit(page_size))

    @mcp.tool(annotations=READ)
    async def list_email_templates(ctx: Context, search: Optional[str] = None,
                                   status: Optional[Literal["active", "inactive"]] = None) -> dict:
        """Email templates (outreach and follow-up) that sequence steps can use."""
        data = await rt.get(ctx, "/templates", search=search, status=status)
        return pick_list(data, ("template_id", "name", "subject", "category", "status", "industry", "goal",
                                "is_default"))

    @mcp.tool(annotations=READ)
    async def preview_auto_enrollment(
        ctx: Context, campaign_id: int, states: Optional[list[str]] = None,
        job_title_keywords: Optional[list[str]] = None, sources: Optional[list[str]] = None,
        min_lead_score: Optional[int] = None,
    ) -> dict:
        """Count how many valid contacts an auto-enrollment rule would match. Changes nothing."""
        rules = {"validation_status": ["Valid"], "states": states or [],
                 "job_title_keywords": job_title_keywords or [], "sources": sources or [],
                 "min_lead_score": min_lead_score}
        return await rt.post(ctx, f"/campaigns/{campaign_id}/enrollment-preview", json={"rules": rules})

    if not write:
        return

    @mcp.tool(annotations=WRITE)
    async def create_campaign_from_leads(
        ctx: Context, lead_ids: list[int], timezone: str = "America/New_York",
        send_window_start: str = "09:00", send_window_end: str = "17:00",
        send_days: Optional[list[Weekday]] = None,
    ) -> dict:
        """Create a DRAFT campaign from leads: a 3-step sequence (email, wait 3 days, follow-up) from
        the active templates, all connected mailboxes assigned, and the leads' contacts enrolled.
        Sends nothing — review with get_campaign, then activate_campaign."""
        ids = list(dict.fromkeys(lead_ids))
        if not ids:
            return {"status": "no_change", "message": "lead_ids is empty."}
        data = await rt.post(ctx, "/campaigns/from-leads", json={
            "lead_ids": ids[:500], "timezone": timezone, "send_window_start": send_window_start,
            "send_window_end": send_window_end, "send_days": send_days or ["mon", "tue", "wed", "thu", "fri"]})
        out = pick(data, CAMPAIGN_FIELDS)
        out["steps"] = [pick(s, STEP_FIELDS) for s in (data.get("steps") or [])]
        out["next_step"] = "Review the steps with the user, edit with update_campaign_step, then activate_campaign."
        return out

    @mcp.tool(annotations=WRITE_IDEMPOTENT)
    async def update_campaign_settings(
        ctx: Context, campaign_id: int, name: Optional[str] = None, description: Optional[str] = None,
        timezone: Optional[str] = None, send_window_start: Optional[str] = None,
        send_window_end: Optional[str] = None, send_days: Optional[list[Weekday]] = None,
        mailbox_ids: Optional[list[int]] = None, daily_limit: Optional[int] = None,
        sending_speed: Optional[Literal["relaxed", "normal", "aggressive"]] = None,
    ) -> dict:
        """Change campaign settings. Only the fields you pass change."""
        body = {k: v for k, v in {
            "name": name, "description": description, "timezone": timezone,
            "send_window_start": send_window_start, "send_window_end": send_window_end,
            "send_days": send_days, "mailbox_ids": mailbox_ids, "daily_limit": daily_limit,
            "sending_speed": sending_speed}.items() if v is not None}
        if not body:
            return {"status": "no_change", "message": "Pass at least one field to update."}
        if mailbox_ids:
            mine = {m.get("mailbox_id") for m in (await rt.get(ctx, "/mailboxes")).get("items", [])}
            unknown = sorted(set(mailbox_ids) - mine)
            if unknown:
                raise ToolError(f"Mailboxes not found in this workspace: {unknown}")
        return pick(await rt.put(ctx, f"/campaigns/{campaign_id}", json=body), CAMPAIGN_FIELDS)

    @mcp.tool(annotations=WRITE)
    async def add_campaign_step(
        ctx: Context, campaign_id: int, step_type: StepType, subject: Optional[str] = None,
        body_html: Optional[str] = None, body_text: Optional[str] = None,
        template_id: Optional[int] = None, delay_days: int = 1, delay_hours: int = 0,
        reply_to_thread: bool = True, step_order: Optional[int] = None,
    ) -> dict:
        """Append (or insert at step_order) a sequence step. Email steps need a subject and body, or a
        template_id. Merge fields like {{first_name}} and {{company}} are supported."""
        if step_type == "email" and not template_id and not (subject and (body_html or body_text)):
            raise ToolError("An email step needs subject + body_html/body_text, or a template_id.")
        body = {"step_type": step_type, "subject": subject, "body_html": body_html, "body_text": body_text,
                "template_id": template_id, "delay_days": max(0, delay_days), "delay_hours": max(0, delay_hours),
                "reply_to_thread": reply_to_thread, "step_order": step_order}
        return pick(await rt.post(ctx, f"/campaigns/{campaign_id}/steps",
                                  json={k: v for k, v in body.items() if v is not None}), STEP_FIELDS)

    @mcp.tool(annotations=WRITE_IDEMPOTENT)
    async def update_campaign_step(
        ctx: Context, campaign_id: int, step_id: int, subject: Optional[str] = None,
        body_html: Optional[str] = None, body_text: Optional[str] = None,
        template_id: Optional[int] = None, delay_days: Optional[int] = None,
        delay_hours: Optional[int] = None, reply_to_thread: Optional[bool] = None,
    ) -> dict:
        """Edit a sequence step's copy or timing. Only the fields you pass change."""
        body = {k: v for k, v in {
            "subject": subject, "body_html": body_html, "body_text": body_text, "template_id": template_id,
            "delay_days": delay_days, "delay_hours": delay_hours, "reply_to_thread": reply_to_thread,
        }.items() if v is not None}
        if not body:
            return {"status": "no_change", "message": "Pass at least one field to update."}
        return pick(await rt.put(ctx, f"/campaigns/{campaign_id}/steps/{step_id}", json=body), STEP_FIELDS)

    @mcp.tool(annotations=WRITE)
    async def enroll_contacts(ctx: Context, campaign_id: int, contact_ids: list[int]) -> dict:
        """Enroll contacts (up to 200 per call) in a campaign. Already-enrolled and suppressed contacts
        are skipped. If the campaign is active they start receiving the sequence."""
        ids = list(dict.fromkeys(contact_ids))
        if not ids:
            return {"status": "no_change", "message": "contact_ids is empty."}
        if len(ids) > MAX_ENROLL:
            return {"status": "rejected", "message": f"At most {MAX_ENROLL} contacts per call."}
        await campaign(ctx, campaign_id)  # 404s if not this workspace's campaign
        # The backend does not check contact ownership on enrollment, so verify every id here.
        sem = asyncio.Semaphore(8)

        async def owned(cid: int) -> Optional[int]:
            async with sem:
                try:
                    await rt.get(ctx, f"/contacts/{cid}")
                    return None
                except ToolError:
                    return cid

        missing = [c for c in await asyncio.gather(*(owned(c) for c in ids)) if c is not None]
        if missing:
            raise ToolError(f"Contacts not found in this workspace: {missing[:20]}"
                            + (" …" if len(missing) > 20 else ""))
        return await rt.post(ctx, f"/campaigns/{campaign_id}/contacts", json={"contact_ids": ids})

    @mcp.tool(annotations=EXTERNAL)
    async def activate_campaign(ctx: Context, campaign_id: int, confirm: bool = False) -> dict:
        """Start a campaign: NeuraLeads begins emailing enrolled contacts within its send window (the
        scheduler runs every ~2 minutes). Checks it has email steps, mailboxes and contacts first.
        Requires confirm=true."""
        c = await campaign(ctx, campaign_id)
        problems = []
        email_steps = [s for s in (c.get("steps") or []) if s.get("step_type") == "email"]
        if not email_steps:
            problems.append("no email steps")
        if any(not (s.get("subject") or s.get("template_id")) for s in email_steps):
            problems.append("an email step has no subject or template")
        if not c.get("mailbox_ids"):
            problems.append("no sender mailboxes assigned")
        if not c.get("total_contacts"):
            problems.append("no contacts enrolled")
        if c.get("status") not in ("draft", "paused"):
            problems.append(f"status is '{c.get('status')}' (must be draft or paused)")
        if problems:
            return {"status": "not_ready", "campaign_id": campaign_id, "problems": problems}
        if not confirm:
            return confirmation_required("activate_campaign", {
                "campaign": c.get("name"), "contacts": c.get("total_contacts"),
                "mailboxes": len(c.get("mailbox_ids") or []), "email_steps": len(email_steps),
                "send_window": f"{c.get('send_window_start')}–{c.get('send_window_end')} {c.get('timezone')}",
                "send_days": c.get("send_days"), "daily_limit": c.get("daily_limit"),
                "first_subject": email_steps[0].get("subject")})
        path = "resume" if c.get("status") == "paused" else "activate"
        return await rt.post(ctx, f"/campaigns/{campaign_id}/{path}")

    @mcp.tool(annotations=WRITE_IDEMPOTENT)
    async def pause_campaign(ctx: Context, campaign_id: int) -> dict:
        """Pause a campaign; no further emails go out until it is activated again."""
        return await rt.post(ctx, f"/campaigns/{campaign_id}/pause")

    @mcp.tool(annotations=WRITE)
    async def complete_campaign(ctx: Context, campaign_id: int, confirm: bool = False) -> dict:
        """Mark a campaign completed (stops it permanently). Requires confirm=true."""
        if not confirm:
            c = await campaign(ctx, campaign_id)
            return confirmation_required("complete_campaign", {
                "campaign": c.get("name"), "status": c.get("status"),
                "note": "A completed campaign cannot be restarted."})
        return await rt.post(ctx, f"/campaigns/{campaign_id}/complete")

    @mcp.tool(annotations=READ)
    async def suggest_subject_lines(ctx: Context, campaign_id: int) -> dict:
        """Five AI subject-line ideas based on the campaign's enrolled leads. Saves nothing."""
        return await rt.post(ctx, f"/campaigns/{campaign_id}/ai-suggest-subjects")
