# Plan — Deal Detail 360 (mail chain + job + candidates + status/notes)

> Branch: `feature/deal-detail-360`. Date: 2026-08-16.
> Decisions (confirmed): Candidates = **BOTH** (in-app submissions on the deal + link to
> Resource Pool ATS). Mail chain = **inline thread + "Open in Inbox" link**. Plus job
> details, and the existing status(stage)+notes made prominent.

## What exists (reuse)
- Job: `Deal → contact_id → ContactDetails.lead_id → LeadDetails` (job_title, job_link,
  salary_min/max, company, company_size, posting_date, description).
- Mail chain: `OutreachEvent` (sends: subject, body, sent_at) + `InboxMessage`
  (threaded, direction sent/received, subject, body, received_at) by contact_id.
- RP ATS: `resource_pool_client.build_external_ref(lead_id, tenant_id)` + base_url; jobs
  are addressable by external_ref (jobCode).
- Status = deal stage selector (exists). Notes = DealActivity timeline + add-note (exists).

## New model: DealCandidate
`deal_candidates`: deal_candidate_id, tenant_id(FK), deal_id(FK, index), name,
email, phone, linkedin_url, resume_url, status
(submitted|reviewed|sent_to_client|placed|rejected), notes, submitted_by_user_id(FK),
+ Base (created_at/updated_at/is_archived). Auto-created via Base.metadata.create_all
(register in db/base.py + models/__init__).

## PR A — Backend
- [ ] DealCandidate model + registration.
- [ ] Candidate CRUD (deals.py): GET/POST/PUT/DELETE `/deals/{id}/candidates[/{cid}]`.
      Add/edit by rep(bdm/recruiter)+admin; submitted_by=current user; status pipeline;
      tenant-scoped; logs a DealActivity ("candidate_submitted"/"candidate_status").
- [ ] Mail chain: GET `/deals/{id}/messages` — merge OutreachEvent(sent) + InboxMessage
      for the deal's contact, chronological ascending; {direction, subject, body_preview,
      from, to, at}. Empty when no contact.
- [ ] Enrich GET `/deals/{id}`: `job` (lead details or null), `resource_pool`
      {external_ref, ats_url or match_url}, `candidate_count`, `contact` basics.
- [ ] Tests: candidate CRUD + perms/isolation; messages merged/ordered; job in detail.

## PR B — Frontend (deal detail drawer)
- [ ] Restructure drawer into sections: **Overview** (value/prob/claim/owner/age +
      **Status** stage selector + **Job details** card w/ job_link + **ATS link**),
      **Candidates** (list w/ status badges + Add/Edit form), **Conversation** (inline
      sent/received bubbles + "Open in Inbox" link), **Activity/Notes** (existing + add).
- [ ] Clicking a deal on the Deals page OR the dashboard My Queue opens this detail.
- [ ] dealsApi: candidates CRUD, messages; consume enriched get.

## PR C (optional) — deploy both, verify on prod.

## Notes / risks
- Candidates are IN THIS system (demand-gen), distinct from the RP ATS candidate records;
  the ATS link points to the job's ATS page. Keep the two clearly labeled.
- Mail-chain merge may show a send twice if it's in both OutreachEvent and InboxMessage;
  acceptable for v1 (label source, sort by time).
- My Queue widget currently links to /dashboard/deals (list). Ensure clicking opens the
  deal detail (pass deal id via query or open drawer) — small enhancement.
