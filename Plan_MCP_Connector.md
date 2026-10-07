# Plan — NeuraLeads MCP Connector

> Created 2026-10-07. Goal: let AI tools (Claude Desktop / Claude Code / claude.ai, Cursor, ChatGPT,
> any MCP client) operate NeuraLeads: mailboxes, lead sourcing, contact enrichment, email
> validation, outreach campaigns, warmup, inbox, reports.

## Findings (current state)
- API-key auth already exists: `X-API-Key` header in `api/deps/auth.py::get_current_user`
  (SHA-256 hash lookup → acts as the key's owner user, so RBAC + tenant isolation + plan gates +
  credit gates all apply unchanged).
- Key CRUD exists: `POST/GET/DELETE /api/v1/integrations/api-keys` (`integrations.py`), with
  `scopes` (default `["read"]`) stored in `api_keys.scopes_json`.
- Gaps: (a) **scopes are never enforced** — a "read" key can POST/DELETE; (b) **no UI** to create
  or revoke keys; (c) `CLAUDE_REFERENCE/api-endpoints.md` lists a non-existent `/api-keys` router.
- Backend pins `pydantic==2.6.1`; the official `mcp` Python SDK needs pydantic ≥ 2.7, so the MCP
  server must live in its **own package + venv** (also keeps the API process untouched).

## Architecture
```
AI client ──MCP (stdio or Streamable HTTP)──► neuraleads-mcp ──HTTPS + X-API-Key──► /api/v1 (FastAPI)
```
- New top-level package `mcp_server/` (Python 3.12, `mcp` SDK / FastMCP, `httpx`).
- **Thin REST client — no direct DB access.** Every tool calls an existing endpoint, so all
  existing security (RBAC, tenant scoping, feature 402s, credit 402s, send limits, cooldown,
  exclusion gate, Valid-only outreach) is enforced by the backend, not re-implemented.
- Two transports from one codebase:
  1. **stdio** (local): `NEURALEADS_API_KEY=… neuraleads-mcp` — for Claude Desktop/Code, Cursor.
  2. **Streamable HTTP** (hosted): `https://neuraleads.ai/mcp`, key passed per request as
     `Authorization: Bearer nl_…` (or `X-API-Key`) and forwarded upstream. Stateless; no key stored.
- Config via `.env` per global standard (`APP_ENV` + `${APP_ENV}_NEURALEADS_API_URL`, etc.).

## Safety model
- Every tool carries MCP annotations (`readOnlyHint` / `destructiveHint` / `idempotentHint`).
- Backend enforces key scopes (new): `read` → GET/HEAD only; `write` → all except DELETE;
  `admin` → everything. A read-only key physically cannot send email or delete data.
- High-impact tools (activate campaign, run outreach, send reply, delete) require an explicit
  `confirm: true` argument; without it they return a dry-run preview (uses existing `/preview`
  and `enrollment-preview` endpoints where available).
- Server flag `NEURALEADS_MCP_READ_ONLY=true` hides all write tools.
- Errors: backend 401/402/403/429 mapped to clear tool errors ("feature not in your plan",
  "out of credits", …). Retries with backoff on 5xx/timeouts only (never on POSTs that spend credits).
- Response trimming: list tools paginate (default 25, max 100) and drop heavy fields so the
  AI's context isn't flooded.

## Tool catalogue (v1, ~40 tools)
| Area | Read tools | Write tools |
|---|---|---|
| Account | `whoami`, `get_credit_balance`, `get_price_list`, `get_dashboard_kpis` | — |
| Lead sourcing | `search_leads`, `get_lead`, `ai_lead_search`, `get_lead_stats`, `list_pipeline_runs`, `get_pipeline_run` | `run_lead_sourcing`, `update_lead_status` |
| Companies | `search_companies`, `get_company` | `enrich_company` |
| Contact enrichment | `search_contacts`, `get_contact`, `get_contacts_for_lead`, `estimate_enrichment` | `run_contact_enrichment`, `enrich_leads` |
| Email validation | `get_validation_stats`, `get_validation_result` | `validate_emails`, `validate_pending_contacts` |
| Mailboxes | `list_mailboxes`, `get_mailbox`, `get_mailbox_stats` | `test_mailbox_connection`, `update_mailbox_status` |
| Warmup | `get_warmup_status`, `get_warmup_health_scores`, `list_warmup_alerts`, `get_warmup_analytics` | `check_dns`, `check_blacklist`, `apply_warmup_profile`, `assess_warmup` |
| Campaigns | `list_campaigns`, `get_campaign`, `get_campaign_analytics`, `list_campaign_contacts`, `list_available_leads` | `create_campaign_from_leads`, `add_sequence_step`, `update_sequence_step`, `enroll_contacts`, `activate_campaign`, `pause_campaign`, `resume_campaign`, `ai_suggest_subjects` |
| Outreach | `get_outreach_stats`, `list_outreach_events` | `run_outreach` |
| Inbox | `list_inbox_threads`, `get_inbox_thread`, `get_inbox_stats` | `suggest_reply`, `send_reply`, `categorize_thread` |
| Reports | `report_campaign_performance`, `report_mailbox_health`, `report_daily_activity` | — |

