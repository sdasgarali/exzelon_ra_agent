# Plan — MCP Phase 2: full coverage + backend tenant fixes

> Created 2026-10-07. User: "go ahead, build all of them and fix all". Branch `feature/mcp-phase2`
> (from master 1e91924). Phase 1 = PR #122 (see Plan_MCP_Connector.md, CLAUDE_REFERENCE/mcp-connector.md).

## Scope
1. Workspace selection for super-admin keys (MCP + backend header passthrough).
2. Content tools: email templates, AI sequence generator, email-preview drafts, objections, reply macros.
3. Data management: create/edit leads, contacts, companies; delete/merge (admin key + confirm);
   Google Sheet import (preview + import); saved searches; company exclusions; export as summary.
4. Mailbox setup: create mailbox without credentials (finish in UI), archive/restore (confirm),
   OAuth = return the UI link. Passwords/SMTP secrets never pass through MCP (by design).
5. Backend tenant bugs, then expose: direct outreach send, outreach event log/stats, check replies,
   warmup assess (tenant-scoped), warmup recovery.
6. Other bugs found 2026-10-07: contacts/stats cross-tenant count + enum keys, ai-search "in"→IN,
   deliverability summary defaults + can_send ignoring failed connections, demo-seed duplicate,
   seed-test tenant_filter, suggest_* tools unusable with read keys.

## Work partition (parallel agents, each in its own git worktree; integrator = main session)
| Agent | Owns (writes) | Must not touch |
|---|---|---|
| B1 warmup+deliverability | `api/endpoints/warmup.py`, `services/warmup/*`, `services/pipelines/warmup_engine.py`, `schemas/sender_mailbox.py`, `schemas/warmup.py`, `api/endpoints/deliverability.py`, `services/deliverability*`/`seed_tester*`, `api/endpoints/mailboxes.py` (can_send only), new tests `tests/integration/test_warmup_tenant_scope.py`, `test_deliverability_fixes.py` | everything else |
| B2 outreach+validation+enroll+inbox | `api/endpoints/outreach.py`, `api/endpoints/leads.py` (bulk/outreach* only), `services/pipelines/outreach.py`, `api/endpoints/validation.py`, `services/pipelines/email_validation.py`, `api/endpoints/campaigns.py` (enroll only), `services/campaign_engine.py` (enroll only), `api/endpoints/inbox.py` (reply only), `services/reply_checker*`, new tests `test_outreach_tenant_scope.py`, `test_validation_tenant_scope.py`, `test_enroll_and_reply_guards.py` | everything else |
| B3 misc backend | `api/endpoints/contacts.py`, `services/ai_lead_search.py`, `services/demo_seeder.py`, `core/api_key_scopes.py`, `api/deps/auth.py` (only if X-Tenant-ID needs a fix for API keys), new tests | everything else |
| M  MCP tools | `mcp_server/**` only | backend/, frontend/ |

Integration (main session): merge the 4 branches, full backend suite + MCP suite, ruff, docs
(`CLAUDE_REFERENCE/mcp-connector.md`, `api-endpoints.md`, README), PR, merge, deploy, live test.

## Checklist
- [ ] B1 warmup/deliverability fixes + tests
- [ ] B2 outreach/validation/enroll/inbox fixes + tests
- [ ] B3 misc fixes + tests
- [ ] M  MCP phase-2 tools + tests
- [ ] Integrate, full suites green, docs
- [ ] PR + merge (+ watch master, ruleset 24662252 blocks force-push)
- [ ] Deploy (deploy.sh + `install_mcp.sh` for the MCP package) + live test on sandbox tenant 12

## Acceptance
- Every endpoint the connector calls is tenant-scoped server-side (regression test per fix: tenant A
  cannot read/act on tenant B).
- New MCP tools: unit + e2e against real API; destructive ones need admin key + confirm=true.
- Backend suite, MCP suite green; ruff clean; frontend untouched.
