# Stripe Subscriptions setup (ELR-021)

Recurring subscriptions are **inert until you create the Products/Prices in Stripe
and paste the price ids into config.** Do this once per environment.

## 1. Create Products + recurring Prices in Stripe
In the Stripe Dashboard → **Products**, create one product per plan (Starter,
Professional, Enterprise). For each, add a **recurring** price (e.g. monthly, in
your billing currency). Copy each `price_...` id.

(Or via CLI: `stripe products create --name "Professional"` then
`stripe prices create --product <prod_id> --unit-amount 9900 --currency usd --recurring interval=month`.)

## 2. Set the price ids (host `.env`, never in git)
```
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_PROFESSIONAL=price_...
STRIPE_PRICE_ENTERPRISE=price_...
```

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
