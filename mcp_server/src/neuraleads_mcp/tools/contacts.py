"""Contact, enrichment and email-validation tools."""
from __future__ import annotations

from typing import Literal, Optional

from mcp.server.mcpserver import Context, MCPServer

from neuraleads_mcp.runtime import (
    EXTERNAL, READ, Runtime, clamp_limit, confirmation_required, pick, pick_list,
)

CONTACT_FIELDS = ("contact_id", "first_name", "last_name", "title", "email", "phone", "client_name",
                  "location_state", "linkedin_url", "priority_level", "validation_status",
                  "outreach_status", "source", "lead_ids", "last_outreach_date", "created_at")
MAX_ENRICH_LEADS = 200
MAX_VALIDATE_CONTACTS = 500


def register(mcp: MCPServer, rt: Runtime) -> None:
    write = not rt.settings.read_only

    @mcp.tool(annotations=READ)
    async def search_contacts(
        ctx: Context,
        search: Optional[str] = None,
        company: Optional[str] = None,
        lead_id: Optional[int] = None,
        validation_status: Optional[Literal["valid", "invalid", "catch_all", "unknown"]] = None,
        outreach_status: Optional[Literal["active", "inactive", "unsubscribed"]] = None,
        priority_level: Optional[Literal["p1_job_poster", "p2_hr_ta_recruiter", "p3_hr_manager",
                                         "p4_ops_leader", "p5_functional_manager"]] = None,
        state: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict:
        """Search decision-maker contacts. `search` matches name or email. Only `valid` emails are
        eligible for outreach."""
        data = await rt.get(ctx, "/contacts", search=search, client_name=company, lead_id=lead_id,
                            validation_status=validation_status, outreach_status=outreach_status,
                            priority_level=priority_level, state=state, page=max(1, page),
                            page_size=clamp_limit(page_size))
        return pick_list(data, CONTACT_FIELDS)

    @mcp.tool(annotations=READ)
    async def get_contact(ctx: Context, contact_id: int) -> dict:
        """One contact's details."""
        return pick(await rt.get(ctx, f"/contacts/{contact_id}"), CONTACT_FIELDS + ("timezone", "unsubscribed_at"))

    @mcp.tool(annotations=READ)
    async def get_contacts_for_lead(ctx: Context, lead_id: int) -> dict:
        """Contacts found for a lead, best priority first."""
        data = await rt.get(ctx, f"/contacts/by-lead/{lead_id}")
        if isinstance(data, dict) and isinstance(data.get("contacts"), list):
            data["contacts"] = [pick(c, CONTACT_FIELDS) for c in data["contacts"]]
        return data

    @mcp.tool(annotations=READ)
    async def get_contact_stats(ctx: Context) -> dict:
        """Contact totals by priority and by email-validation status."""
        return await rt.get(ctx, "/contacts/stats")

    @mcp.tool(annotations=READ)
    async def preview_contact_enrichment(ctx: Context, lead_ids: list[int]) -> dict:
        """Dry run for enriching specific leads: which leads would be enriched or skipped, and how many
        contacts can be reused from cache vs. need a paid lookup. Costs nothing."""
        return await rt.post(ctx, "/leads/bulk/enrich/preview", json={"lead_ids": lead_ids[:MAX_ENRICH_LEADS]})

    @mcp.tool(annotations=READ)
    async def estimate_contact_enrichment(ctx: Context) -> dict:
        """Estimate for the default enrichment batch (new leads without contacts): eligible leads,
        cache hits, expected API calls, configured providers."""
        return await rt.get(ctx, "/pipelines/contact-enrichment/estimate")

    if write:
        @mcp.tool(annotations=EXTERNAL)
        async def run_contact_enrichment(ctx: Context, lead_ids: list[int], confirm: bool = False) -> dict:
            """Find decision-maker contacts for up to 200 leads. Costs credits per contact found. Runs in
            the background and returns a run_id for get_pipeline_run. Requires confirm=true."""
            ids = list(dict.fromkeys(lead_ids))
            if not ids:
                return {"status": "no_change", "message": "lead_ids is empty."}
            if len(ids) > MAX_ENRICH_LEADS:
                return {"status": "rejected", "message": f"At most {MAX_ENRICH_LEADS} leads per run."}
            if not confirm:
                preview = await rt.post(ctx, "/leads/bulk/enrich/preview", json={"lead_ids": ids})
                prices = await rt.get(ctx, "/credits/price-list")
                cost = next((a.get("credits") for a in prices.get("actions", [])
                             if a.get("action") == "contact_enriched"), None)
                return confirmation_required(
                    "run_contact_enrichment",
                    {"lead_count": len(ids), "credits_per_contact_found": cost},
                    preview=preview.get("summary") if isinstance(preview, dict) else preview)
            return await rt.post(ctx, "/leads/bulk/enrich", json={"lead_ids": ids})

        @mcp.tool(annotations=EXTERNAL)
        async def validate_contact_emails(ctx: Context, contact_ids: list[int], confirm: bool = False) -> dict:
            """Verify the email addresses of specific contacts (up to 500). Costs 1 credit per email.
            Runs in the background — follow with list_pipeline_runs(pipeline_name='email_validation').
            Requires confirm=true."""
            ids = list(dict.fromkeys(contact_ids))
            if not ids:
                return {"status": "no_change", "message": "contact_ids is empty."}
            if len(ids) > MAX_VALIDATE_CONTACTS:
                return {"status": "rejected", "message": f"At most {MAX_VALIDATE_CONTACTS} contacts per call."}
            if not confirm:
                return confirmation_required("validate_contact_emails", {
                    "contact_count": len(ids), "cost": "1 credit per email validated"})
            return await rt.post(ctx, "/pipelines/email-validation/run-selected", json={"contact_ids": ids})

        @mcp.tool(annotations=EXTERNAL)
        async def validate_all_pending_emails(ctx: Context, confirm: bool = False) -> dict:
            """Verify every contact whose email has not been validated yet. Costs 1 credit per email.
            Runs in the background. Requires confirm=true."""
            if not confirm:
                stats = await rt.get(ctx, "/contacts/stats")
                return confirmation_required("validate_all_pending_emails", {
                    "contacts_by_validation_status": stats.get("by_validation"),
                    "cost": "1 credit per email validated"})
            started = await rt.post(ctx, "/pipelines/email-validation/run")
            started["follow_up"] = "Call list_pipeline_runs(pipeline_name='email_validation', limit=1) to track it."
            return started
