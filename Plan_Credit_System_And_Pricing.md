# Plan — Credit System & Three-Tier Pricing (Free / Pro / Max)

> Status: **Phases 0-4 IMPLEMENTED 2026-09-22** (1,585 tests green, frontend builds clean).
> Phase 5 (verification hardening) not started;
> the pricing numbers themselves and the four open decisions in §10 still need sign-off.
> Author: Claude Code session 2026-09-22
> Related: `Plan_WIP.md`, `CLAUDE_REFERENCE/multi-tenancy.md`, `API_Cost_Report.docx`

---

## 1. Executive summary

The platform already has the *skeleton* of a credit system (`services/credit_metering.py`,
`CreditUsage` model, `check_credit_budget()` 402 gate, `cost_tracker.py` COGS registry). What it
did **not** have was the economics: no per-action credit prices, no plan→credit mapping beyond three
config integers, no feature gating, and — critically — `record_usage()` was called in exactly one
place in the entire codebase (`api/endpoints/sms.py:64`). The ledger existed and was empty.
*(Phases 0–2 have since closed all of that except feature gating, which is Phase 3.)*

This plan defines the missing economics and packaging:

| | **Free** | **Pro** | **Max** | **Custom** |
|---|---|---|---|---|
| Price (monthly) | **$0** | **$99/mo** | **$299/mo** | Quoted |
| Price (annual, –20%) | $0 | **$79/mo** ($948/yr) | **$239/mo** ($2,868/yr) | Contract |
| **Credits / month** | **300** | **6,000** | **25,000** | > 25,000 |
| Email sends / month | 500 | 25,000 | 150,000 | > 150,000 |
| **Mailboxes** | 1 | 25 | **1,000** | > 1,000 |
| **Active campaigns** | 2 | 25 | **100** | > 100 |
| Users (seats) | 2 | 10 | **50** | > 50 |
| Lines of business | 1 | 3 | **25** | > 25 |
| Est. COGS at full burn | ~$0.90 | ~$20 | ~$78 | per contract |
| Gross margin | n/a | **~80%** | **~74%** | floor 70% |

Two separate meters, not one. **Credits** meter things with real external COGS (data, enrichment,
validation, AI). **Sends** are a flat monthly quota because their marginal cost is ~$0 — tenants
bring their own mailboxes. Merging them would make users afraid to send, which is the one thing
the product exists to do.

**No tier says "unlimited" anywhere.** Every axis on every self-serve plan is a finite, published
number — Max is 1,000 mailboxes, 50 seats, 25 lines of business. Above any of those is the
**Custom** tier, where the customer picks their own figures with Max's as the floor and we quote
against them (§8a).

This is worth stating as a principle because it changes the code: **if nothing is ever unlimited,
the limit sentinel problem largely disappears.** Every limit becomes a positive integer, so `0` on a
tenant row is freed up to mean exactly one unambiguous thing.

*Refined during implementation:* `0` means **"not configured for this tenant — use the plan's
number"**, and any positive value is an explicit per-tenant limit (a support grant, a trial bump, a
restricted account). That is strictly better than "not included in this plan", because it makes the
existing all-zero rows *self-heal* to their plan's numbers with no data migration, while keeping the
admin override that `PLAN_MATRIX`-only resolution would have silently ignored. Whether a tenant may
touch a feature at all is a feature-gate question (Phase 3), not a limit of zero. See §9 item 0.2.

**Campaigns are capped on ACTIVE, not total.** A campaign that has finished its sequence costs us
nothing — it is history. Only `ACTIVE` and `PAUSED` campaigns hold enrolments and get picked up by
the campaign engine every two minutes, so only those count against the cap. Drafts are free
(nothing processes them) and `COMPLETED`/`ARCHIVED` campaigns never count. The numbers are also
sized against lines of business: Max's 100 campaigns ÷ 25 LOBs ≈ 4 live campaigns per vertical,
which is what an agency running a vertical actually needs.

It also costs us nothing competitively. 50 seats at $299 is **$5.98 per seat**; Apollo charges
$79–119 *per user*, lemlist $32, Reply.io $89. A 50-person team on Apollo Professional pays
$3,950/month. The per-seat argument still lands with a finite number on the card — we just don't
write a cheque we can't cash.

