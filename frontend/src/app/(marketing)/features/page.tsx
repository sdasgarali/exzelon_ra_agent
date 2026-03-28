import type { Metadata } from 'next'
import { Search, Mail, Inbox, Shield, Briefcase, BarChart3, Zap, Brain, Globe, Users } from 'lucide-react'
import { Check } from 'lucide-react'
import ScrollReveal from '@/components/marketing/ScrollReveal'
import CTABanner from '@/components/marketing/CTABanner'

export const metadata: Metadata = {
  title: 'Features',
  description: 'Explore all features: 10 lead sources, 7 contact providers, multi-step campaigns, AI content generation, unified inbox, CRM deals, warmup engine, and analytics.',
  openGraph: {
    title: 'Features — NeuraLeads',
    description: 'Complete outreach platform features. Lead sourcing, campaigns, inbox, CRM, warmup, analytics.',
  },
}

interface FeatureSection {
  icon: typeof Search
  title: string
  description: string
  bullets: string[]
  color: string
}

const featureSections: FeatureSection[] = [
  {
    icon: Search,
    title: 'Lead Sourcing Pipeline',
    description: 'Aggregate leads from 10 job board APIs with intelligent deduplication and scheduling.',
    bullets: [
      'Apollo, JSearch, TheirStack, SerpAPI, Adzuna, SearchAPI, USAJobs, Jooble, JobDataFeeds, Coresignal',
      '3-layer deduplication: external job ID, employer LinkedIn, company+title+location',
      'Sub-source tracking (LinkedIn, Indeed, Glassdoor) for each lead',
      'Scheduled runs 3x daily via APScheduler',
      'AI-powered ICP matching and lead scoring',
    ],
    color: 'from-blue-500 to-cyan-400',
  },
  {
    icon: Users,
    title: 'Contact Discovery',
    description: '7 contact discovery providers to find decision-makers with verified email addresses.',
    bullets: [
      'Apollo, Seamless AI, Hunter.io, Snov.io, RocketReach, People Data Labs, Proxycurl',
      'Priority-based contact ranking (P1 job poster through P5 functional manager)',
      'Automatic email discovery and phone number enrichment',
      'Company enrichment via Clearbit and OpenCorporates',
      'Max 4 contacts per company per job to avoid over-targeting',
    ],
    color: 'from-violet-500 to-purple-400',
  },
  {
    icon: Shield,
    title: 'Email Validation Engine',
    description: '7 validation providers ensure every email is verified before outreach begins.',
    bullets: [
      'NeverBounce, ZeroBounce, Hunter, Clearout, Emailable, MailboxValidator, Reacher',
      'Only contacts with "Valid" status receive outreach',
      'Catch-all detection and disposable email filtering',
      'Bulk validation across your entire contact database',
      'Provider failover for maximum validation coverage',
    ],
    color: 'from-emerald-500 to-green-400',
  },
  {
    icon: Mail,
    title: 'Campaign Engine',
    description: 'Multi-step email sequences with A/B testing, branching logic, and timezone-aware delivery.',
    bullets: [
      'Email, wait, and condition (if/then) branching steps',
      'A/B testing with chi-squared auto-optimization',
      'Spintax text variation with nested pattern support',
      'Round-robin mailbox selection with health scoring',
      'Timezone-aware send windows using contact US state',
    ],
    color: 'from-pink-500 to-rose-400',
  },
  {
    icon: Zap,
    title: 'Warmup Engine',
    description: 'Peer-to-peer domain warmup with DNS health monitoring and blacklist detection.',
    bullets: [
      'Peer-to-peer warmup emails between your mailboxes',
      'AI-generated warmup replies via Groq',
      'SPF, DKIM, DMARC verification checks',
      'IP and domain blacklist monitoring',
      '3 warmup profiles: Conservative (45d), Standard (30d), Aggressive (20d)',
    ],
    color: 'from-amber-500 to-yellow-400',
  },
  {
    icon: Inbox,
    title: 'Unified Inbox',
    description: 'Centralized reply management with AI sentiment analysis and smart categorization.',
    bullets: [
      'Thread grouping via Message-ID chain or email+subject hash',
      'AI sentiment analysis (rule-based + LLM fallback)',
      'AI reply suggestions from conversation context',
      '6 category labels: interested, not interested, OOO, question, referral, do not contact',
      'Automatic CRM forwarding for interested replies',
    ],
    color: 'from-indigo-500 to-blue-400',
  },
  {
    icon: Brain,
    title: 'AI Content Generation',
    description: '4 AI engines for email generation, sequence building, and content optimization.',
    bullets: [
      'Groq, OpenAI, Anthropic Claude, Google Gemini',
      'AI sequence generation with template fallback',
      'Spam score checking (100+ trigger words, score 0-100)',
      'Natural language lead search (NLP query → SQL filter)',
      'AI-generated ICP profiles with rule-based fallback',
    ],
    color: 'from-teal-500 to-cyan-400',
  },
  {
    icon: Briefcase,
    title: 'CRM Deal Pipeline',
    description: 'Kanban-style deal tracking with HubSpot and Salesforce bidirectional sync.',
    bullets: [
      '7 default stages: New Lead → Contacted → Qualified → Proposal → Negotiation → Won/Lost',
      'Deal stats: win rate, average deal size, pipeline value',
      'Activity timeline and task management per deal',
      'Bidirectional HubSpot and Salesforce sync',
      'Auto-forward interested replies to CRM',
    ],
    color: 'from-rose-500 to-pink-400',
  },
  {
    icon: BarChart3,
    title: 'Analytics & Reporting',
    description: 'Comprehensive analytics from email metrics to revenue tracking and team performance.',
    bullets: [
      'Campaign comparison charts and performance metrics',
      'Team leaderboard with individual SDR stats',
      'Revenue metrics with cost tracking and ROI analytics',
      'Custom tracking domains for improved deliverability',
      'Automation event log for full system transparency',
    ],
    color: 'from-orange-500 to-amber-400',
  },
  {
    icon: Globe,
    title: 'Integrations & Webhooks',
    description: 'Connect to your existing stack with webhooks, API keys, and native integrations.',
    bullets: [
      'HMAC-SHA256 signed webhook payloads for 8 event types',
      'API key authentication with scopes and expiry',
      'Slack and Microsoft Teams notifications',
      'Zapier-compatible webhook events',
      'Custom tracking domains with CNAME verification',
    ],
    color: 'from-sky-500 to-blue-400',
  },
]

