'use client'

import { Search, Mail, Inbox, Shield, BarChart3, Briefcase } from 'lucide-react'
import ScrollReveal from './ScrollReveal'

const features = [
  {
    icon: Search,
    title: 'Lead Intelligence',
    description: '10 job source APIs with AI-powered search and 3-layer deduplication. Source thousands of leads daily.',
    color: 'from-blue-500 to-cyan-400',
  },
  {
    icon: Mail,
    title: 'Multi-Step Campaigns',
    description: 'A/B testing, spintax variation, timezone-aware sending, and automated follow-ups across sequences.',
    color: 'from-violet-500 to-purple-400',
  },
  {
    icon: Inbox,
    title: 'Unified Inbox',
    description: 'Thread view with AI sentiment analysis, smart reply suggestions, and automatic categorization.',
    color: 'from-pink-500 to-rose-400',
  },
  {
    icon: Shield,
    title: 'Warmup Engine',
    description: 'Peer-to-peer warmup, DNS health checks, SPF/DKIM/DMARC verification, and blacklist monitoring.',
    color: 'from-emerald-500 to-green-400',
  },
  {
    icon: Briefcase,
    title: 'CRM Deal Pipeline',
    description: 'Kanban board with 7-stage pipeline, deal forecasting, and bidirectional HubSpot/Salesforce sync.',
    color: 'from-amber-500 to-yellow-400',
  },
  {
    icon: BarChart3,
    title: 'Analytics & Reporting',
    description: 'Team leaderboard, campaign comparison, revenue metrics, cost tracking, and ROI analytics.',
    color: 'from-indigo-500 to-blue-400',
  },
]

export default function FeatureGrid() {
  return (
    <section className="py-20 px-6">
      <div className="max-w-7xl mx-auto">
        <ScrollReveal>
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
              Everything You Need to Close More Deals
            </h2>
            <p className="text-slate-400 text-lg max-w-2xl mx-auto">
              A complete outreach automation platform — from finding leads to closing deals.
            </p>
          </div>
        </ScrollReveal>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature, i) => (
            <ScrollReveal key={feature.title} delay={i * 0.08}>
              <div className="marketing-card-glow rounded-2xl p-6 h-full transition-all duration-300 hover:-translate-y-1">
                <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${feature.color} flex items-center justify-center mb-4`}>
                  <feature.icon className="w-6 h-6 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">{feature.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{feature.description}</p>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  )
}