---

## 2. Critical blocker found during analysis — ✅ FIXED 2026-09-22 (Phase 0.1/0.2)

`services/tenant_service.py:47-56` creates every self-signup tenant with:

```python
plan=TenantPlan.STARTER, max_users=3,
max_mailboxes=0, max_contacts=0, max_campaigns=0, max_leads=0
```

And `api/deps/plan_limits.py:63-68` turns `0` + `starter` into a hard 403:

> `"Starter plan does not include {resource}. Upgrade to Professional to unlock."`

**Therefore: a user who signs up today cannot create a mailbox, a lead, a contact, or a campaign.
The product is unusable on signup.** This also contradicts the documented Starter limits in
`CLAUDE_REFERENCE/multi-tenancy.md` (3 / 5 / 500 / 5 / 1000), which are written down but never
assigned anywhere in code.

Any Free tier was dead on arrival until this was fixed, so it became item 1 of the plan.

**Fixed:** `create_tenant_for_signup()` now provisions from `PLAN_MATRIX["free"]`, and a resolved
limit of `0` means "not configured — use the plan's number" rather than "locked", so existing
all-zero rows self-heal with no backfill. Regression tests:
`test_tenant_service.py::test_signup_tenant_can_actually_create_things` walks every resource through
the real `check_plan_limit`, and `test_plan_limits.py::test_unconfigured_limits_fall_back_to_plan`
pins the sentinel.

### 2a. Related: the campaign counter is a one-way ratchet — ✅ FIXED 2026-09-22 (Phase 1.4a)

`plan_limits.RESOURCE_COUNTERS["campaigns"]` counts **every** campaign row a tenant has ever
created:

```python
"campaigns": lambda db, tid: db.query(Campaign).filter(Campaign.tenant_id == tid).count(),
```

No status filter, no `is_archived` filter — even though `CampaignStatus` has `DRAFT`, `ACTIVE`,
`PAUSED`, `COMPLETED` and `ARCHIVED`. So a tenant who runs five campaigns to completion on a
five-campaign plan is **permanently locked out with nothing running**, and the only escape is an
upgrade. Deleting the campaign isn't even an escape if it was soft-archived rather than hard-deleted.

The same ratchet applies to `leads` and `contacts`, which are lifetime-cumulative by nature — worth
a separate decision on whether those should be "records stored" (a true ceiling, needs a purge path)
or "records added this month" (a flow). Recommendation: keep leads/contacts cumulative (they are
genuine storage) but make campaigns a live-state count, per §1.

**Fixed:** the counter now filters to `ACTIVE`/`PAUSED` (`LIVE_CAMPAIGN_STATUSES`). Regression test:
`test_plan_limits.py::test_completed_campaigns_release_their_slot`. The leads/contacts question is
still open — they remain cumulative.

---

## 3. Credits vs "tokens" — naming decision

Use **credits**, not tokens. "Tokens" means LLM tokens to anyone technical, and this product spends
far more on data APIs (Apollo, SerpAPI, NeverBounce) than on LLM inference. Exposing raw model
tokens to a sales user is meaningless — they cannot reason about "1,400 input tokens", they can
reason about "1 enriched contact". Every comparable tool (Apollo, Clay, lemlist) says credits.

**One currency, not two.** Clay splits "Data Credits" and "Actions", and it is their single most
common pricing complaint — two pools that deplete independently and strand each other. We use one
credit pool plus a separate send quota.

---

## 4. Credit price list (derived from real COGS)

Anchor: **1 credit ≈ $0.01 of retail value.** Real COGS below come from
`services/cost_tracker.py::DEFAULT_PROVIDER_PRICING` and the measured spend in
`API_Cost_Report.docx` ($201.75 / 10,671 calls / 213,670 results over ~2 months).

