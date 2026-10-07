'use client'

import { useQuery } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'
import { Coins, Send, AlertTriangle, ArrowUpRight } from 'lucide-react'
import { billingApi } from '@/lib/api'

/**
 * The two meters, side by side.
 *
 * Credits and sends are separate budgets — running out of one says nothing about the
 * other — so they are always shown together. Showing only credits would leave someone
 * blocked by the send quota with no idea why.
 *
 * `near_limit` comes from the API rather than being computed here, so "when do we warn
 * someone?" stays one rule on the server instead of a threshold copy-pasted into every
 * component that draws a bar.
 */

export interface UsageResponse {
  metered: boolean
  plan?: {
    key: string
    label: string
    is_custom: boolean
    // null for Custom — those are quoted, not listed.
    monthly_price_cents: number | null
    annual_price_cents: number | null
    upgrade_to: string | null
    upgrade_label: string | null
  }
  credits?: {
    allowance: number
    topup: number
    topup_next_expiry?: string | null
    topup_next_expiry_credits?: number
    total: number
    period_spent: number
    plan_allowance: number
    percent: number | null
    near_limit: boolean
  }
  sends?: {
    used: number
    limit: number
    remaining: number
    percent: number | null
    near_limit: boolean
    exhausted: boolean
  }
  resources?: Array<{
    resource: string
    used: number
    limit: number
    remaining: number
    percent: number | null
    near_limit: boolean
  }>
  topup?: {
    block_size: number
    block_price_cents: number
    validity_days: number
    available: boolean
  }
}

const fmt = (n: number) => n.toLocaleString()

function Bar({ percent, warn }: { percent: number | null; warn: boolean }) {
  // Always render a sliver for a non-zero value: a bar that reads as empty when a few
  // credits have been spent makes the meter look broken.
  const pct = Math.min(100, Math.max(percent && percent > 0 ? 2 : 0, percent ?? 0))
  return (
    <div className="h-2 w-full rounded-full bg-gray-200 dark:bg-gray-700" role="presentation">
      <div
        className={`h-2 rounded-full transition-all ${
          pct >= 100 ? 'bg-red-500' : warn ? 'bg-amber-500' : 'bg-blue-600'
        }`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function Meter({
  icon,
  label,
  used,
  limit,
  unit,
  percent,
  warn,
  extra,
}: {
  icon: React.ReactNode
  label: string
  used: number
  limit: number
  unit: string
  percent: number | null
  warn: boolean
  extra?: string
}) {
  return (
    <div className="flex-1 min-w-[220px]">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
          {icon}
          {label}
        </span>
        <span
          className="text-sm tabular-nums text-gray-600 dark:text-gray-400"
          aria-label={`${fmt(used)} of ${fmt(limit)} ${unit} used`}
        >
          {fmt(used)} <span className="text-gray-400">/ {fmt(limit)}</span>
        </span>
      </div>
      <Bar percent={percent} warn={warn} />
      <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
        {fmt(Math.max(0, limit - used))} {unit} left this month
        {extra ? ` · ${extra}` : ''}
      </p>
    </div>
  )
}

export default function UsageMeters({ compact = false }: { compact?: boolean }) {
  const router = useRouter()
  const { data, isLoading } = useQuery<UsageResponse>({
    queryKey: ['billing-usage'],
    queryFn: billingApi.usage,
    staleTime: 60_000,
  })

  // Super admins aren't on a plan, so there is nothing to meter — render nothing
  // rather than a row of zeroes that looks like an error.
  if (isLoading || !data?.metered || !data.credits || !data.sends) return null

  const { credits, sends, plan } = data
  const warn = credits.near_limit || sends.near_limit
  const canUpgrade = Boolean(plan?.upgrade_to)

  return (
    <div
      className={`rounded-lg border bg-white p-4 dark:bg-gray-800 ${
        warn
          ? 'border-amber-300 dark:border-amber-700'
          : 'border-gray-200 dark:border-gray-700'
      } ${compact ? '' : 'mb-6'}`}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
          Usage this month
          {plan && (
            <span className="ml-2 rounded bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300">
              {plan.label}
            </span>
          )}
        </h3>
        {canUpgrade && (
          <button
            onClick={() => router.push('/dashboard/billing?tab=plan')}
            className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            Upgrade to {plan?.upgrade_label}
            <ArrowUpRight className="h-3 w-3" />
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-6">
        <Meter
          icon={<Coins className="h-4 w-4 text-blue-600 dark:text-blue-400" />}
          label="Credits"
          used={credits.period_spent}
          limit={credits.plan_allowance}
          unit="credits"
          percent={credits.percent}
          warn={credits.near_limit}
          extra={credits.topup > 0 ? `${fmt(credits.topup)} top-up` : undefined}
        />
        <Meter
          icon={<Send className="h-4 w-4 text-blue-600 dark:text-blue-400" />}
          label="Emails sent"
          used={sends.used}
          limit={sends.limit}
          unit="sends"
          percent={sends.percent}
          warn={sends.near_limit}
        />
      </div>

      {warn && (
        <p className="mt-3 flex items-start gap-2 rounded bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            {sends.exhausted
              ? 'You have used your send quota for this month. Campaigns are paused until it resets.'
              : 'You are close to a monthly limit. Top up credits or upgrade to keep campaigns running.'}
          </span>
        </p>
      )}
    </div>
  )
}
