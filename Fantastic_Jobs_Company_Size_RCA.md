# RCA — Fantastic.jobs Leads Pass the Size Gate With Wrong Company Size (Wasting Apollo Credits)

**Reported by:** stakeholder — lead `R1603` shows company size **156** in our system, but the company's LinkedIn profile shows **>1,000 employees**. "Many more like this." Result: out-of-ICP large companies pass the ≤500 size gate → we spend Apollo **contact-discovery** credits finding contacts for companies we should have dropped.

**Date:** 2026-08-07 · **Status:** RCA complete, remediation plan below (awaiting approval to implement).

---

## 1. Root Cause (confirmed in code + API schema)

Fantastic.jobs returns **two different LinkedIn size signals** per company (schema `s-fantastic-schemas.md:411,423`):

| API field | Type | Meaning | R1603 value |
|---|---|---|---|
| `org_linkedin_headcount` | integer | "Number of employees **according to LinkedIn**" — i.e. the count of LinkedIn **member profiles** that tag this company entity. **Systematically understated** (not everyone is on LinkedIn / tagged correctly). | **156** |
| `org_linkedin_size` | string band | "Employee count range **according to the company**" — the company's **self-reported** size band shown on the LinkedIn profile. Buckets: `1, 2-10, 11-50, 51-200, 201-500, 501-1000, 1001-5000, 5001-10000, 10001+`. This is what the user sees as ">1000". | **`1001-5000`** |

The pipeline keys **everything** on the understated `headcount` and **discards** the authoritative self-reported band. There are **four** compounding layers:

### Layer 1 — Server-side API filter uses headcount
`fantastic_jobs.py:131-132`
```python
"organization_headcount_gte": 1,
"organization_headcount_lt": (max_employee_count or 200) + 1,   # filters on org_linkedin_headcount
```
Per schema, `organization_headcount_lt` filters on `org_linkedin_headcount`. A 5,000-person company with only 156 tagged LinkedIn members satisfies `156 < 501`, so **the API happily returns it**. The self-reported band is never used as a server-side filter (the `organization_size` bucket param is available but unused).

### Layer 2 — Adapter stores headcount, throws away the band
`fantastic_jobs.py:184-211`
```python
headcount = raw_data.get("org_linkedin_headcount")           # 156
employee_count = int(headcount) ...                          # 156
...
"company_size": str(employee_count) if employee_count else (raw_data.get("org_linkedin_size") or ""),  # -> "156"
"employee_count": employee_count,                            # 156
```
Because `headcount` is present, `company_size` becomes `"156"` and the band `"1001-5000"` (the real ">1000" signal) is **only used as a fallback that never fires**.

### Layer 3 — Size gate keeps it (156 ≤ 500)
`lead_sourcing.py:1612-1617` (`_apply_company_gate`)
```python
size_signal = job.get("_employee_count")     # None — adapter emits "employee_count", gate reads "_employee_count" (key mismatch)
if size_signal is None:
    size_signal = job.get("company_size")     # "156"
if exceeds_size_ceiling(size_signal, max_employee_count):   # 156 > 500 -> False -> KEPT
```
Note the **dead-key bug**: the adapter outputs `employee_count`, the gate reads `_employee_count` (with underscore, only ever set by the LLM enrichment step at line 1595). So the numeric signal is inert; only the `"156"` string drives the decision. Same logic in the enrichment-time gate `lead_eligibility.py:232-236`.

### Layer 4 — The one correction that could fix it is SKIPPED
Apollo-by-domain firmographic enrichment (`company_firmographics.py`, authoritative size by domain — and fantastic_jobs **does** provide `org_linkedin_website`) only runs for companies flagged as **missing** size:
`lead_sourcing.py:1569-1572`
```python
missing = [... for job in jobs
    if not (job.get("industry") and (job.get("company_size") or job.get("_employee_count")))]
```
Because fantastic_jobs supplied *an* industry **and** *a* size (`"156"`), the lead is **not** "missing" → firmographic verification never runs → the wrong 156 is never corrected. Same suppression in the cache path `company_enrichment.py:318-321`.

### Net effect
Lead persists with `company_size="156"` → passes the enrichment-time eligibility gate (`156 ≤ 500`) → **Apollo contact-discovery credits are spent** on a 1,001–5,000-employee company that is out of ICP.

---

## 2. Why the size is not "wrong data" — it's the wrong *field*
This is **not** stale data from Fantastic.jobs. `org_linkedin_headcount=156` is a *correct* count of tagged LinkedIn members; it is simply **not** the company's employee count. LinkedIn company pages show two numbers — the self-reported "Company size" band (`org_linkedin_size`, ">1000") and the "X associated members" figure (`org_linkedin_headcount`, 156). We chose the wrong one for ICP gating.

---

## 3. Remediation Plan

