"""Account, credits, dashboard and pipeline-run tools."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from mcp.server.mcpserver import Context, MCPServer

from neuraleads_mcp.runtime import READ, WRITE, Runtime, clamp_limit, pick

PipelineName = Literal["lead_sourcing", "contact_enrichment", "email_validation", "outreach_mailmerge", "outreach_send"]
RUN_FIELDS = ("run_id", "pipeline_name", "status", "started_at", "ended_at", "duration_seconds",
              "progress_pct", "records_processed", "records_success", "records_failed",
              "error_message", "triggered_by", "adapters_used")


def register(mcp: MCPServer, rt: Runtime) -> None:
    @mcp.tool(annotations=READ)
    async def whoami(ctx: Context) -> dict:
        """The NeuraLeads user and workspace this connection acts as (name, role, plan)."""
        me = await rt.get(ctx, "/auth/me")
        out = pick(me, ("user_id", "email", "full_name", "role", "base_role", "tenant_id"))
        if isinstance(me.get("tenant"), dict):
            out["workspace"] = pick(me["tenant"], ("tenant_id", "name", "plan", "industry", "website"))
        out["mcp_read_only"] = rt.settings.read_only
        return out

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
                                 limit: int = 10) -> list:
        """Recent background runs (lead sourcing, enrichment, validation, outreach), newest first.
        Use this to follow a run you just started."""
        runs = await rt.get(ctx, "/pipelines/runs", pipeline_name=pipeline_name, status=status,
                            limit=clamp_limit(limit, 10))
        return [pick(r, RUN_FIELDS) for r in runs] if isinstance(runs, list) else runs

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
