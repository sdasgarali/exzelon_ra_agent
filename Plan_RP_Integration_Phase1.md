# Plan — RP Integration Phase 1 (RA Agent → Resource Pool hand-off)

## Goal
On a qualified lead, RA Agent pushes **Job + Company + Contact + Opportunity** into Resource Pool
via a new RP REST API endpoint. One-way, idempotent, manual trigger first.

## SESSION_CONTEXT_RETRIEVAL
> Building Phase 1 of the RA↔RP integration. Two repos: RA Agent (FastAPI/MySQL, this repo) +
> Resource Pool (Next.js/Prisma/Postgres at ...\agentic_ai_recruiter\resource-pool).
> Step: reading exact patterns on both sides, then implement RP endpoint + RA connector.

## Tasks
### Resource Pool (Next.js) — the intake endpoint
- [ ] Read: src/app/api/v1/candidates/route.ts (auth + shape), api-key auth helper, prisma models
      (Job, Company, Contact, Opportunity — required fields, enums, unique keys), lib/prisma.ts, Zod pattern
- [ ] Add scope `leads:write` (or reuse jobs:write) to API-key scopes
- [ ] Create POST /api/v1/leads — idempotent upsert of Company → Contact → Job → Opportunity
      keyed by external ids (externalRef / email / domain). Zod-validated. Returns created/updated ids.
- [ ] Unit/route test if a test harness exists

### RA Agent (FastAPI) — the connector
- [ ] Settings: resourcepool_api_url, resourcepool_api_key (+ SETTINGS_TAB_MAP, DEFAULT_SETTINGS, config.py)
- [ ] Service: services/integrations/resource_pool_client.py — httpx client, push_lead(payload), retry, idempotency, cost/log
- [ ] Mapper: LeadDetails+ClientInfo+ContactDetails → RP payload
- [ ] Endpoint: POST /api/v1/integrations/resource-pool/push-lead/{lead_id} (manual trigger; RBAC)
- [ ] Store cross-system id map (lead_id ↔ rp job id) — new table or metadata_json
- [ ] Tests (unit: mapper + client contract)

## Acceptance
- Given a lead, calling the RA push endpoint creates/updates the matching Job+Company+Contact+Opportunity
  in RP, is idempotent on repeat, and records the RP ids back on the RA side.

## Completed
- (none yet)

## Notes / decisions
- Manual trigger endpoint first; auto-on-positive-reply is Phase 1.5.
- Idempotency keys: company by domain/name; contact by email; job by external job_link.
