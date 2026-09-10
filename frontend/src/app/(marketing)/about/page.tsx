import type { Metadata } from 'next'
import Link from 'next/link'
import { ShieldCheck, Gauge, KeyRound, Layers } from 'lucide-react'
import ScrollReveal from '@/components/marketing/ScrollReveal'
import CTABanner from '@/components/marketing/CTABanner'

export const metadata: Metadata = {
  title: 'About',
  description:
    'Why NeuraLeads exists: outbound tooling that sources its own leads, protects sending reputation by default, and charges a flat fee instead of per seat.',
  alternates: { canonical: '/about' },
}

const principles = [
  {
    icon: ShieldCheck,
    title: 'Safety is not a setting',
    body: 'Every outbound email passes the same ten checks, on every send path, whether or not anyone remembered to turn something on. Suppression, validation and cooldowns are not features you opt into — they are the floor.',
  },
  {
    icon: KeyRound,
    title: 'Your providers, your keys, your data',
    body: 'You connect your own lead, enrichment, validation and AI accounts. You pay those vendors at their rates, keep the relationship, and can switch whenever you like. We are not a reseller with a margin hidden in the middle.',
  },
  {
    icon: Gauge,
    title: 'Flat fees, not per seat',
    body: 'Charging per seat punishes teams for collaborating and pushes people into sharing logins. One workspace, one price, everyone in.',
  },
  {
    icon: Layers,
    title: 'Signals, not lists',
    body: 'A purchased list is stale the day you buy it. The platform reads live buying signals — job postings, hiring activity, funding, technology changes — so the reason to reach out is the reason the message lands.',
  },
]

export default function AboutPage() {
  return (
    <>
      <section className="pt-32 pb-16 px-6">
        <div className="max-w-4xl mx-auto">
          <ScrollReveal>
            <p className="text-xs font-mono uppercase tracking-[0.14em] text-slate-500 mb-4">
              About NeuraLeads
            </p>
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-6 leading-tight">
              Outbound tooling that respects the inbox it is sending to
            </h1>
            <p className="text-lg text-slate-400 leading-relaxed mb-5">
              Most outbound tools are a mail merge with a dashboard bolted on. They will happily
              help you burn a domain in a fortnight: no validation gate, no cooldown between
              touches, no cap on how many people at one company hear from you in a week.
            </p>
            <p className="text-lg text-slate-400 leading-relaxed">
              NeuraLeads was built the other way round. The safety mechanism came first, the
              sourcing pipeline that feeds it came second, and the campaign builder came last —
              because a campaign is only worth building once you can trust what it sends.
            </p>
          </ScrollReveal>
        </div>
      </section>

      <section className="py-16 px-6 border-t border-white/5">
        <div className="max-w-5xl mx-auto">
          <ScrollReveal>
            <h2 className="text-2xl md:text-3xl font-bold text-white mb-3">What we believe</h2>
            <p className="text-slate-400 mb-10 max-w-2xl">
              Four convictions shaped the product, and you can see each of them in how it behaves.
            </p>
          </ScrollReveal>
          <div className="grid md:grid-cols-2 gap-5">
            {principles.map((p, i) => {
              const Icon = p.icon
              return (
                <ScrollReveal key={p.title} delay={i * 0.08}>
                  <div className="h-full rounded-2xl border border-white/10 bg-white/[0.03] p-6">
                    <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-500 to-indigo-500 flex items-center justify-center mb-4">
                      <Icon className="w-5 h-5 text-white" aria-hidden="true" />
                    </div>
                    <h3 className="text-white font-semibold text-lg mb-2">{p.title}</h3>
                    <p className="text-slate-400 text-sm leading-relaxed">{p.body}</p>
                  </div>
                </ScrollReveal>
              )
            })}
          </div>
        </div>
      </section>

      <section className="py-16 px-6 border-t border-white/5">
        <div className="max-w-4xl mx-auto">
          <ScrollReveal>
            <h2 className="text-2xl md:text-3xl font-bold text-white mb-6">Who we build for</h2>
            <p className="text-slate-400 leading-relaxed mb-4">
              Staffing and recruiting firms who need to reach a hiring manager before the
              requisition goes to a competitor. Service businesses — revenue-cycle management,
              software development, AI services, digital marketing — each with their own buying
              signals and their own way of opening a conversation. Agencies running several brands
              from isolated workspaces.
            </p>
            <p className="text-slate-400 leading-relaxed">
              What they have in common is that outbound is a real channel for them, not an
              experiment, and the cost of a burned domain is measured in quarters.
            </p>
          </ScrollReveal>
        </div>
      </section>

      <section className="py-16 px-6 border-t border-white/5">
        <div className="max-w-4xl mx-auto">
          <ScrollReveal>
            <h2 className="text-2xl md:text-3xl font-bold text-white mb-6">
              How the product works, in full
            </h2>
            <p className="text-slate-400 leading-relaxed mb-6">
              We publish the whole thing rather than a feature list: every screen, the ten checks
              that run before a send, what the AI is and is not allowed to do, the defaults and why
              they are set where they are.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/documentation"
                className="inline-flex items-center gap-2 bg-white/5 hover:bg-white/10 border border-white/10 text-white font-medium px-5 py-3 rounded-xl transition-colors"
              >
                Read the handbook
              </Link>
              <Link
                href="/pricing"
                className="inline-flex items-center gap-2 bg-white/5 hover:bg-white/10 border border-white/10 text-white font-medium px-5 py-3 rounded-xl transition-colors"
              >
                See pricing
              </Link>
              <Link
                href="/contact"
                className="inline-flex items-center gap-2 bg-white/5 hover:bg-white/10 border border-white/10 text-white font-medium px-5 py-3 rounded-xl transition-colors"
              >
                Talk to us
              </Link>
            </div>
          </ScrollReveal>
        </div>
      </section>

      <CTABanner
        headline="See it on your own pipeline"
        subtext="Start a 14-day trial. Mock mode lets you learn the product without spending provider credits."
        ctaText="Start free trial"
      />
    </>
  )
}
