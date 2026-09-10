import type { Metadata } from 'next'
import Link from 'next/link'
import ScrollReveal from '@/components/marketing/ScrollReveal'
import HealthCheck from './HealthCheck'

export const metadata: Metadata = {
  title: 'Service Status',
  description:
    'Check whether the NeuraLeads platform is reachable right now, and what to do if your sending looks wrong but the platform is up.',
  alternates: { canonical: '/status' },
  robots: { index: true, follow: true },
}

const components = [
  {
    name: 'Web application',
    detail: 'The dashboard and marketing site. Covered directly by the check above.',
  },
  {
    name: 'API',
    detail: 'Serves the dashboard and any integration using an API key. Covered by the check above.',
  },
  {
    name: 'Campaign engine',
    detail:
      'Processes sequences every two minutes. If it stalls, campaigns pause rather than double-send.',
  },
  {
    name: 'Inbox sync',
    detail: 'Pulls replies during working hours. A delay here shows as replies arriving late.',
  },
  {
    name: 'Background jobs',
    detail:
      'Sourcing, scoring, warmup, backups and billing runs. Each can be switched off per workspace from the Automation screen.',
  },
]

const selfChecks = [
  {
    q: 'Emails are not sending',
    a: 'Check the send window and send days on the campaign, whether the campaign auto-paused on a bounce or complaint threshold, and whether the mailbox has hit its daily limit. The send gate records a reason for every blocked send.',
    href: '/documentation#sendgate',
    hrefLabel: 'How the send gate works',
  },
  {
    q: 'A provider is failing',
    a: 'Use the test-connection button on the relevant Settings tab. Most sourcing and enrichment failures are an expired key or an exhausted quota at the provider, not the platform.',
    href: '/documentation#integrations',
    hrefLabel: 'Integrations reference',
  },
  {
    q: 'Replies are not appearing',
    a: 'Inbox sync runs on a schedule rather than instantly, and only during its window. Confirm the mailbox still authenticates, then check the Automation screen to see whether the job is enabled.',
    href: '/documentation#automation',
    hrefLabel: 'Background automation',
  },
]

export default function StatusPage() {
  return (
    <>
      <section className="pt-32 pb-10 px-6">
        <div className="max-w-4xl mx-auto">
          <ScrollReveal>
            <p className="text-xs font-mono uppercase tracking-[0.14em] text-slate-500 mb-4">
              Service status
            </p>
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-6 leading-tight">
              Is the platform up?
            </h1>
            <p className="text-lg text-slate-400 leading-relaxed max-w-2xl mb-8">
              This page runs a live check from your browser against the platform’s public health
              endpoint. It reflects what your connection can see right now — not a third-party
              monitoring history, and not a promise about anyone else’s connection.
            </p>
          </ScrollReveal>
          <ScrollReveal delay={0.08}>
            <HealthCheck />
          </ScrollReveal>
        </div>
      </section>

      <section className="py-14 px-6 border-t border-white/5">
        <div className="max-w-4xl mx-auto">
          <ScrollReveal>
            <h2 className="text-2xl font-bold text-white mb-3">What the check covers</h2>
            <p className="text-slate-400 mb-8 max-w-2xl">
              A healthy response means the application and API are answering. Background processing
              runs on its own schedules and is not directly observable from a browser.
            </p>
            <div className="rounded-2xl border border-white/10 overflow-hidden">
              {components.map((c, i) => (
                <div
                  key={c.name}
                  className={`flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-6 p-5 bg-white/[0.03] ${
                    i > 0 ? 'border-t border-white/10' : ''
                  }`}
                >
                  <span className="text-white font-semibold text-sm sm:w-48 sm:flex-shrink-0">
                    {c.name}
                  </span>
                  <span className="text-slate-400 text-sm leading-relaxed">{c.detail}</span>
                </div>
              ))}
            </div>
          </ScrollReveal>
        </div>
      </section>

      <section className="py-14 px-6 border-t border-white/5">
        <div className="max-w-4xl mx-auto">
          <ScrollReveal>
            <h2 className="text-2xl font-bold text-white mb-3">
              Platform is up but something still looks wrong
            </h2>
            <p className="text-slate-400 mb-8 max-w-2xl">
              Most reports that begin “the service is down” turn out to be one of these three, and
              each is something you can confirm yourself in a minute.
            </p>
            <div className="space-y-4">
              {selfChecks.map((s) => (
                <div key={s.q} className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
                  <h3 className="text-white font-semibold mb-2">{s.q}</h3>
                  <p className="text-slate-400 text-sm leading-relaxed mb-3">{s.a}</p>
                  <Link
                    href={s.href}
                    className="text-sm font-medium text-primary-400 hover:text-primary-300 transition-colors"
                  >
                    {s.hrefLabel} →
                  </Link>
                </div>
              ))}
            </div>
          </ScrollReveal>
        </div>
      </section>

      <section className="py-14 px-6 border-t border-white/5">
        <div className="max-w-4xl mx-auto">
          <ScrollReveal>
            <h2 className="text-2xl font-bold text-white mb-3">Still stuck?</h2>
            <p className="text-slate-400 leading-relaxed mb-5 max-w-2xl">
              If the check above reports a problem, or your issue is not one of the three, get in
              touch and include what this page showed you and the time it showed it.
            </p>
            <Link
              href="/contact"
              className="inline-flex items-center gap-2 bg-white/5 hover:bg-white/10 border border-white/10 text-white font-medium px-5 py-3 rounded-xl transition-colors"
            >
              Contact support
            </Link>
          </ScrollReveal>
        </div>
      </section>
    </>
  )
}
