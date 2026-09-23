'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Check, X, Star } from 'lucide-react'
import { motion } from 'framer-motion'
import ScrollReveal from './ScrollReveal'

/**
 * Public pricing.
 *
 * Every number here mirrors `backend/app/core/plans.py::PLAN_MATRIX`. If the two
 * disagree, this page is lying to customers — a limit shown here that the API does not
 * grant becomes a support ticket, and one the API grants but this hides is revenue left
 * on the table. `backend/tests/unit/test_pricing_page_parity.py` fails the build when
 * they drift.
 *
 * Two meters are advertised separately because they are separate budgets: credits buy
 * data and AI, sends are their own monthly allowance. A prospect who reads "6,000
 * credits" as "6,000 emails" has been misled.
 */

type Value = string | boolean

interface PlanFeature {
  label: string
  free: Value
  pro: Value
  max: Value
  custom: Value
}

// ── The meters and caps, straight from PLAN_MATRIX ──────────────────────────
const limits: PlanFeature[] = [
  { label: 'Credits / month', free: '300', pro: '6,000', max: '25,000', custom: 'From 25,000' },
  { label: 'Emails / month', free: '500', pro: '25,000', max: '150,000', custom: 'From 150,000' },
  { label: 'Mailboxes', free: '1', pro: '25', max: '1,000', custom: 'From 1,000' },
  { label: 'Active campaigns', free: '2', pro: '25', max: '100', custom: 'From 100' },
]

// ── Features, mirroring BASE / PRO / MAX feature sets ───────────────────────
const features: PlanFeature[] = [
  ...limits,
  { label: 'Lead sourcing (10 job boards)', free: true, pro: true, max: true, custom: true },
  { label: 'Contact enrichment', free: true, pro: true, max: true, custom: true },
  { label: 'Email validation', free: true, pro: true, max: true, custom: true },
  { label: 'Unified inbox', free: true, pro: true, max: true, custom: true },
  { label: 'CRM deal pipeline', free: true, pro: true, max: true, custom: true },
  { label: 'AI email personalisation', free: true, pro: true, max: true, custom: true },
  { label: 'Warmup engine', free: false, pro: true, max: true, custom: true },
  { label: 'AI Sales Agent', free: false, pro: true, max: true, custom: true },
  { label: 'ICP Wizard', free: false, pro: true, max: true, custom: true },
  { label: 'AI sequence generator', free: false, pro: true, max: true, custom: true },
  { label: 'AI reply agent', free: false, pro: 'You approve', max: 'Autopilot', custom: 'Autopilot' },
  { label: 'A/B testing + auto-optimise', free: false, pro: true, max: true, custom: true },
  { label: 'Analytics & full reports', free: false, pro: true, max: true, custom: true },
  { label: 'Webhooks & CRM sync', free: false, pro: true, max: true, custom: true },
  { label: 'Custom roles & permissions', free: false, pro: true, max: true, custom: true },
  { label: 'Attribution', free: false, pro: false, max: true, custom: true },
  { label: 'Website visitors', free: false, pro: false, max: true, custom: true },
  { label: 'Intent signals', free: false, pro: false, max: true, custom: true },
  { label: 'Revenue forecasting', free: false, pro: false, max: true, custom: true },
  { label: 'Dedicated IP pool', free: false, pro: false, max: true, custom: true },
  { label: 'White-label & agency mode', free: false, pro: false, max: true, custom: true },
  { label: 'Data backups & DR', free: false, pro: false, max: true, custom: true },
  { label: 'Done-for-you onboarding', free: false, pro: false, max: true, custom: true },
  { label: 'SSO', free: false, pro: false, max: true, custom: true },
  { label: 'Priority support & SLA', free: false, pro: false, max: true, custom: true },
]

type PlanKey = 'free' | 'pro' | 'max' | 'custom'

const plans: Array<{
  key: PlanKey
  name: string
  price: number | null
  annualPrice: number | null
  description: string
  cta: string
  href: string
  popular?: boolean
}> = [
  {
    key: 'free',
    name: 'Free',
    price: 0,
    annualPrice: 0,
    description: 'Run the whole pipeline on your own data before you pay anything.',
    cta: 'Start free',
    href: '/signup',
  },
  {
    key: 'pro',
    name: 'Pro',
    price: 99,
    annualPrice: 79,
    description: 'Everything a team needs to run outbound every day.',
    cta: 'Start free, upgrade later',
    href: '/signup',
    popular: true,
  },
  {
    key: 'max',
    name: 'Max',
    price: 299,
    annualPrice: 239,
    description: 'Agency scale — multi-client, white-label, full intelligence.',
    cta: 'Start free, upgrade later',
    href: '/signup',
  },
  {
    key: 'custom',
    name: 'Custom',
    price: null,
    annualPrice: null,
    description: 'Above Max on any axis. You pick the numbers, we quote against them.',
    cta: 'Talk to us',
    href: '/contact?topic=custom-plan',
  },
]

function FeatureValue({ value }: { value: Value }) {
  if (value === true) return <Check className="w-5 h-5 text-green-400 mx-auto" aria-label="Included" />
  if (value === false) return <X className="w-5 h-5 text-slate-600 mx-auto" aria-label="Not included" />
  return <span className="text-slate-300 text-sm">{value}</span>
}

