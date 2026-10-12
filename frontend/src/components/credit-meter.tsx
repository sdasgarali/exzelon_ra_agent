'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { Coins, History, ArrowUpRight } from 'lucide-react'
import { billingApi } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import type { UsageResponse } from './usage-meters'

/**
 * Credit balance pinned to the top bar.
 *
 * Shares the `billing-usage` query with the nav's plan gate and the dashboard meters,
 * so it costs no extra request on load. It refetches every minute and on window
 * focus: pipelines spend credits in the background, and a balance that only changes
 * on reload makes people think a run was free.
 *
 * Renders nothing when the workspace is not metered (a super admin with no
 * workspace selected) — there is no single balance to show.
 */

const fmt = (n: number) => Math.round(n).toLocaleString()

// Roles that can open the billing area (mirrors the Billing nav item).
const BILLING_ROLES = ['super_admin', 'admin', 'bdm']

export function creditTone(total: number, nearLimit: boolean) {
  if (total <= 0) return 'empty' as const
  if (nearLimit) return 'low' as const
  return 'ok' as const
}

const TONE_CLASSES = {
  ok: 'text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700/60 border-gray-200 dark:border-gray-600',
  low: 'text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-900/40 border-amber-300 dark:border-amber-700',
  empty: 'text-red-800 dark:text-red-200 bg-red-50 dark:bg-red-900/40 border-red-300 dark:border-red-700',
}

const BAR_CLASSES = { ok: 'bg-blue-600', low: 'bg-amber-500', empty: 'bg-red-500' }

export function CreditMeter({ compact = false }: { compact?: boolean }) {
  const { user } = useAuthStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data } = useQuery<UsageResponse>({
    queryKey: ['billing-usage'],
    queryFn: billingApi.usage,
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    retry: false,
  })

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!data?.metered || !data.credits) return null

  const { credits, sends } = data
  const tone = creditTone(credits.total, credits.near_limit)
  // Bar shows what is LEFT of the monthly allowance, which is what the number beside
  // it means. Top-ups sit on top of the allowance, so they are listed separately.
  const leftPct = credits.plan_allowance > 0
    ? Math.max(0, Math.min(100, (credits.allowance / credits.plan_allowance) * 100))
    : 0
  const canSeeBilling = BILLING_ROLES.includes(user?.role ?? '')

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors hover:brightness-95 ${TONE_CLASSES[tone]}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`${fmt(credits.total)} credits remaining. Open credit details`}
        data-testid="credit-meter"
      >
        <Coins className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
        <span className="tabular-nums">{fmt(credits.total)}</span>
        {!compact && <span className="hidden xl:inline">credits</span>}
        {!compact && (
          <span className="hidden md:block h-1.5 w-12 rounded-full bg-gray-300/70 dark:bg-gray-600" aria-hidden="true">
            <span className={`block h-1.5 rounded-full ${BAR_CLASSES[tone]}`} style={{ width: `${leftPct}%` }} />
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Credit balance"
          className="absolute right-0 top-full z-50 mt-2 w-72 rounded-lg border border-gray-200 bg-white p-4 text-sm shadow-xl dark:border-gray-700 dark:bg-gray-800"
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Credits this month</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-100">
            {fmt(credits.total)} <span className="text-sm font-normal text-gray-500 dark:text-gray-400">left</span>
          </p>
          <div className="mt-2 h-2 w-full rounded-full bg-gray-200 dark:bg-gray-700" aria-hidden="true">
            <div className={`h-2 rounded-full ${BAR_CLASSES[tone]}`} style={{ width: `${leftPct}%` }} />
          </div>

          <dl className="mt-3 space-y-1.5 text-gray-700 dark:text-gray-300">
            <div className="flex justify-between">
              <dt>Monthly allowance left</dt>
              <dd className="tabular-nums">{fmt(credits.allowance)} / {fmt(credits.plan_allowance)}</dd>
            </div>
            {credits.topup > 0 && (
              <div className="flex justify-between">
                <dt>Purchased credits</dt>
                <dd className="tabular-nums">{fmt(credits.topup)}</dd>
              </div>
            )}
            <div className="flex justify-between">
              <dt>Used this month</dt>
              <dd className="tabular-nums">{fmt(credits.period_spent)}</dd>
            </div>
            {sends && (
              <div className="flex justify-between border-t border-gray-200 pt-1.5 dark:border-gray-700">
                <dt>Email sends left</dt>
                <dd className="tabular-nums">{fmt(sends.remaining)} / {fmt(sends.limit)}</dd>
              </div>
            )}
          </dl>

          {tone !== 'ok' && (
            <p className={`mt-3 rounded-md px-2 py-1.5 text-xs ${tone === 'empty' ? 'bg-red-50 text-red-800 dark:bg-red-900/40 dark:text-red-200' : 'bg-amber-50 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200'}`}>
              {tone === 'empty'
                ? 'You are out of credits. Paid actions will stop until you top up or the allowance refills.'
                : 'You have used most of this month\'s credits.'}
            </p>
          )}

          {canSeeBilling && (
            <div className="mt-3 flex gap-2">
              <Link
                href="/dashboard/billing/credits"
                onClick={() => setOpen(false)}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-md border border-gray-300 px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                <History className="h-3.5 w-3.5" aria-hidden="true" /> Credit history
              </Link>
              <Link
                href="/dashboard/billing"
                onClick={() => setOpen(false)}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-blue-600 px-2 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
              >
                Top up <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default CreditMeter
