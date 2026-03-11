'use client'

import { Check } from 'lucide-react'
import ScrollReveal from './ScrollReveal'

interface ShowcaseItem {
  title: string
  description: string
  bullets: string[]
  gradient: string
  mockLabel: string
}

const showcases: ShowcaseItem[] = [
  {
    title: 'Automated Lead Sourcing Pipeline',
    description: 'Pull from 10 job source APIs simultaneously. Our 3-layer deduplication eliminates duplicates while AI scoring prioritizes the highest-value leads.',
    bullets: [
      'Apollo, JSearch, TheirStack, SerpAPI, Adzuna + 5 more',
      '3-layer deduplication: job ID, LinkedIn URL, company+title',
      'AI-powered lead scoring and ICP matching',
      'Schedule runs 3x daily — wake up to fresh leads',
    ],
    gradient: 'from-blue-500/20 to-cyan-500/20',
    mockLabel: 'Lead Sourcing Pipeline',
  },
  {
    title: 'Intelligent Campaign Engine',
    description: 'Build multi-step email sequences with A/B testing, spintax variation, and timezone-aware delivery that maximizes open rates.',
    bullets: [
      'Multi-step sequences with wait & condition branching',
      'A/B testing with chi-squared auto-optimization',
      'Spintax text variation with nested pattern support',
      'Round-robin mailbox selection and health-aware sending',
    ],
    gradient: 'from-violet-500/20 to-purple-500/20',
    mockLabel: 'Campaign Builder',
  },
  {
    title: 'Full-Stack Analytics Dashboard',
    description: 'Track every metric from email opens to revenue. Campaign comparisons, team leaderboards, and cost tracking give you complete visibility.',
    bullets: [
      'Real-time email open, click, reply, and bounce tracking',
      'Campaign comparison charts and team leaderboards',
      'Revenue metrics with ROI analytics',
      'Custom tracking domains for improved deliverability',
    ],
    gradient: 'from-emerald-500/20 to-green-500/20',
    mockLabel: 'Analytics Dashboard',
  },
]

export default function FeatureShowcase() {
  return (
    <section className="py-20 px-6">
      <div className="max-w-7xl mx-auto space-y-32">
        {showcases.map((item, i) => {
          const isReversed = i % 2 === 1

          return (
            <div
              key={item.title}
              className={`flex flex-col ${isReversed ? 'lg:flex-row-reverse' : 'lg:flex-row'} items-center gap-12 lg:gap-16`}
            >
              {/* Mock screenshot */}
              <ScrollReveal direction={isReversed ? 'right' : 'left'} className="flex-1 w-full">
                <div className={`relative rounded-2xl bg-gradient-to-br ${item.gradient} p-1`}>
                  <div className="bg-navy-800 rounded-xl overflow-hidden">
                    <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5">
                      <div className="flex gap-1.5">
                        <div className="w-3 h-3 rounded-full bg-red-500/60" />
                        <div className="w-3 h-3 rounded-full bg-yellow-500/60" />
                        <div className="w-3 h-3 rounded-full bg-green-500/60" />
                      </div>
                      <span className="text-xs text-slate-500 ml-2">{item.mockLabel}</span>
                    </div>
                    <div className="aspect-video bg-gradient-to-br from-navy-700 to-navy-800 flex items-center justify-center p-8">
                      {/* Stylized mock UI */}
                      <div className="w-full space-y-3">
                        <div className="h-3 bg-white/5 rounded-full w-3/4" />
                        <div className="h-3 bg-white/5 rounded-full w-1/2" />
                        <div className="grid grid-cols-3 gap-3 mt-6">
                          <div className="h-20 bg-white/5 rounded-lg" />
                          <div className="h-20 bg-primary-500/10 border border-primary-500/20 rounded-lg" />
                          <div className="h-20 bg-white/5 rounded-lg" />
                        </div>
                        <div className="h-24 bg-white/3 rounded-lg mt-3" />
                      </div>
                    </div>
                  </div>
                </div>
              </ScrollReveal>

              {/* Text content */}
              <ScrollReveal direction={isReversed ? 'left' : 'right'} className="flex-1">
                <h3 className="text-2xl md:text-3xl font-bold text-white mb-4">{item.title}</h3>
                <p className="text-slate-400 leading-relaxed mb-6">{item.description}</p>
                <ul className="space-y-3">
                  {item.bullets.map((bullet) => (
                    <li key={bullet} className="flex items-start gap-3">
                      <div className="w-5 h-5 rounded-full bg-primary-500/20 flex items-center justify-center mt-0.5 flex-shrink-0">
                        <Check className="w-3 h-3 text-primary-400" />
                      </div>
                      <span className="text-slate-300 text-sm">{bullet}</span>
                    </li>
                  ))}
                </ul>
              </ScrollReveal>
            </div>
          )
        })}
      </div>
    </section>
  )
}