### A. Adapter — capture the authoritative band; keep both signals (`fantastic_jobs.py`)
- Store `company_size` = the **self-reported band** (`org_linkedin_size`) when present (falls back to `str(headcount)`, then `""`). This is what displays as ">1000" and what the ICP gate should judge.
- Keep `employee_count` = `headcount` for completeness/telemetry.
- Rationale: the band's lower bound (`1001`) trips `exceeds_size_ceiling` → the company is dropped at sourcing, never persisted, never enriched → **zero Apollo spend**.

### B. Make the drop decision *conservative across both signals* (`company_filters.py` + both gates)
- Add `exceeds_size_ceiling_any(values, ceiling)` → drops when **any** known signal (band lower-bound OR headcount) exceeds the ceiling (uses `max` of parsed values). Handles the reverse case too (headcount 800 with an understated band `51-200`).
- Fix the **dead-key bug**: have the gate read both `_employee_count` and `employee_count` (and `company_size`) so the numeric headcount is actually honored.
- Apply in `lead_sourcing.py` `_apply_company_gate` and `lead_eligibility.py` `check()`.

### C. Server-side band filter at the source (`fantastic_jobs.py` fetch) — *optional, recall tradeoff*
- Add the `organization_size` bucket-inclusion param (maps to `org_linkedin_size`) so oversized companies aren't even fetched. E.g. ceiling 500 → include `1,2-10,11-50,51-200,201-500`.
- **Tradeoff:** it's an inclusion filter, so companies with a NULL band would be excluded (small recall hit). The existing `organization_headcount_gte:1` already sacrifices similar recall, so posture is consistent — but this is the one item with a judgment call. **Decision needed.**

### D. Backfill existing polluted leads (stop ongoing waste)
Existing rows (R1603 + "many more") already carry the understated numeric `company_size`. Options:
- **D1 (cheap, forward-safe):** flag/quarantine — for fantastic_jobs leads still in a pre-enrichment status (`NEW`), re-resolve size via Apollo **firmographic-by-domain** (they carry `org_linkedin_website`), re-run the gate, and mark >500 as `LeadStatus.EXCLUDED` so contact discovery never touches them. Firmographic `/organizations/enrich` is far cheaper than contact discovery, and only spent on not-yet-enriched leads.
- **D2 (audit only):** report counts by source + size band, no writes, so we quantify the waste first.
- Deliver as `backend/scripts/backfill_fantastic_jobs_company_size.py` (dry-run default, `--apply` to write), tenant-scoped.

### E. Tests & docs
- Unit: `exceeds_size_ceiling_any`, adapter normalize (band preferred, both signals surfaced), both gates drop the 156/`1001-5000` case.
- Regression: a fantastic_jobs raw payload with `headcount=156, size="1001-5000"` is dropped at the sourcing gate.
- Update `CLAUDE_REFERENCE/adapters.md` (fantastic_jobs size mapping) + memory topic file.

---

## 4. Files to touch
| File | Change |
|---|---|
| `backend/app/services/adapters/job_sources/fantastic_jobs.py` | Prefer band for `company_size`; (opt) `organization_size` server filter |
| `backend/app/services/company_filters.py` | New `exceeds_size_ceiling_any` conservative helper |
| `backend/app/services/pipelines/lead_sourcing.py` | Gate uses conservative multi-signal check; fix dead `_employee_count` key |
| `backend/app/services/lead_eligibility.py` | Same conservative check in `check()` |
| `backend/scripts/backfill_fantastic_jobs_company_size.py` | New backfill (dry-run + `--apply`) |
| tests + `CLAUDE_REFERENCE/adapters.md` + memory | coverage + docs |

---

## 5. Decisions (resolved with stakeholder)
1. **ICP ceiling is >200, not >500.** `LEAD_SOURCING_MAX_EMPLOYEE_COUNT` default changed 500 → 200 (`config.py`, `settings.py`). Prod tenant-1 override must also be set to 200 (see §6) — tenant overrides shadow the global default.
2. **Server-side band filter (item C): YES** — added. Fantastic.jobs now receives `organization_size=1,2-10,11-50,51-200` (buckets ≤ 200) so oversized companies are never fetched.
3. **Backfill (item D): audit report first (D2).** Read-only `scripts/audit_fantastic_jobs_company_size.py` ships to quantify the damage; no writes/spend until numbers are reviewed.

## 6. Deployment / follow-up steps
- **Set prod tenant-1 override to 200** (tenant overrides shadow the global default — see `settings-store-tenant-override-gotcha`):
  `set_tenant_setting(db, "lead_sourcing_max_employee_count", 200, tenant_id=1)`.
- **Run the audit on prod** (read-only): `python scripts/audit_fantastic_jobs_company_size.py --tenant 1` → decide whether to spend on a re-verify backfill (D1) for suspect still-pending leads.
- Redeploy backend + frontend per the standard VPS checklist.
