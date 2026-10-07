"""Builds the NeuraLeads MCP server (tools and prompts)."""
from __future__ import annotations

import importlib
from contextlib import asynccontextmanager
from typing import Optional

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from neuraleads_mcp import __version__
from neuraleads_mcp.client import NeuraLeadsClient
from neuraleads_mcp.config import Settings
from neuraleads_mcp.runtime import Runtime

TOOL_MODULES = ("account", "leads", "contacts", "data", "mailboxes", "campaigns", "content", "outreach",
                "inbox", "reports")

INSTRUCTIONS = """\
NeuraLeads is a cold-outreach platform. The pipeline is:
1. Lead sourcing: job postings at target companies become leads (run_lead_sourcing, search_leads,
   create_lead, import_google_sheet).
2. Contact enrichment: decision-maker contacts are found for each lead (run_contact_enrichment).
3. Email validation: only contacts whose email is 'valid' can be emailed (validate_contact_emails).
4. Outreach: campaigns send multi-step email sequences from warmed-up sender mailboxes. Content
   lives in email templates (create_email_template) and the review queue of personalised drafts
   (list_email_drafts). send_lead_outreach emails a lead's contacts directly, outside campaigns.
5. Inbox: replies land in a unified inbox (list_inbox_threads, send_inbox_reply, reply macros).

Rules the platform enforces (you cannot override them): a daily send limit per mailbox, a cooldown
between emails to the same contact, a cap on contacts per company per job, excluded companies
(list_company_exclusions), unsubscribes, and valid-email-only outreach. Paid actions spend workspace
credits; call get_credit_balance first when planning a large run.

Tools that send email, launch or change campaigns, change mailbox status, cost credits or delete
data return status='confirmation_required' unless called with confirm=true. Always show the user
what will happen and get their agreement before repeating the call with confirm=true. Never set
confirm=true on your own initiative. Deletes also need an API key with 'admin' scope.
Passwords and OAuth tokens never pass through these tools: mailboxes are connected in the web app
(mailbox_oauth_link).
whoami shows which workspace you act in. Super-admin keys pick one with list_workspaces and the
X-Tenant-ID header (or NEURALEADS_TENANT_ID locally).
List tools are paginated; ask for more pages rather than huge limits.
"""


def build_server(settings: Settings, *, hosted: bool = False,
                 client: Optional[NeuraLeadsClient] = None) -> tuple[MCPServer, Runtime]:
    rt = Runtime(settings, client, hosted=hosted)

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield {}
        finally:
            if client is None:  # we own it
                await rt.client.aclose()

    mcp = MCPServer(
        name="neuraleads",
        title="NeuraLeads",
        description="Lead sourcing, contact enrichment, email validation, outreach campaigns, "
                    "mailbox warmup and inbox for NeuraLeads.",
        instructions=INSTRUCTIONS,
        website_url="https://neuraleads.ai",
        version=__version__,
        log_level=settings.log_level if settings.log_level in
        ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL") else "INFO",
        lifespan=lifespan if hosted else None,
    )

    for name in TOOL_MODULES:
        importlib.import_module(f"neuraleads_mcp.tools.{name}").register(mcp, rt)

    _register_prompts(mcp)

    @mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "neuraleads-mcp", "version": __version__,
                             "read_only": settings.read_only})

    return mcp, rt


def _register_prompts(mcp: MCPServer) -> None:
    @mcp.prompt(title="Weekly pipeline review")
    def weekly_pipeline_review() -> str:
        """Summarise the last 7 days of sourcing, enrichment, outreach and replies."""
        return ("Review my NeuraLeads pipeline for the last 7 days. Use get_dashboard_kpis, "
                "report_daily_activity (days=7), report_campaign_performance and get_inbox_stats. "
                "Summarise: leads sourced, contacts found, valid emails, emails sent, reply and bounce "
                "rates, the best and worst campaigns, and unread replies needing attention. "
                "End with 3 concrete recommendations. Do not change anything.")

    @mcp.prompt(title="Mailbox health triage")
    def mailbox_health_triage() -> str:
        """Find mailboxes that are hurting deliverability and propose fixes."""
        return ("Check the health of my sender mailboxes. Use get_warmup_overview, "
                "report_mailbox_health (sorted by bounce_count), list_warmup_alerts (unread_only=true) "
                "and get_deliverability_summary. List mailboxes with failed connections, health below 70, "
                "bounce rate above 3%, blacklistings or DNS problems, and propose a fix for each "
                "(e.g. set_mailbox_status to pause, start_warmup_recovery, or reconnecting via "
                "mailbox_oauth_link). Ask me before pausing any mailbox, starting recovery or running checks.")

    @mcp.prompt(title="Launch a campaign for leads")
    def launch_campaign_for_leads(target: str = "my newest leads with valid contacts") -> str:
        """Walk through creating and launching an outreach campaign."""
        return (f"Help me launch an outreach campaign for: {target}.\n"
                "1. Find suitable leads with list_campaign_ready_leads.\n"
                "2. Check credits with get_credit_balance and sending capacity with get_mailbox_stats.\n"
                "3. Draft the campaign with create_campaign_from_leads (it returns a preview first).\n"
                "4. Show me the sequence steps (get_campaign) and suggest subject lines; spam-check each "
                "step with check_spam_with_suggestions and offer fixes.\n"
                "5. Only after I approve, activate it with activate_campaign and confirm=true.")

    @mcp.prompt(title="Content studio")
    def content_studio(offer: str = "our staffing services", audience: str = "HR managers at mid-size companies") -> str:
        """Draft a 3-step email sequence, spam-check it and save it as templates."""
        return (f"Write a 3-step cold email sequence selling {offer} to {audience}.\n"
                "1. Draft it yourself, or with generate_email_sequence (num_steps=3) — that one costs "
                "credits, so ask me first. Keep each email under 120 words, one clear ask, and use merge "
                "fields {{contact_first_name}}, {{company_name}}, {{job_title}} and {{sender_first_name}}.\n"
                "2. Run check_spam_with_suggestions on every step; rewrite until each grades A or B and "
                "show me the scores.\n"
                "3. After I approve the copy, save step 1 with create_email_template (goal=cold_outreach) "
                "and steps 2–3 with goal=follow_up, then preview each with preview_email_template.\n"
                "4. Ask before making any of them active (activate_email_template). Send nothing.")