| Action | Where it fires | Real COGS | **Credits** | Retail | Markup |
|---|---|---|---|---|---|
| Lead sourced (stored, post-dedup) | `pipelines/lead_sourcing.py` | ~$0.003 blended | **1** | $0.01 | ~3x |
| Contact discovered / enriched | `pipelines/contact_enrichment.py` | $0.01–0.02 | **3** | $0.03 | ~2–3x |
| Email validated | `pipelines/email_validation.py` | $0.004–0.008 | **1** | $0.01 | ~2x |
| AI email personalization (per email) | `services/ai_personalizer.py` | ~$0.0004 | **1** | $0.01 | high |
| AI reply classify + draft | `ai_reply_agent_service.py` | ~$0.001 | **2** | $0.02 | high |
| AI sequence generation (per sequence) | `ai_sequence_generator.py` | ~$0.003 | **5** | $0.05 | high |
| AI ICP Wizard run | `ai_icp_wizard.py` | ~$0.005 | **10** | $0.10 | high |
| Company firmographic lookup (Apollo org) | `company_firmographics.py` | $0.01 | **3** | $0.03 | ~3x |
| Intent signal scan (per company) | `intent_signal_monitor.py` | $0–0.01 | **1** | $0.01 | — |
| Firecrawl applicant scrape | `firecrawl_client.py` | ~$0.01 | **3** | $0.03 | ~3x |
| SMS (Twilio) | `api/endpoints/sms.py` | ~$0.0079 | **2** | $0.02 | ~2.5x |
| **Email send** | `campaign_engine.py` | ~$0 | **0** | — | separate quota |
| **Warmup email** | `services/warmup/` | ~$0 | **0** | — | unmetered |

**Blended cost of one fully-processed contact** (source → discover → validate → personalize):
`1 + 3 + 1 + 1 = 6 credits ≈ $0.06 retail, ~$0.018 COGS`.

That single number drives every allowance below.

Groq is the default AI provider and is **free-tier** (`AI_MODEL_PRICING` lists Groq models at
`(0.0, 0.0)`). AI actions therefore carry very high margin today; the credit prices above are set
against paid-model COGS (OpenAI/Anthropic) so the economics survive a provider switch.

---

## 5. Recommended allowances — and why

### Free: 300 credits/month

= **50 fully-processed contacts/month.** Enough to source a real list, enrich it, validate it, and
run one genuine test campaign — so the user sees the whole loop work on their own data, which is the
only thing that converts. Not enough to run a business on.

Competitive read: Clay Free gives 100 data credits + 500 actions/mo; Apollo Free gives 900 credits
*per year* (~75/mo) and is widely mocked for it; Reply.io gives 200 emails/mo. **300 credits is
deliberately more generous than Apollo and Clay on the dimension that matters (completed contacts),
and costs us ~$0.90/month per free tenant.**

Guardrails that make this safe: 1 mailbox, no warmup peer pool, 500 sends/mo, no autopilot AI, and
tenant cleanup already deactivates empty tenants at 3 AM (`multi-tenancy.md`).

### Pro: 6,000 credits/month

= **~1,000 fully-processed contacts/month**, or 2,000 enrichments, or 6,000 AI personalizations.
This is a genuine solo/SMB outbound motion — roughly 50 new contacts per working day.

Worst-case burn (100% on the priciest action, contact discovery at 3cr/$0.01 COGS) = 2,000 lookups
= **$20 COGS on a $99 plan → 80% gross margin.** Typical mixed burn lands near $18.

### Max: 25,000 credits/month

= **~4,150 fully-processed contacts/month.** Agency / multi-client scale, which matches the
`agency_mode` + white-label + multi-LOB features gated to this tier.

Worst-case burn = 8,333 lookups = **$83 COGS on $299 → 72% margin.** Typical ~$78 → 74%.

### Top-ups and rollover

- **Top-up: $20 per 1,000 credits** (changed 2026-09-25 from $10 — at $10 top-ups were cheaper
  per credit than Pro and Max monthly, so Pro + top-ups undercut a Max upgrade). Each purchase is
  **valid 12 months**, consumed only after the monthly allowance is exhausted, soonest-expiry first.
  See `Plan_Topup_Pricing_Expiry.md`.
- **No rollover of monthly allowance** in v1 (Free included). Rollover is the single biggest source
  of credit-accounting bugs; ship it later if churn data demands it.
