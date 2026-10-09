# Plan — AI Copilot on DeepSeek, feature-aware, with memory (2026-10-09)

## Problem (verified)
- Prod `POST /api/v1/copilot/chat` returns **503** (nginx + API logs 2026-10-09 14:48/14:49 UTC):
  no AI key resolves. Provider/key come from DB settings (`ai_provider` -> `<provider>_api_key`, `ai_model`),
  tenant settings first, then global (`core/settings_resolver.py`).
- `copilot.py:74` calls `get_ai_adapter(db)` WITHOUT tenant_id -> tenant-level AI settings ignored, cost tracked to no tenant.
- DeepSeek not supported (factory `services/adapters/ai_content.py` knows groq/openai/anthropic/gemini only).
- Anthropic adapter gets a `system` role inside messages (API rejects); Gemini `_call_api` expects str, gets list.
- System prompt: no product feature knowledge, no off-topic refusal. No memory (client state only, lost on reload).
- Frontend `copilot-chat.tsx` swallows every error into "Sorry, I encountered an error"; no suggested prompts.

## User requirements
1. Copilot works, on DeepSeek (key supplied by user — store ONLY in prod DB settings, never git/memory/docs).
2. Functional: when a user wants something, recommend the right feature/page and how to use it.
3. Remember: conversation persists per user (survives reload / new session).
4. Refuse off-topic questions (only NeuraLeads / cold outreach / lead gen / deliverability / platform usage).

## Tasks
- [x] 1. Backend: `DeepSeekAdapter` (OpenAI-compatible, base `https://api.deepseek.com/v1`, model `deepseek-chat`, retries like Groq);
      factory + `deepseek_api_key` setting registration + Settings test-connection + cost pricing.
- [x] 2. Backend copilot: pass tenant_id; feature-catalog + guardrail system prompt; persisted memory
      (`copilot_messages` table, Alembic revision, GET/DELETE `/copilot/history`); system prompt passed in a
      provider-safe way (fix Anthropic/Gemini paths).
- [x] 3. Frontend copilot: load history on open, show real error detail, suggested prompts per page,
      clear-history button, request timeout, links to recommended pages.
- [x] 4. Tests (pytest: adapter, factory, copilot endpoint incl. off-topic prompt contract, history isolation per user/tenant;
      jest: widget), build.
- [ ] 5. PR, merge, deploy with Alembic (DB backup first — deploy.sh does not migrate), set prod
      `ai_provider=deepseek` + `deepseek_api_key` (global), live test.
- [x] 6. Docs: CLAUDE_REFERENCE adapters.md, services.md, data-models.md, api-endpoints.md.

## Results (2026-10-09)
- pytest full suite 1994/1994; jest 91/91; tsc OK; next build OK.
- DeepSeek also wired into the 3 standalone factories (warmup content, company enrichment, AI fallback chain).
- Prod settings to apply at deploy: global ai_provider=deepseek, warmup_ai_provider=deepseek, ai_model=deepseek-chat,
  deepseek_api_key=<user key>; tenant 1/2/3 overrides ai_provider/warmup_ai_provider/ai_model -> deepseek (user approved 'DeepSeek everywhere').

## Acceptance
- Copilot answers on prod via DeepSeek; feature questions get a concrete page recommendation;
  off-topic questions get a short refusal; reloading the page keeps the conversation; users never see another user's history.
