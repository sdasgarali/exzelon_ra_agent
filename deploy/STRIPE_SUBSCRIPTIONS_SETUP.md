# Stripe Subscriptions setup (ELR-021)

Recurring subscriptions are **inert until you create the Products/Prices in Stripe
and paste the price ids into config.** Do this once per environment.

## 1. Create Products + recurring Prices in Stripe
Only **two** plans are charged through Stripe. Free costs nothing, and Custom is
quoted and invoiced by contract through the `ManualGateway` — neither has a price id.

In the Stripe Dashboard → **Products**, create one product per billable plan and give
each **two** recurring prices, monthly and yearly:

| Plan | Monthly | Annual (billed yearly) |
|------|---------|------------------------|
| Pro  | $99 (`unit_amount=9900`, `interval=month`) | $948 (`unit_amount=94800`, `interval=year`) — $79/mo |
| Max  | $299 (`unit_amount=29900`, `interval=month`) | $2,868 (`unit_amount=286800`, `interval=year`) — $239/mo |

Also create a **one-time** price for credit top-ups: $20 per 1,000 credits
(`unit_amount=2000`, no `recurring`). It must match `CREDIT_TOPUP_BLOCK_PRICE_CENTS`
(the billing UI displays that value; Stripe charges this price).

(Or via CLI: `stripe products create --name "Pro"` then
`stripe prices create --product <prod_id> --unit-amount 9900 --currency usd --recurring interval=month`.)

These amounts must match `PLAN_MATRIX` in `backend/app/core/plans.py`, which is the
source of truth for what the app believes a plan costs.

## 2. Set the price ids (host `.env`, never in git)
```
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_MAX=price_...
STRIPE_PRICE_PRO_ANNUAL=price_...
STRIPE_PRICE_MAX_ANNUAL=price_...
STRIPE_PRICE_CREDIT_TOPUP=price_...
```

Checkout picks the annual price when the request sets `annual: true`; both price ids
map back to the same plan on the webhook side.

## 3. Add the webhook endpoint in Stripe
Point a webhook at `https://<your-host>/api/v1/billing/webhook/stripe` and enable
at least these events:
- `checkout.session.completed` (links tenant ↔ subscription on first checkout)
- `customer.subscription.created`, `customer.subscription.updated`,
  `customer.subscription.deleted` (status/plan/period sync)
- `invoice.paid`, `invoice.payment_failed` (renewals + dunning; already handled)
- `charge.refunded`, `charge.dispute.created` (already handled)

The signing secret from that endpoint is `STRIPE_WEBHOOK_SECRET`.

## 4. How it works
- `POST /billing/subscription/checkout {plan?}` → returns a Stripe Checkout URL
  (subscription mode) for the tenant's plan. Redirect the customer there.
- On completion, `checkout.session.completed` creates a `subscriptions` row linking
  the tenant to the Stripe subscription; `customer.subscription.*` events keep the
  row's status/price/period and the tenant's `plan` in sync.
- `GET /billing/subscription` → current status. `POST /billing/subscription/cancel`
  → cancels at period end.
- Failed renewals (`invoice.payment_failed`) mark the invoice OVERDUE; the overdue
  job suspends the tenant after the grace window (ELR-023).

## 5. Test with the Stripe CLI
`stripe listen --forward-to localhost:8000/api/v1/billing/webhook/stripe` then
`stripe trigger customer.subscription.updated`.
