import type { Metadata } from 'next'
import ComparisonTable from '@/components/marketing/ComparisonTable'
import CTABanner from '@/components/marketing/CTABanner'
import ScrollReveal from '@/components/marketing/ScrollReveal'

export const metadata: Metadata = {
  title: 'Compare',
  description: 'Side-by-side comparison of NeuraMail vs leading cold email platforms. See scores across 8 categories and 50+ features.',
  openGraph: {
    title: 'NeuraMail vs Leading Outreach Platforms',
    description: 'Feature-by-feature comparison. NeuraMail scores 135/150 vs top competitors.',
  },
}

export default function ComparePage() {
  return (
    <>
      {/* Hero */}
      <section className="pt-32 pb-16 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <ScrollReveal>
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-4">
              NeuraMail vs. The Competition
            </h1>
            <p className="text-lg text-slate-400 max-w-2xl mx-auto">
              See how we compare against the top outreach platforms
              across every major feature category. Click each row to expand details.
            </p>
          </ScrollReveal>
        </div>
      </section>

      {/* Full comparison */}
      <section className="px-6 pb-20">
        <ComparisonTable />
      </section>

      {/* Why switch section */}
      <section className="py-20 px-6 border-t border-white/5">
        <div className="max-w-4xl mx-auto">
          <ScrollReveal>
            <h2 className="text-3xl font-bold text-white text-center mb-12">
              Why Teams Switch to NeuraMail
            </h2>
          </ScrollReveal>

          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                title: '70-90% Cost Savings',
                description: 'No per-seat fees. Flat monthly pricing starts at $49/mo for your entire team — vs $141-652/mo for per-seat competitors.',
              },
              {
                title: 'Self-Hosted Control',
                description: 'Deploy on your own infrastructure. Full data ownership, compliance with your security policies, and zero vendor lock-in.',
              },
              {
                title: 'More Providers, More Reach',
                description: '10 lead sources, 7 contact providers, 7 validation engines, and 4 AI models. No other platform offers this breadth.',
              },
            ].map((item, i) => (
              <ScrollReveal key={item.title} delay={i * 0.1}>
                <div className="marketing-card-glow rounded-2xl p-6 h-full">
                  <h3 className="text-lg font-semibold text-white mb-2">{item.title}</h3>
                  <p className="text-slate-400 text-sm leading-relaxed">{item.description}</p>
                </div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      <CTABanner
        headline="Ready to Make the Switch?"
        subtext="14-day free trial. No credit card required. Migrate from your current tool in minutes."
        ctaText="Start Free Trial"
      />
    </>
  )
}
