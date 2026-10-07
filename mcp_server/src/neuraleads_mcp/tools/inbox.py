"""Unified inbox tools (replies to outreach)."""
from __future__ import annotations

from typing import Literal, Optional

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from neuraleads_mcp.runtime import (
    EXTERNAL, READ, WRITE, WRITE_IDEMPOTENT, Runtime, clamp_limit, confirmation_required, pick,
)

Category = Literal["interested", "not_interested", "ooo", "question", "referral", "do_not_contact", "other"]
MESSAGE_FIELDS = ("message_id", "direction", "from_email", "from_name", "to_email", "subject", "body_text",
                  "received_at", "is_read", "category", "sentiment", "mailbox_id")
MAX_BODY_CHARS = 4000


def _trim_message(m: dict) -> dict:
    out = pick(m, MESSAGE_FIELDS)
    body = out.get("body_text") or ""
    if not body and m.get("body_html"):
        out["body_html"] = m["body_html"][:MAX_BODY_CHARS]
    elif len(body) > MAX_BODY_CHARS:
        out["body_text"] = body[:MAX_BODY_CHARS] + " …[truncated]"
    return out


def register(mcp: MCPServer, rt: Runtime) -> None:
    write = not rt.settings.read_only

    @mcp.tool(annotations=READ)
    async def list_inbox_threads(
        ctx: Context, category: Optional[Category] = None, unread_only: bool = False,
        mailbox_ids: Optional[list[int]] = None, campaign_ids: Optional[list[int]] = None,
        search: Optional[str] = None, page: int = 1, page_size: int = 20,
    ) -> dict:
        """Inbox conversations, latest first, with category (interested, question, ooo, …),
        sentiment, unread count and a snippet."""
        return await rt.get(ctx, "/inbox/threads", category=category, is_read=False if unread_only else None,
                            mailbox_id=mailbox_ids, campaign_id=campaign_ids, search=search,
                            page=max(1, page), page_size=clamp_limit(page_size, 20))

    @mcp.tool(annotations=READ)
    async def get_inbox_thread(ctx: Context, thread_id: str) -> dict:
        """A full conversation (oldest first) with the contact's details."""
        data = await rt.get(ctx, f"/inbox/threads/{thread_id}")
        data["messages"] = [_trim_message(m) for m in (data.get("messages") or [])]
        return data

    @mcp.tool(annotations=READ)
    async def get_inbox_stats(ctx: Context) -> dict:
        """Thread totals, unread threads, and threads per category."""
        return await rt.get(ctx, "/inbox/stats")

    @mcp.tool(annotations=READ)
    async def list_reply_drafts(ctx: Context, thread_id: str) -> dict:
        """AI reply drafts awaiting approval for a thread."""
        return await rt.get(ctx, f"/inbox/threads/{thread_id}/drafts")

    if not write:
        return

    @mcp.tool(annotations=READ)
    async def suggest_reply(ctx: Context, thread_id: str) -> dict:
        """An AI-suggested reply for a thread (subject + body). Saves and sends nothing."""
        return await rt.post(ctx, f"/inbox/threads/{thread_id}/suggest-reply")

    @mcp.tool(annotations=WRITE_IDEMPOTENT)
    async def mark_thread_read(ctx: Context, thread_id: str) -> dict:
        """Mark every message in a thread as read."""
        return await rt.put(ctx, f"/inbox/threads/{thread_id}/read")

    @mcp.tool(annotations=WRITE_IDEMPOTENT)
    async def categorize_thread(ctx: Context, thread_id: str, category: Category) -> dict:
        """Set a thread's category (e.g. interested, not_interested, do_not_contact)."""
        return await rt.put(ctx, f"/inbox/threads/{thread_id}/category", json={"category": category})

    @mcp.tool(annotations=WRITE)
    async def generate_reply_draft(ctx: Context, thread_id: str) -> dict:
        """Create an AI reply draft for the latest received message. It is saved as pending and NOT sent;
        send it with approve_reply_draft."""
        return await rt.post(ctx, f"/inbox/threads/{thread_id}/generate-draft")

    @mcp.tool(annotations=EXTERNAL)
    async def approve_reply_draft(ctx: Context, thread_id: str, draft_id: int, confirm: bool = False) -> dict:
        """Approve a pending AI draft and send it immediately from the thread's mailbox (send-safety
        checks apply). Requires confirm=true."""
        if not confirm:
            drafts = (await rt.get(ctx, f"/inbox/threads/{thread_id}/drafts")).get("drafts") or []
            draft = next((d for d in drafts if d.get("draft_id") == draft_id), None)
            if draft is None:
                raise ToolError(f"Draft {draft_id} is not pending on thread {thread_id}.")
            return confirmation_required("approve_reply_draft", {
                "thread_id": thread_id, "subject": draft.get("subject"),
                "body_text": (draft.get("body_text") or "")[:MAX_BODY_CHARS]})
        return await rt.post(ctx, f"/inbox/threads/{thread_id}/drafts/{draft_id}/approve")

    @mcp.tool(annotations=WRITE_IDEMPOTENT)
    async def reject_reply_draft(ctx: Context, thread_id: str, draft_id: int) -> dict:
        """Discard a pending AI draft."""
        return await rt.post(ctx, f"/inbox/threads/{thread_id}/drafts/{draft_id}/reject")

    @mcp.tool(annotations=EXTERNAL)
    async def send_inbox_reply(ctx: Context, thread_id: str, body_text: str,
                               mailbox_id: Optional[int] = None, body_html: Optional[str] = None,
                               confirm: bool = False) -> dict:
        """Send a reply in a thread right away (subject is 'Re: …' of the thread). Uses the thread's
        mailbox unless mailbox_id is given. Refuses if the contact unsubscribed or is do-not-contact.
        Requires confirm=true."""
        if not body_text.strip():
            raise ToolError("body_text is empty.")
        thread = await rt.get(ctx, f"/inbox/threads/{thread_id}")
        messages = thread.get("messages") or []
        if not messages:
            raise ToolError("Thread has no messages.")
        if any(m.get("category") == "do_not_contact" for m in messages):
            raise ToolError("This thread is marked do_not_contact; not sending.")
        contact = thread.get("contact") or {}
        if contact.get("contact_id"):
            details = await rt.get(ctx, f"/contacts/{contact['contact_id']}")
            if details.get("outreach_status") == "unsubscribed" or details.get("unsubscribed_at"):
                raise ToolError("This contact has unsubscribed; not sending.")
        sender = mailbox_id or next((m.get("mailbox_id") for m in reversed(messages) if m.get("mailbox_id")), None)
        if not sender:
            raise ToolError("Could not tell which mailbox to send from; pass mailbox_id.")
        if not confirm:
            last_in = next((m for m in reversed(messages) if m.get("direction") == "received"), messages[-1])
            return confirmation_required("send_inbox_reply", {
                "to": contact.get("email") or last_in.get("from_email"), "from_mailbox_id": sender,
                "subject": messages[0].get("subject"), "body_text": body_text[:MAX_BODY_CHARS]})
        html = body_html or "<p>" + body_text.replace("&", "&amp;").replace("<", "&lt;").replace(
            ">", "&gt;").replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
        return await rt.post(ctx, "/inbox/reply", json={"thread_id": thread_id, "mailbox_id": sender,
                                                        "body_html": html, "body_text": body_text})
