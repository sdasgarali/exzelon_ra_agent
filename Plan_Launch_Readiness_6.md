# Plan — Lift five launch areas to 6+/10

Branch: `feature/launch-readiness-6` (from `master` ef42e31). Source: launch audit 2026-10-12 (overall 58/100).

## SESSION_CONTEXT_RETRIEVAL
> Plan written 2026-10-12, awaiting user answers to the open questions below before coding.
> Campaigns stay PAUSED until D1 ships (494 cold cPanel mailboxes on one IP are send-eligible today).

## Targets
| Area | Now | Target | Needs from user |
|---|---|---|---|
| Monitoring & operations | 4 | 7 | alert email address (Sentry DSN optional) |
| Backups & recovery | 4 | 7 | approve off-site storage (new Backblaze B2 bucket) |
| Email deliverability | 4 | 6-7 | DNS: DMARC for neuraleads.ai; M365 DKIM for exzelon.com (optional, +1) |
| Legal & compliance | 3 | 6-7 | legal entity name, address, jurisdiction, support/privacy emails |
| New-customer experience | 4 | 7 | support email address to publish |

## Monitoring & operations (4 → 7)
- [ ] M1 `GET /ready`: DB, Redis, scheduler heartbeat (last job run < 10 min), disk free; `/health` stays cheap
- [ ] M2 Unhandled exceptions log the full traceback (currently `str(exc)` only)
- [ ] M3 Watchdog: systemd timer on the VPS curls `/ready` every 5 min; on 2 consecutive failures emails the alert address via the existing Resend system mailer (de-duplicated, recovery email too)
- [ ] M4 Error alerts: 5xx/unhandled-exception digest email, rate-limited (max 1 per 15 min) — Sentry stays env-gated if a DSN is provided
- [ ] M5 `deploy.sh`: pre-deploy DB backup, `alembic upgrade head`, wait for workers before health check, print rollback command
- [ ] M6 Bind uvicorn to 127.0.0.1 (ufw already blocks 8000; defence in depth)

## Backups & recovery (4 → 7)
- [ ] B1 Local retention 3 → 14 days (disk: ~19 MB/day, 134 GB free)
- [ ] B2 Off-site copy: encrypted upload to B2 (existing `BACKUP_S3_BUCKET` path in `backup_service.py`) — needs user OK + bucket keys
- [ ] B3 Backup integrity check after each dump (gunzip -t + row-count sanity) and alert via M3 on failure
- [ ] B4 Restore drill script: restore latest dump into a scratch DB on the VPS, compare table row counts, drop it; run once now and document in `deploy/DR_RUNBOOK.md`

## Email deliverability (4 → 6-7)
- [ ] D1 Warmup gate in `mailbox_selector`: a mailbox is outreach-eligible only after `warmup_days_completed >= 14` AND `warmup_emails_sent >= N` (configurable, `MIN_WARMUP_DAYS`, `MIN_WARMUP_EMAILS`); `update-status` endpoint refuses COLD_READY/ACTIVE without it (super admin override with audit log)
- [ ] D2 Enforce the ISP ramp in `domain_reputation.recommended_daily_ramp` as the effective daily cap during the first 30 days of sending
- [ ] D3 Per-IP cohort cap: limit how many domains sharing one sending IP can be in live outreach at once (default 1) — the 10 .in domains share 118.139.181.36
- [ ] D4 Ramp runbook: start warmup on one domain cohort (5-10 mailboxes) — warmup only, no outreach
- [ ] D5 (user, DNS) add `_dmarc.neuraleads.ai` TXT; optional M365 DKIM for exzelon.com

## Legal & compliance (3 → 6-7)
- [ ] L1 Send gate blocks outreach when the workspace has no postal address; dashboard + onboarding prompt to add one
- [ ] L2 Remove the Exzelon logo default from outgoing templates (workspace logo or none)
- [ ] L3 Remove the "123 Business St" placeholder default + clean the 4 settings rows that hold it
- [ ] L4 Terms/Privacy acceptance checkbox at signup; store `terms_accepted_at` + version (Alembic migration)
- [ ] L5 Legal pages read entity name/address/jurisdiction/emails from config (`LEGAL_*` env keys) — filled with user's details
- [ ] L6 In-app "Delete my workspace" + "Export my data" (Settings) using existing GDPR endpoints

## New-customer experience (4 → 7)
- [ ] U1 Signup: show password rules up front, validate client-side, use `getApiError` so 422s never crash the page
- [ ] U2 `payments_enabled` flag from backend; when Stripe isn't configured, Upgrade/Buy-credits become "Request access" (existing quote request) — no developer error text
- [ ] U3 Publish the support email on /contact, footer, in-app Help menu; "Contact support" links use it
- [ ] U4 Home "Get Started" → /signup; hide `mock` job source; hide LinkedIn "Coming soon" step; neutral SMTP example text
- [ ] U5 Getting-started checklist: steps 3-4 deep-link to the right Pipelines tab
- [ ] U6 Playwright check of signup → verify → first login → checklist on the local QA stack

## Delivery
- Fan-out by area (exclusive file ownership), integrator merges, full backend + MCP + frontend suites,
  browser QA, PR, deploy only on user's go. No campaign unpause as part of this work.

## Open questions for the user
1. Alert / support email address(es) to publish and to receive alerts.
2. Off-site backups: OK to create a new Backblaze B2 bucket (private) for this app?
3. Legal details: entity name, registered address, jurisdiction — or ship config-driven pages now and fill later.
4. Warmup gate thresholds: 14 days / 50 warmup emails per mailbox before outreach (recommended).
