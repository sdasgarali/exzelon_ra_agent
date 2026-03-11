import type { Metadata } from 'next'
import Link from 'next/link'
import Hero from '@/components/marketing/Hero'
import FeatureGrid from '@/components/marketing/FeatureGrid'
import FeatureShowcase from '@/components/marketing/FeatureShowcase'
import ComparisonTable from '@/components/marketing/ComparisonTable'
import ROICalculator from '@/components/marketing/ROICalculator'
import CTABanner from '@/components/marketing/CTABanner'
import ScrollReveal from '@/components/marketing/ScrollReveal'

export const metadata: Metadata = {
  title: 'NeuraMail — AI-Powered Sales Outreach Platform',
  description: 'AI-powered outreach automation with 10 lead sources, 7 contact providers, and 4 AI engines. Full pipeline from lead sourcing to closed deals at 70% less cost than competitors.',
  openGraph: {
    title: 'NeuraMail — AI-Powered Sales Outreach Platform',
    description: 'Full-pipeline outreach automation. 10 lead sources. 7 contact providers. 4 AI engines. 70% less cost.',
  },
}

/* ── Integration logo bar ── */
const integrations = [
  'Apollo', 'HubSpot', 'Salesforce', 'Slack', 'Teams', 'Gmail', 'Outlook', 'Zapier',
  'Hunter.io', 'Snov.io', 'RocketReach', 'NeverBounce', 'ZeroBounce',
]

function LogoBar() {
  return (
    <section className="py-12 border-y border-white/5 overflow-hidden">
      <p className="text-center text-slate-500 text-sm font-medium tracking-wider uppercase mb-8">
        Integrates with your favorite tools
      </p>
      <div className="relative">
        <div className="flex animate-marquee gap-12 whitespace-nowrap">
          {[...integrations, ...integrations].map((name, i) => (
            <span
              key={i}
              className="text-slate-500 font-semibold text-lg opacity-50 hover:opacity-80 transition-opacity"
            >
              {name}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Testimonial cards ── */
const testimonials = [
  {
    quote: 'We replaced two separate outreach tools with NeuraMail. The self-hosted option alone saves us thousands per year, and the lead sourcing pipeline is unmatched.',
    name: 'Sarah Chen',
    title: 'VP of Sales, TechCorp',
    rating: 5,
  },
  {
    quote: 'The AI-powered inbox categorization changed our workflow. Our SDR team responds to interested leads 3x faster now.',
    name: 'Marcus Johnson',
    title: 'Head of Growth, ScaleUp Inc',
    rating: 5,
  },
  {
    quote: 'Having 10 lead source APIs and 7 validation providers in one platform eliminated 4 separate tools from our stack.',
    name: 'Emily Rodriguez',
    title: 'Director of Operations, DataFlow',
    rating: 5,
  },
]

function Testimonials() {
  return (
    <section className="py-20 px-6">
      <div className="max-w-7xl mx-auto">
        <ScrollReveal>
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-4">
            Trusted by Sales Teams
          </h2>
          <p className="text-slate-400 text-center mb-12 max-w-xl mx-auto">
            See why teams are switching from legacy outreach tools.
          </p>
        </ScrollReveal>
        <div className="grid md:grid-cols-3 gap-6">
          {testimonials.map((t, i) => (
            <ScrollReveal key={i} delay={i * 0.1}>
              <div className="marketing-card-glow rounded-2xl p-6 h-full flex flex-col">
                <div className="flex gap-1 mb-4">
                  {Array.from({ length: t.rating }).map((_, j) => (
                    <svg key={j} className="w-4 h-4 text-yellow-400 fill-current" viewBox="0 0 20 20">
                      <path d="M10 15l-5.878 3.09 1.123-6.545L.489 6.91l6.572-.955L10 0l2.939 5.955 6.572.955-4.756 4.635 1.123 6.545z" />
                    </svg>
                  ))}
                </div>
                <p className="text-slate-300 text-sm leading-relaxed flex-1 mb-4">&ldquo;{t.quote}&rdquo;</p>
                <div>
                  <div className="text-white font-medium text-sm">{t.name}</div>
                  <div className="text-slate-500 text-xs">{t.title}</div>
                </div>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Comparison snapshot ── */
function ComparisonSnapshot() {
  return (
    <section className="py-20 px-6">
      <div className="max-w-7xl mx-auto">
        <ScrollReveal>
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
              How NeuraMail Stacks Up
            </h2>
            <p className="text-slate-400 text-lg">
              Side-by-side with the top outreach platforms.
            </p>
          </div>
        </ScrollReveal>
        <ComparisonTable compact />
        <ScrollReveal>
          <div className="text-center mt-10">
            <Link
              href="/compare"
              className="text-primary-400 hover:text-primary-300 font-medium text-sm transition-colors"
            >
              See full comparison &rarr;
            </Link>
          </div>
        </ScrollReveal>
      </div>
    </section>
  )
}

/* ── Landing page ── */
export default function LandingPage() {
  return (
    <>
      <Hero />
      <LogoBar />
      <FeatureGrid />
      <FeatureShowcase />
      <ComparisonSnapshot />
      <ROICalculator />
      <Testimonials />
      <CTABanner />
    </>
  )
}
