# Plan WIP
## SESSION_CONTEXT_RETRIEVAL
> Smart Contact Enrichment and Pipeline Lead Selection (REQ-035 to REQ-038) fully implemented. Backend: lead_ids param + smart contact reuse + bulk enrich endpoints + pipeline endpoint changes. Frontend: Contact Enrich button on leads page + lead selector popup on pipelines page. All verified: Python imports OK, frontend builds clean.

## Immediate TODO
- [ ] End-to-end test: select leads on Leads page -> Contact Enrich -> verify preview shows reuse/skip/enrich
- [ ] End-to-end test: Pipelines page -> Contact Enrichment -> lead selector -> run for selected
- [ ] End-to-end test: Pipelines page -> Outreach -> lead selector -> run for selected

## Completed
- [x] Backend: Smart contact reuse (_reuse_existing_contacts, _update_lead_from_contacts) (2026-02-27)
- [x] Backend: lead_ids parameter in run_contact_enrichment_pipeline (2026-02-27)
- [x] Backend: POST /leads/bulk/enrich/preview + /bulk/enrich endpoints (2026-02-27)
- [x] Backend: Contact-enrichment/run + outreach/run accept optional lead_ids body (2026-02-27)
- [x] Backend: parse_counters updated with contacts_reused + api_calls_saved (2026-02-27)
- [x] Frontend: bulkEnrichPreview + bulkEnrich added to leadsApi (2026-02-27)
- [x] Frontend: pipelinesApi.runContactEnrichment + runOutreach accept optional leadIds (2026-02-27)
- [x] Frontend: Contact Enrich button + preview modal + results modal on leads page (2026-02-27)
- [x] Frontend: Lead selector popup on pipelines page for Contact Enrichment + Outreach (2026-02-27)
- [x] Master_Plan.md updated with REQ-035 to REQ-038 (2026-02-27)
- [x] Verification: All backend imports OK, frontend builds clean (2026-02-27)

## Previous Work
- [x] DB migration: ALTER TABLE outreach_events ADD message_id + sender_mailbox_id (2026-02-26)
- [x] Backend: Enrich lead detail endpoint with contact_name, contact_email, sender_name, sender_email (2026-02-26)
- [x] Frontend: Inbox-style email thread view with HTML iframe, reply blocks, UNSUBSCRIBE badges (2026-02-26)
- [x] Reply tracker service, scheduler job, API endpoints (2026-02-26)
- [x] Email Templates feature fully implemented (2026-02-26)

## Blockers / Notes
- Write/Edit tools have Windows path issues; used python3 -c workaround for backend, Write/Edit tools for frontend
- SQLAlchemy create_all creates new tables with all columns; existing tables need ALTER TABLE
