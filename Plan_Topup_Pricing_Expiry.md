# Plan — Credit top-up repricing ($20/1k) + 12-month expiry

> Created 2026-09-25. Branch: `feature/topup-pricing-expiry`.
> User decisions (2026-09-25): top-up = **$20 per 1,000 credits**; purchased credits **expire 12 months after purchase**.

## Problem
Top-ups were $10/1k and never expired, so they were cheaper than Pro ($16.50/1k monthly, $13.17 annual)
and Max monthly ($11.96/1k). Pro + 19 top-ups ($289) beat Max ($299) for 25k credits, and the top-up
credits never lapse. The code comment claiming "same $0.01/credit as the plan" was false.
Stripe is not configured yet (deferred), so nobody has been charged; prod has zero top-up rows.

## Design
- **Price**: `CREDIT_TOPUP_BLOCK_PRICE_CENTS` default 1000 -> 2000. Expose block size + price + validity
  in the credits API so the billing UI stops hardcoding `$10`. (Stripe price object for
  `STRIPE_PRICE_CREDIT_TOPUP` must be created at $20 when Stripe is set up.)
- **Expiry**: new table `credit_topup_lots` (one row per purchase: purchased, remaining, purchased_at,
  expires_at, expired_at, reference_id). `tenant_credit_balances.topup_credits` stays as the cached
  total of live lots, so every existing reader keeps working and the balance row stays the lock point.
  - `grant_topup` creates a lot, `expires_at = now + CREDIT_TOPUP_VALIDITY_DAYS` (365).
  - `_debit` drains top-up lots **soonest-expiring first** (FIFO) when it spends from top-ups.
  - `expire_topup_lots()` zeroes lots past `expires_at`, subtracts their remainder from
    `topup_credits` (under the balance lock), logs `credit_topup_expired`. Daily scheduler job
    (`credit_topup_expiry`, 00:15 UTC, advisory lock, job-toggle aware).
  - Legacy `topup_credits` with no lots (none on prod) are adopted as one lot expiring 365 days after migration.
- **Copy**: pricing page FAQ, PricingCards, documentation page, billing panel -> "$20 per 1,000, valid 12 months".

## Tasks
- [x] 1. Model `CreditTopupLot` + `db/base.py` registration + Alembic `0005_credit_topup_lots`
- [x] 2. config: price 2000, `CREDIT_TOPUP_VALIDITY_DAYS=365`; fix docstrings/comments
- [x] 3. credit_metering: lot creation in `grant_topup`, FIFO drain in `_debit`, `expire_topup_lots`,
       `available_credits` adds `topup_next_expiry` + top-up price info
- [x] 4. Scheduler daily expiry job
- [x] 5. Frontend: billing panel reads price from API; marketing/docs copy
- [x] 6. Tests: lot FIFO, expiry, refill keeps lots, price in API, migration idempotent
- [x] 7. Docs: data-models.md, services.md, deploy/MIGRATIONS note; full test suite + frontend build
- [x] 8. PR #120 merged (dcf93de) + deployed 2026-09-25 18:03 UTC: backup backups/pre-topup-lots-20260925-180106.sql.gz, alembic 0004 -> 0005 (head), frontend rebuilt, health 200, `Daily Top-up Credit Expiry` job registered.

## Acceptance
- 1,000 top-up credits cost $20 everywhere (API, billing UI, marketing, docs).
- A lot past 12 months contributes 0 credits; unexpired lots are spent oldest-expiry first.
- Allowance is still spent before top-ups; monthly refill never touches lots.
- Full backend suite green; frontend builds.
