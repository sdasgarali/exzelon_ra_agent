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

### Choosing a workspace (super admins)

A normal key always acts in its owner's workspace. A **super admin's** key can act in any
workspace: list them with `list_workspaces`, then select one with the `X-Tenant-ID` header.
`whoami` shows the effective workspace (`effective_workspace_id`).

```bash
# Claude Code, hosted
claude mcp add --transport http neuraleads https://neuraleads.ai/mcp \
  --header "Authorization: Bearer <SUPER_ADMIN_KEY>" --header "X-Tenant-ID: 5"
```
Local (stdio): set `NEURALEADS_TENANT_ID=5` in the server's environment (a request's
`X-Tenant-ID` header still wins). In hosted mode the server's own setting is never used. Other
keys' `X-Tenant-ID` is ignored by NeuraLeads. Without a selected workspace a super-admin key reads
across all workspaces and most writes are refused.

## Safety

- **Confirmation gate.** Tools that send email, launch or complete campaigns, change mailbox
  status, spend credits or delete data (`run_lead_sourcing`, `run_contact_enrichment`,
  `validate_*`, `activate_campaign`, `complete_campaign`, `send_inbox_reply`,
  `approve_reply_draft`, `set_mailbox_status`, `send_lead_outreach`, `send_email_drafts`,
  `generate_email_sequence`, `import_google_sheet`, `start_warmup_recovery`,
  `assess_all_warmup`, `restore_mailbox`, `merge_contacts` and every `delete_*`/`archive_*`/
  `remove_*` tool) first return `status: "confirmation_required"` with a preview. They act only when
  called again with `confirm: true`, which the assistant is instructed to do only after you agree.
- **Deletes need an `admin` key.** `write` keys are refused by NeuraLeads for any delete.
- **Every send passes NeuraLeads' send rules**: daily mailbox limits, the cooldown per contact,
  suppression/unsubscribes, excluded companies and valid-email-only. Campaign email goes through
  the scheduler; `send_lead_outreach` and `send_email_drafts` send now but through the same
  checks. There is no "send arbitrary email" tool.
- **Mailbox credentials never pass through MCP.** `create_mailbox` registers a mailbox with no
  password and leaves it inactive; you connect it in the web app (Microsoft/Google sign-in or the
  SMTP password) — `mailbox_oauth_link` gives the link. No tool accepts or returns passwords or
  OAuth tokens.
- **Read-only server mode.** Set `NEURALEADS_MCP_READ_ONLY=true` to hide every write tool.
- **Workspace checks.** Mailbox, contact, lead, template and campaign ids are checked to belong to
  your workspace before they're used.
- **No secrets in responses.** Credential-like fields are stripped from everything returned.
- In hosted mode the server stores no keys; each request carries its own.

## Tools

148 tools (73 in read-only mode).

