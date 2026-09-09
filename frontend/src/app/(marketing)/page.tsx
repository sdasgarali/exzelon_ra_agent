import type { Metadata } from 'next'
import Link from 'next/link'
import Hero from '@/components/marketing/Hero'
import FeatureGrid from '@/components/marketing/FeatureGrid'
import FeatureShowcase from '@/components/marketing/FeatureShowcase'
import ROICalculator from '@/components/marketing/ROICalculator'

export const metadata: Metadata = {
  title: 'NeuraLeads — Outbound that knows what not to send',
  description:
    'Ten job boards in, thirty emails out. Three-layer dedup, a company-size gate, seven validation providers and a ten-check send gate before anything reaches a mailbox.',
  openGraph: {
    title: 'NeuraLeads — Outbound that knows what not to send',
    description:
      'Full-pipeline outreach automation with a ten-check send gate on every path. Self-hosted or managed, no per-seat pricing.',
  },
}

/* ────────────────────────────────────────────────────────────────────────────
   Integrations — grouped by the job they do.
   Every name below is a real adapter in `services/adapters/`. The previous
   scrolling marquee listed Zapier, which the product does not integrate with.
   ──────────────────────────────────────────────────────────────────────────── */

const INTEGRATION_GROUPS: { role: string; names: string[] }[] = [
  {
    role: 'Job sources',
    names: ['Apollo', 'JSearch', 'TheirStack', 'SerpAPI', 'Adzuna', 'SearchAPI', 'USAJobs', 'Jooble', 'JobDataFeeds', 'Coresignal'],
  },
  {
    role: 'Contact discovery',
    names: ['Apollo', 'Seamless', 'Hunter.io', 'Snov.io', 'RocketReach', 'People Data Labs', 'Proxycurl'],
  },
  {
    role: 'Email validation',
    names: ['NeverBounce', 'ZeroBounce', 'Hunter', 'Clearout', 'Emailable', 'MailboxValidator', 'Reacher'],
  },
  {
    role: 'CRM and comms',
    names: ['HubSpot', 'Salesforce', 'Slack', 'Microsoft Teams', 'Twilio', 'Stripe'],
  },
  {
    role: 'Language models',
    names: ['Groq', 'OpenAI', 'Anthropic', 'Gemini'],
  },
]

function Integrations() {
  return (
    <section className="border-t border-paper-200 bg-paper px-6 py-20 lg:py-24">
      <div className="mx-auto max-w-7xl">
        <div className="max-w-[54ch]">
          <h2 className="text-balance text-[clamp(1.9rem,3.6vw,2.9rem)] font-extrabold leading-[1.08] tracking-[-0.03em] text-ink">
            Bring your own providers.
          </h2>
          <p className="mt-5 text-[17px] leading-relaxed text-ink-700">
            Every provider is an adapter behind a common interface, selected per tenant. Swap
            one out and nothing downstream changes — and you pay them directly, at their
            rates, not ours.
          </p>
        </div>

        <dl className="mt-12 space-y-0">
          {INTEGRATION_GROUPS.map((g) => (
            <div
              key={g.role}
              className="grid grid-cols-1 gap-x-10 gap-y-3 border-t border-paper-200 py-6 md:grid-cols-[13rem_1fr]"
            >
              <dt className="text-[14px] font-bold tracking-tight text-ink">{g.role}</dt>
              <dd className="flex flex-wrap gap-x-2.5 gap-y-2">
                {g.names.map((n) => (
                  <span
                    key={n}
                    className="rounded border border-paper-200 bg-paper-0 px-2.5 py-1 text-[13px] font-medium text-ink-700"
                  >
                    {n}
                  </span>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}

/* ────────────────────────────────────────────────────────────────────────────
   Why teams switch — three honest structural claims, each verifiable.
   ──────────────────────────────────────────────────────────────────────────── */

const REASONS = [
  {
    head: 'One system, not five subscriptions',
    body: 'Sourcing, enrichment, validation, sending, inbox and deals are one pipeline sharing one database. Most teams arrive here consolidating three to five separate tools.',
  },
  {
    head: 'Priced per workspace, not per seat',
    body: 'Add the whole team without re-reading the pricing page. Provider costs are passed through at cost and tracked per source, down to fractions of a cent.',
  },
  {
    head: 'Self-host it if you want to',
    body: 'Run it on your own box with your own database and mailboxes. Your lead data and your reply history never have to leave your infrastructure.',
  },
]

function WhySwitch() {
  return (
    <section className="border-t border-paper-200 bg-paper-100 px-6 py-20 lg:py-24">
      <div className="mx-auto max-w-7xl">
        <h2 className="max-w-[20ch] text-balance text-[clamp(1.9rem,3.6vw,2.9rem)] font-extrabold leading-[1.08] tracking-[-0.03em] text-ink">
          Why teams move over.
        </h2>

        <div className="mt-12 grid gap-x-14 gap-y-10 md:grid-cols-3">
          {REASONS.map((r) => (
            <div key={r.head} className="border-t-2 border-ink pt-5">
              <h3 className="text-[17px] font-bold leading-snug tracking-tight text-ink">
                {r.head}
              </h3>
              <p className="mt-3 text-[14.5px] leading-relaxed text-ink-700">{r.body}</p>
            </div>
          ))}
        </div>

        <Link
          href="/compare"
          className="mt-12 inline-flex items-center gap-2 border-b-2 border-brand pb-0.5 text-[15px] font-semibold text-brand transition-colors hover:border-brand-700 hover:text-brand-700"
        >
          Full comparison against the major platforms
          <span aria-hidden>&rarr;</span>
        </Link>
      </div>
    </section>
  )
}

/* ────────────────────────────────────────────────────────────────────────────
   Closing — bookends the hero drench.
   ──────────────────────────────────────────────────────────────────────────── */

function Close() {
  return (
    <section className="bg-brand-600 px-6 py-20 lg:py-28">
      <div className="mx-auto flex max-w-7xl flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="max-w-[18ch] text-balance text-[clamp(2rem,4.2vw,3.25rem)] font-extrabold leading-[1.04] tracking-[-0.035em] text-white">
            Point it at your ICP tonight.
          </h2>
          <p className="mt-5 max-w-[48ch] text-[17px] leading-relaxed text-white/80">
            Connect a mailbox, set your industries and headcount ceiling, and read the run
            report in the morning before anything sends.
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-3">
          <Link
            href="/signup"
            className="rounded-lg bg-white px-6 py-3.5 text-[15px] font-semibold text-brand-700 transition-transform duration-200 ease-out hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
          >
            Start free trial
          </Link>
          <Link
            href="/pricing"
            className="rounded-lg border border-white/25 px-6 py-3.5 text-[15px] font-semibold text-white transition-colors duration-200 hover:border-white/50 hover:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
          >
            See pricing
          </Link>
        </div>
      </div>
    </section>
  )
}

export default function LandingPage() {
  return (
    <>
      <Hero />
      <div id="pipeline">
        <FeatureGrid />
      </div>
      <FeatureShowcase />
      <Integrations />
      <ROICalculator />
      <WhySwitch />
      <Close />
    </>
  )
}
