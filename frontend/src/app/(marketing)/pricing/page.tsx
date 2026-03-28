import type { Metadata } from 'next'
import PricingCards from '@/components/marketing/PricingCards'
import FAQAccordion from '@/components/marketing/FAQAccordion'
import CTABanner from '@/components/marketing/CTABanner'
import ScrollReveal from '@/components/marketing/ScrollReveal'

export const metadata: Metadata = {
  title: 'Pricing',
  description: 'Simple, transparent pricing with no per-seat fees. Start at $49/mo for your entire team. Save 70-90% compared to leading outreach platforms.',
  openGraph: {
    title: 'Pricing — NeuraLeads',
    description: 'Flat-fee pricing starting at $49/mo. No per-seat charges. 14-day free trial.',
  },
}

const pricingFAQ = [
  {
    question: 'Can I switch plans at any time?',
    answer: 'Yes. Upgrade or downgrade at any time. When upgrading, you get immediate access to new features. When downgrading, your current plan continues until the end of the billing period.',
  },
  {
    question: 'Is there a free trial?',
    answer: 'Yes! Every plan comes with a 14-day free trial. No credit card required. You get full access to all features in your chosen plan during the trial.',
  },
  {
    question: 'What does "self-hosted" mean?',
    answer: 'With the Enterprise plan, you can deploy NeuraLeads on your own servers. This gives you full control over your data, compliance with your security policies, and no dependency on our infrastructure.',
  },
  {
    question: 'Are there per-seat fees?',
    answer: 'No. Unlike per-seat competitors that charge $49-$69 per user per month, NeuraLeads charges a flat monthly fee. Add as many team members as your plan allows at no extra cost.',
  },
  {
    question: 'What happens if I exceed my daily email limit?',
    answer: 'Emails beyond your daily limit are automatically queued and sent the next day. You can also upgrade your plan at any time to increase your limit.',
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
    answer: 'Starter plans get email support. Professional plans include email + live chat. Enterprise customers get a dedicated account manager and priority response times.',
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
                No per-seat fees. No hidden costs. Pay one flat price and add your whole team.
                Save 70-90% compared to per-seat competitors.
              </p>
            </div>
          </ScrollReveal>

          <PricingCards />
        </div>
      </section>

      <FAQAccordion items={pricingFAQ} title="Pricing FAQ" />

      <CTABanner
        headline="Start Your 14-Day Free Trial"
        subtext="No credit card required. Full access to all features. Cancel anytime."
        ctaText="Get Started Free"
      />
    </>
  )
}