export default function FeaturesPage() {
  return (
    <>
      {/* Hero */}
      <section className="pt-32 pb-16 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <ScrollReveal>
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-4">
              Every Feature You Need
            </h1>
            <p className="text-lg text-slate-400 max-w-2xl mx-auto">
              From lead sourcing to closed deals — a complete outreach automation platform
              with 10 lead sources, 7 contact providers, and 4 AI engines.
            </p>
          </ScrollReveal>
        </div>
      </section>

      {/* Feature sections */}
      <section className="px-6 pb-20">
        <div className="max-w-6xl mx-auto space-y-24">
          {featureSections.map((section, i) => {
            const isReversed = i % 2 === 1
            const Icon = section.icon

            return (
              <div
                key={section.title}
                className={`flex flex-col ${isReversed ? 'lg:flex-row-reverse' : 'lg:flex-row'} items-start gap-12`}
              >
                {/* Icon card */}
                <ScrollReveal direction={isReversed ? 'right' : 'left'} className="flex-shrink-0">
                  <div className={`w-16 h-16 rounded-2xl bg-gradient-to-br ${section.color} flex items-center justify-center`}>
                    <Icon className="w-8 h-8 text-white" />
                  </div>
                </ScrollReveal>

                {/* Content */}
                <ScrollReveal direction={isReversed ? 'left' : 'right'} className="flex-1">
                  <h2 className="text-2xl md:text-3xl font-bold text-white mb-3">{section.title}</h2>
                  <p className="text-slate-400 leading-relaxed mb-6">{section.description}</p>
                  <ul className="space-y-3">
                    {section.bullets.map((bullet) => (
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

      <CTABanner
        headline="See It In Action"
        subtext="Start your 14-day free trial. No credit card required."
        ctaText="Start Free Trial"
      />
    </>
  )
}
