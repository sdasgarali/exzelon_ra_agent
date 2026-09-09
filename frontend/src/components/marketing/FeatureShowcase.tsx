/**
 * The send gate, in full.
 *
 * Replaces the previous section's fake browser-chrome mockups (grey rectangles
 * standing in for screenshots). The artifact on the right is the real ordered
 * check list from `services/send_gate.py` — names and reason codes verbatim.
 * Showing the actual mechanism is both more honest and more distinctive than a
 * stylised dashboard nobody believes.
 */

interface Check {
  n: string
  name: string
  code: string
  what: string
}

const CHECKS: Check[] = [
  { n: '01', name: 'Contact status', code: 'UNSUBSCRIBED · INACTIVE', what: 'Opted out, or marked inactive after a hard bounce.' },
  { n: '02', name: 'Suppression', code: 'SUPPRESSED', what: 'On the tenant suppression list, by address or whole domain.' },
  { n: '03', name: 'Email validation', code: 'INVALID_EMAIL', what: 'Never verified, or verified and not Valid.' },
  { n: '04', name: 'Contact–lead cooldown', code: 'CONTACT_LEAD_COOLDOWN', what: 'Already contacted about this same role too recently.' },
  { n: '05', name: 'Contact cooldown', code: 'CONTACT_COOLDOWN', what: 'Inside the global window between any two emails to a person.' },
  { n: '06', name: 'Lead contact limit', code: 'LEAD_CONTACT_LIMIT', what: 'This role has already reached its outreach ceiling.' },
  { n: '07', name: 'Company cap', code: 'COMPANY_CAP', what: 'Enough people at this company have been approached already.' },
  { n: '08', name: 'Sequence fatigue', code: 'SEQUENCE_FATIGUE', what: 'Too many steps sent with nothing coming back.' },
  { n: '09', name: 'Domain throttle', code: 'DOMAIN_THROTTLE', what: 'Daily ceiling for this recipient domain is spent.' },
  { n: '10', name: 'Agent policy', code: 'AI_BLOCKED', what: 'Policy engine vetoed the content or the recipient.' },
]

export default function FeatureShowcase() {
  return (
    <section id="gate" className="border-t border-paper-200 bg-paper-100 px-6 py-20 lg:py-28">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-14 lg:grid-cols-[0.85fr_1.15fr] lg:gap-20">
        {/* Argument */}
        <div className="lg:sticky lg:top-28 lg:self-start">
          <h2 className="text-balance text-[clamp(1.9rem,3.6vw,2.9rem)] font-extrabold leading-[1.08] tracking-[-0.03em] text-ink">
            Ten reasons an email doesn&rsquo;t go out.
          </h2>
          <p className="mt-5 max-w-[46ch] text-[17px] leading-relaxed text-ink-700">
            Domain reputation is the one asset in outbound you can&rsquo;t buy back. So every
            message passes the same ordered gate, and the first failure stops it — no
            override, no &ldquo;send anyway&rdquo;.
          </p>
          <p className="mt-4 max-w-[46ch] text-[15px] leading-relaxed text-ink-500">
            All four send paths run through it: campaigns, pipeline outreach, one-off sends,
            and agent replies. There is no fifth path.
          </p>

          <dl className="mt-9 grid grid-cols-2 gap-x-8 gap-y-5 border-t border-paper-200 pt-7">
            <div>
              <dt className="text-[13px] text-ink-500">Per mailbox, per day</dt>
              <dd className="mt-0.5 text-[20px] font-extrabold tabular-nums tracking-tight text-ink">30</dd>
            </div>
            <div>
              <dt className="text-[13px] text-ink-500">Cooldown between emails</dt>
              <dd className="mt-0.5 text-[20px] font-extrabold tabular-nums tracking-tight text-ink">10 days</dd>
            </div>
          </dl>
        </div>

        {/* Artifact */}
        <div>
          <div className="flex items-baseline justify-between border-b border-ink/15 pb-3">
            <h3 className="text-[14px] font-bold tracking-tight text-ink">
              unified_send_gate
            </h3>
            <span className="text-[12px] text-ink-500">first failure wins</span>
          </div>

          <ol className="mt-1">
            {CHECKS.map((c) => (
              <li
                key={c.n}
                className="group grid grid-cols-[2.25rem_1fr] items-start gap-x-3 border-b border-paper-200 py-3.5 transition-colors duration-150 hover:bg-paper"
              >
                <span className="pt-0.5 text-[12px] font-bold tabular-nums text-brand">{c.n}</span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <h4 className="text-[15px] font-bold tracking-tight text-ink">{c.name}</h4>
                    <code className="break-all font-mono text-[11px] font-medium text-signal">
                      {c.code}
                    </code>
                  </div>
                  <p className="mt-1 max-w-[52ch] text-[13.5px] leading-relaxed text-ink-700">
                    {c.what}
                  </p>
                </div>
              </li>
            ))}
          </ol>

          <p className="mt-4 text-[12px] leading-relaxed text-ink-500">
            Replies and flagged test contacts skip checks 04&ndash;08 by design; everything else
            runs every time.
          </p>
        </div>
      </div>
    </section>
  )
}
