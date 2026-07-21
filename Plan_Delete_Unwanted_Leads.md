# Plan — Delete Unwanted Leads (preserve companies + contacts)

**Date:** 2026-07-21 · **Env:** production (`187.124.74.175`, db `exzelon_ra_agent`)
**Scope chosen:** the 38 leads rejected by the production `LeadEligibilityGate`
**Method chosen:** hard delete + full backup

## What gets deleted
- **38 `lead_details` rows** (tenant 1), lead_ids from `/tmp/unwanted_leads.csv`.
- Reasons: `keyword_excluded` (28), `excluded_company_list` (4), `salary_below_threshold` (4), `placeholder_company` (2).

## What is preserved (verified)
- **`client_info` (companies)** — never referenced by a lead FK → untouched (8,906 rows).
- **`contact_details` (contacts)** — FK `ON DELETE SET NULL`; the 58 linked contacts stay, their `lead_id` becomes NULL (16,030 rows unchanged).
- `lead_contact_associations` — FK `ON DELETE CASCADE`; the 83 junction rows auto-remove (join links only, not contacts).

## Safety checks (verified before writing this plan)
- `outreach_events`, `outreach_drafts`, `campaign_contacts` (the 3 `ON DELETE NO ACTION` FKs) have **0 rows** referencing these 38 leads → no blocker, no outreach history lost.
- Full pre-delete backup of the 38 lead rows + 83 associations + 58 contact→lead links written to `/tmp/unwanted_leads_backup.json` (restore source).

## Execution steps
1. `scripts/delete_unwanted_leads.py` (dry-run) → writes backup, prints what would be deleted. ✅ show output.
2. Re-run with `--execute` → `DELETE FROM lead_details WHERE lead_id IN (…38…)` in one transaction.
3. Post-delete verification:
   - leads 14,604 → 14,566 (−38)
   - contacts 16,030 → 16,030 (Δ0)
   - clients 8,906 → 8,906 (Δ0)
   - unwanted remaining = 0
   - the 58 formerly-linked contacts now have `lead_id IS NULL`

## Rollback
Restore from `/tmp/unwanted_leads_backup.json` (re-INSERT lead rows with original ids, re-link contacts, re-insert associations).

## Not in scope (deliberately)
Big / too-small / stale / high-applicant leads from the manual review — **not identifiable** (size/industry NULL in DB; the root cause). Revisit after firmographic enrichment is fixed (Apollo 422) + backfilled.
