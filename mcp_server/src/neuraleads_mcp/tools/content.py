"""Content tools: email templates, AI sequences, preview drafts, objection responses, reply macros.

Drafts in the "email preview" queue are real, personalised emails waiting for review. Approving a
draft does not send it; sending is a separate, confirmation-gated step that goes through the
backend's send gate (suppression, cooldown, valid-email and daily-limit rules).
"""
from __future__ import annotations

import asyncio
from typing import Literal, Optional

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from neuraleads_mcp.runtime import (
    DESTRUCTIVE, EXTERNAL, READ, WRITE, WRITE_IDEMPOTENT, Runtime, clamp_limit, compact,
    confirmation_required, items_of, pick,
)

TEMPLATE_FIELDS = ("template_id", "name", "subject", "body_html", "body_text", "status", "category",
                   "goal", "industry", "description", "is_default", "is_system", "is_archived",
                   "created_at", "updated_at")
TEMPLATE_LIST_FIELDS = ("template_id", "name", "subject", "status", "category", "goal", "industry")
DRAFT_FIELDS = ("draft_id", "status", "source", "subject", "contact_id", "lead_id", "campaign_id",
                "step_id", "mailbox_id", "spam_score", "spam_grade", "deliverability_score",
                "ai_rewritten", "batch_id", "approved_at", "sent_at", "expires_at", "created_at")
OBJECTION_FIELDS = ("template_id", "objection_type", "objection_text", "response_text", "category",
                    "effectiveness_score", "times_used", "is_system")
MACRO_FIELDS = ("macro_id", "title", "body_text", "body_html", "category", "usage_count", "updated_at")
ObjectionType = Literal["budget", "timing", "authority", "need", "competitor", "trust", "followup", "custom"]
Goal = Literal["cold_outreach", "demo_request", "event_invite", "follow_up", "re_engagement"]
MAX_BODY_CHARS = 6000
MAX_DRAFT_IDS = 100


class SpamReplacement(BaseModel):
    """One word/phrase swap for fix_draft_spam_words."""
    original: str = Field(min_length=1, description="Exact text to replace")
    replacement: str = Field(min_length=1, description="Text to put in its place")


def _trim_body(d: dict) -> dict:
    for key in ("body_html", "body_text"):
        v = d.get(key)
        if isinstance(v, str) and len(v) > MAX_BODY_CHARS:
            d[key] = v[:MAX_BODY_CHARS] + " …[truncated]"
    return d


def _draft_summary(d: dict, with_body: bool = False) -> dict:
    out = pick(d, DRAFT_FIELDS + (("body_html", "body_text", "flagged_words") if with_body else ()))
    contact = d.get("contact") or {}
    if contact:
        out["to"] = {"email": contact.get("email"),
                     "name": f"{contact.get('first_name') or ''} {contact.get('last_name') or ''}".strip(),
                     "company": contact.get("client_name")}
    mailbox = d.get("mailbox") or {}
    if mailbox:
        out["from"] = mailbox.get("email")
    if with_body and isinstance(d.get("lead"), dict):
        out["lead"] = d["lead"]
    return _trim_body(out)


