# Plan: Pricing → Signup → Upgrade flow

## Problem (found 2026-11-06)
A new visitor picks Pro or Max on /pricing, but the choice is lost and there is no obvious way to upgrade afterwards.

| Step | What happens today | File |
|---|---|---|
| Pricing card | Pro and Max buttons both go to plain `/signup`. The plan and the monthly/annual toggle are dropped. | `components/marketing/PricingCards.tsx` |
| Signup | Ignores any plan. Shows "Check your email". | `app/signup/page.tsx` |
| Verify → login | Login always sends the user to `/dashboard`. | `app/login/page.tsx` |
| Dashboard | Upgrade lives only inside **Billing** (sidebar), in the plan panel at the top. Nothing on the dashboard, header or sidebar says "Upgrade". | `app/dashboard/layout.tsx` |
| Billing plan panel | Offers only the *next* tier (Free → Pro). A Free user cannot pick Max or compare plans. With payments off (prod today), it shows only "Request upgrade" by email. | `components/plan-usage-panel.tsx` |

The backend already accepts any plan (`POST /billing/subscription/checkout {plan, annual}`). One additive backend change: `upgrade_options` on `GET /billing/usage` so the picker shows prices from PLAN_MATRIX instead of hardcoding them.

## Fix — slices
- [x] 1. **Keep the choice.** Pricing Pro/Max buttons → `/signup?plan=pro&billing=annual` (follows the toggle). Button text: "Start free, then upgrade to Pro".
- [x] 2. **Remember it through email verification.** Signup reads `plan`/`billing`, shows "You picked Pro — after you verify your email we'll take you to checkout", and saves the intent in localStorage (`nl_pending_upgrade`, expires after 7 days; try/catch, works without it).
- [x] 3. **Land on the upgrade.** After login, if an intent is saved (or `/login?plan=` is used) → `/dashboard/billing?upgrade=pro&billing=annual` instead of `/dashboard`.
- [x] 4. **Plan picker on Billing.** Replace the single "Upgrade to next tier" button with Pro and Max cards (price, credits, sends, monthly/annual toggle, "Current plan" badge). `?upgrade=` preselects and scrolls to the card. Clicking → Stripe Checkout. Payments off → "Request upgrade to <plan>" email, as today.
- [x] 5. **Make it findable.** A visible "Upgrade" button in the sidebar (above the user menu) for Free and Pro workspace admins → `/dashboard/billing#plans`. Hidden for super admins, Max and Custom.
- [x] 6. **Tests.** Jest: pricing hrefs, signup intent saved, login redirect, picker preselect and checkout call. Lint + typecheck + `npm run build`. Backend unchanged.
- [ ] 7. **Ship.** PR → CI → merge → deploy → check the flow on prod with a fresh signup.

## Acceptance
- Pick Max (annual) on /pricing → sign up → verify → log in → land on Billing with Max (annual) selected → one click to Stripe Checkout.
- A Free admin can see "Upgrade" from any dashboard page and choose Pro or Max.
- With Stripe off (prod now), the same path ends at "Request upgrade to Max" instead of an error.

## Note
On neuraleads.ai, payments are off until live Stripe keys are set, so step 4 shows "Request upgrade" there. Real checkout on prod needs the live-keys step.
