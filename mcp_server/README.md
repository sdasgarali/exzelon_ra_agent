# NeuraLeads MCP connector

Lets AI tools — Claude (Code, Desktop, claude.ai), Cursor, and any other
[Model Context Protocol](https://modelcontextprotocol.io) client — work inside your NeuraLeads
workspace: source leads, find and validate contacts, build and launch campaigns, watch mailbox
warmup and deliverability, and handle replies.

It is a thin layer over the NeuraLeads REST API. Every call is made **as the owner of the API
key**, so roles, workspace isolation, plan features, credits and sending rules apply exactly as
they do in the app.

## 1. Create an API key

NeuraLeads → **Settings → API Keys & MCP → Create key**. Pick a scope:

| Scope | Can do |
|---|---|
| `read` | Look things up only. Cannot change anything. |
| `write` | Read, plus operational actions: source leads, enrich, validate, build/launch campaigns, reply in the inbox. Cannot delete, and cannot manage users, billing, roles or keys. |
| `admin` | Everything the key owner can do, including delete. |

The key is shown once. Keys can be given an expiry and revoked at any time.

## 2. Connect your AI tool

### Hosted (no install) — `https://neuraleads.ai/mcp`

**Claude Code**
```bash
claude mcp add --transport http neuraleads https://neuraleads.ai/mcp \
  --header "Authorization: Bearer <YOUR_API_KEY>"
```

**Cursor** (`~/.cursor/mcp.json`)
```json
{ "mcpServers": { "neuraleads": {
    "url": "https://neuraleads.ai/mcp",
    "headers": { "Authorization": "Bearer <YOUR_API_KEY>" } } } }
```

**Claude Desktop** (`claude_desktop_config.json`)
```json
{ "mcpServers": { "neuraleads": {
    "command": "npx",
    "args": ["-y", "mcp-remote", "https://neuraleads.ai/mcp",
             "--header", "Authorization:Bearer <YOUR_API_KEY>"] } } }
```

### Local (stdio)

Requires Python 3.11+.
```bash
pip install ./mcp_server            # from the repo root (or: uv tool install ./mcp_server)
export NEURALEADS_API_KEY=exz_...   # PowerShell: $env:NEURALEADS_API_KEY="exz_..."
neuraleads-mcp                      # speaks MCP over stdin/stdout
```
Client config example:
```json
{ "mcpServers": { "neuraleads": {
    "command": "neuraleads-mcp",
    "env": { "NEURALEADS_API_KEY": "<YOUR_API_KEY>",
             "NEURALEADS_API_URL": "https://neuraleads.ai/api/v1" } } } }
```

## Safety

- **Confirmation gate.** Tools that send email, launch or complete campaigns, or spend credits
  (`run_lead_sourcing`, `run_contact_enrichment`, `validate_*`, `activate_campaign`,
  `complete_campaign`, `send_inbox_reply`, `approve_reply_draft`, `set_mailbox_status`) first
  return `status: "confirmation_required"` with a preview. They act only when called again with
  `confirm: true`, which the assistant is instructed to do only after you agree.
- **Campaign sends go through NeuraLeads' scheduler**, which enforces daily mailbox limits, the
  cooldown per contact, suppression/unsubscribes and valid-email-only rules. The connector has no
  "send arbitrary email" tool.
- **Read-only server mode.** Set `NEURALEADS_MCP_READ_ONLY=true` to hide every write tool.
- **Workspace checks.** Mailbox, contact and campaign ids are checked to belong to your workspace
  before they're used.
- **No secrets in responses.** Credential-like fields are stripped from everything returned.
- In hosted mode the server stores no keys; each request carries its own.

## Tools

| Area | Tools |
|---|---|
| Account | `whoami`, `get_credit_balance`, `get_price_list`, `get_dashboard_kpis`, `get_pipeline_overview`, `get_business_rules`, `list_pipeline_runs`, `get_pipeline_run`, `cancel_pipeline_run` |
| Lead sourcing | `search_leads`, `get_lead`, `get_lead_stats`, `ai_lead_search`, `list_lead_sources`, `run_lead_sourcing`, `update_lead_status` |
| Companies | `search_companies`, `get_company`, `enrich_company` |
| Contacts & enrichment | `search_contacts`, `get_contact`, `get_contacts_for_lead`, `get_contact_stats`, `preview_contact_enrichment`, `estimate_contact_enrichment`, `run_contact_enrichment` |
| Email validation | `validate_contact_emails`, `validate_all_pending_emails` (status via `get_contact_stats` / `search_contacts`) |
| Mailboxes | `list_mailboxes`, `get_mailbox`, `get_mailbox_stats`, `test_mailbox_connection`, `set_mailbox_status`, `update_mailbox_settings` |
| Warmup & deliverability | `get_warmup_overview`, `get_warmup_health_scores`, `get_warmup_schedule`, `get_mailbox_warmup_history`, `list_warmup_alerts`, `get_mailbox_dns_status`, `get_mailbox_blacklist_status`, `list_warmup_profiles`, `run_dns_check`, `run_blacklist_check`, `assess_mailbox_warmup`, `apply_warmup_profile`, `get_deliverability_summary`, `get_mailbox_deliverability`, `check_spam_score` |
| Campaigns | `list_campaigns`, `get_campaign`, `get_campaign_analytics`, `get_campaign_health`, `get_campaign_mailbox_stats`, `list_campaign_contacts`, `list_campaign_ready_leads`, `list_email_templates`, `preview_auto_enrollment`, `create_campaign_from_leads`, `update_campaign_settings`, `add_campaign_step`, `update_campaign_step`, `enroll_contacts`, `activate_campaign`, `pause_campaign`, `complete_campaign`, `suggest_subject_lines` |
| Inbox | `list_inbox_threads`, `get_inbox_thread`, `get_inbox_stats`, `list_reply_drafts`, `suggest_reply`, `mark_thread_read`, `categorize_thread`, `generate_reply_draft`, `approve_reply_draft`, `reject_reply_draft`, `send_inbox_reply` |
| Reports | `report_campaign_performance`, `report_mailbox_health`, `report_daily_activity`, `report_client_analytics` |

Prompts: `weekly_pipeline_review`, `mailbox_health_triage`, `launch_campaign_for_leads`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `NEURALEADS_API_URL` | `https://neuraleads.ai/api/v1` | REST API base |
| `NEURALEADS_API_KEY` | — | Key used in stdio mode (ignored when hosted) |
| `NEURALEADS_MCP_READ_ONLY` | `false` | Hide all write tools |
| `NEURALEADS_TIMEOUT_SECONDS` | `60` | Per-request timeout |
| `NEURALEADS_MAX_RETRIES` | `2` | Retries for GETs on 502/503/504/network errors (never for writes) |
| `MCP_HTTP_HOST` / `MCP_HTTP_PORT` | `127.0.0.1` / `8010` | Hosted mode bind |
| `MCP_ALLOWED_HOSTS` | `127.0.0.1:*,localhost:*` | Accepted `Host` headers in hosted mode (e.g. `neuraleads.ai`) |
| `MCP_LOG_LEVEL` | `INFO` | Log level (logs go to stderr) |
| `APP_ENV` | — | Optional `TEST`/`DEV`/`PROD`; `${APP_ENV}_X` overrides `X` |

Run hosted mode: `neuraleads-mcp --transport http` (health check: `GET /healthz`).

## Development

```bash
cd mcp_server
uv venv .venv && uv pip install -e ".[dev]"
.venv/Scripts/python -m pytest        # Windows   (Linux/macOS: .venv/bin/python -m pytest)
```
The integration tests drive the real NeuraLeads FastAPI app in-process (SQLite), so they also
need the backend's dependencies: `uv pip install -r ../backend/requirements.txt` in a **separate**
venv is not enough — see `tests/README` notes in `CLAUDE_REFERENCE/mcp-connector.md`.