def register(mcp: MCPServer, rt: Runtime) -> None:
    write = not rt.settings.read_only

    async def owned_ids(ctx: Context, path_fmt: str, ids: list) -> list:
        """ids that a tenant-scoped GET does NOT find (i.e. not in this workspace)."""
        sem = asyncio.Semaphore(8)

        async def missing(i: int) -> Optional[int]:
            async with sem:
                try:
                    await rt.get(ctx, path_fmt.format(i))
                    return None
                except ToolError:
                    return i

        return [i for i in await asyncio.gather(*(missing(i) for i in ids)) if i is not None]

    # ── email templates ─────────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def get_email_template(ctx: Context, template_id: int) -> dict:
        """One email template with its full subject and body (merge fields like {{contact_first_name}},
        {{company_name}}, {{job_title}}, {{sender_first_name}}, {{signature}})."""
        return _trim_body(pick(await rt.get(ctx, f"/templates/{template_id}"), TEMPLATE_FIELDS))

    @mcp.tool(annotations=READ)
    async def preview_email_template(ctx: Context, template_id: int) -> dict:
        """Render a template with sample data (John at Acme Corp, …) to see how it reads. Saves nothing."""
        return _trim_body(await rt.post(ctx, f"/templates/{template_id}/preview"))

    if write:
        @mcp.tool(annotations=WRITE)
        async def create_email_template(
            ctx: Context, name: str, subject: str, body_html: str, body_text: Optional[str] = None,
            description: Optional[str] = None, goal: Optional[Goal] = None, industry: Optional[str] = None,
            category: Literal["outreach", "followup"] = "outreach",
        ) -> dict:
            """Save a new email template (inactive). Use merge fields such as {{contact_first_name}},
            {{company_name}}, {{job_title}}, {{sender_first_name}} and {{signature}}. `goal`
            follow_up/re_engagement makes it a follow-up template. Make it the default for new
            campaigns with activate_email_template. Needs a workspace admin."""
            body = compact({"name": name, "subject": subject, "body_html": body_html, "body_text": body_text,
                            "description": description, "goal": goal, "industry": industry,
                            "category": category, "status": "inactive"})
            return _trim_body(pick(await rt.post(ctx, "/templates", json=body), TEMPLATE_FIELDS))

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def update_email_template(
            ctx: Context, template_id: int, name: Optional[str] = None, subject: Optional[str] = None,
            body_html: Optional[str] = None, body_text: Optional[str] = None,
            description: Optional[str] = None, goal: Optional[Goal] = None, industry: Optional[str] = None,
            category: Optional[Literal["outreach", "followup"]] = None,
        ) -> dict:
            """Edit a template. Only the fields you pass change. Campaign steps already copied from it
            keep their old text."""
            body = compact({"name": name, "subject": subject, "body_html": body_html, "body_text": body_text,
                            "description": description, "goal": goal, "industry": industry,
                            "category": category})
            if not body:
                return {"status": "no_change", "message": "Pass at least one field to update."}
            return _trim_body(pick(await rt.put(ctx, f"/templates/{template_id}", json=body), TEMPLATE_FIELDS))

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def activate_email_template(ctx: Context, template_id: int) -> dict:
            """Make a template the active one for its category (outreach or follow-up); the previously
            active one in that category is deactivated. New campaigns built with
            create_campaign_from_leads use the active templates."""
            return pick(await rt.post(ctx, f"/templates/{template_id}/activate"), TEMPLATE_LIST_FIELDS)

        @mcp.tool(annotations=WRITE)
        async def duplicate_email_template(ctx: Context, template_id: int) -> dict:
            """Copy a template (as an inactive '<name> (Copy)') so it can be edited safely."""
            return pick(await rt.post(ctx, f"/templates/{template_id}/duplicate"), TEMPLATE_LIST_FIELDS)

        @mcp.tool(annotations=WRITE)
        async def seed_template_library(ctx: Context) -> dict:
            """Add NeuraLeads' 12 starter templates (cold outreach per industry, follow-ups, breakup,
            meeting request…) to the workspace as inactive templates. Super admins only; templates
            that already exist are skipped."""
            return await rt.post(ctx, "/templates/seed-library", errors={
                403: "Seeding the template library is limited to super admins"})

        @mcp.tool(annotations=DESTRUCTIVE)
        async def archive_email_template(ctx: Context, template_id: int, confirm: bool = False) -> dict:
            """Archive (soft-delete) a template; it disappears from the template list. The default
            template can't be archived. Needs an admin-scoped key. Requires confirm=true."""
            t = pick(await rt.get(ctx, f"/templates/{template_id}"), TEMPLATE_LIST_FIELDS)
            if not confirm:
                return confirmation_required("archive_email_template", t)
            await rt.delete(ctx, f"/templates/{template_id}")
            return {"status": "archived", "template_id": template_id}

    # ── AI sequence generator ───────────────────────────────────────────
    if write:
        @mcp.tool(annotations=EXTERNAL)
        async def generate_email_sequence(
            ctx: Context, goal: str, product: str,
            tone: Literal["professional", "casual", "urgent", "friendly"] = "professional",
            num_steps: int = 3, confirm: bool = False,
        ) -> dict:
            """AI-draft a 2–6 step cold email sequence (subject, body and send delay per step) for a goal
            (e.g. 'book intro calls with HR managers at hospitals') and offer (`product`). Costs AI
            credits; saves nothing — keep the steps with create_email_template or add_campaign_step.
            Plan feature: ai_sequence_generator. Requires confirm=true."""
            steps = max(2, min(num_steps, 6))
            if not confirm:
                prices = await rt.get(ctx, "/credits/price-list")
                cost = next((a.get("credits") for a in (prices.get("actions") or [])
                             if a.get("action") == "ai_sequence"), None)
                return confirmation_required("generate_email_sequence", {
                    "goal": goal, "product": product, "tone": tone, "num_steps": steps,
                    "credits": cost, "note": "Charged only when the AI writes it (the template fallback is free)."})
            data = await rt.post(ctx, "/sequence-generator/generate", json={
                "goal": goal, "product": product, "tone": tone, "num_steps": steps})
            if isinstance(data, dict):
                data["steps"] = [_trim_body(s) if isinstance(s, dict) else s for s in data.get("steps") or []]
            return data

    # ── email preview drafts ────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def list_email_drafts(
        ctx: Context, status: Optional[Literal["pending", "approved", "rejected", "sent", "expired"]] = None,
        source: Optional[Literal["campaign", "pipeline", "broadcast"]] = None,
        batch_id: Optional[str] = None, campaign_id: Optional[int] = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        """Personalised emails waiting for review (the email-preview queue), newest first, with spam
        score and counts per status. Bodies are omitted; use get_email_draft. Plan feature:
        email_preview."""
        data = await rt.get(ctx, "/email-preview/drafts", status=status, source=source, batch_id=batch_id,
                            campaign_id=campaign_id, page=max(1, page), per_page=clamp_limit(page_size, 20))
        out = {k: data.get(k) for k in ("total", "page", "per_page", "pages", "pending_count",
                                        "approved_count", "sent_count", "rejected_count") if k in data}
        out["items"] = [_draft_summary(d) for d in items_of(data, ("drafts",))]
        return out

    @mcp.tool(annotations=READ)
    async def get_email_draft(ctx: Context, draft_id: int) -> dict:
        """One draft in full: recipient, sender mailbox, subject, body, flagged spam words, lead."""
        return _draft_summary(await rt.get(ctx, f"/email-preview/drafts/{draft_id}"), with_body=True)

    @mcp.tool(annotations=READ)
    async def check_spam_with_suggestions(ctx: Context, subject: str, body_html: str) -> dict:
        """Spam-score an email (0–100, grade, flagged words) and get replacement suggestions for each
        trigger word. Nothing is saved or sent."""
        return await rt.post(ctx, "/email-preview/spam-check", json={"subject": subject, "body_html": body_html})

    @mcp.tool(annotations=READ)
    async def get_deliverability_score(ctx: Context, mailbox_id: int, subject: str, body_html: str) -> dict:
        """Composite inbox-placement score for sending this email from this mailbox (DNS, spam
        content, blacklist and reputation). Nothing is sent."""
        await rt.get(ctx, f"/mailboxes/{int(mailbox_id)}")  # workspace check
        return await rt.post(ctx, "/email-preview/deliverability-score",
                             json={"mailbox_id": mailbox_id, "subject": subject, "body_html": body_html})

    if write:
        @mcp.tool(annotations=WRITE)
        async def generate_email_drafts(
            ctx: Context, source: Literal["campaign", "pipeline", "broadcast"],
            campaign_id: Optional[int] = None, step_index: Optional[int] = None,
            template_id: Optional[int] = None, mailbox_id: Optional[int] = None,
            contact_ids: Optional[list[int]] = None, limit: int = 30,
        ) -> dict:
            """Create personalised drafts for review — nothing is sent. `campaign`: the given step
            (step_index = step_order) for the campaign's contacts. `pipeline`: up to `limit` eligible
            new contacts. `broadcast`: `contact_ids` with `template_id` from `mailbox_id`. Review with
            list_email_drafts, approve, then send_email_drafts. Limited to 10 runs per hour."""
            if source == "campaign":
                if campaign_id is None or step_index is None:
                    raise ToolError("source='campaign' needs campaign_id and step_index.")
                await rt.get(ctx, f"/campaigns/{campaign_id}")
            if source == "broadcast":
                ids = list(dict.fromkeys(contact_ids or []))
                if not ids or template_id is None or mailbox_id is None:
                    raise ToolError("source='broadcast' needs contact_ids, template_id and mailbox_id.")
                if len(ids) > 200:
                    raise ToolError("At most 200 contacts per broadcast.")
                # The backend doesn't check these belong to the workspace; do it here.
                await rt.get(ctx, f"/templates/{template_id}")
                await rt.get(ctx, f"/mailboxes/{int(mailbox_id)}")
                missing = await owned_ids(ctx, "/contacts/{}", ids)
                if missing:
                    raise ToolError(f"Contacts not found in this workspace: {missing[:20]}")
                contact_ids = ids
            body = compact({"source": source, "campaign_id": campaign_id, "step_index": step_index,
                            "template_id": template_id, "mailbox_id": mailbox_id, "contact_ids": contact_ids,
                            "limit": max(1, min(limit, 100))})
            return await rt.post(ctx, "/email-preview/generate", json=body)

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def update_email_draft(ctx: Context, draft_id: int, subject: Optional[str] = None,
                                     body_html: Optional[str] = None, body_text: Optional[str] = None,
                                     mailbox_id: Optional[int] = None) -> dict:
            """Edit a draft's subject, body or sending mailbox. The spam score is recalculated."""
            body = compact({"subject": subject, "body_html": body_html, "body_text": body_text,
                            "mailbox_id": mailbox_id})
            if not body:
                return {"status": "no_change", "message": "Pass at least one field to update."}
            if mailbox_id is not None:
                await rt.get(ctx, f"/mailboxes/{int(mailbox_id)}")  # workspace check
            return _draft_summary(await rt.put(ctx, f"/email-preview/drafts/{draft_id}", json=body), with_body=True)

        @mcp.tool(annotations=WRITE)
        async def rewrite_email_draft(ctx: Context, draft_id: int) -> dict:
            """Let AI rewrite a draft (keeps the original for comparison). Limited to 20 per hour."""
            return _trim_body(await rt.post(ctx, f"/email-preview/drafts/{draft_id}/ai-rewrite"))

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def fix_draft_spam_words(ctx: Context, draft_id: int, replacements: list[SpamReplacement]) -> dict:
            """Apply word swaps (e.g. from check_spam_with_suggestions) to a draft's subject and body,
            then re-score it."""
            if not replacements:
                return {"status": "no_change", "message": "replacements is empty."}
            return _trim_body(await rt.post(ctx, f"/email-preview/drafts/{draft_id}/spam-fix", json={
                "replacements": [r.model_dump() for r in replacements]}))

        @mcp.tool(annotations=WRITE)
        async def approve_email_drafts(ctx: Context, draft_ids: list[int]) -> dict:
            """Approve pending drafts (up to 100). Approval does NOT send — use send_email_drafts."""
            ids = list(dict.fromkeys(draft_ids))[:MAX_DRAFT_IDS]
            if not ids:
                return {"status": "no_change", "message": "draft_ids is empty."}
            return await rt.post(ctx, "/email-preview/drafts/bulk-approve", json={"draft_ids": ids})

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def reject_email_draft(ctx: Context, draft_id: int) -> dict:
            """Reject a pending draft so it is never sent."""
            return await rt.post(ctx, f"/email-preview/drafts/{draft_id}/reject")

        @mcp.tool(annotations=EXTERNAL)
        async def send_email_drafts(ctx: Context, draft_ids: Optional[list[int]] = None,
                                    batch_id: Optional[str] = None, confirm: bool = False) -> dict:
            """Send APPROVED drafts now: pass draft_ids (up to 100) or a batch_id. Each send passes the
            send gate (unsubscribes, cooldown, valid email, mailbox limits) and may be blocked.
            One draft is sent immediately; several run in the background. Requires confirm=true."""
            if bool(draft_ids) == bool(batch_id):
                raise ToolError("Pass either draft_ids or batch_id.")
            if batch_id:
                data = await rt.get(ctx, "/email-preview/drafts", batch_id=batch_id, status="approved", per_page=100)
                approved = [_draft_summary(d) for d in items_of(data, ("drafts",))]
                if not confirm:
                    return confirmation_required("send_email_drafts", {
                        "batch_id": batch_id, "approved_drafts": data.get("total", len(approved)),
                        "recipients": [d.get("to", {}).get("email") for d in approved][:25]})
                return await rt.post(ctx, "/email-preview/drafts/send-batch", json={"batch_id": batch_id})

            ids = list(dict.fromkeys(draft_ids or []))
            if len(ids) > MAX_DRAFT_IDS:
                return {"status": "rejected", "message": f"At most {MAX_DRAFT_IDS} drafts per call."}
            if not confirm:
                sem = asyncio.Semaphore(8)

                async def load(i: int):
                    async with sem:
                        try:
                            return _draft_summary(await rt.get(ctx, f"/email-preview/drafts/{i}"))
                        except ToolError:
                            return {"draft_id": i, "status": "not_found"}

                drafts = await asyncio.gather(*(load(i) for i in ids))
                not_ready = [d["draft_id"] for d in drafts if d.get("status") != "approved"]
                return confirmation_required("send_email_drafts", {
                    "draft_count": len(ids), "not_approved_will_be_skipped": not_ready,
                    "emails": [{"draft_id": d["draft_id"], "to": d.get("to", {}).get("email"),
                                "from": d.get("from"), "subject": d.get("subject")}
                               for d in drafts if d.get("status") == "approved"][:25]})
            if len(ids) == 1:
                return await rt.post(ctx, f"/email-preview/drafts/{ids[0]}/send")
            return await rt.post(ctx, "/email-preview/drafts/bulk-send", json={"draft_ids": ids})

        @mcp.tool(annotations=DESTRUCTIVE)
        async def delete_email_drafts(ctx: Context, draft_ids: list[int], confirm: bool = False) -> dict:
            """Permanently delete drafts (up to 100). Needs an admin-scoped key. Requires confirm=true."""
            ids = list(dict.fromkeys(draft_ids))[:MAX_DRAFT_IDS]
            if not ids:
                return {"status": "no_change", "message": "draft_ids is empty."}
            if not confirm:
                return confirmation_required("delete_email_drafts", {
                    "draft_ids": ids, "note": "Deleted drafts cannot be recovered."})
            return await rt.delete(ctx, "/email-preview/drafts/bulk", json={"draft_ids": ids})

    # ── objection responses ─────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def list_objection_responses(ctx: Context, objection_type: Optional[ObjectionType] = None,
                                       category: Optional[str] = None, page: int = 1,
                                       page_size: int = 50) -> dict:
        """Saved answers to common prospect objections (budget, timing, authority, competitor…), most
        effective first."""
        data = await rt.get(ctx, "/objections", objection_type=objection_type, category=category,
                            page=max(1, page), page_size=clamp_limit(page_size, 50))
        return {**data, "items": [pick(i, OBJECTION_FIELDS) for i in items_of(data)]}

    if write:
        @mcp.tool(annotations=WRITE)
        async def create_objection_response(ctx: Context, objection_type: ObjectionType, objection_text: str,
                                            response_text: str, category: Optional[str] = None) -> dict:
            """Save an answer to a prospect objection, e.g. objection 'We already use an agency' →
            response text."""
            return await rt.post(ctx, "/objections", json=compact({
                "objection_type": objection_type, "objection_text": objection_text,
                "response_text": response_text, "category": category}))

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def update_objection_response(
            ctx: Context, template_id: int, objection_type: Optional[ObjectionType] = None,
            objection_text: Optional[str] = None, response_text: Optional[str] = None,
            category: Optional[str] = None, effectiveness_score: Optional[int] = None,
        ) -> dict:
            """Edit a saved objection response. Only the fields you pass change; effectiveness 0–100."""
            body = compact({"objection_type": objection_type, "objection_text": objection_text,
                            "response_text": response_text, "category": category,
                            "effectiveness_score": effectiveness_score})
            if not body:
                return {"status": "no_change", "message": "Pass at least one field to update."}
            return await rt.put(ctx, f"/objections/{template_id}", json=body)

        @mcp.tool(annotations=WRITE)
        async def use_objection_response(ctx: Context, template_id: int) -> dict:
            """Get an objection response's text to use in a reply, and count the use (feeds its
            effectiveness ranking)."""
            return await rt.post(ctx, f"/objections/{template_id}/use")

        @mcp.tool(annotations=DESTRUCTIVE)
        async def delete_objection_response(ctx: Context, template_id: int, confirm: bool = False) -> dict:
            """Archive a custom objection response (system ones can't be deleted). Needs an
            admin-scoped key. Requires confirm=true."""
            if not confirm:
                return confirmation_required("delete_objection_response", {"template_id": template_id})
            return await rt.delete(ctx, f"/objections/{template_id}")

    # ── reply macros ────────────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def list_reply_macros(ctx: Context, search: Optional[str] = None, category: Optional[str] = None,
                                page: int = 1, page_size: int = 50) -> dict:
        """Canned inbox replies (macros), most used first."""
        data = await rt.get(ctx, "/reply-macros", search=search, category=category, page=max(1, page),
                            page_size=clamp_limit(page_size, 50))
        return {**data, "items": [_trim_body(pick(i, MACRO_FIELDS)) for i in items_of(data)]}

    if write:
        @mcp.tool(annotations=WRITE)
        async def create_reply_macro(ctx: Context, title: str, body_text: str, body_html: Optional[str] = None,
                                     category: Optional[str] = None) -> dict:
            """Save a canned inbox reply (e.g. 'Send calendar link')."""
            return pick(await rt.post(ctx, "/reply-macros", json=compact({
                "title": title, "body_text": body_text, "body_html": body_html, "category": category})),
                MACRO_FIELDS)

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def update_reply_macro(ctx: Context, macro_id: int, title: Optional[str] = None,
                                     body_text: Optional[str] = None, body_html: Optional[str] = None,
                                     category: Optional[str] = None) -> dict:
            """Edit a reply macro. Only the fields you pass change."""
            body = compact({"title": title, "body_text": body_text, "body_html": body_html, "category": category})
            if not body:
                return {"status": "no_change", "message": "Pass at least one field to update."}
            return pick(await rt.put(ctx, f"/reply-macros/{macro_id}", json=body), MACRO_FIELDS)

        @mcp.tool(annotations=WRITE)
        async def use_reply_macro(ctx: Context, macro_id: int) -> dict:
            """Count a use of a macro (ranks it higher). Get its text from list_reply_macros and send it
            with send_inbox_reply."""
            return await rt.post(ctx, f"/reply-macros/{macro_id}/use")

        @mcp.tool(annotations=DESTRUCTIVE)
        async def delete_reply_macro(ctx: Context, macro_id: int, confirm: bool = False) -> dict:
            """Archive a reply macro. Needs an admin-scoped key. Requires confirm=true."""
            if not confirm:
                return confirmation_required("delete_reply_macro", {"macro_id": macro_id})
            return await rt.delete(ctx, f"/reply-macros/{macro_id}")
