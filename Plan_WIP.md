# Plan WIP

## SESSION_CONTEXT_RETRIEVAL
> Implementing 3 deliverables on branch `feature/cost-tracking-and-query-negatives`:
> (a) API cost report as .docx, (b) cost tracking for contact-discovery + AI layers,
> (c) query-side negative-keyword filtering for job boards that support it.
> Then commit, push, deploy to VPS.
> (Prior session 95 — Tenant-to-LOB Mapping — already merged to master.)

## Immediate TODO
- [ ] (a) Generate API cost report .docx (scripts/generate_api_cost_report.py)
- [ ] (b1) cost_tracker.py: add CONTACT_DISCOVERY + AI model pricing; generalize record_pipeline_cost (category, tenant_id); add record_ai_cost()
- [ ] (b2) contact_enrichment.py: record per-adapter cost from adapter_stats at end of run
- [ ] (b3) AI adapters (openai/groq/gemini/anthropic): record token cost in _call_api via base helper; wire _cost_db/_cost_tenant_id in get_ai_adapter factories
- [ ] (c1) base.py: helpers build_negative_terms() + google_negative_suffix()
- [ ] (c2) serpapi.py, jsearch.py (Google-syntax -kw), adzuna.py (what_exclude) — push negatives into query; keep local filter as backstop
- [ ] (c3) lead_sourcing.py: read `push_exclusions_to_query` setting, pass _push_negatives to adapters
- [ ] Tests: add unit tests for new pricing/recording + negative-term builders; run full backend suite
- [ ] Update CLAUDE_REFERENCE (services.md / adapters.md) + memory
- [ ] Commit, push, open PR, merge, deploy to VPS, verify

## Completed
- [x] Analyzed cost tracking + filter data flow; produced production cost report (2026-06-17)

## Blockers / Notes
- AI cost recording uses caller's db session via begin_nested() SAVEPOINT for isolation (no new SessionLocal → no test side effects; adapters built without _cost_db simply skip recording).
- Local filter_excluded() stays in place as backstop; query-side negatives are an optimization only.
- Pricing values are estimates, overridable via Settings key `provider_pricing`.
