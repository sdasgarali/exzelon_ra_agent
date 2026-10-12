'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { ArrowLeft, Coins, Download, History, RefreshCw } from 'lucide-react'
import { billingApi, creditsApi } from '@/lib/api'
import type { UsageResponse } from '@/components/usage-meters'
import { formatLedgerCredits, ledgerToCsv, type LedgerItem } from '@/lib/credit-ledger'

/**
 * Credit history — every charge and grant on this workspace's credit ledger.
 *
 * Reads `/credits/usage` (paginated ledger) and `/credits/summary` (this month by
 * action). Labels and categories come from the server so a new metered action shows
 * up here without a frontend change.
 */

interface LedgerPage {
  items: LedgerItem[]
  total: number
  page: number
  page_size: number
}

interface SummaryRow {
  usage_type: string
  label: string
  category: string
  total_credits: number
  count: number
}

const PAGE_SIZE = 50
const fmt = (n: number) => (Number.isInteger(n) ? n.toLocaleString() : n.toLocaleString(undefined, { maximumFractionDigits: 2 }))

const CATEGORY_STYLES: Record<string, string> = {
  data: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200',
  validation: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200',
  ai: 'bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200',
  comms: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200',
  grant: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200',
  other: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
}

function CategoryBadge({ category }: { category: string }) {
  const label = category === 'grant' ? 'top-up' : category
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize ${CATEGORY_STYLES[category] || CATEGORY_STYLES.other}`}>
      {label}
    </span>
  )
}

export default function CreditHistoryPage() {
  const [usageType, setUsageType] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [page, setPage] = useState(1)

  const { data: usage } = useQuery<UsageResponse>({
    queryKey: ['billing-usage'],
    queryFn: billingApi.usage,
    staleTime: 60_000,
  })

  const { data: summary } = useQuery<{ month: string; total_credits_used: number; by_type: SummaryRow[] }>({
    queryKey: ['credits-summary'],
    queryFn: () => creditsApi.summary(),
    staleTime: 60_000,
  })

  const { data: prices } = useQuery<{ actions: { action: string; label: string }[] }>({
    queryKey: ['credits-price-list'],
    queryFn: creditsApi.priceList,
    staleTime: 10 * 60_000,
  })

  const params = {
    usage_type: usageType || undefined,
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
    page,
    page_size: PAGE_SIZE,
  }
  const { data: ledger, isLoading, isError, isFetching, refetch } = useQuery<LedgerPage>({
    queryKey: ['credits-usage', params],
    queryFn: () => creditsApi.usage(params),
    placeholderData: keepPreviousData,
  })

  const totalPages = ledger ? Math.max(1, Math.ceil(ledger.total / PAGE_SIZE)) : 1
  const resetPage = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1) }

  const downloadCsv = () => {
    if (!ledger?.items.length) return
    const blob = new Blob([ledgerToCsv(ledger.items)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `credit-history-page-${page}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const credits = usage?.metered ? usage.credits : undefined
  const topActions = (summary?.by_type ?? []).slice().sort((a, b) => b.total_credits - a.total_credits)

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <Link href="/dashboard/billing" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
          <ArrowLeft className="h-4 w-4" /> Billing
        </Link>
        <h1 className="mt-1 flex items-center gap-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
          <History className="h-6 w-6 text-blue-600" aria-hidden="true" /> Credit history
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">Every credit charged or added on this workspace.</p>
      </div>

      {/* Summary */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            <Coins className="h-3.5 w-3.5" /> Credits left
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-100">
            {credits ? fmt(Math.round(credits.total)) : '—'}
          </p>
          {credits && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {fmt(Math.round(credits.allowance))} allowance{credits.topup > 0 ? ` · ${fmt(Math.round(credits.topup))} purchased` : ''}
            </p>
          )}
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Used this month</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-100">
            {summary ? fmt(summary.total_credits_used) : '—'}
          </p>
          {credits && <p className="text-xs text-gray-500 dark:text-gray-400">of {fmt(credits.plan_allowance)} monthly allowance</p>}
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Where it went this month</p>
          {topActions.length === 0 ? (
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">No credits used yet.</p>
          ) : (
            <ul className="mt-2 space-y-1 text-sm">
              {topActions.slice(0, 4).map((r) => (
                <li key={r.usage_type} className="flex justify-between gap-2 text-gray-700 dark:text-gray-300">
                  <span className="truncate">{r.label} <span className="text-gray-400">×{fmt(r.count)}</span></span>
                  <span className="tabular-nums">{fmt(r.total_credits)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <label className="flex flex-col gap-1 text-xs font-medium text-gray-600 dark:text-gray-300">
          Action
          <select
            value={usageType}
            onChange={(e) => resetPage(setUsageType)(e.target.value)}
            className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
          >
            <option value="">All actions</option>
            {(prices?.actions ?? []).map((a) => (
              <option key={a.action} value={a.action}>{a.label}</option>
            ))}
            <option value="topup_purchase">Credits purchased</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-gray-600 dark:text-gray-300">
          From
          <input type="date" value={fromDate} onChange={(e) => resetPage(setFromDate)(e.target.value)}
            className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100" />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-gray-600 dark:text-gray-300">
          To
          <input type="date" value={toDate} onChange={(e) => resetPage(setToDate)(e.target.value)}
            className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100" />
        </label>
        {(usageType || fromDate || toDate) && (
          <button
            onClick={() => { setUsageType(''); setFromDate(''); setToDate(''); setPage(1) }}
            className="text-sm text-blue-600 hover:underline dark:text-blue-400"
          >
            Clear filters
          </button>
        )}
        <div className="ml-auto flex gap-2">
          <button onClick={() => refetch()} className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700">
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} /> Refresh
          </button>
          <button onClick={downloadCsv} disabled={!ledger?.items.length} className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700">
            <Download className="h-4 w-4" /> CSV
          </button>
        </div>
      </div>

      {/* Ledger */}
      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
        <table className="min-w-full divide-y divide-gray-200 text-sm dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-900/40">
            <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
              <th className="px-4 py-2">Date</th>
              <th className="px-4 py-2">Action</th>
              <th className="px-4 py-2">Type</th>
              <th className="px-4 py-2 text-right">Credits</th>
              <th className="px-4 py-2">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {isLoading && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">Loading…</td></tr>
            )}
            {isError && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-red-600 dark:text-red-400">Could not load credit history.</td></tr>
            )}
            {ledger && ledger.items.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">No credit activity for these filters.</td></tr>
            )}
            {ledger?.items.map((i) => (
              <tr key={i.usage_id} className="text-gray-700 dark:text-gray-200">
                <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-500 dark:text-gray-400">
                  {i.recorded_at ? new Date(i.recorded_at + (i.recorded_at.endsWith('Z') ? '' : 'Z')).toLocaleString() : '—'}
                </td>
                <td className="px-4 py-2 font-medium">{i.label}</td>
                <td className="px-4 py-2"><CategoryBadge category={i.category} /></td>
                <td className={`whitespace-nowrap px-4 py-2 text-right tabular-nums font-medium ${i.credits_used < 0 ? 'text-green-700 dark:text-green-400' : ''}`}>
                  {formatLedgerCredits(i.credits_used)}
                </td>
                <td className="max-w-md px-4 py-2 text-gray-500 dark:text-gray-400">
                  <span className="line-clamp-2">{i.description || '—'}</span>
                  {i.reference_id && <span className="text-xs text-gray-400"> · ref {i.reference_id}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {ledger && ledger.total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-gray-600 dark:text-gray-300">
          <span>{fmt(ledger.total)} entries · page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-md border border-gray-300 px-3 py-1.5 disabled:opacity-50 dark:border-gray-600">Previous</button>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded-md border border-gray-300 px-3 py-1.5 disabled:opacity-50 dark:border-gray-600">Next</button>
          </div>
        </div>
      )}
    </div>
  )
}
