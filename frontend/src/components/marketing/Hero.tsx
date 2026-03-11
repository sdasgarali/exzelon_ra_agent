'use client'

import Link from 'next/link'
import { motion } from 'framer-motion'
import StatsCounter from './StatsCounter'

const heroStats = [
  { value: 10, suffix: '+', label: 'Lead Sources' },
  { value: 7, label: 'Validation Providers' },
  { value: 4, label: 'AI Engines' },
  { value: 90, suffix: '%', label: 'Feature Score' },
]

export default function Hero() {
  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center px-6 pt-16 pb-20 overflow-hidden">
      {/* Animated gradient orbs */}
      <div className="absolute top-1/4 -left-32 w-96 h-96 bg-primary-500/20 rounded-full blur-[128px] animate-glow-pulse" />
      <div className="absolute bottom-1/4 -right-32 w-96 h-96 bg-indigo-500/20 rounded-full blur-[128px] animate-glow-pulse" style={{ animationDelay: '1.5s' }} />

      <div className="relative max-w-5xl mx-auto text-center">
        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="inline-flex items-center gap-2 bg-white/5 border border-white/10 rounded-full px-4 py-1.5 mb-8"
        >
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-sm text-slate-300">Scores 135/150 — Beats Every Leading Platform</span>
        </motion.div>

        {/* Headline */}
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold text-white leading-tight mb-6"
        >
          The AI-Powered Outreach
          <br />
          <span className="marketing-gradient-text">Platform That Converts</span>
        </motion.h1>

        {/* Subheadline */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed"
        >
          10 lead sources. 7 contact providers. 4 AI engines. Full pipeline automation
          from lead sourcing to closed deals — at 70% less cost than competitors.
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-20"
        >
          <Link
            href="/login"
            className="group bg-primary-500 hover:bg-primary-400 text-white font-semibold px-8 py-3.5 rounded-xl text-lg transition-all shadow-lg shadow-primary-500/25 hover:shadow-primary-400/30"
          >
            Start Free Trial
            <span className="inline-block ml-2 group-hover:translate-x-1 transition-transform">&rarr;</span>
          </Link>
          <Link
            href="/pricing"
            className="text-slate-300 hover:text-white font-medium px-8 py-3.5 rounded-xl text-lg border border-white/10 hover:border-white/20 transition-all"
          >
            See Pricing
          </Link>
        </motion.div>

        {/* Stats */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
        >
          <StatsCounter stats={heroStats} />
        </motion.div>
      </div>
    </section>
  )
}
