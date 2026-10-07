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
| `src/neuraleads_mcp/tools/*.py` | One module per area; each has `register(mcp, rt)` |
| `src/neuraleads_mcp/__main__.py` | CLI; `build_http_app()` for hosted mode |
| `tests/` | unit (respx), e2e vs the real API, hosted HTTP, stdio entry point |

## API-key scopes (backend, `app/core/api_key_scopes.py`)
Checked in `get_current_user` for every API-key request (403 with a clear reason):
- `read` — GET/HEAD/OPTIONS + compute-only POSTs (`/leads/ai-search`, `/leads/database-search`,
  `*/preview`, `*/enrollment-preview`, `/campaigns/compare`, `/spam-check`).
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

## Backend gaps the connector works around (fix in the backend, then simplify)
Found 2026-10-07 while specifying the tools; **not yet fixed**:
- `/warmup/*` by mailbox id (`assess/{id}`, `analytics`, `alerts`, `alerts/{id}/read`,
  `profiles/{p}/apply/{m}`, `recovery/{id}/start`, `dns/{id}`, `blacklist/{id}`) has no tenant
  check; `POST /warmup/assess` (no id) assesses **all tenants**. Connector: ownership pre-check,
  never calls `/warmup/assess`, filters alerts to own mailboxes.
- `POST /campaigns/{id}/contacts` doesn't check contact ownership. Connector: verifies each id.
- `POST /outreach/send-emails`, `/outreach/run-mailmerge`, `/leads/bulk/outreach[/preview]`,
  `/outreach/check-replies` run without the caller's tenant (fall back to tenant 1 / all
  mailboxes); `/leads/bulk/outreach` has no role check. Connector: **does not expose them**;
  outreach goes through campaigns (scheduler) only.
- `POST /validation/validate-bulk` and `/validate-pending-contacts` don't pass tenant_id;
  `/validation/results` and `/stats/summary` are global. Connector: uses
  `/pipelines/email-validation/run[-selected]` and `/contacts/stats` instead.
- `POST /inbox/reply` bypasses the send gate. Connector: refuses unsubscribed / do_not_contact
  and requires confirm; prefers `approve_reply_draft` (gated).
- Mailbox status `recovering` isn't in `WarmupStatusEnum` → mailbox serialisation 500s after
  `POST /warmup/recovery/{id}/start`. Connector: does not expose recovery.
Fixed in this branch: `DELETE /clients/{id}` (500 + cross-tenant cascade) and
`/pipelines/email-validation/run-selected` tenant attribution.

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
