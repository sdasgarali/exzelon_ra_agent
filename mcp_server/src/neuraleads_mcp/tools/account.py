"""Account, credits, dashboard and pipeline-run tools."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from mcp.server.mcpserver import Context, MCPServer

from neuraleads_mcp.runtime import READ, WRITE, Runtime, as_items, clamp_limit, pick

PipelineName = Literal["lead_sourcing", "contact_enrichment", "email_validation", "outreach_mailmerge", "outreach_send"]
RUN_FIELDS = ("run_id", "pipeline_name", "status", "started_at", "ended_at", "duration_seconds",
              "progress_pct", "records_processed", "records_success", "records_failed",
              "error_message", "triggered_by", "adapters_used")


def register(mcp: MCPServer, rt: Runtime) -> None:
    @mcp.tool(annotations=READ)
    async def whoami(ctx: Context) -> dict:
        """The NeuraLeads user and workspace this connection acts as (name, role, plan), and the
        effective workspace id every other tool uses."""
        me = await rt.get(ctx, "/auth/me")
        out = pick(me, ("user_id", "email", "full_name", "role", "base_role", "tenant_id"))
        if isinstance(me.get("tenant"), dict):
            out["workspace"] = pick(me["tenant"], ("tenant_id", "name", "plan", "industry", "website"))
        selected = rt.tenant_for(ctx)
        is_super = str(me.get("role") or "").lower() == "super_admin"
        if is_super and selected is not None:
            out["effective_workspace_id"] = selected
            out["workspace_selected_by"] = "X-Tenant-ID"
        elif is_super:
            out["effective_workspace_id"] = None
            out["workspace_note"] = ("Super-admin key with no workspace selected: reads span all "
                                     "workspaces and most writes are refused. Pick one with "
                                     "list_workspaces and set X-Tenant-ID / NEURALEADS_TENANT_ID.")
        else:
            out["effective_workspace_id"] = me.get("tenant_id")
            if selected is not None and selected != me.get("tenant_id"):
                out["workspace_note"] = "X-Tenant-ID is ignored: only super-admin keys can switch workspace."
        out["mcp_read_only"] = rt.settings.read_only
        return out

    @mcp.tool(annotations=READ)
    async def list_workspaces(ctx: Context, search: Optional[str] = None, offset: int = 0,
                              limit: int = 50) -> dict:
        """Super admins only: every workspace (tenant) with its plan and lead/contact/mailbox/campaign
        counts. Use a workspace's tenant_id as the X-Tenant-ID header (hosted) or
        NEURALEADS_TENANT_ID (local) to act inside it."""
        rows = await rt.get(ctx, "/admin/tenants", search=search, skip=max(0, offset),
                            limit=clamp_limit(limit, 50), errors={
                                403: "list_workspaces needs a super-admin user's API key with 'admin' scope; "
                                     "other keys always act in their own workspace"})
        return as_items(rows, ("tenant_id", "name", "slug", "plan", "is_active", "industry",
                               "user_count", "lead_count", "contact_count", "mailbox_count",
                               "campaign_count", "created_at"))

    @mcp.tool(annotations=READ)
    async def get_credit_balance(ctx: Context) -> dict:
        """Credits left this month (plan allowance + top-ups) and the monthly email send quota."""
        return await rt.get(ctx, "/credits/balance")

    @mcp.tool(annotations=READ)
    async def get_price_list(ctx: Context) -> dict:
        """What each paid action costs in credits (lead sourced, contact enriched, email validated, …)."""
        return await rt.get(ctx, "/credits/price-list")

    @mcp.tool(annotations=READ)
    async def get_dashboard_kpis(ctx: Context, from_date: Optional[date] = None,
                                 to_date: Optional[date] = None) -> dict:
        """Headline KPIs. Leads/companies and emails sent/bounced/replied cover the date window
        (default: last 30 days); contacts and valid emails are all-time totals."""
        return await rt.get(ctx, "/dashboard/kpis",
                            from_date=from_date.isoformat() if from_date else None,
                            to_date=to_date.isoformat() if to_date else None)

    @mcp.tool(annotations=READ)
    async def get_pipeline_overview(ctx: Context) -> dict:
        """All-time totals across the pipeline: leads by status/source, contacts by validation status,
        outreach results, mailboxes by warmup status, templates."""
        return await rt.get(ctx, "/dashboard/stats")

    @mcp.tool(annotations=READ)
    async def get_business_rules(ctx: Context) -> dict:
        """Outreach rules in force: daily send limit per mailbox, cooldown days between emails to the
        same contact, max contacts per company per job."""
        return await rt.get(ctx, "/pipelines/business-rules")

    @mcp.tool(annotations=READ)
    async def list_pipeline_runs(ctx: Context, pipeline_name: Optional[PipelineName] = None,
                                 status: Optional[Literal["pending", "running", "completed", "failed", "cancelled"]] = None,
                                 limit: int = 10) -> dict:
        """Recent background runs (lead sourcing, enrichment, validation, outreach), newest first.
        Use this to follow a run you just started."""
        runs = await rt.get(ctx, "/pipelines/runs", pipeline_name=pipeline_name, status=status,
                            limit=clamp_limit(limit, 10))
        return as_items(runs, RUN_FIELDS)

    @mcp.tool(annotations=READ)
    async def get_pipeline_run(ctx: Context, run_id: int, include_summary: bool = False) -> dict:
        """Status and counters of one run. Finished runs can include an AI summary with highlights
        and suggestions (include_summary=true)."""
        run = await rt.get(ctx, f"/pipelines/runs/{run_id}")
        out = pick(run, RUN_FIELDS + ("counters",))
        results = run.get("lead_results") if isinstance(run, dict) else None
        if isinstance(results, list):
            out["lead_results_count"] = len(results)
            out["lead_results_sample"] = results[:10]
        if include_summary and out.get("status") in ("completed", "failed", "cancelled"):
            summary = await rt.get(ctx, f"/pipelines/runs/{run_id}/summary")
            out["summary"] = pick(summary, ("summary", "highlights", "success_score", "quality_funnel",
                                            "error_analysis", "suggestions"))
        return out

    if not rt.settings.read_only:
        @mcp.tool(annotations=WRITE)
        async def cancel_pipeline_run(ctx: Context, run_id: int) -> dict:
            """Ask a running background run to stop."""
            return await rt.post(ctx, f"/pipelines/jobs/{run_id}/cancel")
