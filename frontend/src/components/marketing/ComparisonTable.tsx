'use client'

import { Fragment, useState } from 'react'
import { Check, X, Minus, ChevronDown } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import ScrollReveal from './ScrollReveal'

interface ComparisonRow {
  feature: string
  exzelon: string | boolean
  instantly: string | boolean
  smartlead: string | boolean
  lemlist: string | boolean
}

interface ComparisonCategory {
  name: string
  exzelonScore: number
  instantlyScore: number
  smartleadScore: number
  lemlistScore: number
  rows: ComparisonRow[]
}

const categories: ComparisonCategory[] = [
  {
    name: 'Lead Sourcing',
    exzelonScore: 9, instantlyScore: 8, smartleadScore: 5, lemlistScore: 7,
    rows: [
      { feature: 'Job board APIs', exzelon: '10 sources', instantly: 'Built-in DB', smartlead: false, lemlist: 'LinkedIn only' },
      { feature: 'Contact discovery providers', exzelon: '7 providers', instantly: '1 built-in', smartlead: '1 built-in', lemlist: '1 built-in' },
      { feature: 'AI lead scoring', exzelon: true, instantly: true, smartlead: false, lemlist: false },
      { feature: 'ICP Wizard', exzelon: true, instantly: false, smartlead: false, lemlist: false },
      { feature: 'Automated scheduling', exzelon: '3x/day', instantly: 'Manual', smartlead: false, lemlist: 'Manual' },
    ],
  },
  {
    name: 'Email Warmup',
    exzelonScore: 10, instantlyScore: 9, smartleadScore: 9, lemlistScore: 7,
    rows: [
      { feature: 'Peer-to-peer warmup', exzelon: true, instantly: true, smartlead: true, lemlist: 'Add-on' },
      { feature: 'DNS health checks', exzelon: 'SPF/DKIM/DMARC', instantly: 'Basic', smartlead: 'Basic', lemlist: false },
      { feature: 'Blacklist monitoring', exzelon: true, instantly: true, smartlead: true, lemlist: false },
      { feature: 'Auto-reply generation', exzelon: 'AI-powered', instantly: 'Templates', smartlead: 'Templates', lemlist: false },
    ],
  },
  {
    name: 'Campaign Engine',
    exzelonScore: 9, instantlyScore: 9, smartleadScore: 8, lemlistScore: 9,
    rows: [
      { feature: 'Multi-step sequences', exzelon: true, instantly: true, smartlead: true, lemlist: true },
      { feature: 'A/B testing', exzelon: 'Auto-optimize', instantly: true, smartlead: true, lemlist: true },
      { feature: 'Spintax support', exzelon: 'Nested', instantly: true, smartlead: true, lemlist: true },
      { feature: 'Condition branching', exzelon: true, instantly: true, smartlead: false, lemlist: true },
      { feature: 'Timezone-aware delivery', exzelon: true, instantly: true, smartlead: true, lemlist: true },
    ],
  },
  {
    name: 'AI Content',
    exzelonScore: 10, instantlyScore: 8, smartleadScore: 7, lemlistScore: 8,
    rows: [
      { feature: 'AI engines available', exzelon: '4 (Groq/OpenAI/Claude/Gemini)', instantly: '1 (proprietary)', smartlead: '1', lemlist: '1' },
      { feature: 'AI sequence generation', exzelon: true, instantly: true, smartlead: false, lemlist: true },
      { feature: 'AI sentiment analysis', exzelon: true, instantly: false, smartlead: false, lemlist: false },
      { feature: 'Spam score checking', exzelon: true, instantly: false, smartlead: false, lemlist: false },
    ],
  },
  {
    name: 'Unified Inbox',
    exzelonScore: 9, instantlyScore: 8, smartleadScore: 8, lemlistScore: 7,
    rows: [
      { feature: 'Thread grouping', exzelon: true, instantly: true, smartlead: true, lemlist: true },
      { feature: 'AI categorization', exzelon: '6 labels', instantly: 'Basic', smartlead: false, lemlist: false },
      { feature: 'Smart reply suggestions', exzelon: 'AI-powered', instantly: false, smartlead: false, lemlist: false },
      { feature: 'CRM auto-forward', exzelon: true, instantly: false, smartlead: false, lemlist: false },
    ],
  },
  {
    name: 'CRM & Deals',
    exzelonScore: 9, instantlyScore: 7, smartleadScore: 5, lemlistScore: 6,
    rows: [
      { feature: 'Deal pipeline (Kanban)', exzelon: true, instantly: 'Basic', smartlead: false, lemlist: false },
      { feature: 'HubSpot sync', exzelon: 'Bidirectional', instantly: 'One-way', smartlead: 'One-way', lemlist: 'One-way' },
      { feature: 'Salesforce sync', exzelon: 'Bidirectional', instantly: 'One-way', smartlead: false, lemlist: false },
      { feature: 'Deal tasks & activities', exzelon: true, instantly: false, smartlead: false, lemlist: false },
    ],
  },
  {
    name: 'Analytics',
    exzelonScore: 10, instantlyScore: 8, smartleadScore: 7, lemlistScore: 8,
    rows: [
      { feature: 'Campaign comparison', exzelon: true, instantly: true, smartlead: false, lemlist: true },
      { feature: 'Team leaderboard', exzelon: true, instantly: false, smartlead: false, lemlist: false },
      { feature: 'Revenue metrics', exzelon: true, instantly: false, smartlead: false, lemlist: false },
      { feature: 'Cost tracking & ROI', exzelon: true, instantly: false, smartlead: false, lemlist: false },
    ],
  },
  {
    name: 'Pricing & Value',
    exzelonScore: 10, instantlyScore: 7, smartleadScore: 7, lemlistScore: 6,
    rows: [
      { feature: 'Starting price', exzelon: '$49/mo', instantly: '$30/mo', smartlead: '$39/mo', lemlist: '$69/mo' },
      { feature: 'Per-seat fees', exzelon: 'None', instantly: 'None', smartlead: 'None', lemlist: '$69+/seat' },
      { feature: 'Self-hosted option', exzelon: true, instantly: false, smartlead: false, lemlist: false },
      { feature: 'White-label', exzelon: 'Enterprise', instantly: false, smartlead: false, lemlist: false },
    ],
  },
]

