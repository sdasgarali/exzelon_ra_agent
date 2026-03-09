"""Generate Instantly.ai vs Exzelon RA Agent comparison document (.docx).

Run: python scripts/generate_comparison_doc.py
Produces: Instantly_vs_Exzelon_Comparison.docx in project root.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml


# ── Color Constants ──
GREEN = "22C55E"
RED = "EF4444"
YELLOW = "F59E0B"
BLUE = "3B82F6"
GRAY = "6B7280"
LIGHT_GREEN = "DCFCE7"
LIGHT_RED = "FEE2E2"
LIGHT_YELLOW = "FEF3C7"
LIGHT_BLUE = "DBEAFE"
WHITE = "FFFFFF"
DARK = "1F2937"


def set_cell_shading(cell, color):
    """Set background color on a table cell."""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def set_cell_text(cell, text, bold=False, color=None, size=None, align=None):
    """Set text in a cell with formatting."""
    cell.text = ""
    p = cell.paragraphs[0]
    if align:
        p.alignment = align
    run = p.add_run(str(text))
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if size:
        run.font.size = Pt(size)


def add_comparison_table(doc, headers, rows, col_widths=None):
    """Add a styled comparison table with header row."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Style header row
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        set_cell_shading(cell, "1E3A5F")
        set_cell_text(cell, header, bold=True, color=WHITE, size=10)

    # Data rows
    for row_idx, row_data in enumerate(rows):
        bg = WHITE if row_idx % 2 == 0 else "F3F4F6"
        for col_idx, value in enumerate(row_data):
            cell = table.rows[row_idx + 1].cells[col_idx]
            set_cell_shading(cell, bg)
            # Color-code status cells
            text = str(value)
            if col_idx > 0:
                if text.startswith("[YES]"):
                    set_cell_shading(cell, LIGHT_GREEN)
                    set_cell_text(cell, text.replace("[YES]", "").strip(), size=9, color="166534")
                elif text.startswith("[NO]"):
                    set_cell_shading(cell, LIGHT_RED)
                    set_cell_text(cell, text.replace("[NO]", "").strip(), size=9, color="991B1B")
                elif text.startswith("[PARTIAL]"):
                    set_cell_shading(cell, LIGHT_YELLOW)
                    set_cell_text(cell, text.replace("[PARTIAL]", "").strip(), size=9, color="92400E")
                else:
                    set_cell_text(cell, text, size=9)
            else:
                set_cell_text(cell, text, bold=True, size=9)

    # Set column widths if provided
    if col_widths:
        for row in table.rows:
            for idx, width in enumerate(col_widths):
                row.cells[idx].width = Cm(width)

    doc.add_paragraph()
    return table


def add_score_table(doc, category, instantly_score, exzelon_score, max_score=10):
    """Add a single-row score comparison."""
    p = doc.add_paragraph()
    run = p.add_run(f"  {category}: ")
    run.bold = True
    run.font.size = Pt(11)

    run = p.add_run(f"Instantly {instantly_score}/{max_score}")
    run.font.color.rgb = RGBColor.from_string(BLUE)
    run.font.size = Pt(11)
    run.bold = True

    run = p.add_run(f"  vs  ")
    run.font.size = Pt(11)

    color = RED if exzelon_score < instantly_score else GREEN
    run = p.add_run(f"Exzelon {exzelon_score}/{max_score}")
    run.font.color.rgb = RGBColor.from_string(color)
    run.font.size = Pt(11)
    run.bold = True