Plus MCP **prompts** (canned workflows): `weekly_pipeline_review`, `launch_campaign_for_leads`,
`mailbox_health_triage`. Plus **resource** `neuraleads://business-rules` (send limit, cooldown, etc.).
Exact endpoint ↔ tool mapping is verified against the route signatures during slice 3.

## Slices (each = commit on `feature/mcp-connector`)
- [x] 1. Backend: enforce API-key scopes in `get_current_user` (+ `api_key_scopes` on request state);
      validate scopes on create (`read|write|admin`); cap key creation to admins of the tenant.
      Tests: read key → 403 on POST/DELETE, write key → 403 on DELETE, expired/revoked → 401.
- [x] 2. Frontend: Settings → "API Keys & MCP" tab — create (name, scopes, expiry), show key once
      with copy button, list (prefix, scopes, last used), revoke; copy-paste config snippets for
      Claude Desktop / Claude Code / Cursor / hosted URL. `SETTINGS_TAB_MAP` + roles page entry.
- [x] 3. `mcp_server/` package: config loader, `NeuraLeadsClient` (httpx, auth, error mapping,
      retry policy), tool modules per area, prompts, resource, stdio + HTTP entry points,
      `pyproject.toml` (installable via `pip install ./mcp_server` or `uvx`).
- [x] 4. Tests: unit (client error mapping, arg validation, confirm-gating, trimming) with
      `respx`-mocked HTTP; integration: spin up FastAPI `TestClient` + real SQLite and drive tools
      end-to-end through the MCP in-memory client; MCP Inspector smoke run.
- [x] 5. Docs: `mcp_server/README.md` (install + client configs), `CLAUDE_REFERENCE/mcp-connector.md`,
      fix `api-endpoints.md` (`/integrations/api-keys`), CLAUDE.md table row, `.env.example` keys.
- [x] 6. (DONE 2026-10-07, PR #122 -> 21ed0d5) Deploy (needs your explicit VPS go-ahead): systemd unit `neuraleads-mcp` on a free
      loopback port (checked with `ss -tlnp` first; proposing 8010), nginx `location /mcp` on
      neuraleads.ai, health check; update port table + `deployment.md`.
- [ ] 7. Phase 2 (later, separate approval): OAuth 2.1 for one-click "Add connector" in claude.ai /
      ChatGPT without pasting a key.

## Status 2026-10-07
Slices 1-5 done on `feature/mcp-connector` (82 tools; 46 MCP tests + 1,745 backend tests green).
Changed from plan: no `neuraleads://business-rules` resource (static resources get no request
context, so hosted mode can't authenticate them) — `get_business_rules` tool instead. Key prefix
stays `exz_`. Direct-send outreach endpoints NOT wrapped (tenant bugs, see
CLAUDE_REFERENCE/mcp-connector.md "Backend gaps"). Slice 6 (deploy) waits for VPS authorization.

## Acceptance criteria
- A read-scoped key in Claude Desktop can list mailboxes, leads, campaigns, warmup health — and any
  write attempt fails with a clear "key is read-only" message.
- A write-scoped key can source leads → enrich → validate → create a campaign → activate it, with
  each high-impact step requiring `confirm: true`.
- Tenant A's key never sees tenant B's data (integration test).
- Full backend test suite green; new MCP tests green; ruff clean.

## New dependencies (rationale)
- `mcp` (official Model Context Protocol SDK) — protocol + transports; only in `mcp_server/`.
- `httpx` (already used by backend) — REST client.
- `respx` (dev only) — HTTP mocking in MCP tests.
