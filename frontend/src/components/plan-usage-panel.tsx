'use client'

import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Coins, Send, ArrowUpRight, Plus, Check, Loader2, Mail } from 'lucide-react'
import { billingApi, getApiError } from '@/lib/api'
import { useSiteInfo } from '@/lib/use-site-info'
import type { UsageResponse, UpgradeOption } from './usage-meters'
import { clearPendingUpgrade, parseAnnual, parseUpgradePlan, readPendingUpgrade } from '@/lib/pending-upgrade'
import { useToast } from './toast'

/** mailto: link to our team with the request pre-filled. Used while online payments are
 *  off: the custom-quote API only accepts requests *above* Max, so a Pro upgrade or a
 *  credit top-up is requested by email instead and set up for the customer by hand. */
export function requestMailto(to: string, subject: string, body: string): string {
  return `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
}

export const PAYMENTS_OFF_NOTE = "Online payments open soon — we'll set it up for you."

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
  const { payments_enabled: paymentsEnabled, support_email: supportEmail } = useSiteInfo()
  const [annual, setAnnual] = useState(false)
  // Plan preselected by ?upgrade= (from /pricing → signup → login) or a saved choice.
  const [selected, setSelected] = useState<string | null>(null)
  const plansRef = useRef<HTMLDivElement>(null)
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

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const fromUrl = parseUpgradePlan(params.get('upgrade'))
    const pending = fromUrl ? null : readPendingUpgrade()
    const picked = fromUrl ?? pending?.plan ?? null
    if (picked) {
      setSelected(picked)
      setAnnual(fromUrl ? parseAnnual(params.get('billing')) : Boolean(pending?.annual))
    }
    // The choice has reached the picker; don't redirect future logins here again.
    clearPendingUpgrade()
  }, [])

  // Bring the picker into view once it has rendered (the #plans anchor can't scroll to
  // it on arrival, because it only exists after the usage call returns).
  useEffect(() => {
    if (data?.metered && (selected || window.location.hash === '#plans')) {
      plansRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    }
  }, [selected, data?.metered])

  const upgrade = useMutation({
    mutationFn: (planKey: string) => billingApi.subscribe({ plan: planKey, annual }),
    onSuccess: (res) => {
      if (res?.checkout_url) window.location.href = res.checkout_url
      else toast('error', `Checkout is not available yet. Email ${supportEmail} and we'll set it up.`)
    },
    onError: (e: any) => toast('error', getApiError(e, 'Upgrade failed')),
  })

  const topup = useMutation({
    mutationFn: () => billingApi.buyCredits(blocks),
    onSuccess: (res) => {
      if (res?.checkout_url) window.location.href = res.checkout_url
      else toast('error', `Credit top-ups are not available yet. Email ${supportEmail} and we'll set it up.`)
    },
    onError: (e: any) => toast('error', getApiError(e, 'Top-up failed')),
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
    onError: (e: any) => toast('error', getApiError(e, 'Could not send that request')),
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
  const options = data.upgrade_options ?? []
  // Price and validity come from the API (config), never hardcoded here.
  const topupOffer = data.topup ?? {
    block_size: 1000, block_price_cents: 2000, validity_days: 365, available: plan.key !== 'free',
  }
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
      </div>

      {options.length > 0 && (
        <div id="plans" ref={plansRef} className="mb-6 scroll-mt-24">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Upgrade your plan</h3>
            <div role="group" aria-label="Billing period" className="inline-flex rounded-lg border border-gray-200 p-0.5 text-xs dark:border-gray-600">
              <button
                type="button"
                aria-pressed={!annual}
                onClick={() => setAnnual(false)}
                className={`rounded-md px-3 py-1.5 font-medium ${!annual ? 'bg-blue-600 text-white' : 'text-gray-600 dark:text-gray-300'}`}
              >
                Monthly
              </button>
              <button
                type="button"
                aria-pressed={annual}
                onClick={() => setAnnual(true)}
                className={`rounded-md px-3 py-1.5 font-medium ${annual ? 'bg-blue-600 text-white' : 'text-gray-600 dark:text-gray-300'}`}
              >
                Annual · save 20%
              </button>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {options.map((opt: UpgradeOption) => {
              const isSelected = selected === opt.key
              const perMonth = (annual ? opt.annual_price_cents : opt.monthly_price_cents) / 100
              return (
                <div
                  key={opt.key}
                  data-testid={`plan-option-${opt.key}`}
                  className={`flex flex-col rounded-lg border p-5 ${
                    isSelected
                      ? 'border-blue-600 ring-2 ring-blue-600/30 dark:border-blue-400'
                      : 'border-gray-200 dark:border-gray-700'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-gray-900 dark:text-white">{opt.label}</p>
                    {isSelected && (
                      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                        Your pick
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">
                    ${fmt(perMonth)}
                    <span className="text-sm font-normal text-gray-500 dark:text-gray-400">/mo</span>
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {annual ? `billed $${fmt(perMonth * 12)} yearly` : 'billed monthly'}
                  </p>
                  <ul className="mt-3 flex-1 space-y-1.5 text-sm text-gray-600 dark:text-gray-300">
                    <li className="flex items-center gap-2"><Check className="h-4 w-4 text-green-600" aria-hidden="true" />{fmt(opt.credits_per_month)} credits / month</li>
                    <li className="flex items-center gap-2"><Check className="h-4 w-4 text-green-600" aria-hidden="true" />{fmt(opt.send_quota_per_month)} sends / month</li>
                    <li className="flex items-center gap-2"><Check className="h-4 w-4 text-green-600" aria-hidden="true" />{fmt(opt.max_mailboxes)} mailboxes</li>
                    <li className="flex items-center gap-2"><Check className="h-4 w-4 text-green-600" aria-hidden="true" />{fmt(opt.max_contacts)} contacts</li>
                  </ul>
                  {paymentsEnabled ? (
                    <button
                      type="button"
                      onClick={() => { setSelected(opt.key); upgrade.mutate(opt.key) }}
                      disabled={upgrade.isPending}
                      className="mt-4 inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
                    >
                      {upgrade.isPending && upgrade.variables === opt.key
                        ? <Loader2 className="h-4 w-4 animate-spin" />
                        : <ArrowUpRight className="h-4 w-4" />}
                      Upgrade to {opt.label}
                    </button>
                  ) : (
                    <a
                      href={requestMailto(
                        supportEmail,
                        `Upgrade request: ${plan.label} to ${opt.label}${annual ? ' (annual)' : ''}`,
                        `Hi NeuraLeads team,\n\nPlease upgrade our workspace from the ${plan.label} plan to ${opt.label}, billed ${annual ? 'annually' : 'monthly'}.\n\nThanks!`,
                      )}
                      className="mt-4 inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
                    >
                      <Mail className="h-4 w-4" aria-hidden="true" />
                      Request upgrade to {opt.label}
                    </a>
                  )}
                </div>
              )
            })}
          </div>
          {!paymentsEnabled && (
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{PAYMENTS_OFF_NOTE}</p>
          )}
        </div>
      )}

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
            {credits.topup > 0 && ` · ${fmt(credits.topup)} purchased`}
          </p>
          {credits.topup_next_expiry && (credits.topup_next_expiry_credits ?? 0) > 0 && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {fmt(credits.topup_next_expiry_credits!)} purchased credits expire on{' '}
              {new Date(credits.topup_next_expiry).toLocaleDateString()}
            </p>
          )}

          {/* Top-up. Priced above every plan's per-credit rate on purpose: it covers a
              short month, it is not a cheaper substitute for upgrading. */}
          {topupOffer.available && (
          <>
          <div className="mt-3 flex items-center gap-2">
            <select
              value={blocks}
              onChange={(e) => setBlocks(Number(e.target.value))}
              className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              aria-label="Credit blocks to buy"
            >
              {[1, 2, 5, 10, 25].map((b) => (
                <option key={b} value={b}>
                  {fmt(b * topupOffer.block_size)} credits — ${fmt((b * topupOffer.block_price_cents) / 100)}
                </option>
              ))}
            </select>
            {paymentsEnabled ? (
              <button
                onClick={() => topup.mutate()}
                disabled={topup.isPending}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                {topup.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                Buy credits
              </button>
            ) : (
              <a
                href={requestMailto(
                  supportEmail,
                  `Credit top-up request: ${fmt(blocks * topupOffer.block_size)} credits`,
                  `Hi NeuraLeads team,\n\nPlease add ${fmt(blocks * topupOffer.block_size)} credits ` +
                    `($${fmt((blocks * topupOffer.block_price_cents) / 100)}) to our ${plan.label} workspace.\n\nThanks!`,
                )}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                <Mail className="h-4 w-4" aria-hidden="true" />
                Request credits
              </a>
            )}
          </div>
          {!paymentsEnabled && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{PAYMENTS_OFF_NOTE}</p>
          )}
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Purchased credits are used after your monthly allowance and are valid for{' '}
            {Math.round(topupOffer.validity_days / 30.4)} months.
          </p>
          </>
          )}
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
