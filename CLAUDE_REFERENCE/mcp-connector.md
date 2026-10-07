# MCP Connector — NeuraLeads for AI tools

> Referenced from: `CLAUDE.md` — read this before changing `mcp_server/`, API-key scopes, or adding
> an endpoint that AI tools should reach.

## What it is
`mcp_server/` is a standalone Python package (`neuraleads-mcp`) that exposes NeuraLeads to MCP
clients (Claude Code/Desktop/claude.ai, Cursor, …). It is a **thin REST client**: every tool calls
`/api/v1` with the caller's API key (`X-API-Key`), so RBAC, tenant isolation, plan gates (402),
credits and send rules are enforced by the backend, never re-implemented. User docs:
`mcp_server/README.md`.

- **Own venv.** The `mcp` SDK (2.x, `MCPServer`, formerly FastMCP) needs pydantic ≥ 2.7; the
  backend pins 2.6.1. Never add `mcp` to `backend/requirements.txt`.
- **Transports.** `neuraleads-mcp` (stdio, key from `NEURALEADS_API_KEY`) and
  `neuraleads-mcp --transport http` (stateless Streamable HTTP at `/mcp`, `/healthz`). Hosted
  mode takes the key **per request** (`Authorization: Bearer` or `X-API-Key`) and never falls back
  to a server key.

## Layout
| File | Role |
|---|---|
| `src/neuraleads_mcp/config.py` | Env settings (`APP_ENV` prefix support, fail-fast validation) |
| `src/neuraleads_mcp/client.py` | httpx client; HTTP status → actionable message; retries **GET only** |
| `src/neuraleads_mcp/runtime.py` | Key resolution, `sanitize()` (strips credential fields), annotation presets, `confirmation_required()`, `pick/pick_list` |
| `src/neuraleads_mcp/server.py` | `build_server()` — registers tool modules + prompts + `/healthz` |
| `src/neuraleads_mcp/tools/*.py` | One module per area (`account`, `leads`, `contacts`, `mailboxes`, `campaigns`, `inbox`, `reports`, `content`, `data`, `outreach`); each has `register(mcp, rt)`. 148 tools (73 read-only). |
| `src/neuraleads_mcp/__main__.py` | CLI; `build_http_app()` for hosted mode |
| `tests/` | unit (respx), e2e vs the real API, hosted HTTP, stdio entry point |

## API-key scopes (backend, `app/core/api_key_scopes.py`)
Checked in `get_current_user` for every API-key request (403 with a clear reason):
- `read` — GET/HEAD/OPTIONS + compute-only POSTs (`/leads/ai-search`, `/leads/database-search`,
  `*/preview`, `*/enrollment-preview`, `/campaigns/compare`, `/spam-check`, `/suggest-reply`,
  `/ai-suggest-subjects`, `/templates/score|fixes|apply-fixes`, `/templates/{id}/preview`,
  `/leads/import/google-sheet/preview`, `/saved-searches/{id}/execute`). Not allowed (they write or
  spend credits): email-preview ai-rewrite, deliverability-score, preview-personalization,
  sequence-generator.
- `write` — all but DELETE; never `/auth`, `/users`, `/roles`, `/admin`, `/billing`, `/gdpr`,
  `/backups`, `/activity`, `/integrations/api-keys`.
- `admin` — everything the owner can do.
- **No key may create/revoke keys**; unknown/empty scopes = read-only. Keys:
  `POST/GET/DELETE /integrations/api-keys` (`scopes`, `expires_in_days`), UI: Settings → "12. API
  Keys & MCP" (`frontend/src/components/settings/api-keys-mcp-tab.tsx`).

## Tool rules (follow when adding tools)
1. Register write tools only when `not rt.settings.read_only`; give every tool an annotation preset
   (`READ`, `WRITE`, `WRITE_IDEMPOTENT`, `EXTERNAL`, `DESTRUCTIVE`) and a real docstring.
2. Anything that sends email, launches/completes a campaign, changes mailbox status or spends
   credits takes `confirm: bool = False` and returns `confirmation_required(...)` (with a preview
   where an endpoint offers one) until `confirm=True`.
3. Trim output with `pick`/`pick_list`; cap list sizes with `clamp_limit` (max 100).
4. **Ownership pre-checks** for routes that don't scope by tenant (see below): resolve the id via
   a tenant-scoped GET first; a 404 there stops the tool.
5. If a POST only reads, add its path to `_READ_ONLY_POST_SUFFIXES` so read keys can use it.

## Tenant isolation history (phase 2, 2026-10-07)
The phase-1 connector worked around backend routes that ignored the caller's tenant. Phase 2
(`Plan_MCP_Phase2.md`) fixed them server-side, each with an A-cannot-touch-B regression test:
- warmup by-id routes, alerts, analytics, peer history, export, dns/blacklist checks; `/warmup/assess`
  scoped to the caller (scheduler still assesses all); `recovering` added to `WarmupStatusEnum`
- deliverability: real health summary (`failed_connection_count`, …); mailbox `can_send` false when
  the connection failed; seed-test scoped
- outreach send / mail-merge / bulk outreach (+ role check) / check-replies run under the caller's
  tenant; validation pipelines + results/stats scoped
- enrollment rejects foreign contacts (400); `enroll_contacts` + auto-enroll filter by tenant
- inbox reply refuses suppressed / unsubscribed / do_not_contact before sending
- contacts/stats leak; saved-search execute; campaign engine mailbox selection (`select_best_mailbox`
  takes `tenant_id`) + fair due-contact batching; peer warmup scheduler ran each mailbox N times
- wave 2 (B4): contacts create/update lead ownership, templates import-to-step, broadcast drafts,
  `POST /mailboxes` duplicate/role/user lookups, single-lead outreach role check, `POST /outreach/events`
The connector keeps its ownership pre-checks as defence in depth.

**Still open (need a model/product decision):** `WarmupProfile` and `PUT /warmup/config` are global
across tenants (no tenant_id); peer-warmup pairing is a shared cross-tenant pool (looks
deliberate); AI calls in email-preview rewrite / spam suggestions / suggest-reply are not
credit-metered.

## Workspace selection (super-admin keys)
A super-admin key without `X-Tenant-ID` sees ALL tenants (the key's stored tenant_id is
bookkeeping only). The connector forwards an incoming `X-Tenant-ID` header (hosted) or
`NEURALEADS_TENANT_ID` (stdio only). Non-super-admin keys always get their own tenant; the header
is ignored. `list_workspaces` = `GET /admin/tenants` (super admin).

## Run / test
```bash
cd mcp_server && uv venv .venv && uv pip install -e ".[dev]"
.venv/Scripts/python -m pytest          # needs backend/venv for the e2e tests (auto-detected,
                                        # or NEURALEADS_BACKEND_PYTHON=...); they boot the real
                                        # API on a temp SQLite file and seed two tenants
```

## Deploy (hosted `/mcp`)
`deploy/mcp/install_mcp.sh` (venv + `pip install`, default `.env`, systemd unit
`deploy/systemd/neuraleads-mcp.service`, health check) and `deploy/mcp/nginx-mcp-location.conf`
(include in the neuraleads.ai server block). Loopback port 8010 (verify free with `ss -tlnp`
first). See `CLAUDE_REFERENCE/deployment.md` → "MCP connector".
