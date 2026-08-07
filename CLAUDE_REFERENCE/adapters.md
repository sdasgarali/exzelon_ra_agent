# Adapter Pattern — Exzelon RA Agent

> Referenced from: `CLAUDE.md` — Read this when working on external integrations or adding new adapters.

## Overview

All external integrations implement abstract base classes from `services/adapters/base.py`. Provider selection is driven by `.env` settings. Each category has a `mock` adapter for development/testing.

## Adapter Registry

| Category | Adapters | Config Key |
|---|---|---|
| **Job Sources** | Apollo, JSearch, TheirStack, SerpAPI (Google Jobs), Adzuna, SearchAPI, USAJobs, Jooble, JobDataFeeds, Coresignal | `JOB_SOURCES`, `JSEARCH_API_KEY`, `THEIRSTACK_API_KEY`, `SERPAPI_API_KEY`, `ADZUNA_APP_ID`+`ADZUNA_API_KEY`, `SEARCHAPI_API_KEY`, `USAJOBS_API_KEY`+`USAJOBS_EMAIL`, `JOOBLE_API_KEY`, `JOBDATAFEEDS_API_KEY`, `CORESIGNAL_API_KEY` |
| **Contact Discovery** | Apollo, Seamless, Hunter.io, Snov.io, RocketReach, People Data Labs, Proxycurl | `CONTACT_PROVIDER`, `HUNTER_CONTACT_API_KEY`, `SNOVIO_CLIENT_ID`+`SNOVIO_CLIENT_SECRET`, `ROCKETREACH_API_KEY`, `PDL_API_KEY`, `PROXYCURL_API_KEY` |
| **Company Enrichment** | Clearbit (Breeze), OpenCorporates | `CLEARBIT_API_KEY`, `OPENCORPORATES_API_KEY` |
| **Email Validation** | NeverBounce, ZeroBounce, Hunter, Clearout, Emailable, MailboxValidator, Reacher | `EMAIL_VALIDATION_PROVIDER` |
| **Email Sending** | SMTP, Mock | `EMAIL_SEND_MODE` |
| **AI Content** | Groq, OpenAI, Anthropic, Gemini | Per-adapter API keys, shared factory in `adapters/ai_content.py` |
| **CRM** | HubSpot, Salesforce | `HUBSPOT_API_KEY`, `SALESFORCE_CLIENT_ID` |
| **Notifications** | Slack, Microsoft Teams | Webhook URLs in settings |
| **Communications** | Twilio (SMS + Calling) | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` |
| **LOB Lead Sources** | NPI Registry, Google Business, Crunchbase, BuiltWith, PageSpeed, GitHub Org, Hiring Signal, News Signal | `GOOGLE_PLACES_API_KEY`, `CRUNCHBASE_API_KEY`, `BUILTWITH_API_KEY`, `GITHUB_TOKEN` (per-tenant via settings or config.py) |

## LOB Lead Source Adapters (`services/adapters/lead_sources/`)

All extend `LeadSourceAdapter` (base class in `adapters/base.py`). Return normalized lead dicts with `client_name`, `industry`, `state`, `city`, `source`, `metadata`.

| Adapter | File | LOB Types | API Cost | Key Config |
|---------|------|-----------|----------|------------|
| NPI Registry | `npi_registry.py` | RCM | Free | No key needed |
| Google Business | `google_business.py` | RCM, Digital Marketing | Paid ($32/1K) | `google_places_api_key` |
| Crunchbase | `crunchbase.py` | Software Dev, AI Services | Paid | `crunchbase_api_key` |
| BuiltWith | `builtwith.py` | Software Dev, Digital Marketing | Paid | `builtwith_api_key` |
| PageSpeed | `pagespeed.py` | Digital Marketing | Free (with API key) | `google_places_api_key` |
| GitHub Org | `github_org.py` | Software Dev, AI Services | Free (token optional) | `github_token` |
| Hiring Signal | `hiring_signal.py` | RCM, Software Dev, AI Services, Digital Marketing | Free (internal) | No key — mines existing `lead_details` for LOB-specific hiring patterns |
| News Signal | `news_signal.py` | RCM, Software Dev, AI Services, Digital Marketing | Free | No key — Google News RSS feeds |

Settings UI: All keys configurable under `lob_lead_sources` tab. Test-connection for all 6 external adapters via `POST /settings/test-connection/{provider}`.

## Job Source Adapter Tuning Parameters

All 9 job source adapters accept a `tuning: Optional[Dict] = None` parameter in `fetch_jobs()`. Values are loaded from the `job_source_tuning` setting (Settings UI → Source Tuning tab) and passed by the pipeline.

| Adapter | Parameters | Defaults | Impact |
|---------|-----------|----------|--------|
| JSearch | `batch_size`, `num_pages` | 4, 10 | Titles per query; pages per query (10 results/page) |
| SerpAPI | `batch_size`, `max_pages` | 4, 3 | Titles per OR query; pages (1 API credit each) |
| SearchAPI | `batch_size`, `max_pages` | 4, 3 | Titles per OR query; pages (1 API credit each) |
| Adzuna | `batch_size`, `max_pages`, `results_per_page` | 4, 10, 50 | Titles per query; pages; results/page (max 50) |
| TheirStack | `batch_size`, `max_pages`, `max_employee_count`, `min_employee_count`, `include_unknown_size`, `industry_id_or`, `industry_id_not` | 20, 10, 200, –, false, –, – | Titles per batch (API limit 20); pages (100/page). **Firmographic filters pushed server-side**: `max_employee_count` (≤200 default; `null` disables; `include_unknown_size:true` switches to `max_employee_count_or_null` for more volume), `industry_id_*` = LinkedIn Industry Codes V2 (opt-in, for non-IT targeting). Staffing-agency company names (`_exclude_company`) and excluded titles (`_exclude_title`) are pushed as `company_name_partial_match_not` / `job_title_not` when push-negatives is on. |
| USAJobs | `batch_size`, `max_pages`, `results_per_page` | 2, 5, 100 | Titles per query; pages; results/page |
| Jooble | `batch_size`, `max_pages` | 4, 5 | Titles per query; pages |
| JobDataFeeds | `batch_size`, `max_pages`, `results_per_page` | 4, 50, 100 | Titles per query; pages; results/page |
| Coresignal | `batch_size`, `max_pages`, `results_per_page` | 5, 5, 100 | Titles per query; pages (2 credits/record); results/page |

Pipeline-level settings: `pipeline_adapter_limit` (default 1000) caps results per adapter; `pipeline_max_workers` (default 6) sets thread pool size.

**Company attributes captured at source:** TheirStack (`company_object.industry`/`employee_count`) and Coresignal (`company_industry`/`company_employees_count`) map company `industry` + `company_size` into job_data. These feed the size/industry exclusion gate (`_apply_company_gate` in `pipelines/lead_sourcing.py`, helpers in `services/company_filters.py`), which drops companies over `lead_sourcing_max_employee_count` (**default 200** — ICP ceiling is >200), excluded industries (IT/staffing/government via `lead_sourcing_excluded_industries`), and confidential/blank employers (`lead_sourcing_drop_confidential`). Sources lacking these attributes are filled by a bounded, cached Groq LLM step (`company_enrichment.resolve_company_metadata_batch`, gated by `lead_sourcing_enrich_company_at_source` / `lead_sourcing_enrich_max_companies`). Unknown size/industry is never dropped.

**Fantastic.jobs company size — use the self-reported BAND, not the headcount.** Fantastic.jobs (`job_sources/fantastic_jobs.py`) returns two LinkedIn size signals: `org_linkedin_headcount` (a count of *tagged member profiles* — systematically UNDERSTATED) and `org_linkedin_size` (the company's SELF-REPORTED band, e.g. `1001-5000`, i.e. what the LinkedIn profile shows). The adapter maps `company_size` = the **band** (falling back to `str(headcount)` only when the band is absent) and keeps `employee_count` = headcount. Keying the gate on headcount let oversized companies pass and burned Apollo credits (the R1603 bug — headcount 156 for a 1001-5000 company). The gate is now **conservative across both signals** via `exceeds_size_ceiling_any` / `below_size_floor_any` (drops on the LARGEST parsed size). The adapter also pushes `organization_size` (band buckets ≤ ceiling, via `size_buckets_within_ceiling`) as a server-side filter so oversized companies are never fetched. Audit existing damage with `backend/scripts/audit_fantastic_jobs_company_size.py` (read-only). See `Fantastic_Jobs_Company_Size_RCA.md`.

All configurable via Settings → Source Tuning tab (tab permission key: `source_tuning`).

## Adding a New Adapter

1. Implement the abstract base class from `adapters/base.py`
2. Add the mock variant for testing
3. Register in the provider factory
4. Add config key to `core/config.py` and `.env.example`
5. Update this reference doc
