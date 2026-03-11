'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Check, X, Star } from 'lucide-react'
import { motion } from 'framer-motion'
import ScrollReveal from './ScrollReveal'

interface PlanFeature {
  label: string
  starter: string | boolean
  professional: string | boolean
  enterprise: string | boolean
}

const features: PlanFeature[] = [
  { label: 'Email accounts', starter: '5', professional: '25', enterprise: 'Unlimited' },
  { label: 'Emails/day', starter: '500', professional: '2,500', enterprise: '10,000+' },
  { label: 'Lead sources', starter: '3', professional: '7', enterprise: 'All 10' },
  { label: 'Contact providers', starter: '2', professional: '5', enterprise: 'All 7' },
  { label: 'AI engines', starter: '1 (Groq)', professional: '2', enterprise: 'All 4' },
  { label: 'Active campaigns', starter: '3', professional: '15', enterprise: 'Unlimited' },
  { label: 'A/B testing', starter: false, professional: true, enterprise: true },
  { label: 'Unified Inbox', starter: false, professional: true, enterprise: true },
  { label: 'CRM Deals', starter: false, professional: true, enterprise: true },
  { label: 'Analytics', starter: 'Basic', professional: 'Advanced', enterprise: 'Full + API' },
  { label: 'Warmup mailboxes', starter: '5', professional: '25', enterprise: 'Unlimited' },
  { label: 'ICP Wizard', starter: false, professional: true, enterprise: true },
  { label: 'Webhooks & Integrations', starter: false, professional: 'Basic', enterprise: 'Full' },
  { label: 'Custom tracking domains', starter: false, professional: '1', enterprise: 'Unlimited' },
  { label: 'Priority support', starter: 'Email', professional: 'Email + Chat', enterprise: 'Dedicated' },
  { label: 'Self-hosted option', starter: false, professional: false, enterprise: true },
  { label: 'White-label', starter: false, professional: false, enterprise: true },
]

const plans = [
  { name: 'Starter', price: 49, annualPrice: 39, description: 'For individuals getting started with outreach' },
  { name: 'Professional', price: 99, annualPrice: 79, description: 'For growing teams that need full automation', popular: true },
  { name: 'Enterprise', price: 199, annualPrice: 159, description: 'For organizations needing full control & scale' },
]

function FeatureValue({ value }: { value: string | boolean }) {
  if (value === true) return <Check className="w-5 h-5 text-green-400 mx-auto" />
  if (value === false) return <X className="w-5 h-5 text-slate-600 mx-auto" />
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
      <div className="grid md:grid-cols-3 gap-6 max-w-6xl mx-auto mb-16">
        {plans.map((plan, i) => {
          const price = annual ? plan.annualPrice : plan.price
          const planKey = plan.name.toLowerCase() as 'starter' | 'professional' | 'enterprise'

          return (
            <ScrollReveal key={plan.name} delay={i * 0.1}>
              <div
                className={`relative rounded-2xl p-1 h-full ${
                  plan.popular
                    ? 'bg-gradient-to-b from-primary-400 to-indigo-500'
                    : 'bg-white/5'
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-gradient-to-r from-primary-500 to-indigo-500 text-white text-xs font-bold px-4 py-1 rounded-full flex items-center gap-1">
                    <Star className="w-3 h-3 fill-current" /> Most Popular
                  </div>
                )}
                <div className="bg-navy-800 rounded-xl p-8 h-full flex flex-col">
                  <h3 className="text-xl font-bold text-white">{plan.name}</h3>
                  <p className="text-slate-500 text-sm mt-1 mb-6">{plan.description}</p>

                  <div className="mb-6">
                    <span className="text-5xl font-bold text-white">${price}</span>
                    <span className="text-slate-500 text-sm">/mo</span>
                    {annual && (
                      <span className="block text-xs text-slate-500 mt-1">billed annually</span>
                    )}
                  </div>

                  <Link
                    href="/login"
                    className={`block text-center font-semibold py-3 rounded-xl transition-colors mb-8 ${
                      plan.popular
                        ? 'bg-primary-500 hover:bg-primary-400 text-white'
                        : 'bg-white/5 hover:bg-white/10 text-white border border-white/10'
                    }`}
                  >
                    Get Started
                  </Link>

                  {/* Inline feature list */}
                  <ul className="space-y-3 flex-1">
                    {features.slice(0, 10).map((f) => {
                      const val = f[planKey]
                      if (val === false) return null
                      return (
                        <li key={f.label} className="flex items-center gap-2 text-sm">
                          <Check className="w-4 h-4 text-green-400 flex-shrink-0" />
                          <span className="text-slate-400">
                            {typeof val === 'string' ? `${f.label}: ${val}` : f.label}
                          </span>
                        </li>
                      )
                    })}
                  </ul>
                </div>
              </div>
            </ScrollReveal>
          )
        })}
      </div>

      {/* Full comparison table */}
      <ScrollReveal>
        <div className="max-w-5xl mx-auto">
          <h3 className="text-2xl font-bold text-white text-center mb-8">Full Feature Comparison</h3>
          <div className="marketing-card-glow rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/5">
                    <th className="text-left px-6 py-4 text-slate-400 text-sm font-medium w-1/3">Feature</th>
                    {plans.map((p) => (
                      <th key={p.name} className={`px-6 py-4 text-sm font-semibold text-center ${p.popular ? 'text-primary-400' : 'text-white'}`}>
                        {p.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {features.map((f, i) => (
                    <tr key={f.label} className={i % 2 === 0 ? '' : 'bg-white/[0.02]'}>
                      <td className="px-6 py-3 text-slate-400 text-sm">{f.label}</td>
                      <td className="px-6 py-3 text-center"><FeatureValue value={f.starter} /></td>
                      <td className="px-6 py-3 text-center"><FeatureValue value={f.professional} /></td>
                      <td className="px-6 py-3 text-center"><FeatureValue value={f.enterprise} /></td>
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
