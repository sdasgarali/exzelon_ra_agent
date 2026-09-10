# Marketing site — make every footer/nav destination real

> Audit + build plan. Trigger: every option in the top bar and footer must lead to a real page,
> and Privacy/Terms must be thought through before being designed.

## 1. Audit — what was broken (before this change)

| Link | Location | Was | Problem |
|---|---|---|---|
| Sales Teams | Footer › Use Cases | `/features#campaigns` | Anchor does not exist — lands at page top |
| Lead Generation | Footer › Use Cases | `/features#lead-sourcing` | Anchor does not exist |
| Email Outreach | Footer › Use Cases | `/features#outreach` | Anchor does not exist |
| CRM Integration | Footer › Use Cases | `/features#crm` | Anchor does not exist |
| API Documentation | Footer › Resources | `/dashboard` | Wrong destination; real Swagger UI is public at `/api/docs` |
| Status | Footer › Resources | `/` | Placeholder |
| About | Footer › Company | `/` | Placeholder |
| Contact | Footer › Company | `/` | Placeholder |
| Privacy Policy | Footer › Company | `/` | Placeholder |
| Terms of Service | Footer › Company | `/` | Placeholder |
| Privacy | Footer › bottom bar | `/` | Placeholder |
| Terms | Footer › bottom bar | `/` | Placeholder |

Verified working already: Features, Pricing, Compare, Documentation, Dashboard, Log in, Get Started.

## 2. Thinking before designing — Privacy & Terms

### 2.1 The fact that shapes both documents

NeuraLeads is a **cold outreach platform**. Its customers source, enrich and email
**third parties who never had a relationship with NeuraLeads**. That creates two
distinct data relationships, and conflating them (as a generic SaaS policy would)
would be both wrong and legally dangerous:

| Relationship | Whose data | Our role | Who decides purpose |
|---|---|---|---|
| Account holder | The customer's own staff — name, email, billing | **Controller** | Us |
| Prospect data | People the customer targets — name, work email, employer, engagement events | **Processor** | The customer |

Everything else follows from this split.

### 2.2 Consequences that must appear in the Privacy Policy

- [x] A prospect-facing section. People who receive a cold email will land on the privacy
      page looking for how to stop it. If the only audience addressed is "customers",
      the page fails the person with the strongest need. Must cover: how they got the
      email, how to opt out, how to complain, how to reach the actual sender.
- [x] Where prospect data originates — public job postings and third-party providers —
      stated plainly rather than hidden.
- [x] Sub-processor disclosure. The platform fans data out to job boards, contact
      providers, validation providers, AI engines, payments and SMS. That list is
      material and is already known from the product.
- [x] The AI nuance: customers supply **their own** provider keys, so the AI provider
      relationship is largely theirs, not ours. Saying "we never send your data to AI
      vendors" would be false; saying nothing would be evasive.
- [x] Tracking split: cookies **we** set on the marketing site vs. open/click pixels and
      the visitor script **the customer** deploys. Different controllers, different page.
- [x] Data-subject rights are routed through the customer, with us assisting — the
      product already ships export and erasure tooling.

### 2.3 Consequences that must appear in the Terms

- [x] Acceptable use is the centre of gravity, not boilerplate: CAN-SPAM / GDPR / CASL
      compliance, accurate sender identity, honoured unsubscribes, business contacts
      only, no scraped consumer lists, no circumventing the send gate or throttles.
- [x] Right to suspend on bounce/complaint thresholds — the platform already enforces
      these automatically, so the terms must back the product's behaviour.
- [x] Customer indemnity for the content and recipients of their outreach. We supply the
      instrument; they choose who to contact and what to say.
- [x] No warranty of deliverability, inbox placement, reply rate or revenue. This is the
      single most likely source of a disappointed-customer dispute.
- [x] Third-party provider keys: customer pays those vendors directly, and their outages
      and costs are not ours.
- [x] Billing reality must match the product: 14-day trial, flat fee, no per-seat charge,
      20% annual discount, plan limits enforced at creation, cancellation at period end.

### 2.4 What must NOT be invented

The repo has no configured legal entity, registered address, jurisdiction or contact
address (`BILLING_COMPANY_*` are all empty; the only addresses in the codebase are seed
data). Inventing a privacy contact would send data-subject requests into a black hole —
a real harm, not a cosmetic gap.

**Decision:** ship the documents with these facts marked by a visible `Pending` chip
rather than guessed. Items to supply:

1. Legal entity name and registered address
2. Governing law / jurisdiction
3. Privacy & data-request address
4. Support address
5. Security disclosure address

Both documents also carry a "last updated" date and need a lawyer's review before being
relied upon — noted to the operator, not to visitors.

## 3. Build list

- [x] `/privacy` — Privacy Policy (16 sections, incl. prospect-facing section)
- [x] `/terms` — Terms of Service (17 sections)
- [x] `/about` — grounded in what the product actually is; no invented founding story,
      team, funding or offices
- [x] `/contact` — routed by need (sales, support, data requests, security)
- [x] `/status` — honest: performs a live check from the visitor's browser against the
      public health endpoint and labels it as such. No fabricated uptime history.
- [x] Add anchor ids to the feature sections so the Use Cases links resolve
- [x] Repoint API Documentation to `/api/docs` (verified public, returns 200)
- [x] Shared legal shell + rail so Privacy and Terms stay visually consistent
- [x] Shared marketing font module so Plex Mono / Source Serif load once

## 4. Verification

- [ ] `tsc --noEmit` clean
- [ ] `npm run build` succeeds, new routes prerender
- [ ] Every footer and nav link resolves to 200 (crawled, not eyeballed)
- [ ] Desktop + mobile render checked
