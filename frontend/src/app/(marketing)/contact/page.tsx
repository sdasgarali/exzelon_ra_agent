import type { Metadata } from 'next'
import Link from 'next/link'
import { LifeBuoy, Briefcase, ShieldAlert, Scale } from 'lucide-react'
import ScrollReveal from '@/components/marketing/ScrollReveal'

export const metadata: Metadata = {
  title: 'Contact',
  description:
    'How to reach NeuraLeads — sales enquiries, product support, data and privacy requests, and security disclosure.',
  alternates: { canonical: '/contact' },
}

/** A contact address that has not been configured yet. Shown rather than invented:
 *  an address that does not receive mail is worse than an honest gap. */
function PendingAddress({ label }: { label: string }) {
  return (
    <span className="inline-block font-mono text-[11.5px] tracking-tight px-2 py-0.5 rounded border border-dashed border-amber-400/70 bg-amber-400/10 text-amber-300">
      {label} — to be published
    </span>
  )
}

const routes = [
  {
    icon: Briefcase,
    title: 'Sales and plans',
    body: 'Questions about which plan fits, migrating from another tool, volume beyond the Enterprise limits, or self-hosting.',
    action: { label: 'Compare plans', href: '/pricing' },
    pending: 'Sales address',
  },
  {
    icon: LifeBuoy,
    title: 'Product support',
    body: 'Something not behaving as documented, a provider that will not connect, or a mailbox that will not send. Support level follows your plan: email on Starter, email and chat on Professional, a dedicated manager on Enterprise.',
    action: { label: 'Check the handbook first', href: '/documentation' },
    pending: 'Support address',
  },
  {
    icon: Scale,
    title: 'Data and privacy requests',
    body: 'Access, correction or erasure requests, sub-processor lists, and data processing agreements. If you received an email sent through the platform, the privacy policy explains exactly who is responsible and how to stop it.',
    action: { label: 'Read the privacy policy', href: '/privacy#recipients' },
    pending: 'Privacy address',
  },
  {
    icon: ShieldAlert,
    title: 'Security disclosure',
    body: 'Report a suspected vulnerability. Please give us a reasonable window to investigate and fix before disclosing publicly, and do not access or modify data that is not yours while testing.',
    action: null,
    pending: 'Security address',
  },
]

export default function ContactPage() {
  return (
    <>
      <section className="pt-32 pb-12 px-6">
        <div className="max-w-4xl mx-auto">
          <ScrollReveal>
            <p className="text-xs font-mono uppercase tracking-[0.14em] text-slate-500 mb-4">
              Contact
            </p>
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-6 leading-tight">
              Reach the right person the first time
            </h1>
            <p className="text-lg text-slate-400 leading-relaxed max-w-2xl">
              Four different things get routed four different ways. Pick the one that matches what
              you need — it gets to someone who can actually act on it faster.
            </p>
          </ScrollReveal>
        </div>
      </section>

      <section className="pb-16 px-6">
        <div className="max-w-5xl mx-auto grid md:grid-cols-2 gap-5">
          {routes.map((r, i) => {
            const Icon = r.icon
            return (
              <ScrollReveal key={r.title} delay={i * 0.08}>
                <div className="h-full rounded-2xl border border-white/10 bg-white/[0.03] p-6 flex flex-col">
                  <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-500 to-indigo-500 flex items-center justify-center mb-4">
                    <Icon className="w-5 h-5 text-white" aria-hidden="true" />
                  </div>
                  <h2 className="text-white font-semibold text-lg mb-2">{r.title}</h2>
                  <p className="text-slate-400 text-sm leading-relaxed mb-5 flex-1">{r.body}</p>
                  <div className="flex flex-wrap items-center gap-3">
                    <PendingAddress label={r.pending} />
                    {r.action ? (
                      <Link
                        href={r.action.href}
                        className="text-sm font-medium text-primary-400 hover:text-primary-300 transition-colors"
                      >
                        {r.action.label} →
                      </Link>
                    ) : null}
                  </div>
                </div>
              </ScrollReveal>
            )
          })}
        </div>
      </section>

      <section className="py-14 px-6 border-t border-white/5">
        <div className="max-w-4xl mx-auto">
          <ScrollReveal>
            <h2 className="text-2xl font-bold text-white mb-4">Answers you can get right now</h2>
            <p className="text-slate-400 leading-relaxed mb-6 max-w-2xl">
              Most questions we receive are already answered in writing, and reading takes less time
              than waiting for a reply.
            </p>
            <div className="grid sm:grid-cols-3 gap-4">
              <Link
                href="/documentation"
                className="rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] p-5 transition-colors"
              >
                <span className="block text-white font-semibold mb-1">Product handbook</span>
                <span className="block text-slate-500 text-sm">
                  Every screen, rule and default, in full.
                </span>
              </Link>
              <Link
                href="/pricing"
                className="rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] p-5 transition-colors"
              >
                <span className="block text-white font-semibold mb-1">Pricing and limits</span>
                <span className="block text-slate-500 text-sm">
                  What each plan includes, with the FAQ.
                </span>
              </Link>
              <Link
                href="/status"
                className="rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] p-5 transition-colors"
              >
                <span className="block text-white font-semibold mb-1">Service status</span>
                <span className="block text-slate-500 text-sm">
                  Check whether the platform is reachable.
                </span>
              </Link>
            </div>
          </ScrollReveal>
        </div>
      </section>
    </>
  )
}
