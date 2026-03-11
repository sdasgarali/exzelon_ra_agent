'use client'

import { useState, useEffect } from 'react'
import axios from 'axios'
import { api } from '@/lib/api'
import {
  DollarSign, TrendingUp, Target, Award, BarChart3, Users,
  Plus, Loader2, AlertCircle, Receipt, Trash2, Bot,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

// ---------- Types ----------

interface RevenueMetrics {
  total_won_value: number
  avg_deal_size: number
  pipeline_value: number
  win_rate: number
  roi_percent: number
  cost_per_lead: number
}

interface CampaignRow {
  campaign_id: number
  name: string
  status: string
  total_contacts: number
  sent: number
  replied: number
  reply_rate: number
  bounce_rate: number
}

interface LeaderboardRow {
  user_id: number
  name: string
  role: string
  emails_sent: number
  deals_won: number
  total_won_value: number
}

interface CostEntry {
  cost_id: number
  category: string
  amount: number
  date: string
  entry_date: string
  notes: string
  source_adapter: string | null
  is_automated: boolean
  api_calls_count: number | null
  results_count: number | null
  created_at: string
}

interface CostBySource {
  source: string
  total_cost: number
  total_api_calls: number
  total_results: number
  entry_count: number
  cost_per_lead: number | null
}

// ---------- Helpers ----------

const fmtCurrency = (v: number) => {
  if (v == null || isNaN(v)) return '$0'
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}K`
  return `$${v.toFixed(0)}`
}

const statusBadge = (s: string) => {
  const map: Record<string, string> = {
    draft: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
    active: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
    paused: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
    completed: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
    archived: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  }
  return map[s] || map.draft
}

const COST_CATEGORIES = [
  'Email Infrastructure',
  'Data / Lead Lists',
  'API Subscriptions',
  'Tools & Software',
  'Domain & Hosting',
  'Advertising',
  'Personnel',
  'Other',
]

// ---------- Component ----------

export default function AnalyticsPage() {
  // Revenue metrics
  const [revenue, setRevenue] = useState<RevenueMetrics | null>(null)
  const [revenueLoading, setRevenueLoading] = useState(true)
  const [revenueError, setRevenueError] = useState('')

  // Campaign comparison
  const [campaigns, setCampaigns] = useState<CampaignRow[]>([])
  const [campaignsLoading, setCampaignsLoading] = useState(true)
  const [campaignsError, setCampaignsError] = useState('')

  // Team leaderboard
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([])
  const [leaderboardLoading, setLeaderboardLoading] = useState(true)
  const [leaderboardError, setLeaderboardError] = useState('')

  // Cost tracking
  const [costs, setCosts] = useState<CostEntry[]>([])
  const [costsLoading, setCostsLoading] = useState(true)
  const [costsError, setCostsError] = useState('')
  const [costForm, setCostForm] = useState({ category: COST_CATEGORIES[0], amount: '', date: '', notes: '' })
  const [costSaving, setCostSaving] = useState(false)
  const [showCostForm, setShowCostForm] = useState(false)
  const [costDeleting, setCostDeleting] = useState<number | null>(null)

  // Cost by source
  const [costsBySource, setCostsBySource] = useState<CostBySource[]>([])
  const [costsBySourceLoading, setCostsBySourceLoading] = useState(true)

  // ---------- Data fetching ----------

  useEffect(() => {
    fetchRevenue()
    fetchCampaigns()
    fetchLeaderboard()
    fetchCosts()
    fetchCostsBySource()
  }, [])

  const fetchRevenue = async () => {
    setRevenueLoading(true)
    setRevenueError('')
    try {
      const { data } = await api.get('/analytics/revenue', { params: { days: 90 } })
      setRevenue(data)
    } catch (err: any) {
      if (axios.isCancel(err)) return
      setRevenueError(err?.response?.data?.detail || 'Failed to load revenue metrics')
    }
    setRevenueLoading(false)
  }

  const fetchCampaigns = async () => {
    setCampaignsLoading(true)
    setCampaignsError('')
    try {
      const { data } = await api.get('/analytics/campaign-comparison')
      setCampaigns(data?.campaigns || data || [])
    } catch (err: any) {
      if (axios.isCancel(err)) return
      setCampaignsError(err?.response?.data?.detail || 'Failed to load campaign data')
    }
    setCampaignsLoading(false)
  }

  const fetchLeaderboard = async () => {
    setLeaderboardLoading(true)
    setLeaderboardError('')
    try {
      const { data } = await api.get('/analytics/team-leaderboard', { params: { days: 30 } })
      setLeaderboard(data?.leaderboard || data || [])
    } catch (err: any) {
      if (axios.isCancel(err)) return
      setLeaderboardError(err?.response?.data?.detail || 'Failed to load leaderboard')
    }
    setLeaderboardLoading(false)
  }

  const fetchCosts = async () => {
    setCostsLoading(true)
    setCostsError('')
    try {
      const { data } = await api.get('/analytics/costs')
      setCosts(data?.costs || data || [])
    } catch (err: any) {
      if (axios.isCancel(err)) return
      setCostsError(err?.response?.data?.detail || 'Failed to load cost data')
    }
    setCostsLoading(false)
  }

  const fetchCostsBySource = async () => {
    setCostsBySourceLoading(true)
    try {
      const { data } = await api.get('/analytics/costs/per-source', { params: { days: 30 } })
      setCostsBySource(data?.sources || [])
    } catch {
      // silently fail — chart is supplementary
    }
    setCostsBySourceLoading(false)
  }

  const handleAddCost = async () => {
    if (!costForm.amount || !costForm.date) return
    setCostSaving(true)
    try {
      await api.post('/analytics/costs', {
        category: costForm.category,
        amount: parseFloat(costForm.amount),
        entry_date: costForm.date,
        notes: costForm.notes,
      })
      setCostForm({ category: COST_CATEGORIES[0], amount: '', date: '', notes: '' })
      setShowCostForm(false)
      await fetchCosts()
    } catch (err: any) {
      setCostsError(err?.response?.data?.detail || 'Failed to add cost entry')
    }
    setCostSaving(false)
  }

  const handleDeleteCost = async (costId: number) => {
    setCostDeleting(costId)
    try {
      await api.delete(`/analytics/costs/${costId}`)
      await fetchCosts()
      await fetchCostsBySource()
    } catch (err: any) {
      setCostsError(err?.response?.data?.detail || 'Failed to delete cost entry')
    }
    setCostDeleting(null)
  }

  // ---------- Chart data ----------

  const campaignChartData = campaigns.slice(0, 8).map(c => ({
    name: c.name.length > 18 ? c.name.substring(0, 18) + '...' : c.name,
    Sent: c.sent,
    Replied: c.replied,
  }))

  // ---------- Render helpers ----------

  const renderError = (msg: string) => (
    <div className="flex items-center gap-2 text-red-600 dark:text-red-400 text-sm py-4 justify-center">
      <AlertCircle className="w-4 h-4" /> {msg}
    </div>
  )

  const renderSpinner = () => (
    <div className="flex items-center justify-center py-8">
      <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
    </div>
  )

  // ---------- Layout ----------

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Analytics</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">Revenue, campaigns, team performance, and cost tracking</p>
      </div>

      {/* ─── Revenue Metrics Cards ────────────────────────────────── */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-green-600" /> Revenue Metrics
          <span className="text-xs font-normal text-gray-400 ml-1">(last 90 days)</span>
        </h2>
        {revenueLoading ? renderSpinner() : revenueError ? renderError(revenueError) : revenue && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {[
              { label: 'Total Won Value', value: fmtCurrency(revenue.total_won_value), icon: DollarSign, color: 'text-green-600' },
              { label: 'Avg Deal Size', value: fmtCurrency(revenue.avg_deal_size), icon: TrendingUp, color: 'text-blue-600' },
              { label: 'Pipeline Value', value: fmtCurrency(revenue.pipeline_value), icon: Target, color: 'text-purple-600' },
              { label: 'Win Rate', value: `${revenue.win_rate.toFixed(1)}%`, icon: Award, color: 'text-amber-600' },
              { label: 'ROI', value: `${revenue.roi_percent.toFixed(1)}%`, icon: BarChart3, color: 'text-indigo-600' },
              { label: 'Cost per Lead', value: fmtCurrency(revenue.cost_per_lead), icon: Receipt, color: 'text-red-500' },
            ].map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 text-sm mb-1">
                  <Icon className={`w-4 h-4 ${color}`} /> {label}
                </div>
                <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{value}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ─── Campaign Comparison ──────────────────────────────────── */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-blue-600" /> Campaign Comparison
        </h2>
        {campaignsLoading ? renderSpinner() : campaignsError ? renderError(campaignsError) : (
          <>
            {/* Chart */}
            {campaignChartData.length > 0 && (
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 mb-4">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={campaignChartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: 8, color: '#fff' }} />
                    <Legend />
                    <Bar dataKey="Sent" fill="#6366f1" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Replied" fill="#22c55e" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            {/* Table */}
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 dark:bg-gray-700/50">
                    <tr>
                      {['Campaign', 'Status', 'Contacts', 'Sent', 'Replied', 'Reply Rate', 'Bounce Rate'].map(h => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {campaigns.length === 0 ? (
                      <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">No campaign data available</td></tr>
                    ) : campaigns.map(c => (
                      <tr key={c.campaign_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100 max-w-[200px] truncate">{c.name}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${statusBadge(c.status)}`}>{c.status}</span>
                        </td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{c.total_contacts.toLocaleString()}</td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{c.sent.toLocaleString()}</td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{c.replied.toLocaleString()}</td>
                        <td className="px-4 py-3 font-medium text-green-600 dark:text-green-400">{c.reply_rate.toFixed(1)}%</td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{c.bounce_rate.toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </section>

      {/* ─── Team Leaderboard ─────────────────────────────────────── */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
          <Users className="w-5 h-5 text-amber-600" /> Team Leaderboard
          <span className="text-xs font-normal text-gray-400 ml-1">(last 30 days)</span>
        </h2>
        {leaderboardLoading ? renderSpinner() : leaderboardError ? renderError(leaderboardError) : (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-700/50">
                  <tr>
                    {['Rank', 'Name', 'Role', 'Emails Sent', 'Deals Won', 'Won Value'].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {leaderboard.length === 0 ? (
                    <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">No leaderboard data available</td></tr>
                  ) : leaderboard.map((row, idx) => {
                    const rank = idx + 1
                    return (
                    <tr key={row.user_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold ${
                          rank === 1 ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300' :
                          rank === 2 ? 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-200' :
                          rank === 3 ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300' :
                          'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                        }`}>{rank}</span>
                      </td>
                      <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{row.name}</td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400 capitalize">{row.role.replace('_', ' ')}</td>
                      <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{row.emails_sent.toLocaleString()}</td>
                      <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{row.deals_won}</td>
                      <td className="px-4 py-3 font-semibold text-green-600 dark:text-green-400">{fmtCurrency(row.total_won_value)}</td>
                    </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {/* ─── Cost Tracking ────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Receipt className="w-5 h-5 text-red-500" /> Cost Tracking
          </h2>
          <button
            onClick={() => setShowCostForm(!showCostForm)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Plus className="w-4 h-4" /> Add Cost
          </button>
        </div>

        {/* Cost by Source Chart */}
        {!costsBySourceLoading && costsBySource.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 mb-4">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Cost by Source (last 30 days)</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={costsBySource} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                <XAxis dataKey="source" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: 8, color: '#fff' }}
                  formatter={(value: number, name: string) => {
                    if (name === 'Cost') return [`$${value.toFixed(2)}`, name]
                    if (name === 'Cost/Lead') return [value != null ? `$${value.toFixed(4)}` : 'N/A', name]
                    return [value, name]
                  }}
                />
                <Legend />
                <Bar dataKey="total_cost" name="Cost" fill="#ef4444" radius={[4, 4, 0, 0]} />
                <Bar dataKey="cost_per_lead" name="Cost/Lead" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-4 mt-3 text-xs text-gray-500 dark:text-gray-400">
              {costsBySource.map(s => (
                <span key={s.source}>
                  <span className="font-medium text-gray-700 dark:text-gray-300">{s.source}</span>: {s.total_api_calls} calls, {s.total_results} results
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Add Cost Form */}
        {showCostForm && (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 mb-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Category</label>
                <select
                  value={costForm.category}
                  onChange={e => setCostForm(f => ({ ...f, category: e.target.value }))}
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                >
                  {COST_CATEGORIES.map(cat => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Amount ($)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={costForm.amount}
                  onChange={e => setCostForm(f => ({ ...f, amount: e.target.value }))}
                  placeholder="0.00"
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Date</label>
                <input
                  type="date"
                  value={costForm.date}
                  onChange={e => setCostForm(f => ({ ...f, date: e.target.value }))}
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Notes</label>
                <input
                  type="text"
                  value={costForm.notes}
                  onChange={e => setCostForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="Optional description"
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => setShowCostForm(false)}
                className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleAddCost}
                disabled={!costForm.amount || !costForm.date || costSaving}
                className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors flex items-center gap-1.5"
              >
                {costSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                {costSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        )}

        {/* Costs Table */}
        {costsLoading ? renderSpinner() : costsError ? renderError(costsError) : (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-700/50">
                  <tr>
                    {['Category', 'Source', 'Amount', 'Date', 'Notes', ''].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {costs.length === 0 ? (
                    <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">No cost entries yet. Click &quot;Add Cost&quot; to start tracking expenses.</td></tr>
                  ) : costs.map(c => (
                    <tr key={c.cost_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300">{c.category}</span>
                          {c.is_automated && (
                            <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" title="Auto-tracked by pipeline">
                              <Bot className="w-3 h-3" /> Auto
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-600 dark:text-gray-300 text-xs">
                        {c.source_adapter ? (
                          <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300 font-medium">{c.source_adapter}</span>
                        ) : '-'}
                      </td>
                      <td className="px-4 py-3 font-semibold text-red-600 dark:text-red-400">${parseFloat(String(c.amount)).toFixed(2)}</td>
                      <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{new Date(c.entry_date || c.date).toLocaleDateString()}</td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400 max-w-[250px] truncate">{c.notes || '-'}</td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => handleDeleteCost(c.cost_id)}
                          disabled={costDeleting === c.cost_id}
                          className="p-1 text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors disabled:opacity-50"
                          title="Delete cost entry"
                        >
                          {costDeleting === c.cost_id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
