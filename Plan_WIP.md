# Plan WIP

## SESSION_CONTEXT_RETRIEVAL
> Branch `feature/pre-enrichment-exclusion-gate`. Foolproof pre-enrichment
> exclusion gate — guarantee ZERO paid API (contact-discovery + LLM) spend on
> unwanted leads via ANY entry path. Full plan + design in
> `Plan_Exclusion_Gate_Foolproof.md`.
> Implementation is COMMITTED (e652dde enrichment choke-point + c487532 sealed
> entry paths). Remaining = tests + verification + commit tests + push + PR.
> STATUS (2026-07-07): new tests written; fixed 2 test-only bugs in
> test_enrichment_exclusion_gate.py (return-shape `result["excluded"]`, and
> `_make_lead` duplicate lead_status kwarg). Unit + integration gate tests GREEN.
> Full backend suite running to confirm zero regressions, THEN commit the
> uncommitted BACKEND test files and open PR.

## Immediate TODO
- [x] Implement gate (lead_eligibility.py) + wire enrichment choke-point (committed)
- [x] Seal entry paths + ad-hoc search + salary + EXCLUDED status (committed)
- [x] Write unit tests (test_lead_eligibility.py) — GREEN
- [x] Write integration tests (test_enrichment_exclusion_gate.py) — fixed 2 test bugs, GREEN
- [x] Salary unit tests in test_company_filters.py + rate-limiter reset fixture in conftest.py
- [ ] Full backend suite green (running)
- [ ] Commit backend test files, push, open PR to master
- [ ] Decide on unrelated uncommitted FRONTEND changes (see Blockers)

## Completed
- [x] Traced pipeline, mapped paid call sites, locked design decisions (2026-07-07)
- [x] Gate + entry-path sealing implemented and committed (2026-07-07)

## Blockers / Notes
- UNRELATED uncommitted frontend changes present, NOT part of this gate feature:
  - `frontend/src/app/dashboard/lob/page.tsx`: adds `useAuthStore` import that is
    NEVER used → orphaned/broken edit, would fail ESLint. Likely revert.
  - `login/__tests__/login.test.tsx`, `mailboxes/__tests__/page.test.tsx`: stale-test
    alignment to current UI (NeuraLeads AI Agent, /signup link, mailbox wizard,
    refresh_token). Legitimate but separate concern from the backend gate.
  - `frontend/tsconfig.tsbuildinfo`: build artifact.
  → Plan: keep this PR backend-only (the gate). Handle frontend fixes separately.
