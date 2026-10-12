import type { Metadata } from 'next'
import Link from 'next/link'
import { LifeBuoy, Briefcase, ShieldAlert, Scale, Mail } from 'lucide-react'
import ScrollReveal from '@/components/marketing/ScrollReveal'
import { fetchSiteInfo, SITE_INFO_FALLBACK, type SiteInfo } from '@/lib/site-info'

export const metadata: Metadata = {
  title: 'Contact',
  description:
    'How to reach NeuraLeads — sales enquiries, product support, data and privacy requests, and security disclosure.',
  alternates: { canonical: '/contact' },
}

/** Site details from the API; the published fallback keeps the page useful if it is down. */
async function loadSiteInfo(): Promise<SiteInfo> {
  try {
    return await fetchSiteInfo()
  } catch {
    return SITE_INFO_FALLBACK
  }
}

function mailto(address: string, subject: string): string {
  return `mailto:${address}?subject=${encodeURIComponent(subject)}`
}

function EmailLink({ address, subject }: { address: string; subject: string }) {
  return (
    <a
      href={mailto(address, subject)}
      className="inline-flex items-center gap-1.5 font-mono text-[12.5px] tracking-tight px-2.5 py-1 rounded border border-white/15 bg-white/[0.05] text-slate-200 hover:text-white hover:border-white/30 transition-colors"
    >
      <Mail className="w-3.5 h-3.5" aria-hidden="true" />
      {address}
    </a>
  )
}

const TOPIC_SUBJECTS: Record<string, string> = {
  'custom-plan': 'Custom plan enquiry',
}

export default async function ContactPage({
  searchParams,
}: {
  searchParams?: { topic?: string | string[] }
}) {
  const info = await loadSiteInfo()
  const supportEmail = info.support_email || SITE_INFO_FALLBACK.support_email
  const privacyEmail = info.privacy_email || supportEmail
  const topic = typeof searchParams?.topic === 'string' ? searchParams.topic : ''
  const ctaSubject = TOPIC_SUBJECTS[topic] || 'Question about NeuraLeads'

  const routes = [
    {
      icon: Briefcase,
      title: 'Sales and plans',
      body: 'Questions about which plan fits, migrating from another tool, volume beyond the published limits, or a custom plan.',
      action: { label: 'Compare plans', href: '/pricing' },
      email: supportEmail,
      subject: 'Sales enquiry',
    },
    {
      icon: LifeBuoy,
      title: 'Product support',
      body: 'Something not behaving as documented, a provider that will not connect, or a mailbox that will not send. Tell us your workspace name and what you expected to happen.',
      action: { label: 'Check the handbook first', href: '/documentation' },
      email: supportEmail,
      subject: 'Support request',
    },
    {
      icon: Scale,
      title: 'Data and privacy requests',
      body: 'Access, correction or erasure requests, sub-processor lists, and data processing agreements. If you received an email sent through the platform, the privacy policy explains exactly who is responsible and how to stop it.',
      action: { label: 'Read the privacy policy', href: '/privacy#recipients' },
      email: privacyEmail,
      subject: 'Privacy request',
    },
    {
      icon: ShieldAlert,
      title: 'Security disclosure',
      body: 'Report a suspected vulnerability. Please give us a reasonable window to investigate and fix before disclosing publicly, and do not access or modify data that is not yours while testing.',
      action: null,
      email: supportEmail,
      subject: 'Security disclosure',
    },
  ]

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
            <p className="text-lg text-slate-400 leading-relaxed max-w-2xl mb-8">
              Four different things get routed four different ways. Pick the one that matches what
              you need — it gets to someone who can actually act on it faster.
            </p>
            <div className="flex flex-wrap items-center gap-4">
              <a
                href={mailto(supportEmail, ctaSubject)}
                className="inline-flex items-center gap-2 bg-white hover:bg-white/90 text-brand-700 font-semibold text-sm px-5 py-2.5 rounded-lg transition-colors"
              >
                <Mail className="w-4 h-4" aria-hidden="true" />
                Email us
              </a>
              <span className="text-sm text-slate-400">
                or write to{' '}
                <a href={`mailto:${supportEmail}`} className="text-primary-400 hover:text-primary-300">
                  {supportEmail}
                </a>
              </span>
            </div>
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
                    <EmailLink address={r.email} subject={r.subject} />
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
