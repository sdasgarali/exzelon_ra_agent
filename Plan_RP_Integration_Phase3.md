# Plan — RP Integration Phase 3 (candidate fit-score + match-summary feed)

## Goal
Consolidate candidate matching in Resource Pool with the calibrated fit-score rubric,
and expose a per-job "match summary" the RA Agent consumes to power the cold-email pitch
("we already have N candidates >80% fit for this role").

## Resource Pool
- [ ] services/fit-score.ts: deterministic explainable rubric (skills 28, title 22, seniority 15,
      location 12, industry 10, salary 8, active-recency 5) + hard gates (must-have skill, location,
      seniority floor) capping disqualified candidates; returns { fit_0_100, breakdown[], gates }.
      (Platt calibration = documented follow-on; needs labeled outcomes.)
- [ ] GET /api/v1/jobs/by-code/{jobCode}/match-summary (API key, scope jobs:read):
      score active candidates for the job, return { threshold, matchCount, topMatches[] (anonymized:
      fitScore, title, location, topReasons), generatedAt }.

## RA Agent
- [ ] ResourcePoolClient.get_match_summary(external_ref) → GET the RP summary
- [ ] GET /integrations/resource-pool/match-summary/{lead_id} (RBAC) → summary for a lead
- [ ] Tests (client + endpoint)

## Acceptance
- For a job pushed as ra-lead-<id>, the RA endpoint returns the RP match summary
  (count ≥80% + top anonymized matches); unconfigured → 400.
