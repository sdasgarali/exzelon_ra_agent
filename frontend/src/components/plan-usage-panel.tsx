'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Coins, Send, ArrowUpRight, Plus, Check, Loader2 } from 'lucide-react'
import { billingApi } from '@/lib/api'
import type { UsageResponse } from './usage-meters'
import { useToast } from './toast'

/**
 * Plan & usage panel for the billing page.
 *
 * Shows what the plan grants, what has been used against it, and the two ways to get
 * more: upgrade, or top up credits. The Custom configurator lives here too — its
 * minimums are Max's numbers, enforced again server-side, because "custom" must never
 * become a way to negotiate *down* from the published tier.
 */

const RESOURCE_LABELS: Record<string, string> = {
  leads: 'Leads',
  contacts: 'Contacts',
  mailboxes: 'Mailboxes',
  campaigns: 'Active campaigns',
}

// Team seats and lines of business are 1 on every plan and managed by super admin only,
// so they are not metered to the customer.
const HIDDEN_RESOURCES = new Set(['users', 'lobs'])

const fmt = (n: number) => n.toLocaleString()

function MeterRow({
  label,
  used,
  limit,
  percent,
  nearLimit,
}: {
  label: string
  used: number
  limit: number
  percent: number | null
  nearLimit: boolean
}) {
  const pct = Math.min(100, Math.max(percent && percent > 0 ? 2 : 0, percent ?? 0))
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-700 dark:text-gray-300">{label}</span>
        <span className="tabular-nums text-gray-600 dark:text-gray-400">
          {fmt(used)} <span className="text-gray-400">/ {fmt(limit)}</span>
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full rounded-full bg-gray-200 dark:bg-gray-700">
        <div
          className={`h-1.5 rounded-full ${
            pct >= 100 ? 'bg-red-500' : nearLimit ? 'bg-amber-500' : 'bg-blue-600'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export default function PlanUsagePanel() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [annual, setAnnual] = useState(false)
  const [blocks, setBlocks] = useState(1)
  const [showCustom, setShowCustom] = useState(false)
  const [custom, setCustom] = useState({
    mailboxes: '', credits_per_month: '', sends_per_month: '',
    campaigns: '', notes: '',
  })

  const { data, isLoading } = useQuery<UsageResponse>({
    queryKey: ['billing-usage'],
    queryFn: billingApi.usage,
  })

  const upgrade = useMutation({
    mutationFn: () => billingApi.subscribe({ plan: data?.plan?.upgrade_to || undefined, annual }),
    onSuccess: (res) => {
      if (res?.checkout_url) window.location.href = res.checkout_url
      else toast('error', 'Checkout is not configured yet. Contact support.')
    },
    onError: (e: any) =>
      toast('error', e?.response?.data?.detail?.message || e?.response?.data?.detail || 'Upgrade failed'),
  })

  const topup = useMutation({
    mutationFn: () => billingApi.buyCredits(blocks),
    onSuccess: (res) => {
      if (res?.checkout_url) window.location.href = res.checkout_url
      else toast('error', 'Credit top-ups are not configured yet. Contact support.')
    },
    onError: (e: any) =>
      toast('error', e?.response?.data?.detail?.message || e?.response?.data?.detail || 'Top-up failed'),
  })

  const quote = useMutation({
    mutationFn: () => {
      // Only send the axes actually filled in — the API rejects an empty request and
      // requires every supplied value to exceed Max.
      const payload: Record<string, number | string> = {}
      for (const [k, v] of Object.entries(custom)) {
        if (k === 'notes') { if (v) payload.notes = v; continue }
        if (v !== '') payload[k] = Number(v)
      }
      return billingApi.requestCustomQuote(payload)
    },
    onSuccess: () => {
      toast('success', "Thanks — we'll be in touch with a quote.")
      setShowCustom(false)
      qc.invalidateQueries({ queryKey: ['billing-usage'] })
    },
    onError: (e: any) =>
      toast('error', e?.response?.data?.detail?.message || e?.response?.data?.detail || 'Could not send that request'),
  })

  if (isLoading) {
    return (
      <div className="mb-6 flex items-center gap-2 rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-800">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading plan…
      </div>
    )
  }

  // Super admins have no plan of their own; the invoice tools below are what they want.
  if (!data?.metered || !data.plan || !data.credits || !data.sends) return null

  const { plan, credits, sends } = data
  const resources = (data.resources || []).filter((r) => !HIDDEN_RESOURCES.has(r.resource))
  // Max's published numbers, mirrored from PLAN_MATRIX — also enforced server-side.
  const floors: Record<string, number> = {
    mailboxes: 1000, credits_per_month: 25000, sends_per_month: 150000,
    campaigns: 100,
  }

  return (
    <div className="mb-6 rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {plan.label} plan
          </h2>
          <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
            {plan.is_custom
              ? 'Custom contract'
              : plan.monthly_price_cents === 0
              ? 'Free forever — no card required'
              : `$${(plan.monthly_price_cents! / 100).toFixed(0)}/month`}
          </p>
        </div>

        {plan.upgrade_to && (
          <div className="flex items-center gap-3">
            <label className="flex cursor-pointer items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
              <input
                type="checkbox"
                checked={annual}
                onChange={(e) => setAnnual(e.target.checked)}
                className="rounded border-gray-300"
              />
              Annual (save 20%)
            </label>
            <button
              onClick={() => upgrade.mutate()}
              disabled={upgrade.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
            >
              {upgrade.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUpRight className="h-4 w-4" />}
              Upgrade to {plan.upgrade_label}
            </button>
          </div>
        )}
      </div>

      {/* The two meters */}
      <div className="mb-6 grid gap-5 sm:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
            <Coins className="h-4 w-4 text-blue-600 dark:text-blue-400" /> Credits
          </div>
          <MeterRow
            label="Monthly allowance"
            used={credits.period_spent}
            limit={credits.plan_allowance}
            percent={credits.percent}
            nearLimit={credits.near_limit}
          />
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            {fmt(credits.allowance)} allowance left
            {credits.topup > 0 && ` · ${fmt(credits.topup)} purchased (never expire)`}
          </p>

          {/* Top-up. Same $0.01/credit as the plan — running out mid-month should not
              cost more per credit than planning ahead did. */}
          <div className="mt-3 flex items-center gap-2">
            <select
              value={blocks}
              onChange={(e) => setBlocks(Number(e.target.value))}
              className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              aria-label="Credit blocks to buy"
            >
              {[1, 2, 5, 10, 25].map((b) => (
                <option key={b} value={b}>
                  {fmt(b * 1000)} credits — ${b * 10}
                </option>
              ))}
            </select>
            <button
              onClick={() => topup.mutate()}
              disabled={topup.isPending}
              className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
            >
              {topup.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Buy credits
            </button>
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
            <Send className="h-4 w-4 text-blue-600 dark:text-blue-400" /> Emails
          </div>
          <MeterRow
            label="Monthly sends"
            used={sends.used}
            limit={sends.limit}
            percent={sends.percent}
            nearLimit={sends.near_limit}
          />
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            {fmt(sends.remaining)} sends left this month. Sends do not use credits.
          </p>
        </div>
      </div>

      {/* Resource caps */}
      <div className="mb-6">
        <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-white">Plan limits</h3>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {resources.map((r) => (
            <MeterRow
              key={r.resource}
              label={RESOURCE_LABELS[r.resource] || r.resource}
              used={r.used}
              limit={r.limit}
              percent={r.percent}
              nearLimit={r.near_limit}
            />
          ))}
        </div>
      </div>

      {/* Custom plan configurator (deferred from Phase 1.6) */}
      {!plan.is_custom && (
        <div className="border-t border-gray-200 pt-4 dark:border-gray-700">
          {!showCustom ? (
            <button
              onClick={() => setShowCustom(true)}
              className="text-sm font-medium text-blue-600 hover:underline dark:text-blue-400"
            >
              Need more than Max? Build a custom plan →
            </button>
          ) : (
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                Build your plan
              </h3>
              <p className="mt-0.5 mb-3 text-xs text-gray-500 dark:text-gray-400">
                Custom sits above Max, so each figure has to exceed Max&apos;s. Fill in only
                what you need more of — we&apos;ll quote against it.
              </p>
              <div className="grid gap-3 sm:grid-cols-3">
                {(Object.keys(floors) as Array<keyof typeof floors>).map((k) => (
                  <label key={k} className="text-xs text-gray-600 dark:text-gray-400">
                    {RESOURCE_LABELS[k] || k.replace(/_/g, ' ')}
                    <input
                      type="number"
                      min={floors[k] + 1}
                      placeholder={`> ${fmt(floors[k])}`}
                      value={(custom as any)[k]}
                      onChange={(e) => setCustom({ ...custom, [k]: e.target.value })}
                      className="mt-1 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                    />
                  </label>
                ))}
              </div>
              <textarea
                value={custom.notes}
                onChange={(e) => setCustom({ ...custom, notes: e.target.value })}
                placeholder="Anything else we should know?"
                rows={2}
                className="mt-3 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              />
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => quote.mutate()}
                  disabled={quote.isPending}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
                >
                  {quote.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                  Request a quote
                </button>
                <button
                  onClick={() => setShowCustom(false)}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
