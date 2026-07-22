'use client'

import { useState, useEffect, useCallback } from 'react'
import { attributionApi } from '@/lib/api'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from 'recharts'
import {
  RefreshCw, DollarSign, Award, FileCheck, Handshake, TrendingUp, Info,
} from 'lucide-react'

interface BySource { source: string; events: number; amount: number }
interface RecentRow {
  event_type: string; source: string | null; lead_id: number | null
  external_ref: string | null; amount: number | null
  occurred_at: string | null; created_at: string | null
}
interface Summary {
  totals: { offers_accepted: number; placements: number; invoices_paid: number; revenue_paid: number }
  by_source: BySource[]
  by_event: Record<string, number>
  recent: RecentRow[]
}

const BAR_COLORS = ['#2563eb', '#7c3aed', '#0d9488', '#d97706', '#db2777', '#059669', '#dc2626']

const fmtMoney = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n || 0)

const EVENT_LABEL: Record<string, string> = {
  'offer.accepted': 'Offer accepted',
  'placement.created': 'Placement',
  'invoice.paid': 'Invoice paid',
}

function KpiCard({ icon, label, value, accent }: { icon: React.ReactNode; label: string; value: string; accent: string }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 min-w-0">
      <div className="flex items-center gap-3">
        <div className={`shrink-0 w-10 h-10 rounded-lg flex items-center justify-center ${accent}`}>{icon}</div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 truncate">{label}</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 truncate">{value}</p>
        </div>
      </div>
    </div>
  )
}

export default function AttributionPage() {
  const [data, setData] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [preset, setPreset] = useState<'all' | '7d' | '30d' | '90d' | 'ytd' | 'custom'>('all')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')

  const rangeParams = useCallback((): { start?: string; end?: string } => {
    const fmt = (d: Date) => d.toISOString().slice(0, 10)
    const today = new Date()
    if (preset === 'custom') {
      const p: { start?: string; end?: string } = {}
      if (customStart) p.start = customStart
      if (customEnd) p.end = customEnd
      return p
    }
    if (preset === 'all') return {}
    const start = new Date(today)
    if (preset === '7d') start.setDate(today.getDate() - 6)
    else if (preset === '30d') start.setDate(today.getDate() - 29)
    else if (preset === '90d') start.setDate(today.getDate() - 89)
    else if (preset === 'ytd') { start.setMonth(0); start.setDate(1) }
    return { start: fmt(start), end: fmt(today) }
  }, [preset, customStart, customEnd])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await attributionApi.summary(rangeParams()))
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load attribution data')
    } finally {
      setLoading(false)
    }
  }, [rangeParams])

  useEffect(() => { load() }, [load])

  const t = data?.totals
  const empty = !loading && !error && (data?.recent?.length ?? 0) === 0
  const chartData = (data?.by_source || []).slice(0, 8).map((s) => ({ name: s.source || 'unknown', revenue: s.amount || 0, events: s.events }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <TrendingUp className="w-6 h-6 text-emerald-500 shrink-0" /> Revenue Attribution
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Campaign → placement → revenue, sourced from Resource Pool outcomes.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={preset}
            onChange={(e) => setPreset(e.target.value as typeof preset)}
            aria-label="Date range"
            className="text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 px-3 py-2"
          >
            <option value="all">All time</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
            <option value="ytd">Year to date</option>
            <option value="custom">Custom…</option>
          </select>
          {preset === 'custom' && (
            <>
              <input
                type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)}
                aria-label="Start date"
                className="text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 px-2 py-2"
              />
              <span className="text-gray-400 text-sm">–</span>
              <input
                type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)}
                aria-label="End date"
                className="text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 px-2 py-2"
              />
            </>
          )}
          <button
            onClick={load}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard icon={<Handshake className="w-5 h-5 text-blue-600" />} accent="bg-blue-100 dark:bg-blue-900/40" label="Offers accepted" value={loading ? '—' : String(t?.offers_accepted ?? 0)} />
        <KpiCard icon={<Award className="w-5 h-5 text-violet-600" />} accent="bg-violet-100 dark:bg-violet-900/40" label="Placements" value={loading ? '—' : String(t?.placements ?? 0)} />
        <KpiCard icon={<FileCheck className="w-5 h-5 text-teal-600" />} accent="bg-teal-100 dark:bg-teal-900/40" label="Invoices paid" value={loading ? '—' : String(t?.invoices_paid ?? 0)} />
        <KpiCard icon={<DollarSign className="w-5 h-5 text-emerald-600" />} accent="bg-emerald-100 dark:bg-emerald-900/40" label="Revenue (paid)" value={loading ? '—' : fmtMoney(t?.revenue_paid ?? 0)} />
      </div>

      {empty && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-8 text-center text-sm text-gray-500 dark:text-gray-400">
          <Info className="w-6 h-6 mx-auto mb-2 text-gray-400" />
          {preset === 'all'
            ? 'No attribution yet. Outcomes (offers, placements, paid invoices) from Resource Pool will appear here, mapped back to the campaign and source that produced them.'
            : 'No attribution in the selected date range.'}
        </div>
      )}

      {!empty && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Revenue by source (chart) */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 min-w-0">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3">Revenue by source</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={50} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : String(v))} />
                  <Tooltip formatter={(v: number) => fmtMoney(v)} />
                  <Bar dataKey="revenue" radius={[4, 4, 0, 0]}>
                    {chartData.map((_, i) => <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* By source (table) */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 min-w-0">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3">Source breakdown</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                    <th className="py-2 pr-3 font-medium">Source</th>
                    <th className="py-2 px-3 font-medium text-right">Outcomes</th>
                    <th className="py-2 pl-3 font-medium text-right">Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {(data?.by_source || []).map((s) => (
                    <tr key={s.source} className="text-gray-800 dark:text-gray-200">
                      <td className="py-2 pr-3 truncate max-w-[160px]">{s.source || 'unknown'}</td>
                      <td className="py-2 px-3 text-right">{s.events}</td>
                      <td className="py-2 pl-3 text-right font-medium">{fmtMoney(s.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Recent outcomes */}
      {!empty && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 min-w-0">
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3">Recent outcomes</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  <th className="py-2 pr-3 font-medium">Outcome</th>
                  <th className="py-2 px-3 font-medium">Source</th>
                  <th className="py-2 px-3 font-medium">Lead</th>
                  <th className="py-2 px-3 font-medium text-right">Amount</th>
                  <th className="py-2 pl-3 font-medium">When</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {(data?.recent || []).map((r, i) => (
                  <tr key={i} className="text-gray-800 dark:text-gray-200">
                    <td className="py-2 pr-3 whitespace-nowrap">
                      <span className="inline-flex items-center rounded-full bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs">
                        {EVENT_LABEL[r.event_type] || r.event_type}
                      </span>
                    </td>
                    <td className="py-2 px-3 truncate max-w-[140px]">{r.source || '—'}</td>
                    <td className="py-2 px-3 whitespace-nowrap text-gray-500 dark:text-gray-400">
                      {r.lead_id ? `#${r.lead_id}` : (r.external_ref || '—')}
                    </td>
                    <td className="py-2 px-3 text-right">{r.amount != null ? fmtMoney(r.amount) : '—'}</td>
                    <td className="py-2 pl-3 whitespace-nowrap text-gray-500 dark:text-gray-400">
                      {(r.occurred_at || r.created_at)?.slice(0, 10) || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
