"""Reporting tools (read-only)."""
from __future__ import annotations

from typing import Literal, Optional

from mcp.server.mcpserver import Context, MCPServer

from neuraleads_mcp.runtime import READ, Runtime, clamp_limit

SortOrder = Literal["asc", "desc"]


def register(mcp: MCPServer, rt: Runtime) -> None:
    @mcp.tool(annotations=READ)
    async def report_campaign_performance(
        ctx: Context, search: Optional[str] = None, status: Optional[str] = None,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        sort_by: Literal["name", "status", "total_contacts", "sent", "total_opened", "total_replied",
                         "total_bounced", "health_score", "created_at"] = "created_at",
        sort_order: SortOrder = "desc", page: int = 1, page_size: int = 25,
    ) -> dict:
        """Per-campaign sent / open / reply / bounce / unsubscribe counts and rates.
        Dates are YYYY-MM-DD (campaign creation date)."""
        return await rt.get(ctx, "/reports/campaign-performance", search=search, status=status,
                            date_from=date_from, date_to=date_to, sort_by=sort_by, sort_order=sort_order,
                            page=max(1, page), page_size=clamp_limit(page_size))

    @mcp.tool(annotations=READ)
    async def report_mailbox_health(
        ctx: Context, search: Optional[str] = None, warmup_status: Optional[str] = None,
        sort_by: Literal["email", "warmup_status", "connection_status", "emails_sent_today",
                         "total_emails_sent", "bounce_count", "reply_count", "complaint_count"] = "bounce_count",
        sort_order: SortOrder = "desc", page: int = 1, page_size: int = 25,
    ) -> dict:
        """Per-mailbox deliverability table (bounce and complaint rates, volume, status)."""
        return await rt.get(ctx, "/reports/mailbox-health", search=search, warmup_status=warmup_status,
                            sort_by=sort_by, sort_order=sort_order, page=max(1, page),
                            page_size=clamp_limit(page_size))

    @mcp.tool(annotations=READ)
    async def report_daily_activity(ctx: Context, days: int = 30,
                                    granularity: Literal["daily", "weekly"] = "daily") -> dict:
        """Time series of emails sent, opened, replied and bounced (7–180 days)."""
        return await rt.get(ctx, "/reports/daily-activity", days=max(7, min(days, 180)), granularity=granularity)

    @mcp.tool(annotations=READ)
    async def report_client_analytics(
        ctx: Context, search: Optional[str] = None, industry: Optional[str] = None,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        page: int = 1, page_size: int = 25,
    ) -> dict:
        """Per-company outreach results: contacts, leads, sent, replies, bounces, placements."""
        return await rt.get(ctx, "/reports/client-analytics", search=search, industry=industry,
                            date_from=date_from, date_to=date_to, page=max(1, page),
                            page_size=clamp_limit(page_size))