def generate():
    doc = Document()

    # ── Page setup ──
    for section in doc.sections:
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(1.5)
        section.right_margin = Cm(1.5)

    # ── Title Page ──
    for _ in range(4):
        doc.add_paragraph()

    title = doc.add_heading("Instantly.ai vs Exzelon RA Agent", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.size = Pt(28)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run("Comprehensive Feature Comparison & Gap Analysis")
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor.from_string(GRAY)

    doc.add_paragraph()
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = meta.add_run("Prepared for: Exzelon AI Operations Team\nMarch 2026")
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor.from_string(GRAY)

    doc.add_page_break()

    # ── Table of Contents ──
    doc.add_heading("Table of Contents", level=1)
    toc_items = [
        "1. Executive Summary & Overall Scorecard",
        "2. Platform Overview",
        "3. Lead Database & Sourcing",
        "4. Email Warmup & Deliverability",
        "5. Campaign Management & Outreach",
        "6. AI Features",
        "7. Unified Inbox & Reply Management",
        "8. CRM & Deal Management",
        "9. Analytics & Reporting",
        "10. Integrations & API",
        "11. Mailbox & Sending Infrastructure",
        "12. Contact Discovery & Enrichment",
        "13. Email Validation",
        "14. User Management & Permissions",
        "15. Agency & Multi-Client Features",
        "16. Pricing Comparison",
        "17. Gap Analysis & Priority Improvements",
        "18. Improvement Roadmap",
    ]
    for item in toc_items:
        p = doc.add_paragraph(item)
        p.paragraph_format.space_after = Pt(2)

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 1. EXECUTIVE SUMMARY
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("1. Executive Summary & Overall Scorecard", level=1)

    doc.add_paragraph(
        "This document provides a feature-by-feature comparison between Instantly.ai, "
        "a market-leading cold email outreach platform, and Exzelon RA Agent, our in-house "
        "recruitment automation system. The analysis identifies 23 critical feature gaps and "
        "proposes a prioritized improvement roadmap to close them."
    )

    doc.add_heading("Overall Score by Category", level=2)

    scores = [
        ("Lead Database & Sourcing", 9, 7),
        ("Email Warmup & Deliverability", 10, 7),
        ("Campaign Management", 10, 4),
        ("AI Features", 10, 3),
        ("Unified Inbox", 9, 2),
        ("CRM & Deal Management", 8, 3),
        ("Analytics & Reporting", 9, 5),
        ("Integrations & API", 9, 3),
        ("Mailbox Infrastructure", 10, 6),
        ("Contact Discovery", 7, 9),
        ("Email Validation", 8, 8),
        ("User Management & RBAC", 6, 9),
        ("Agency / White-Label", 9, 0),
        ("Pricing Flexibility", 8, 10),
    ]

    add_comparison_table(doc,
        ["Category", "Instantly.ai (out of 10)", "Exzelon RA (out of 10)", "Gap", "Priority"],
        [
            [cat, f"{i}/10", f"{e}/10",
             f"{i - e} pts behind" if i > e else ("Ahead" if e > i else "Parity"),
             "CRITICAL" if (i - e) >= 5 else ("HIGH" if (i - e) >= 3 else ("MEDIUM" if (i - e) >= 1 else "N/A"))]
            for cat, i, e in scores
        ],
        col_widths=[5.5, 3.5, 3.5, 3, 2.5]
    )

    instantly_total = sum(s[1] for s in scores)
    exzelon_total = sum(s[2] for s in scores)
    p = doc.add_paragraph()
    run = p.add_run(f"Overall: Instantly.ai {instantly_total}/{len(scores)*10} ({instantly_total*100//(len(scores)*10)}%)  |  ")
    run.bold = True
    run.font.size = Pt(12)
    run = p.add_run(f"Exzelon RA {exzelon_total}/{len(scores)*10} ({exzelon_total*100//(len(scores)*10)}%)")
    run.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor.from_string(RED)

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 2. PLATFORM OVERVIEW
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("2. Platform Overview", level=1)

    add_comparison_table(doc,
        ["Aspect", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["Type", "SaaS (cloud-hosted)", "Self-hosted (VPS)"],
            ["Target Market", "Sales teams, agencies, marketers", "Recruitment/staffing agencies"],
            ["Primary Use Case", "Cold email outreach for sales", "Job lead sourcing + recruitment outreach"],
            ["Hosting", "Cloud (instantly.ai manages)", "Single VPS (Ubuntu 24.04, 4 vCPU, 16GB RAM)"],
            ["Tech Stack", "Proprietary (closed-source)", "FastAPI + Next.js 14 (open-source stack)"],
            ["Pricing Model", "Monthly SaaS subscription", "Self-hosted (infrastructure cost only)"],
            ["Database", "Proprietary (450M+ B2B contacts)", "MySQL + external API integrations"],
            ["Users", "Unlimited (Hypergrowth+)", "4-role RBAC (Super Admin, Admin, Operator, Viewer)"],
            ["API", "RESTful API v2 with scopes", "RESTful API with Bearer token auth"],
            ["Uptime SLA", "Enterprise SLA available", "Self-managed (no SLA)"],
        ],
        col_widths=[4, 7, 7]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 3. LEAD DATABASE & SOURCING
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("3. Lead Database & Sourcing", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["B2B Contact Database", "[YES] 450M+ verified contacts", "[NO] No built-in database; sources from job boards via APIs"],
            ["Lead Search Filters", "[YES] 13+ filters (title, industry, location, revenue, tech stack, funding, seniority, dept, lookalike)", "[PARTIAL] Title, industry, location, salary. No revenue/tech stack/funding/seniority filters"],
            ["AI Natural Language Search", "[YES] Describe ICP in plain English, AI builds filters", "[NO] Not available"],
            ["Lookalike Search", "[YES] Find companies similar to a target", "[NO] Not available"],
            ["Job Board Integration", "[NO] Not a job board aggregator", "[YES] 6 adapters: JSearch (LinkedIn/Indeed/Glassdoor), Apollo, TheirStack, SerpAPI, Adzuna + Mock"],
            ["Multi-Source Parallel Fetching", "[NO] Single database", "[YES] ThreadPoolExecutor with 6 workers fetching simultaneously"],
            ["Deduplication", "[YES] Email-based dedup", "[YES] 3-layer dedup: external_job_id, employer LinkedIn, company+title+state+city"],
            ["Auto-Refresh Lists", "[YES] Daily/weekly/monthly auto-refresh with new matching leads", "[YES] Scheduled 3x/day via APScheduler (6am/12pm/6pm UTC)"],
            ["Direct Campaign Push", "[YES] SuperSearch leads flow directly into campaigns", "[PARTIAL] Leads feed into contact enrichment pipeline, then outreach"],
            ["Data Enrichment", "[YES] 5+ waterfall providers, real-time verification", "[PARTIAL] Clearbit + OpenCorporates for company data; Apollo/Seamless for contacts"],
            ["Credits System", "[YES] Credit-based (150-10,000 credits/month)", "[YES] API-key based, no credit metering (direct API costs)"],
            ["CSV Import", "[YES] Bulk CSV with verification", "[YES] CSV import with dedup preview"],
            ["Export", "[YES] To Salesforce, HubSpot, Apollo, Lemlist, Smartlead, Pipedrive, CSV", "[PARTIAL] CSV and XLSX export only"],
            ["Job Titles Searched", "N/A (people search, not job search)", "[YES] 55+ recruitment-specific titles"],
            ["Industry Coverage", "[YES] All industries via database filters", "[YES] 22 non-IT target industries"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 4. EMAIL WARMUP & DELIVERABILITY
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("4. Email Warmup & Deliverability", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["Warmup Network Size", "[YES] 4.2M+ accounts in private network", "[PARTIAL] Peer-to-peer between owned mailboxes only (limited pool)"],
            ["Unlimited Warmup", "[YES] Unlimited warmup on all plans", "[YES] Unlimited warmup for configured mailboxes"],
            ["AI-Generated Warmup Emails", "[YES] Contextual conversations with positive sentiment", "[YES] AI warmup emails via Groq LLM"],
            ["Read Emulation", "[YES] Simulates human reading behavior (scrolling, time)", "[NO] Not implemented"],
            ["Warmup Profiles", "[PARTIAL] Standard + Premium pools", "[YES] 3 profiles: Conservative (45d), Standard (30d), Aggressive (20d) + Custom"],
            ["Inbox Placement Testing", "[YES] Seed tests across Gmail, Outlook, Yahoo + alerts", "[PARTIAL] Connection status testing only; no seed-based placement tests"],
            ["SPF/DKIM/DMARC Checks", "[YES] Setup guidance + validation", "[YES] Full DNS health checking with scoring (0-100)"],
            ["Blacklist Monitoring", "[YES] 400+ blacklist sources, continuous", "[YES] DNSBL checking, IP + domain monitoring, scheduled checks"],
            ["Auto-Pause on Issues", "[YES] Auto-pause senders when placement degrades", "[YES] Auto-pause on health threshold violations"],
            ["Auto-Recovery", "[PARTIAL] Manual intervention typical", "[YES] Auto-recovery system with reduced limits, scheduled checks"],
            ["IP Rotation (SISR)", "[YES] Server IP Sharding & Rotation (Light Speed plan)", "[NO] Single-server deployment, no IP rotation"],
            ["Private IP Pools", "[YES] Dedicated IP pools for high-volume senders", "[NO] Shared VPS IP"],
            ["Custom Tracking Domain", "[YES] Dedicated domain for tracking, reputation isolation", "[NO] Uses main domain for tracking"],
            ["Spam Word Checker", "[YES] AI-powered copy analysis for spam triggers", "[NO] Not available"],
            ["Global Block List", "[YES] Account-wide domain/address blocking", "[PARTIAL] Suppression list for unsubscribed contacts"],
            ["Health Score", "[PARTIAL] Deliverability analytics dashboard", "[YES] Composite health score (0-100) per mailbox with daily logs"],
            ["Warmup Analytics", "[YES] Warmup-specific analytics dashboard", "[YES] Warmup analytics with daily log snapshots, trend charts"],
            ["Pre-Warmed Accounts", "[YES] Purchase ready-to-send accounts (batches of 5)", "[NO] Must warm your own accounts"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 5. CAMPAIGN MANAGEMENT
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("5. Campaign Management & Outreach", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["Multi-Step Sequences", "[YES] Drag-and-drop multi-step email sequences", "[NO] Single-step email only (template-based)"],
            ["Subsequences", "[YES] Conditional follow-ups based on open/click/reply behavior", "[NO] No conditional branching"],
            ["A/Z Testing", "[YES] Up to 26 variants per step with auto-optimize", "[NO] No A/B testing"],
            ["Inbox Rotation", "[YES] Auto-distribute sends across unlimited accounts", "[PARTIAL] Round-robin mailbox selection per send"],
            ["Smart Scheduling", "[YES] Timezone-aware sending based on recipient location", "[NO] No timezone-aware scheduling"],
            ["Sending Windows", "[YES] Configure days of week + time ranges", "[NO] Pipeline runs on-demand or scheduled (no send windows)"],
            ["Personalization Variables", "[YES] First name, company, website, custom fields", "[YES] job_title, contact_first_name, sender_first_name, company_name, job_location"],
            ["Spintax", "[YES] AI-generated text variations per email", "[NO] No spintax support"],
            ["Liquid Syntax", "[YES] Advanced template logic (if/else, loops)", "[NO] Basic variable substitution only"],
            ["Image Personalization", "[YES] Dynamic images per recipient", "[NO] Not available"],
            ["Open Tracking", "[YES] Unique opens per lead (pixel-based)", "[YES] Tracking pixel (/t/{id}/px.gif)"],
            ["Click Tracking", "[YES] Unique clicks per lead per link", "[YES] Link redirect (/t/{id}/l)"],
            ["Reply Detection", "[YES] Auto-refresh, real-time reply tracking", "[YES] Reply detection with content storage"],
            ["Bounce Handling", "[YES] Automatic bounce handling + categorization", "[PARTIAL] Bounce detection + reason capture, no auto-processing"],
            ["Unsubscribe", "[YES] One-click unsubscribe + suppression", "[YES] Unsubscribe link + suppression list"],
            ["Daily Send Limits", "[YES] Per-account + per-campaign configurable", "[YES] Per-mailbox configurable (default 30/day)"],
            ["Cooldown Period", "[PARTIAL] Manual spacing configuration", "[YES] Enforced 10-day cooldown between same-contact emails"],
            ["Campaign Templates", "[YES] Save and reuse campaign templates", "[YES] Email template CRUD with preview + duplicate"],
            ["Lead Tagging", "[YES] Tag leads by campaign, status, category", "[PARTIAL] Lead status tracking (open/hunting/closed)"],
            ["Duplicate Detection on Import", "[YES] Email-based dedup on CSV import", "[YES] 3-layer dedup on import"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 6. AI FEATURES
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("6. AI Features", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["AI Copilot", "[YES] Built-in assistant for campaign strategy, ICP definition, analytics summaries", "[NO] No AI copilot/assistant"],
            ["AI Sequence Generator", "[YES] Creates complete multi-step sequences with variables and spintax", "[NO] No sequence generation (single-step only)"],
            ["AI Spintax Writer", "[YES] Auto-generates text variations for deliverability", "[NO] Not available"],
            ["AI Personalization Lines", "[YES] Per-prospect custom content via AI prompts", "[NO] Not available"],
            ["AI Reply Agent", "[YES] Autopilot or human-in-the-loop reply generation (<5 min response)", "[NO] No automated reply generation"],
            ["AI Inbox Manager", "[YES] GPT-4 sentiment analysis, auto-categorize replies (Interested/Not Interested/OOO/Meeting Booked)", "[NO] No AI inbox management"],
            ["AI Forecasting", "[YES] Revenue forecasting using engagement data, 28% accuracy improvement", "[NO] Not available"],
            ["AI Email Content", "[PARTIAL] Part of copilot and sequence generator", "[YES] AI email generation via 4 LLM providers (Groq, OpenAI, Anthropic, Gemini)"],
            ["AI Warmup Content", "[YES] Contextual warmup conversations", "[YES] AI-generated warmup emails via Groq"],
            ["LLM Provider Choice", "[NO] Proprietary AI (likely GPT-4)", "[YES] 4 providers with fallback chain (Groq, OpenAI, Anthropic, Gemini)"],
            ["AI Lead Scoring", "[PARTIAL] Engagement-based scoring", "[NO] No AI-based lead scoring"],
            ["AI ICP Definition", "[YES] AI helps define ideal customer profile", "[NO] Manual configuration only"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 7. UNIFIED INBOX
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("7. Unified Inbox & Reply Management", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["Unified Inbox (Unibox)", "[YES] Centralized master inbox for ALL campaign replies across unlimited accounts", "[NO] No unified inbox; replies tracked in outreach events table"],
            ["AI Sentiment Analysis", "[YES] GPT-4 powered reply categorization", "[NO] Not available"],
            ["Reply Categories", "[YES] Interested, Not Interested, OOO, Meeting Booked, Referral, Objection + custom", "[NO] Basic reply detection only (replied yes/no)"],
            ["One-Click Reply", "[YES] Reply directly from unified interface", "[NO] Must use external email client"],
            ["Thread View", "[YES] Full conversation context per lead", "[PARTIAL] Reply subject + body stored, no thread reconstruction"],
            ["Auto-Forward to CRM", "[YES] Auto-forward interested leads", "[NO] No CRM integration"],
            ["Filter by Campaign/Sender", "[YES] Filter and search across all conversations", "[NO] Basic outreach event listing only"],
            ["Webhook on Reply", "[YES] Real-time webhook triggers on reply events", "[NO] No webhooks"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    # ══════════════════════════════════════════════════════════════════
    # 8. CRM & DEAL MANAGEMENT
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("8. CRM & Deal Management", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["Visual Pipeline (Kanban)", "[YES] Kanban-style deal pipeline with custom stages", "[NO] No deal pipeline; leads tracked by status only"],
            ["Deal Tracking", "[YES] Revenue estimation, deal value, win rates", "[NO] No deal/revenue tracking"],
            ["Contact Timeline", "[YES] Full interaction history per contact", "[PARTIAL] Outreach events per contact, no unified timeline"],
            ["Tasks & Follow-ups", "[YES] Task creation, assignment, scheduling", "[NO] No task management"],
            ["Built-in Calling", "[YES] Dialer from CRM (Hyper plan)", "[NO] Not available"],
            ["Built-in SMS", "[YES] SMS from CRM (Hyper plan)", "[NO] Not available"],
            ["Opportunity Reports", "[YES] Pipeline value, hot prospect reports, ROI", "[NO] No opportunity reporting"],
            ["Client Management", "[PARTIAL] Contact-centric, no company lifecycle", "[YES] Full client lifecycle: categorization (regular/occasional/prospect), service counts, enrichment"],
            ["Company Enrichment", "[YES] Via SuperSearch data", "[YES] Clearbit + OpenCorporates enrichment with website, LinkedIn, industry, size"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 9. ANALYTICS & REPORTING
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("9. Analytics & Reporting", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["Campaign Analytics", "[YES] Sent, opens, replies, clicks, bounces, unsubscribes per campaign/step/daily", "[PARTIAL] Basic outreach event counts; no per-campaign breakdown"],
            ["Revenue Analytics", "[YES] Opportunities, pipeline value, conversions, ROI, cost per meeting", "[NO] No revenue/ROI tracking"],
            ["Deliverability Analytics", "[YES] Inbox placement rates by provider, domain health, IP reputation", "[YES] DNS health scores, blacklist status, warmup daily logs"],
            ["A/B Test Results", "[YES] Variant performance comparison with auto-optimize", "[NO] No A/B testing"],
            ["Team/Rep Comparison", "[YES] Compare by sequence, sender, segment, workspace", "[NO] No team analytics"],
            ["Dashboard KPIs", "[YES] Campaign-focused KPIs", "[YES] Lead/Contact/Outreach KPIs, trend charts (7/30/90 day)"],
            ["Warmup Analytics", "[YES] Warmup-specific dashboard", "[YES] Daily log snapshots, health trend charts, phase progression"],
            ["Export Reports", "[PARTIAL] In-app reporting", "[YES] CSV/JSON/XLSX export for leads, contacts, warmup data"],
            ["Pipeline Run Reports", "[NO] No pipeline concept", "[YES] Per-run counters, per-source breakdown, API diagnostics, AI summaries"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    # ══════════════════════════════════════════════════════════════════
    # 10. INTEGRATIONS
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("10. Integrations & API", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["REST API", "[YES] API v2 with Bearer auth, scoped access, interactive docs", "[YES] FastAPI with Bearer auth, Swagger/OpenAPI docs"],
            ["Webhooks", "[YES] Real-time events (sent, opened, clicked, bounced, replied, unsubscribed, status changed)", "[NO] No webhook support"],
            ["Zapier", "[YES] 8,000+ app integrations via triggers/actions", "[NO] Not available"],
            ["Make (Integromat)", "[YES] 3,000+ integrations", "[NO] Not available"],
            ["HubSpot", "[YES] Two-way sync via OutboundSync", "[NO] Not available"],
            ["Salesforce", "[YES] Two-way sync via OutboundSync", "[NO] Not available"],
            ["Pipedrive", "[YES] Native integration", "[NO] Not available"],
            ["Slack", "[YES] Notifications, visitor alerts", "[NO] Not available"],
            ["CRM Export", "[YES] Salesforce, HubSpot, Apollo, Lemlist, Smartlead, Pipedrive", "[NO] CSV/XLSX export only"],
            ["Microsoft 365 OAuth", "[PARTIAL] Email account connection", "[YES] Full OAuth2 flow for mailboxes"],
            ["Gmail OAuth", "[YES] Native OAuth connection", "[PARTIAL] Planned, not yet implemented"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 11. MAILBOX INFRASTRUCTURE
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("11. Mailbox & Sending Infrastructure", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["Email Accounts", "[YES] Unlimited on ALL plans", "[YES] Unlimited (self-hosted, no cap)"],
            ["Gmail OAuth", "[YES] One-click connection", "[PARTIAL] Planned, not yet implemented"],
            ["Outlook/M365 OAuth", "[YES] One-click connection", "[YES] Full OAuth2 flow implemented"],
            ["SMTP Support", "[YES] Any SMTP provider", "[YES] Generic SMTP support"],
            ["Inbox Rotation", "[YES] Natural distribution across accounts per campaign", "[PARTIAL] Round-robin selection, no per-campaign rotation"],
            ["Pre-Warmed Accounts", "[YES] Purchase ready-to-send accounts", "[NO] Must warm your own"],
            ["Smart Throttling", "[YES] Prevents over-sending with intelligent pacing", "[PARTIAL] Daily limit enforcement, no intelligent pacing"],
            ["Connection Testing", "[YES] Account connectivity validation", "[YES] SMTP handshake + OAuth token validation"],
            ["Health Monitoring", "[PARTIAL] Via deliverability dashboard", "[YES] Per-mailbox health score (0-100) with composite metrics"],
            ["Daily Limit Configuration", "[YES] Per-account + per-campaign", "[YES] Per-mailbox configurable"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    # ══════════════════════════════════════════════════════════════════
    # 12. CONTACT DISCOVERY
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("12. Contact Discovery & Enrichment", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["Contact Discovery Providers", "[YES] 5+ waterfall providers (proprietary)", "[YES] 8 providers: Apollo, Seamless, Hunter.io, Snov.io, RocketReach, PDL, Proxycurl + Mock"],
            ["Waterfall Enrichment", "[YES] Real-time across multiple providers", "[PARTIAL] Single provider per run (configurable), no waterfall"],
            ["Decision-Maker Priority", "[NO] Basic title matching", "[YES] 5-level hierarchy: P1 Job Poster → P5 Functional Manager"],
            ["Phone Discovery", "[PARTIAL] Via enrichment credits", "[YES] Phone discovery where API tier supports it"],
            ["Contact Reuse", "[YES] Database-cached contacts", "[YES] Contact caching across runs with API savings tracking"],
            ["Max Contacts per Company", "[NO] Unlimited per search", "[YES] Configurable (default 4 per company per job)"],
            ["Email Verification", "[YES] Built-in verification on import", "[YES] 8 validation providers (NeverBounce, ZeroBounce, Hunter, etc.)"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 13. EMAIL VALIDATION
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("13. Email Validation", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["Validation Providers", "[YES] Built-in proprietary", "[YES] 8 providers: NeverBounce, ZeroBounce, Hunter, Clearout, Emailable, MailboxValidator, Reacher, Mock"],
            ["Bulk Validation", "[YES] On CSV import", "[YES] Bulk validation pipeline"],
            ["Spam Trap Detection", "[YES] Built-in", "[PARTIAL] Provider-dependent"],
            ["Result Categories", "[YES] Valid, Invalid, Risky, Unknown", "[YES] Valid, Invalid, Catch-All, Unknown"],
            ["Validation Caching", "[PARTIAL] Per-import validation", "[YES] Result caching with timestamps"],
            ["Outreach Gate", "[YES] Only verified emails receive campaigns", "[YES] Only Valid emails proceed to outreach"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    # ══════════════════════════════════════════════════════════════════
    # 14. USER MANAGEMENT
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("14. User Management & Permissions", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["Role System", "[PARTIAL] Basic workspace roles", "[YES] 4-tier RBAC: Super Admin, Admin, Operator, Viewer"],
            ["Module-Level Permissions", "[NO] Role-based access only", "[YES] Per-module + per-tab permission matrix"],
            ["User Overrides", "[NO] Not available", "[YES] Per-user permission overrides (Super Admin sets)"],
            ["Unlimited Team Members", "[YES] On Hypergrowth+ plans", "[YES] No user limit (self-hosted)"],
            ["Audit Trail", "[NO] No audit logging", "[YES] Full audit trail for permission changes and entity modifications"],
            ["SA Protection", "[NO] Basic admin roles", "[YES] Cannot demote/delete last Super Admin"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 15. AGENCY FEATURES
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("15. Agency & Multi-Client Features", level=1)

    add_comparison_table(doc,
        ["Feature", "Instantly.ai", "Exzelon RA Agent"],
        [
            ["Multi-Client Workspaces", "[YES] Separate workspaces per client, data siloed", "[NO] Single-tenant deployment"],
            ["White-Label", "[YES] Custom domain, logo, branding for client portals", "[NO] Not available"],
            ["Client Access Portal", "[YES] Branded access without Instantly login", "[NO] Not available"],
            ["Unified Operations", "[YES] Manage all clients from single login", "[NO] Single workspace only"],
            ["Per-Client Billing", "[YES] Agency-specific billing features", "[NO] Not applicable (self-hosted)"],
        ],
        col_widths=[4.5, 6.5, 7]
    )

    # ══════════════════════════════════════════════════════════════════
    # 16. PRICING
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("16. Pricing Comparison", level=1)

    add_comparison_table(doc,
        ["Tier", "Instantly.ai (Monthly)", "Exzelon RA Agent"],
        [
            ["Entry Level", "$37.60/mo (Growth, annual) - 5K emails, 1K contacts", "$0 software cost + ~$15-30/mo VPS + API costs"],
            ["Mid Tier", "$77.60/mo (Hypergrowth) - 100K emails, 25K contacts", "Same VPS cost, scales with API usage"],
            ["High Volume", "$286.30/mo (Light Speed) - 500K emails, 100K contacts, SISR", "Same VPS cost, higher API costs for high volume"],
            ["Lead Database", "$9-197/mo (150-10,000 credits)", "Direct API costs (JSearch free 500/mo, Apollo free tier, etc.)"],
            ["CRM", "$37.90-97/mo additional", "Built-in client management (included)"],
            ["Total Cost (typical)", "$120-400/mo for full platform", "$15-200/mo total (VPS + API keys)"],
            ["Cost at Scale", "$500-1000+/mo for agency use", "$50-300/mo (same VPS, more API calls)"],
            ["Per-Seat Pricing", "None (unlimited seats on most plans)", "None (unlimited users, self-hosted)"],
        ],
        col_widths=[4, 7, 7]
    )

    p = doc.add_paragraph()
    run = p.add_run("Key Insight: ")
    run.bold = True
    p.add_run(
        "Exzelon RA has a significant cost advantage ($15-200/mo vs $120-400+/mo), but "
        "Instantly.ai delivers more features out-of-the-box. The cost savings from self-hosting "
        "can fund the development effort to close feature gaps."
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 17. GAP ANALYSIS
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("17. Gap Analysis & Priority Improvements", level=1)

    doc.add_paragraph(
        "The following table lists all significant feature gaps between Exzelon RA and Instantly.ai, "
        "ranked by business impact and implementation effort."
    )

    add_comparison_table(doc,
        ["#", "Gap", "Business Impact", "Effort", "Priority"],
        [
            ["1", "No multi-step email sequences (follow-ups)", "CRITICAL - massively reduces reply rates", "40-60 hrs", "P0"],
            ["2", "No unified inbox (Unibox)", "CRITICAL - reply management across accounts", "60-80 hrs", "P0"],
            ["3", "No A/B testing", "HIGH - can't optimize email copy", "20-30 hrs", "P1"],
            ["4", "No AI reply agent / auto-responses", "HIGH - slow response kills conversion", "40-60 hrs", "P1"],
            ["5", "No AI sentiment analysis on replies", "HIGH - manual triage doesn't scale", "20-30 hrs", "P1"],
            ["6", "No spintax / text variation", "HIGH - hurts deliverability at scale", "15-20 hrs", "P1"],
            ["7", "No timezone-aware smart scheduling", "MEDIUM - reduces open rates", "15-20 hrs", "P1"],
            ["8", "No CRM deal pipeline (Kanban)", "HIGH - can't track revenue/ROI", "40-60 hrs", "P1"],
            ["9", "No webhook support", "HIGH - blocks 3rd-party integrations", "10-15 hrs", "P1"],
            ["10", "No Zapier/Make integration", "MEDIUM - limits automation ecosystem", "20-30 hrs", "P2"],
            ["11", "No HubSpot/Salesforce integration", "MEDIUM - agency clients expect this", "30-40 hrs", "P2"],
            ["12", "No IP rotation / SISR", "MEDIUM - deliverability ceiling", "30-40 hrs", "P2"],
            ["13", "No custom tracking domain", "MEDIUM - shares reputation risk", "10-15 hrs", "P2"],
            ["14", "No inbox placement seed testing", "MEDIUM - can't measure inbox vs spam", "20-30 hrs", "P2"],
            ["15", "No AI copilot / campaign assistant", "MEDIUM - manual setup is slower", "40-60 hrs", "P2"],
            ["16", "No read emulation in warmup", "LOW - nice-to-have for warmup quality", "10-15 hrs", "P3"],
            ["17", "No image personalization", "LOW - text emails work for recruitment", "15-20 hrs", "P3"],
            ["18", "No white-label / multi-tenant", "LOW - only if selling to agencies", "80-120 hrs", "P3"],
            ["19", "No built-in calling/SMS", "LOW - recruitment is email-first", "60-80 hrs", "P3"],
            ["20", "No website visitor tracking", "LOW - more relevant for sales", "40-60 hrs", "P3"],
            ["21", "No Slack notifications", "LOW - nice-to-have", "5-10 hrs", "P3"],
            ["22", "No campaign-level analytics (per-step)", "MEDIUM - can't optimize sequences", "15-20 hrs", "P1"],
            ["23", "No lead scoring (AI-based)", "MEDIUM - manual prioritization", "20-30 hrs", "P2"],
        ],
        col_widths=[1, 6.5, 3.5, 2.5, 1.5]
    )

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════
    # 18. IMPROVEMENT ROADMAP
    # ══════════════════════════════════════════════════════════════════
    doc.add_heading("18. Improvement Roadmap", level=1)

    doc.add_paragraph(
        "Based on the gap analysis, the following phased roadmap will bring Exzelon RA Agent "
        "to feature parity with Instantly.ai's core capabilities while maintaining the cost advantage "
        "and recruitment-specific strengths."
    )

    doc.add_heading("Phase 1: Campaign Engine (P0) — Est. 100-140 hours", level=2)
    phase1 = [
        "Multi-step email sequences with configurable delays between steps",
        "Subsequences with conditional branching (opened/clicked/replied/no-action)",
        "Unified Inbox (Unibox) aggregating replies across all mailboxes",
        "Thread view with full conversation history per lead",
        "One-click reply from unified inbox",
        "Reply categorization (manual labels: Interested, Not Interested, OOO, etc.)",
    ]
    for item in phase1:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("Phase 2: AI & Optimization (P1) — Est. 130-190 hours", level=2)
    phase2 = [
        "AI reply agent — auto-generate responses with human-in-the-loop approval",
        "AI sentiment analysis — auto-categorize replies using LLM",
        "A/B testing framework — up to 5 variants per sequence step with auto-optimize",
        "Spintax engine — text variation generation for deliverability",
        "Timezone-aware smart scheduling — send based on recipient location",
        "Per-step campaign analytics — open/reply/click rates per sequence step",
        "Webhook system — push events to external systems (sent, opened, replied, bounced)",
        "CRM deal pipeline — Kanban board with stages, revenue tracking, win rates",
    ]
    for item in phase2:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("Phase 3: Integrations & Scale (P2) — Est. 120-170 hours", level=2)
    phase3 = [
        "Zapier/Make integration — publish triggers and actions",
        "HubSpot two-way sync — contacts, deals, timeline events",
        "Salesforce integration — contact and opportunity sync",
        "Custom tracking domain — dedicated domain for open/click tracking",
        "Inbox placement seed testing — test delivery to Gmail, Outlook, Yahoo",
        "AI copilot — in-app assistant for campaign strategy and ICP definition",
        "AI lead scoring — engagement-based automated lead prioritization",
        "IP rotation — multi-IP sending infrastructure",
    ]
    for item in phase3:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("Phase 4: Advanced Features (P3) — Est. 200-350 hours", level=2)
    phase4 = [
        "White-label multi-tenant support for agency clients",
        "Website visitor identification and tracking",
        "Built-in calling/SMS integration",
        "Image personalization engine",
        "Read emulation for warmup emails",
        "Slack/Teams notification integration",
        "Waterfall contact enrichment (chain multiple providers)",
    ]
    for item in phase4:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_paragraph()

    # Summary table
    doc.add_heading("Roadmap Summary", level=2)
    add_comparison_table(doc,
        ["Phase", "Focus", "Est. Hours", "Timeline", "Score After"],
        [
            ["Phase 1", "Campaign Engine (sequences, Unibox)", "100-140 hrs", "4-6 weeks", "From 55% → 70%"],
            ["Phase 2", "AI & Optimization (AI reply, A/B, CRM)", "130-190 hrs", "6-8 weeks", "From 70% → 82%"],
            ["Phase 3", "Integrations & Scale (Zapier, CRM sync, IP rotation)", "120-170 hrs", "6-8 weeks", "From 82% → 90%"],
            ["Phase 4", "Advanced (white-label, calling, visitor tracking)", "200-350 hrs", "8-14 weeks", "From 90% → 95%+"],
        ],
        col_widths=[2.5, 5.5, 3, 3, 4]
    )

    p = doc.add_paragraph()
    p.add_run("")
    doc.add_paragraph()
    p = doc.add_paragraph()
    run = p.add_run("Total estimated effort: 550-850 hours across 4 phases (24-36 weeks)")
    run.bold = True
    run.font.size = Pt(12)

    doc.add_paragraph()
    doc.add_heading("Exzelon RA Agent's Unique Strengths (vs Instantly.ai)", level=2)
    strengths = [
        "Recruitment-specific pipeline: Job board sourcing → Contact discovery → Validation → Outreach (Instantly.ai is sales-focused only)",
        "8 contact discovery providers vs Instantly's single proprietary database (more flexibility, no lock-in)",
        "5-level decision-maker priority hierarchy (P1 Job Poster → P5 Functional Manager)",
        "Enterprise RBAC with 4 roles, module-level permissions, and per-user overrides",
        "Full database backup/restore system with audit trail",
        "3-profile warmup engine (Conservative/Standard/Aggressive) with auto-recovery",
        "Self-hosted: complete data ownership, no vendor lock-in, 3-10x lower cost",
        "4 LLM provider support with fallback chain (Groq, OpenAI, Anthropic, Gemini)",
        "55+ recruitment-specific job titles with 6 job board adapters",
        "Composite per-mailbox health scoring (0-100) with daily trend logging",
    ]
    for item in strengths:
        doc.add_paragraph(item, style="List Bullet")

    # ── Save ──
    output_path = os.path.join(os.path.dirname(__file__), "..", "Instantly_vs_Exzelon_Comparison.docx")
    output_path = os.path.abspath(output_path)
    doc.save(output_path)
    print(f"Document saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    generate()