| Area | Tools |
|---|---|
| Account | `whoami`, `list_workspaces`, `get_credit_balance`, `get_price_list`, `get_dashboard_kpis`, `get_pipeline_overview`, `get_business_rules`, `list_pipeline_runs`, `get_pipeline_run`, `cancel_pipeline_run` |
| Lead sourcing | `search_leads`, `get_lead`, `get_lead_stats`, `ai_lead_search`, `list_lead_sources`, `run_lead_sourcing`, `update_lead_status`, `create_lead`, `update_lead`, `delete_lead` |
| Import & export | `preview_google_sheet_import`, `import_google_sheet`, `export_summary` (count + first rows; the CSV itself is downloaded in the app) |
| Saved searches | `list_saved_searches`, `run_saved_search`, `create_saved_search`, `update_saved_search`, `delete_saved_search` |
| Companies | `search_companies`, `get_company`, `enrich_company`, `create_company`, `update_company`, `delete_company` |
| Company exclusions | `list_company_exclusions`, `add_company_exclusions`, `update_company_exclusion`, `remove_company_exclusion` |
| Contacts & enrichment | `search_contacts`, `get_contact`, `get_contacts_for_lead`, `get_contact_stats`, `create_contact`, `update_contact`, `delete_contact`, `list_duplicate_contacts`, `merge_contacts`, `preview_contact_enrichment`, `estimate_contact_enrichment`, `run_contact_enrichment` |
| Email validation | `validate_contact_emails`, `validate_all_pending_emails` (status via `get_contact_stats` / `search_contacts`) |
| Mailboxes | `list_mailboxes`, `get_mailbox`, `get_mailbox_stats`, `test_mailbox_connection`, `set_mailbox_status`, `update_mailbox_settings`, `create_mailbox` (no credentials), `archive_mailbox`, `restore_mailbox`, `mailbox_oauth_link` |
| Warmup & deliverability | `get_warmup_overview`, `get_warmup_health_scores`, `get_warmup_schedule`, `get_mailbox_warmup_history`, `list_warmup_alerts`, `get_mailbox_dns_status`, `get_mailbox_blacklist_status`, `list_warmup_profiles`, `run_dns_check`, `run_blacklist_check`, `assess_mailbox_warmup`, `assess_all_warmup`, `start_warmup_recovery`, `apply_warmup_profile`, `get_deliverability_summary`, `get_mailbox_deliverability`, `check_spam_score` |
| Campaigns | `list_campaigns`, `get_campaign`, `get_campaign_analytics`, `get_campaign_health`, `get_campaign_mailbox_stats`, `list_campaign_contacts`, `list_campaign_ready_leads`, `preview_auto_enrollment`, `create_campaign_from_leads`, `update_campaign_settings`, `add_campaign_step`, `update_campaign_step`, `enroll_contacts`, `activate_campaign`, `pause_campaign`, `complete_campaign`, `suggest_subject_lines` |
| Direct outreach | `list_outreach_events`, `get_outreach_stats`, `preview_lead_outreach`, `send_lead_outreach`, `check_replies` |
| Email templates | `list_email_templates`, `get_email_template`, `preview_email_template`, `create_email_template`, `update_email_template`, `activate_email_template`, `duplicate_email_template`, `archive_email_template`, `seed_template_library` (super admin), `generate_email_sequence` (AI, costs credits) |
| Draft review queue | `list_email_drafts`, `get_email_draft`, `generate_email_drafts`, `update_email_draft`, `rewrite_email_draft`, `check_spam_with_suggestions`, `fix_draft_spam_words`, `get_deliverability_score`, `approve_email_drafts`, `reject_email_draft`, `send_email_drafts`, `delete_email_drafts` |
| Objections & macros | `list_objection_responses`, `create_objection_response`, `update_objection_response`, `use_objection_response`, `delete_objection_response`, `list_reply_macros`, `create_reply_macro`, `update_reply_macro`, `use_reply_macro`, `delete_reply_macro` |
| Inbox | `list_inbox_threads`, `get_inbox_thread`, `get_inbox_stats`, `list_reply_drafts`, `suggest_reply`, `mark_thread_read`, `categorize_thread`, `generate_reply_draft`, `approve_reply_draft`, `reject_reply_draft`, `send_inbox_reply` |
| Reports | `report_campaign_performance`, `report_mailbox_health`, `report_daily_activity`, `report_client_analytics` |

Some tools need a particular role in NeuraLeads (e.g. templates and exclusions: workspace admin;
`restore_mailbox`, `seed_template_library`, `list_workspaces`: super admin; `start_warmup_recovery`:
warmup-settings "full" permission). Paid plan features (warmup, email preview, AI sequence
generator) return a clear "not in your plan" message when missing.

Prompts: `weekly_pipeline_review`, `mailbox_health_triage`, `launch_campaign_for_leads`, `content_studio`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `NEURALEADS_API_URL` | `https://neuraleads.ai/api/v1` | REST API base |
| `NEURALEADS_API_KEY` | — | Key used in stdio mode (ignored when hosted) |
| `NEURALEADS_TENANT_ID` | — | Default workspace for a super-admin key in stdio mode (sent as `X-Tenant-ID`; ignored when hosted) |
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