function CellValue({ value }: { value: string | boolean }) {
  if (value === true) return <Check className="w-4 h-4 text-green-400 mx-auto" />
  if (value === false) return <X className="w-4 h-4 text-slate-600 mx-auto" />
  return <span className="text-xs md:text-sm text-slate-300">{value}</span>
}

function ScoreBadge({ score }: { score: number }) {
  const color = score >= 9 ? 'text-green-400' : score >= 7 ? 'text-yellow-400' : 'text-slate-500'
  return <span className={`font-bold text-sm ${color}`}>{score}/10</span>
}

export default function ComparisonTable({ compact = false }: { compact?: boolean }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const displayed = compact ? categories.slice(0, 4) : categories

  const totalScores = categories.reduce(
    (acc, c) => ({
      exzelon: acc.exzelon + c.exzelonScore,
      instantly: acc.instantly + c.instantlyScore,
      smartlead: acc.smartlead + c.smartleadScore,
      lemlist: acc.lemlist + c.lemlistScore,
    }),
    { exzelon: 0, instantly: 0, smartlead: 0, lemlist: 0 }
  )

  const toggle = (name: string) => {
    const next = new Set(expanded)
    next.has(name) ? next.delete(name) : next.add(name)
    setExpanded(next)
  }

  return (
    <div>
      {/* Score summary */}
      <ScrollReveal>
        <div className="grid grid-cols-4 gap-4 max-w-3xl mx-auto mb-12">
          {[
            { name: 'NeuraMail', score: totalScores.exzelon, max: categories.length * 10, highlight: true },
            { name: 'Flat-Fee Tool', score: totalScores.instantly, max: categories.length * 10 },
            { name: 'Warmup Tool', score: totalScores.smartlead, max: categories.length * 10 },
            { name: 'Per-Seat Tool', score: totalScores.lemlist, max: categories.length * 10 },
          ].map((item) => (
            <div key={item.name} className={`text-center p-4 rounded-xl ${item.highlight ? 'marketing-card-glow border-primary-500/30' : 'marketing-card-glow'}`}>
              <div className={`text-2xl md:text-3xl font-bold ${item.highlight ? 'text-primary-400' : 'text-white'}`}>
                {item.score}/{item.max}
              </div>
              <div className="text-xs text-slate-500 mt-1">{item.name}</div>
            </div>
          ))}
        </div>
      </ScrollReveal>

      {/* Table */}
      <ScrollReveal>
        <div className="marketing-card-glow rounded-2xl overflow-hidden max-w-6xl mx-auto">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/5">
                  <th className="text-left px-4 md:px-6 py-4 text-slate-400 text-xs md:text-sm font-medium">Category</th>
                  <th className="px-4 md:px-6 py-4 text-xs md:text-sm font-semibold text-primary-400 text-center">NeuraMail</th>
                  <th className="px-4 md:px-6 py-4 text-xs md:text-sm font-medium text-slate-400 text-center">Flat-Fee Tool</th>
                  <th className="px-4 md:px-6 py-4 text-xs md:text-sm font-medium text-slate-400 text-center hidden md:table-cell">Warmup Tool</th>
                  <th className="px-4 md:px-6 py-4 text-xs md:text-sm font-medium text-slate-400 text-center hidden md:table-cell">Per-Seat Tool</th>
                </tr>
              </thead>
              <tbody>
                {displayed.map((cat) => (
                  <Fragment key={cat.name}>
                    <tr
                      onClick={() => toggle(cat.name)}
                      className="border-b border-white/5 cursor-pointer hover:bg-white/[0.02] transition-colors"
                    >
                      <td className="px-4 md:px-6 py-3 text-sm text-white font-medium flex items-center gap-2">
                        <motion.div animate={{ rotate: expanded.has(cat.name) ? 180 : 0 }} transition={{ duration: 0.2 }}>
                          <ChevronDown className="w-4 h-4 text-slate-500" />
                        </motion.div>
                        {cat.name}
                      </td>
                      <td className="px-4 md:px-6 py-3 text-center"><ScoreBadge score={cat.exzelonScore} /></td>
                      <td className="px-4 md:px-6 py-3 text-center"><ScoreBadge score={cat.instantlyScore} /></td>
                      <td className="px-4 md:px-6 py-3 text-center hidden md:table-cell"><ScoreBadge score={cat.smartleadScore} /></td>
                      <td className="px-4 md:px-6 py-3 text-center hidden md:table-cell"><ScoreBadge score={cat.lemlistScore} /></td>
                    </tr>
                    <AnimatePresence>
                      {expanded.has(cat.name) && cat.rows.map((row) => (
                        <motion.tr
                          key={`${cat.name}-${row.feature}`}
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          className="bg-white/[0.01] border-b border-white/[0.03]"
                        >
                          <td className="px-4 md:px-6 py-2.5 text-xs text-slate-500 pl-12">{row.feature}</td>
                          <td className="px-4 md:px-6 py-2.5 text-center"><CellValue value={row.exzelon} /></td>
                          <td className="px-4 md:px-6 py-2.5 text-center"><CellValue value={row.instantly} /></td>
                          <td className="px-4 md:px-6 py-2.5 text-center hidden md:table-cell"><CellValue value={row.smartlead} /></td>
                          <td className="px-4 md:px-6 py-2.5 text-center hidden md:table-cell"><CellValue value={row.lemlist} /></td>
                        </motion.tr>
                      ))}
                    </AnimatePresence>
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </ScrollReveal>
    </div>
  )
}
