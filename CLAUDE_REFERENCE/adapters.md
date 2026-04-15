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

## Adding a New Adapter

1. Implement the abstract base class from `adapters/base.py`
2. Add the mock variant for testing
3. Register in the provider factory
4. Add config key to `core/config.py` and `.env.example`
5. Update this reference doc
