'use client'

import Link from 'next/link'
import ScrollReveal from './ScrollReveal'

interface CTABannerProps {
  headline?: string
  subtext?: string
  ctaText?: string
  ctaHref?: string
}

export default function CTABanner({
  headline = 'Ready to Outperform Your Competition?',
  subtext = 'No credit card required. Self-hosted. Full control over your data.',
  ctaText = 'Get Started Free',
  ctaHref = '/login',
}: CTABannerProps) {
  return (
    <section className="relative py-24 overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-r from-primary-600 via-blue-600 to-indigo-600" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(255,255,255,0.15),transparent_70%)]" />
      <div className="relative max-w-4xl mx-auto px-6 text-center">
        <ScrollReveal>
          <h2 className="text-3xl md:text-5xl font-bold text-white mb-6">
            {headline}
          </h2>
          <p className="text-lg text-blue-100 mb-10 max-w-2xl mx-auto">
            {subtext}
          </p>
          <Link
            href={ctaHref}
            className="inline-flex items-center gap-2 bg-white text-primary-700 font-semibold px-8 py-4 rounded-xl text-lg hover:bg-blue-50 transition-colors shadow-lg shadow-black/20"
          >
            {ctaText}
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </Link>
        </ScrollReveal>
      </div>
    </section>
  )
}
