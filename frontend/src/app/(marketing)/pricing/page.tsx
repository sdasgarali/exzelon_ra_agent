import type { Metadata } from 'next'
import PricingCards from '@/components/marketing/PricingCards'
import FAQAccordion from '@/components/marketing/FAQAccordion'
import CTABanner from '@/components/marketing/CTABanner'
import ScrollReveal from '@/components/marketing/ScrollReveal'

export const metadata: Metadata = {
  title: 'Pricing',
  description: 'A genuinely free tier, then $99/mo for a whole team. No per-seat fees. Credits cover data and AI; sends have their own monthly allowance.',
  openGraph: {
    title: 'Pricing — NeuraLeads',
    description: 'Free forever to start. Pro $99/mo, Max $299/mo, flat — no per-seat charges.',
  },
}

const pricingFAQ = [
  {
    question: 'Can I switch plans at any time?',
    answer: 'Yes. Upgrade or downgrade at any time. When upgrading, you get immediate access to new features. When downgrading, your current plan continues until the end of the billing period.',
  },
  {
    question: 'Is there a free plan?',
    answer: 'Better — there is a free tier, not a trial. It never expires and needs no card: 300 credits and 500 emails a month, enough to source, enrich, validate and email around 50 contacts. Most competitors offer no free plan at all.',
  },
  {
    question: 'What is the Custom plan?',
    answer: 'Custom sits above Max. If you need more than 1,000 mailboxes, 25,000 credits or 150,000 sends a month, you choose your own numbers — each one starting above Max — and we quote against them on an annual contract.',
  },
  {
    question: 'How many users does a plan include?',
    answer: 'Every plan includes one user login for the workspace. You pay per workspace, never per seat — if you need an extra login, contact us and we will set it up.',
  },
  {
    question: 'What happens when I run out of credits or sends?',
    answer: 'They are two separate budgets. Running out of credits pauses data and AI work — buy a top-up on a paid plan at $20 per 1,000 credits, valid for 12 months (or upgrade for a better per-credit rate). Running out of monthly sends pauses campaigns until the 1st, or until you upgrade. Day-to-day, each mailbox is also paced at 30 emails a day to protect your domain.',
  },
  {
    question: 'Do you offer annual billing discounts?',
    answer: 'Yes. Annual billing saves you 20% compared to monthly billing. Toggle the annual option on the pricing cards above to see discounted prices.',
  },
  {
    question: 'Can I use my own email providers (Gmail, Outlook, etc.)?',
    answer: 'Absolutely. NeuraLeads works with any SMTP-compatible email provider including Gmail, Outlook, and custom domains. Connect as many mailboxes as your plan allows.',
  },
  {
    question: 'What kind of support do you offer?',
    answer: 'Free and Pro get email support. Max adds priority support with an SLA and done-for-you onboarding. Custom contracts include a named account manager.',
  },
]

export default function PricingPage() {
  return (
    <>
      <section className="pt-32 pb-20 px-6">
        <div className="max-w-7xl mx-auto">
          <ScrollReveal>
            <div className="text-center mb-12">
              <h1 className="text-4xl md:text-5xl font-bold text-white mb-4">
                Simple, Transparent Pricing
              </h1>
              <p className="text-lg text-slate-400 max-w-2xl mx-auto">
                Start free and stay free until you outgrow it. No per-seat fees — one flat
                price covers your whole team.
              </p>
            </div>
          </ScrollReveal>

          <PricingCards />
        </div>
      </section>

      <FAQAccordion items={pricingFAQ} title="Pricing FAQ" />

      <CTABanner
        headline="Start Free — No Card, No Deadline"
        subtext="300 credits and 500 emails every month, free forever. Upgrade only when you outgrow it."
        ctaText="Create your workspace"
      />
    </>
  )
}
