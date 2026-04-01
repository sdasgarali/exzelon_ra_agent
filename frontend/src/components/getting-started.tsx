'use client'

import { useRouter } from 'next/navigation'
import {
  X,
  CheckCircle,
  Inbox,
  Search,
  Users,
  ShieldCheck,
  Zap,
  DollarSign,
  Lock,
  HelpCircle,
} from 'lucide-react'

interface OnboardingStatus {
  is_dismissed: boolean
  steps: {
    has_mailboxes: boolean
    has_leads: boolean
    has_contacts: boolean
    has_valid_contacts: boolean
    has_active_campaign: boolean
    has_deals: boolean
  }
  completed_count: number
  total_steps: number
  completion_percentage: number
  should_show_onboarding: boolean
}

interface GettingStartedProps {
  status: OnboardingStatus
  onDismiss: () => void
}

const STEPS = [
  {
    key: 'has_mailboxes' as const,
    number: 1,
    title: 'Setup Mailbox',
    description: 'Add your email accounts (Gmail, Outlook, or SMTP) for sending outreach.',
    icon: Inbox,
    href: '/dashboard/mailboxes',
    cta: 'Add Mailbox',
    color: 'purple',
  },
  {
    key: 'has_leads' as const,
    number: 2,
    title: 'Source Leads',
    description: 'Run the lead sourcing pipeline to find job postings and target companies.',
    icon: Search,
    href: '/dashboard/pipelines',
    cta: 'Run Sourcing',
    color: 'indigo',
  },
  {
    key: 'has_contacts' as const,
    number: 3,
    title: 'Enrich Contacts',
    description: 'Discover decision-maker contacts (emails, titles) from your sourced leads.',
    icon: Users,
    href: '/dashboard/pipelines',
    cta: 'Enrich Contacts',
    color: 'violet',
  },
  {
    key: 'has_valid_contacts' as const,
    number: 4,
    title: 'Validate Emails',
    description: 'Verify contact emails to reduce bounces and protect your sender reputation.',
    icon: ShieldCheck,
    href: '/dashboard/pipelines',
    cta: 'Validate Emails',
    color: 'cyan',
  },
  {
    key: 'has_active_campaign' as const,
    number: 5,
    title: 'Launch Campaign',
    description: 'Create a multi-step email campaign with A/B testing and smart scheduling.',
    icon: Zap,
    href: '/dashboard/campaigns',
    cta: 'Create Campaign',
    color: 'amber',
  },
  {
    key: 'has_deals' as const,
    number: 6,
    title: 'Close Deals',
    description: 'Track interested prospects through your sales pipeline to close deals.',
    icon: DollarSign,
    href: '/dashboard/deals',
    cta: 'View Deals',
    color: 'green',
  },
]

function getStepState(
  stepKey: string,
  steps: OnboardingStatus['steps'],
  stepIndex: number
): 'done' | 'current' | 'locked' {
  if (steps[stepKey as keyof typeof steps]) return 'done'

  // Find the first incomplete step
  const stepKeys = STEPS.map(s => s.key)
  const firstIncomplete = stepKeys.findIndex(k => !steps[k as keyof typeof steps])
  if (stepIndex === firstIncomplete) return 'current'

  return 'locked'
}

export function GettingStarted({ status, onDismiss }: GettingStartedProps) {
  const router = useRouter()

  return (
    <div className="relative rounded-2xl overflow-hidden mb-6 bg-gradient-to-br from-indigo-600 via-purple-600 to-indigo-700 text-white shadow-lg">
      {/* Dismiss button */}
      <button
        onClick={onDismiss}
        className="absolute top-4 right-4 p-1.5 rounded-lg bg-white/10 hover:bg-white/20 transition-colors z-10"
        title="Skip setup guide"
      >
        <X className="w-4 h-4" />
      </button>

      {/* Header */}
      <div className="px-6 pt-6 pb-4">
        <h2 className="text-xl font-bold">Welcome to NeuraLeads!</h2>
        <p className="text-indigo-100 mt-1 text-sm">
          Complete these 6 steps to set up your cold-email automation pipeline.
        </p>

        {/* Progress bar */}
        <div className="mt-4 flex items-center gap-3">
          <div className="flex-1 h-2.5 bg-white/20 rounded-full overflow-hidden">
            <div
              className="h-full bg-white rounded-full transition-all duration-500"
              style={{ width: `${status.completion_percentage}%` }}
            />
          </div>
          <span className="text-sm font-semibold whitespace-nowrap">
            {status.completed_count} of {status.total_steps} steps
          </span>
        </div>
      </div>

      {/* Step cards */}
      <div className="px-6 pb-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {STEPS.map((step, idx) => {
          const state = getStepState(step.key, status.steps, idx)
          const Icon = step.icon

          if (state === 'done') {
            return (
              <div
                key={step.key}
                className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white/15 border border-white/20"
              >
                <div className="w-9 h-9 rounded-lg bg-green-400/20 flex items-center justify-center flex-shrink-0">
                  <CheckCircle className="w-5 h-5 text-green-300" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white/90 flex items-center gap-1.5">
                    <span className="text-xs text-green-300 font-bold">#{step.number}</span>
                    {step.title}
                  </p>
                  <p className="text-xs text-green-200">Completed</p>
                </div>
              </div>
            )
          }

          if (state === 'current') {
            return (
              <div
                key={step.key}
                className="flex flex-col gap-2 px-4 py-3 rounded-xl bg-white text-gray-900 shadow-md border border-white/50 cursor-pointer hover:shadow-lg transition-shadow"
                onClick={() => router.push(step.href)}
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0">
                    <Icon className="w-5 h-5 text-indigo-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold flex items-center gap-1.5">
                      <span className="text-xs text-indigo-500 font-bold">#{step.number}</span>
                      {step.title}
                    </p>
                    <p className="text-xs text-gray-500">{step.description}</p>
                  </div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); router.push(step.href) }}
                  className="self-end text-xs font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
                >
                  {step.cta} &rarr;
                </button>
              </div>
            )
          }

          // locked
          return (
            <div
              key={step.key}
              className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white/5 border border-white/10 opacity-60"
            >
              <div className="w-9 h-9 rounded-lg bg-white/10 flex items-center justify-center flex-shrink-0">
                <Lock className="w-4 h-4 text-white/40" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-white/70 flex items-center gap-1.5">
                  <span className="text-xs text-white/40 font-bold">#{step.number}</span>
                  {step.title}
                </p>
                <p className="text-xs text-white/40">Complete previous steps first</p>
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer tip */}
      <div className="px-6 pb-4 flex items-center gap-2 text-indigo-200 text-xs">
        <HelpCircle className="w-3.5 h-3.5 flex-shrink-0" />
        <span>Click the <strong>?</strong> button in the bottom-right corner anytime to replay the guided tour.</span>
      </div>
    </div>
  )
}
