# Plan — RP Integration Phase 2 (RP → RA attribution feedback loop)

## Goal
Resource Pool emits webhooks on offer.accepted / placement.created / invoice.paid →
RA Agent receives (HMAC-verified), maps back to the originating lead + campaign/source
via externalRef (ra-lead-<id>), and records attribution (campaign → placement → revenue).

## Resource Pool (Next.js)
- [ ] webhooks.ts: register events offer.accepted, placement.created, invoice.paid (offer.created exists)
- [ ] Dispatch on: placement create (with job.jobCode + bill/pay rate + candidate),
      offer status→ACCEPTED, invoice status→PAID. Include `externalRef` (job.jobCode) when resolvable.

## RA Agent (FastAPI)
- [ ] Model: ResourcePoolAttribution (tenant_id, lead_id?, external_ref, event_type, amount, currency,
      rp_ids_json, campaign_id?, source?, occurred_at, raw_json) + migration in main.py lifespan
- [ ] Setting: resourcepool_webhook_secret (shared HMAC secret)
- [ ] Receiver: POST /integrations/resource-pool/webhook — verify X-Exzelon-Signature (HMAC-SHA256),
      parse event, map externalRef ra-lead-<id> → lead → source + campaign, upsert attribution row
- [ ] Reporting: GET /integrations/resource-pool/attribution — summary by source/campaign (count, revenue)
- [ ] Tests: signature verify (good/bad), event→lead mapping, idempotent upsert, summary

## Wiring
- [ ] Register an RP WebhookEndpoint pointing at the RA receiver URL with the shared secret

## Acceptance
- A simulated placement.created webhook (HMAC-signed) creates/updates one attribution row mapped to
  the correct lead + source; bad signature → 401; summary endpoint reports the revenue.