export default function PricingCards() {
  const [annual, setAnnual] = useState(false)

  return (
    <div>
      {/* Toggle */}
      <ScrollReveal>
        <div className="flex items-center justify-center gap-4 mb-12">
          <span className={`text-sm font-medium ${!annual ? 'text-white' : 'text-slate-500'}`}>Monthly</span>
          <button
            onClick={() => setAnnual(!annual)}
            aria-pressed={annual}
            aria-label="Toggle annual billing"
            className={`relative w-14 h-7 rounded-full transition-colors ${annual ? 'bg-primary-500' : 'bg-slate-700'}`}
          >
            <motion.div
              className="absolute top-1 left-1 w-5 h-5 bg-white rounded-full"
              animate={{ x: annual ? 28 : 0 }}
              transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            />
          </button>
          <span className={`text-sm font-medium ${annual ? 'text-white' : 'text-slate-500'}`}>
            Annual <span className="text-green-400 text-xs ml-1">Save 20%</span>
          </span>
        </div>
      </ScrollReveal>

      {/* Cards */}
      <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-6 max-w-7xl mx-auto mb-16">
        {plans.map((plan, i) => {
          const price = annual ? plan.annualPrice : plan.price

          return (
            <ScrollReveal key={plan.key} delay={i * 0.1}>
              <div
                className={`relative rounded-2xl p-1 h-full ${
                  plan.popular ? 'bg-gradient-to-b from-primary-400 to-indigo-500' : 'bg-white/5'
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-gradient-to-r from-primary-500 to-indigo-500 text-white text-xs font-bold px-4 py-1 rounded-full flex items-center gap-1">
                    <Star className="w-3 h-3 fill-current" /> Most Popular
                  </div>
                )}
                <div className="bg-navy-800 rounded-xl p-8 h-full flex flex-col">
                  <h3 className="text-xl font-bold text-white">{plan.name}</h3>
                  <p className="text-slate-500 text-sm mt-1 mb-6 min-h-[40px]">{plan.description}</p>

                  <div className="mb-6">
                    {price === null ? (
                      <span className="text-4xl font-bold text-white">Quoted</span>
                    ) : (
                      <>
                        <span className="text-5xl font-bold text-white">${price}</span>
                        <span className="text-slate-500 text-sm">/mo</span>
                      </>
                    )}
                    {annual && price !== null && price > 0 && (
                      <span className="block text-xs text-slate-500 mt-1">billed annually</span>
                    )}
                    {price === 0 && (
                      <span className="block text-xs text-slate-500 mt-1">no card required</span>
                    )}
                    {price === null && (
                      <span className="block text-xs text-slate-500 mt-1">annual contract</span>
                    )}
                  </div>

                  <Link
                    href={plan.href}
                    className={`block text-center font-semibold py-3 rounded-xl transition-colors mb-8 ${
                      plan.popular
                        ? 'bg-primary-500 hover:bg-primary-400 text-white'
                        : 'bg-white/5 hover:bg-white/10 text-white border border-white/10'
                    }`}
                  >
                    {plan.cta}
                  </Link>

                  {/* The meters first — they are what people actually compare. */}
                  <ul className="space-y-3 flex-1">
                    {limits.map((f) => (
                      <li key={f.label} className="flex items-center gap-2 text-sm">
                        <Check className="w-4 h-4 text-green-400 flex-shrink-0" />
                        <span className="text-slate-400">
                          {f.label.replace(' / month', '')}: {String(f[plan.key])}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </ScrollReveal>
          )
        })}
      </div>

      {/* Honest-numbers note — our send figures assume the 30/day/mailbox that keeps a
          domain alive, unlike headline numbers that need 100+ inboxes bought separately. */}
      <ScrollReveal>
        <p className="max-w-3xl mx-auto text-center text-sm text-slate-500 mb-16">
          Send limits assume the 30 emails per mailbox per day that keeps your domain
          healthy — they are what you can actually send, not a headline that needs a
          hundred inboxes bought separately. Credits cover data and AI; extra credits are
          $10 per 1,000 and never expire.
        </p>
      </ScrollReveal>

      {/* Full comparison table */}
      <ScrollReveal>
        <div className="max-w-6xl mx-auto">
          <h3 className="text-2xl font-bold text-white text-center mb-8">Full Feature Comparison</h3>
          <div className="marketing-card-glow rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px]">
                <thead>
                  <tr className="border-b border-white/5">
                    <th className="text-left px-6 py-4 text-slate-400 text-sm font-medium w-1/3">Feature</th>
                    {plans.map((p) => (
                      <th
                        key={p.key}
                        className={`px-6 py-4 text-sm font-semibold text-center ${
                          p.popular ? 'text-primary-400' : 'text-white'
                        }`}
                      >
                        {p.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {features.map((f, i) => (
                    <tr key={f.label} className={i % 2 === 0 ? '' : 'bg-white/[0.02]'}>
                      <td className="px-6 py-3 text-slate-400 text-sm">{f.label}</td>
                      {plans.map((p) => (
                        <td key={p.key} className="px-6 py-3 text-center">
                          <FeatureValue value={f[p.key]} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </ScrollReveal>
    </div>
  )
}
