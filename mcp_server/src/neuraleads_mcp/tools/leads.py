"""Lead sourcing and company tools."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from mcp.server.mcpserver import Context, MCPServer

from neuraleads_mcp.runtime import (
    EXTERNAL, READ, WRITE, Runtime, clamp_limit, confirmation_required, pick, pick_list,
)

LeadStatus = Literal["open", "hunting", "closed_hired", "closed_not_hired", "closed_test", "new",
                     "enriched", "validated", "sent", "skipped", "excluded"]
LEAD_FIELDS = ("lead_id", "client_name", "job_title", "state", "posting_date", "lead_status", "source",
               "industry", "company_size", "salary_min", "salary_max", "contact_count", "mailing_status",
               "response_status", "campaign_id", "campaign_status", "intent_tier", "job_link", "created_at")
COMPANY_FIELDS = ("client_id", "client_name", "status", "client_category", "industry", "company_size",
                  "employee_count", "location_state", "website", "domain", "linkedin_url",
                  "enriched_at", "created_at")


def register(mcp: MCPServer, rt: Runtime) -> None:
    write = not rt.settings.read_only

    @mcp.tool(annotations=READ)
    async def search_leads(
        ctx: Context,
        search: Optional[str] = None,
        status: Optional[LeadStatus] = None,
        job_title: Optional[str] = None,
        company: Optional[str] = None,
        states: Optional[list[str]] = None,
        industries: Optional[list[str]] = None,
        source: Optional[str] = None,
        mailing_status: Optional[Literal["Campaign-Active", "Campaign-Paused", "Campaign-Draft",
                                         "Campaign-Closed", "Mailed-Offline", "Not-Mailed",
                                         "Follow-Up-Sent", "Bounced", "No-Valid-Email"]] = None,
        response_status: Optional[Literal["Interested", "Referral", "Question", "Not-Interested",
                                          "Do-Not-Contact", "OOO", "Other", "Replied", "No-Response",
                                          "Not-Contacted"]] = None,
        posted_from: Optional[date] = None,
        posted_to: Optional[date] = None,
        sort_by: Literal["created_at", "posting_date", "client_name", "job_title", "state",
                         "contact_count", "lead_status"] = "created_at",
        sort_order: Literal["asc", "desc"] = "desc",
        page: int = 1,
        page_size: int = 25,
    ) -> dict:
        """Search leads (job postings at target companies). `search` matches company, title, state or
        contact email; digits match a lead id, 'R42' a sourcing run, 'campaign:7' a campaign.
        `states` are US state codes."""
        data = await rt.get(
            ctx, "/leads", search=search, status=status, job_title=job_title, client_name=company,
            state=states, industry=industries, source=source, mailing_status=mailing_status,
            response_status=response_status,
            from_date=posted_from.isoformat() if posted_from else None,
            to_date=posted_to.isoformat() if posted_to else None,
            sort_by=sort_by, sort_order=sort_order, page=max(1, page), page_size=clamp_limit(page_size))
        data = pick_list(data, LEAD_FIELDS)
        if isinstance(data, dict):
            data.pop("total_contact_associations", None)
        return data

    @mcp.tool(annotations=READ)
    async def get_lead(ctx: Context, lead_id: int) -> dict:
        """One lead with its contacts and outreach history."""
        data = await rt.get(ctx, f"/leads/{lead_id}/detail")
        out = pick(data, LEAD_FIELDS + ("employer_website", "employment_type", "skip_reason"))
        out["contacts"] = [pick(c, ("contact_id", "first_name", "last_name", "title", "email",
                                    "validation_status", "outreach_status", "priority_level"))
                           for c in (data.get("contacts") or [])]
        out["outreach_events"] = [pick(e, ("event_id", "contact_email", "sender_email", "sent_at",
                                           "status", "subject", "reply_detected_at", "bounce_reason"))
                                  for e in (data.get("outreach_events") or [])][:50]
        return out

    @mcp.tool(annotations=READ)
    async def get_lead_stats(ctx: Context) -> dict:
        """Lead counts by status, source and campaign status."""
        return await rt.get(ctx, "/leads/stats")

    @mcp.tool(annotations=READ)
    async def ai_lead_search(ctx: Context, query: str, limit: int = 25) -> dict:
        """Natural-language search over existing leads, e.g. 'hospitals in Texas hiring nurses posted
        this week, salary over 60k'. Returns the filters it understood plus matches."""
        return await rt.post(ctx, "/leads/ai-search", json={"query": query, "limit": clamp_limit(limit)})

    @mcp.tool(annotations=READ)
    async def list_lead_sources(ctx: Context, lob_id: Optional[int] = None) -> dict:
        """Lead-sourcing providers available for the workspace (or a line of business)."""
        return await rt.get(ctx, "/pipelines/lead-sourcing/lob-sources", lob_id=lob_id)

    if write:
        @mcp.tool(annotations=EXTERNAL)
        async def run_lead_sourcing(ctx: Context, sources: Optional[list[str]] = None,
                                    lob_id: Optional[int] = None, confirm: bool = False) -> dict:
            """Start a lead-sourcing run that pulls new job postings from job boards (default
            linkedin + indeed). Costs credits per new lead; limited to 5 runs per hour. Runs in the
            background — follow it with list_pipeline_runs(pipeline_name='lead_sourcing').
            Requires confirm=true."""
            chosen = sources or ["linkedin", "indeed"]
            if not confirm:
                balance = await rt.get(ctx, "/credits/balance")
                return confirmation_required("run_lead_sourcing", {
                    "sources": chosen, "lob_id": lob_id,
                    "cost": "1 credit per new lead inserted",
                    "credits_remaining": balance.get("total_remaining")})
            started = await rt.post(ctx, "/pipelines/lead-sourcing/run", sources=chosen, lob_id=lob_id)
            started["follow_up"] = "Call list_pipeline_runs(pipeline_name='lead_sourcing', limit=1) to track it."
            return started

        @mcp.tool(annotations=WRITE)
        async def update_lead_status(ctx: Context, lead_ids: list[int], status: LeadStatus) -> dict:
            """Change the status of leads (e.g. mark closed_hired). Invalid transitions are rejected
            per lead and listed in `rejected`."""
            if not lead_ids:
                return {"status": "no_change", "message": "lead_ids is empty."}
            return await rt.put(ctx, "/leads/bulk/status", json={"lead_ids": lead_ids[:500], "status": status})

    # ── companies ───────────────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def search_companies(
        ctx: Context, search: Optional[str] = None, industries: Optional[list[str]] = None,
        state: Optional[str] = None,
        category: Optional[Literal["regular", "occasional", "prospect", "dormant"]] = None,
        sort_by: Literal["client_name", "created_at", "industry", "company_size", "enriched_at"] = "client_name",
        sort_order: Literal["asc", "desc"] = "asc", offset: int = 0, limit: int = 25,
    ) -> dict:
        """Search target companies (clients) with firmographics."""
        data = await rt.get(ctx, "/clients", search=search, industry=industries, location_state=state,
                            category=category, sort_by=sort_by, sort_order=sort_order,
                            skip=max(0, offset), limit=clamp_limit(limit))
        return pick_list(data, COMPANY_FIELDS)

    @mcp.tool(annotations=READ)
    async def get_company(ctx: Context, company_id: int) -> dict:
        """One company's full profile."""
        return await rt.get(ctx, f"/clients/{company_id}")

    if write:
        @mcp.tool(annotations=EXTERNAL)
        async def enrich_company(ctx: Context, company_id: int) -> dict:
            """Fill in a company's firmographics (industry, size, HQ, website…) using AI research.
            Returns the fields that changed."""
            return await rt.post(ctx, f"/clients/{company_id}/enrich")