- Free tier **cannot** buy top-ups — that is the upgrade trigger.

---

## 6. Send quotas — the honest-numbers differentiator

`DAILY_SEND_LIMIT = 30` per mailbox is a deliverability best practice already enforced in code
(`config.py:156`, `send_gate.py`, `domain_throttle.py`). A mailbox can therefore send ~900/month.
Our send quotas are set to be **arithmetically consistent** with that:

| Plan | Mailbox cap | Max safe sends (30/day × 30d) | **Quota we sell** | Mailboxes actually needed |
|---|---|---|---|---|
| Free | 1 | 900 | 500 | 1 |
| Pro | 25 | 22,500 | 25,000 | ~28 |
| Max | **1,000** | 900,000 | 150,000 | **~167** |
| Custom | > 1,000 | — | > 150,000 | per contract |

Note the last column: at Max's 150,000-send quota a customer only needs ~167 mailboxes, so the
1,000 cap sits at roughly **6× headroom**. It is an anti-abuse ceiling, not a limit real customers
will run into — the send quota binds long before the mailbox count does. Anyone who genuinely needs
more than 1,000 connected mailboxes is running an operation that should be on a contract, not a
self-serve card.

This is a **marketing asset, not a weakness.** Instantly advertises 100,000 emails/mo on
Hypergrowth ($97) and Smartlead 150,000 on Unlimited Smart ($174) — but hitting those numbers
requires the customer to buy and warm 100+ inboxes, which those vendors sell separately
(Instantly's "Pre-Warmed Accounts" module). Our number is what you can actually send without
burning your domain. Lead with that.

---

## 7. Feature distribution across tiers

Based on the 29 RBAC modules in `frontend/src/app/dashboard/roles/page.tsx` and the service
inventory in `CLAUDE_REFERENCE/services.md`.

### Free — prove the core loop

| Included | Gated |
|---|---|
| Dashboard, Leads, Clients, Contacts | Warmup Engine (shared peer pool = abuse vector) |
| Validation (credit-capped) | AI Sales Agent autopilot, Reply Agent |
| Email Templates, **2** active campaigns | A/B testing, Send-time optimization |
| Inbox (basic), Deals/CRM (basic) | Analytics, Attribution, Visitors |
| Pipelines: sourcing, enrichment, validation | Automation Control, Intent Engine, Forecast |
| Reports (basic), 1 mailbox, 2 seats | LOB, Backups, IP rotation, DFY |
| AI personalization (costs credits) | Webhooks, CRM sync, custom roles, white-label |

### Pro ($99) — the working business

Everything in Free, plus:
- **Warmup Engine** (full: peer warmup, DNS/SPF/DKIM/DMARC checks, blacklist monitoring, auto-reply)
- **AI Sales Agent** (send decisions, scoring, policy engine), **AI Sequence Generator**, **ICP Wizard**
- **AI Reply Agent in HITL mode** (suggests, human approves)
- Analytics + full Reports, **A/B testing + auto-optimize**, Send-time optimizer, Email Preview/approval
- Full CRM Deals pipeline, full Inbox with sentiment + threading
- **Webhooks**, **CRM sync** (HubSpot / Salesforce), Zapier
- **3 Lines of Business**, custom RBAC roles, 25 mailboxes, 25 active campaigns, 10 seats

### Max ($299) — agency / scale

Everything in Pro, plus:
- **AI Reply Agent Autopilot** (autonomous send, no human in loop)
- **Attribution**, **Website Visitors**, **Intent Engine + Intent Signals** (7 signal types), **Forecast Engine**
- **Unlimited LOBs**, **Dedicated IP pool / IP rotation**
- **Agency mode**: white-label branding, custom domain, client sub-accounts
- **Data Backups + DR** (offsite S3, Fernet-encrypted)
- **DFY onboarding**, priority support + SLA, SSO (when ELR-020 ships)
- **1,000 mailboxes, 100 active campaigns, 50 seats, 25 lines of business**

**Rationale for the Max split:** Instantly charges *separately* for Website Visitors, DFY Services,
Pre-Warmed Accounts and Inbox Placement on top of its $358 Lightspeed plan. Bundling all of those
into a single $299 tier is the sharpest competitive story we have.

### Custom — above Max

Feature set is identical to Max. What changes is the numbers: the customer **selects** their own
values, and every axis is floored at Max's figure.

| Axis | Minimum (= Max's number) | Notes |
|---|---|---|
| Mailboxes | > 1,000 | The usual reason a customer lands here |
| Credits / month | > 25,000 | Sold in blocks of 5,000 |
| Email sends / month | > 150,000 | Must be consistent with mailbox count × 900 |
| Active campaigns | > 100 | Scheduler load — the campaign engine sweeps these every 2 min |
| Seats | > 50 | Marginal cost ≈ 0; price for the relationship, not the row |
| Lines of business | > 25 | Marginal cost ≈ 0; config rows only |

Commercial shape: **annual contract, invoiced, no public price.** Priced off the same credit
economics as every other tier, with a **70% gross-margin floor** as the quoting guardrail —
i.e. never quote below `(credits × $0.01 COGS-adjusted) ÷ 0.30`. The `ManualGateway` in
`services/billing/payment_gateway.py` already handles non-Stripe invoicing, so this needs no new
payment path.

**Why this is cheap to build:** the `Tenant` model *already* carries per-tenant limit columns
(`max_users`, `max_mailboxes`, `max_contacts`, `max_campaigns`, `max_leads`) and
`/admin/tenants/{id}` already updates them. So Custom is not a new limits system — it is
`plan=custom` plus "limits are read from the tenant row instead of the plan matrix", set by a
super_admin at contract time. The only new rule is a validation guard that a custom tenant's
limits may never be set *below* Max's.

---

## 8. Competitor analysis (researched 2026-09-22)

| Vendor | Entry | Mid | High | Free tier | Credit model |
|---|---|---|---|---|---|
| **Instantly.ai** | Growth $47 (5k emails, 1k contacts) | Hypergrowth $97 (100k emails, 25k contacts) | Lightspeed $358 | ❌ none | Separate modules: Outreach + Credits + CRM; Visitors/DFY/Inbox-Placement all extra. Real setup $94–194/mo |
| **Smartlead** | Basic $39 (2k leads, 6k emails) | Pro $94 | Unlimited Smart $174 (150k emails) / Prime $379 (510k) | ❌ none | Flat plans, unlimited mailboxes; verification/data are separate line items |
| **Apollo.io** | Basic $49/user | Professional $79/user | Organization $119/user (3 seat min) | ✅ 900 credits **/year** | 1 credit = 1 email or phone reveal |
| **Clay** | Launch $185 (2.5k data credits, 15k actions) | Growth $495 (6k / 40k) | Enterprise custom | ✅ 100 data credits + 500 actions/mo | **Dual currency** — Data Credits + Actions, deplete independently (major UX complaint) |
| **lemlist** | Email Starter $32/user (750 cr) | Email Pro | Multichannel Expert $99/user (2.5k cr) | ❌ 14-day trial | 1 verified email = 5 cr ≈ $0.05; phone = 20 cr; top-up $50/5,000 cr |
| **Saleshandy** | $25/mo annual | — | — | ❌ 7-day trial + 5 lead credits | Data credits separate |
| **Reply.io** | Email $49 | Multichannel $89/user | +Jason AI $500/mo | ✅ 200 emails/mo | Per-user |
| **Woodpecker** | Starter $29 (500 prospects) | — | — | ❌ 14-day trial / 100 emails | Per-slot |

### What this tells us

1. **$79–99 is the dense mid-market band** (Instantly $97, Smartlead $94, Apollo $79, lemlist $99).
   Pricing Pro at **$99** puts us exactly where buyers already have budget approved, and our Pro
   includes warmup + AI + CRM + enrichment that Instantly and Smartlead charge extra for.
2. **A real free tier is rare and therefore a wedge.** Instantly, Smartlead, lemlist, Saleshandy and
   Woodpecker have *no* free plan. Only Apollo (stingy, annual) and Clay (tiny) do. A usable Free
   tier is genuine differentiation in this category.
3. **Per-seat pricing is the category's weak point.** Apollo, lemlist and Reply.io all charge per
   user, which punishes teams. Clay went the other way — unlimited seats on all plans — and markets
   it hard. **We should include seats in the plan price, not per-user.** That is already how the
   Tenant model works (`max_users`), so it costs us nothing to adopt.
4. **$299 for Max undercuts** Smartlead Prime ($379), Instantly Lightspeed ($358) and Clay Growth
   ($495) while bundling more modules than any of them.
5. Nobody in this set bundles **job-board lead sourcing** the way we do. That is an unmatched
   feature and belongs in the Pro headline, not buried.

---

## 9. Implementation plan

### Phase 0 — unblock (must ship first)  ✅ DONE 2026-09-22
- [x] **0.1** Fix `tenant_service.create_tenant_for_signup()` to assign real Free-tier limits
      (currently all zeros → product unusable on signup). See §2.
- [x] **0.2** Fix the limit sentinel in `plan_limits.check_plan_limit()`. Today `0` means
      "unlimited" for professional and "locked" for starter — the same value with two opposite
      meanings, which is the root of the §2 blocker.
      **Simplified by the decision that no tier is ever unlimited:** every limit is now a positive
      integer, so `0` needs only ONE meaning — *not included in this plan* — and the
      `if max_allowed == 0: return  # Professional with 0 = unlimited` branch is deleted outright.
      No `-1` sentinel and no nullable-column migration required. Drop the
      `if tenant.plan == ENTERPRISE: return` early-exit too, since Max now has real caps.

### Phase 1 — plan model  ✅ DONE 2026-09-22 (except the 1.6 frontend)
- [x] **1.1** `TenantPlan` enum → `FREE = "free"`, `PRO = "pro"`, `MAX = "max"`,
      `CUSTOM = "custom"`. Alembic revision mapping `starter→free`, `professional→pro`,
      `enterprise→max`. Keep old values accepted on read for one release (JWT claims carry `plan`).
- [x] **1.2** Config: `CREDIT_LIMIT_STARTER/PROFESSIONAL/ENTERPRISE` → `CREDIT_LIMIT_FREE=300`,
      `CREDIT_LIMIT_PRO=6000`, `CREDIT_LIMIT_MAX=25000`. Add `SEND_QUOTA_*`.
- [x] **1.3** `STRIPE_PRICE_STARTER/PROFESSIONAL/ENTERPRISE` → `_FREE/_PRO/_MAX` (+ annual price ids).
- [x] **1.4** Single source of truth `core/plans.py`: `PLAN_MATRIX` = limits + credits + send quota
      + feature flags per plan. Everything else reads from it. Max is
      `max_mailboxes=1000, max_users=50, max_lobs=25` — all finite, no sentinels.
- [x] **1.4a** Rewrite the campaigns counter to live state only (see §2a):
      `.filter(Campaign.status.in_([ACTIVE, PAUSED]))`. Both call sites already exist
      (`campaigns.py:519` and `:695`), so no new enforcement points are needed — only the counter
      changes. Add a regression test that completing a campaign frees a slot.
- [x] **1.4b** **LOBs are not currently a metered resource — this is new plumbing.** `Tenant` has
      `max_users/max_mailboxes/max_contacts/max_campaigns/max_leads` but no `max_lobs`, and
      `plan_limits.RESOURCE_COUNTERS`/`RESOURCE_LIMITS` have no `lobs` key. Needs: a `max_lobs`
      column (Alembic), a counter over `lines_of_business` filtered by tenant, and a
      `check_plan_limit(db, tid, "lobs")` call on the LOB create endpoint.
      Note `LineOfBusiness` is an *instance* table (a tenant can have many LOBs of the same
      `lob_type`, e.g. three separate staffing LOBs), so counting rows is the right cap —
      distinct from `TenantLOBAssignment`, which gates which of the 6 *types* a tenant may use.
- [x] **1.5** **Custom tier resolution**: when `plan == custom`, limits resolve from the `Tenant`
      row (those columns already exist) instead of `PLAN_MATRIX`. Add a validation guard in
      `admin_tenants.py` update + create so a custom tenant's limits can never be set *below* Max's
      — the floor is the whole point of the tier.
- [x] **1.6** (UI shipped in Phase 4 — the configurator lives in `plan-usage-panel.tsx`,
      with each stepper's minimum set to Max's figure and re-validated server-side)
      Public "Build your plan" configurator: each axis is a stepper whose minimum is Max's
      number, producing a quote request rather than a checkout. Backed by a new
      `POST /billing/custom-quote` that records the requested numbers and notifies sales.
      Billing runs through the existing `ManualGateway`, not Stripe.

### Phase 2 — credit engine  ✅ DONE 2026-09-22
- [x] **2.1** `core/credit_costs.py` — the §4 price list as a registry, overridable via the existing
      Settings pattern (`provider_pricing` precedent).
- [x] **2.2** `TenantCreditBalance` model — per-tenant row with `allowance_credits`,
      `topup_credits`, `period_start`. Atomic `SELECT … FOR UPDATE` decrement. This is the
      already-tracked **ELR-009b** hardening (`credit_metering.check_credit_budget` docstring
      admits the current sum-then-check guard admits overage under concurrency).
- [x] **2.3** **Wire `record_usage()` at every choke-point.** It is currently called in ONE file
      (`sms.py`). Required call sites: lead sourcing, contact enrichment, email validation,
      ai_personalizer, ai_reply_agent_service, ai_sequence_generator, ai_icp_wizard,
      company_firmographics, intent_signal_monitor, firecrawl_client.
- [x] **2.4** Monthly reset job (APScheduler, alongside the existing billing jobs).
- [x] **2.5** Top-up purchase flow (Stripe one-time price) + `POST /billing/credits/topup`.

### Phase 3 — feature gating  ✅ DONE 2026-09-22
- [x] **3.1** `api/deps/features.py::require_feature("warmup")` reading `PLAN_MATRIX`, returning 402
      with an upgrade CTA (mirrors the existing `check_credit_budget` 402 pattern).
- [x] **3.2** Apply to the Max/Pro-only routers: warmup, attribution, visitors, intent, forecast,
      ip_rotation, backups, automation, lob, webhooks, crm_sync, roles.
- [x] **3.3** Send-quota gate in `send_gate.unified_send_gate()` as an 11th ordered check.

### Phase 4 — surface  ✅ DONE 2026-09-22
- [x] **4.1** `GET /billing/usage` — credits used / remaining / send quota / per-type breakdown
      (`get_usage_summary()` already returns most of this).
- [x] **4.2** Dashboard credit meter + upgrade CTA; usage tab under Billing.
- [x] **4.3** Public pricing page; in-app upgrade → Stripe Checkout (`/billing/subscription/checkout`
      already exists from ELR-021).

### Phase 5 — verification
- [ ] **5.1** Unit tests: credit arithmetic, concurrency (two parallel spends cannot overdraw).
- [ ] **5.2** Integration: each gated route returns 402 on Free, 200 on Max.
- [ ] **5.3** Tenant-isolation tests — credit balances must never leak across tenants
      (extends `tests/security/test_tenant_isolation.py`).
- [ ] **5.4** Migration test: existing starter/professional/enterprise tenants land on free/pro/max
      with limits preserved.

---

## 10. Open decisions for the user

1. **Pro at $99 or $79?** $99 matches Instantly/Smartlead; $79 matches Apollo and undercuts the
   field. Recommendation: **$99 monthly / $79 annual** — you get the low number in marketing while
   protecting monthly revenue.
2. **Does Free get warmup?** Recommendation **no** (shared peer pool is an abuse vector). If we say
   yes, it becomes the strongest free tier in the category — at real deliverability risk.
3. **Annual discount 20%?** Category norm is 17–20% (Smartlead 17%, Instantly 20%).
4. **Credit rollover?** Recommendation: none in v1.
5. ~~**Keep an Enterprise/custom tier above Max?**~~ — **DECIDED 2026-09-22: yes.** Max is capped
   at 1,000 mailboxes; the **Custom** tier sits above it, where the customer selects their own
   numbers with Max's figures as the floor. See §8a. Open sub-question: should Custom credits be
   sold in blocks of 5,000 (simpler to quote) or fully free-form?
