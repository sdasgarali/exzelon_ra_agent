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
| TheirStack | `batch_size`, `max_pages` | 20, 10 | Titles per batch (API limit 20); pages (100/page) |
| USAJobs | `batch_size`, `max_pages`, `results_per_page` | 2, 5, 100 | Titles per query; pages; results/page |
| Jooble | `batch_size`, `max_pages` | 4, 5 | Titles per query; pages |
| JobDataFeeds | `batch_size`, `max_pages`, `results_per_page` | 4, 50, 100 | Titles per query; pages; results/page |
| Coresignal | `batch_size`, `max_pages`, `results_per_page` | 5, 5, 100 | Titles per query; pages (2 credits/record); results/page |

Pipeline-level settings: `pipeline_adapter_limit` (default 1000) caps results per adapter; `pipeline_max_workers` (default 6) sets thread pool size.

All configurable via Settings → Source Tuning tab (tab permission key: `source_tuning`).

## Adding a New Adapter

1. Implement the abstract base class from `adapters/base.py`
2. Add the mock variant for testing
3. Register in the provider factory
4. Add config key to `core/config.py` and `.env.example`
5. Update this reference doc
