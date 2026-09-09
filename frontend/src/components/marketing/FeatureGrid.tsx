/**
 * Capability spec sheet.
 *
 * Deliberately not a card grid: nine identical rounded boxes with gradient icon
 * chips is the shape every generated SaaS page ships. This is a specification
 * list — hairline-ruled rows, name / description / hard figure — which suits a
 * product whose whole argument is that it counts things carefully.
 *
 * Every figure here is real and checkable in the codebase.
 */

interface Spec {
  name: string
  body: string
  figure: string
  unit: string
}

const SPECS: Spec[] = [
  {
    name: 'Lead sourcing',
    body: 'Ten job boards queried in parallel, normalised, then deduplicated on external job ID, employer LinkedIn URL, and company + title + state.',
    figure: '10',
    unit: 'sources',
  },
  {
    name: 'Company gate',
    body: 'Drops confidential employers, anything over your headcount ceiling, and excluded industries before a single credit is spent on enrichment.',
    figure: '22',
    unit: 'target industries',
  },
  {
    name: 'Contact discovery',
    body: 'Waterfall enrichment across seven providers, capped at four decision-makers per company per role so you never carpet-bomb an org.',
    figure: '7',
    unit: 'providers',
  },
  {
    name: 'Email validation',
    body: 'Every address verified before it can queue. Only addresses that come back Valid are ever eligible for outreach.',
    figure: '7',
    unit: 'validators',
  },
  {
    name: 'Send gate',
    body: 'Ten ordered checks — status, suppression, validation, cooldown, per-lead limit, company cap, fatigue, domain throttle — on all four send paths.',
    figure: '10',
    unit: 'ordered checks',
  },
  {
    name: 'Campaign engine',
    body: 'Multi-step sequences with wait and condition branching, A/B variants with chi-squared auto-optimisation, spintax, and per-contact timezone windows.',
    figure: '4',
    unit: 'step types',
  },
  {
    name: 'Warmup engine',
    body: 'Peer-to-peer warmup between your own mailboxes, SPF/DKIM/DMARC verification, and continuous IP and domain blacklist monitoring.',
    figure: '30',
    unit: 'day ramp',
  },
  {
    name: 'Unified inbox',
    body: 'Replies threaded by Message-ID chain, categorised by intent, with sentiment scoring and drafted responses held for approval.',
    figure: '6',
    unit: 'intent labels',
  },
  {
    name: 'Deals and reporting',
    body: 'Seven-stage pipeline with two-way HubSpot and Salesforce sync, plus per-source cost tracking down to the fraction of a cent.',
    figure: '2-way',
    unit: 'CRM sync',
  },
  {
    name: 'Roles and tenancy',
    body: 'Every table is tenant-scoped. Four built-in roles plus custom ones you define, with permissions granular down to individual settings tabs.',
    figure: '4+',
    unit: 'roles, extensible',
  },
]

export default function FeatureGrid() {
  return (
    <section className="border-t border-paper-200 bg-paper px-6 py-20 lg:py-28">
      <div className="mx-auto max-w-7xl">
        <div className="max-w-[54ch]">
          <h2 className="text-balance text-[clamp(1.9rem,3.6vw,2.9rem)] font-extrabold leading-[1.08] tracking-[-0.03em] text-ink">
            One system, sourcing through signed.
          </h2>
          <p className="mt-5 text-[17px] leading-relaxed text-ink-700">
            The pipeline above isn&rsquo;t a marketing diagram — it&rsquo;s the actual
            architecture. Here is what each stage ships with.
          </p>
        </div>

        <div className="mt-14 grid gap-x-16 md:grid-cols-2">
          {SPECS.map((s) => (
            <article
              key={s.name}
              className="grid grid-cols-[1fr_auto] items-start gap-x-6 border-t border-paper-200 py-6"
            >
              <div>
                <h3 className="text-[15px] font-bold tracking-tight text-ink">{s.name}</h3>
                <p className="mt-1.5 max-w-[46ch] text-[14px] leading-relaxed text-ink-700">
                  {s.body}
                </p>
              </div>
              <div className="pt-0.5 text-right">
                <div className="text-[22px] font-extrabold leading-none tracking-tight tabular-nums text-brand">
                  {s.figure}
                </div>
                <div className="mt-1 text-[11px] leading-tight text-ink-500">{s.unit}</div>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
