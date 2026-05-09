'use client'

import { useState, useEffect, useCallback } from 'react'
import { reportsApi } from '@/lib/api'
import type {
  PaginatedResponse,
  ClientAnalyticsRow,
  CampaignPerformanceRow,
  MailboxHealthRow,
  DailyActivityResponse,
  ContactEngagementRow,
  DomainDeliverabilityRow,
} from '@/types/api'
import {
  Building,
  Zap,
  Inbox,
  BarChart3,
  Users,
  Mail,
  Search,
  Download,
  ChevronUp,
  ChevronDown,
  ArrowLeft,
  ArrowRight,
  RefreshCw,
  Calendar,
} from 'lucide-react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from 'recharts'

// ─── Helpers ─────────────────────────────────────────────────────────

function exportToXlsx(data: Record<string, any>[], filename: string) {
  import('xlsx').then((XLSX) => {
    const ws = XLSX.utils.json_to_sheet(data)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Report')
    XLSX.writeFile(wb, `${filename}.xlsx`)
  })
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    active: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
    draft: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
    paused: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
    completed: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
    archived: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
    warming_up: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300',
    cold_ready: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/40 dark:text-cyan-300',
    inactive: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    blacklisted: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    recovering: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium capitalize ${colors[status] || colors.draft}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

function ConnectionDot({ status }: { status: string }) {
  const color = status === 'connected' ? 'bg-green-500' : status === 'failed' ? 'bg-red-500' : 'bg-gray-400'
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${color}`} title={status} />
}

function HealthBar({ score }: { score: number | null }) {
  if (score == null) return <span className="text-gray-400 text-xs">--</span>
  const color = score >= 80 ? 'bg-green-500' : score >= 50 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(score, 100)}%` }} />
      </div>
      <span className="text-xs text-gray-600 dark:text-gray-400">{score}</span>
    </div>
  )
}

function SortHeader({
  label, field, current, order, onSort,
}: { label: string; field: string; current: string; order: string; onSort: (f: string) => void }) {
  const active = current === field
  return (
    <th
      className="px-3 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none"
      onClick={() => onSort(field)}
    >
      <div className="flex items-center gap-1">
        {label}
        {active ? (
          order === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
        ) : (
          <ChevronUp className="w-3 h-3 opacity-20" />
        )}
      </div>
    </th>
  )
}

function Pagination({
  page, pages, total, onPage,
}: { page: number; pages: number; total: number; onPage: (p: number) => void }) {
  if (pages <= 1) return null
  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 text-sm">
      <span className="text-gray-500 dark:text-gray-400">{total} results</span>
      <div className="flex items-center gap-2">
        <button disabled={page <= 1} onClick={() => onPage(page - 1)} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-30">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <span className="text-gray-600 dark:text-gray-300">Page {page} of {pages}</span>
        <button disabled={page >= pages} onClick={() => onPage(page + 1)} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-30">
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 text-center">
      <div className="text-2xl font-bold text-gray-900 dark:text-white">{typeof value === 'number' ? value.toLocaleString() : value}</div>
      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{label}</div>
    </div>
  )
}

// ─── Tabs ─────────────────────────────────────────────────────────

type TabKey = 'client' | 'campaign' | 'mailbox' | 'activity' | 'engagement' | 'domain'

const TABS: { key: TabKey; label: string; icon: typeof Building }[] = [
  { key: 'client', label: 'Client Analytics', icon: Building },
  { key: 'campaign', label: 'Campaign Performance', icon: Zap },
  { key: 'mailbox', label: 'Mailbox Health', icon: Inbox },
  { key: 'activity', label: 'Daily Activity', icon: BarChart3 },
  { key: 'engagement', label: 'Contact Engagement', icon: Users },
  { key: 'domain', label: 'Domain Deliverability', icon: Mail },
]

// ─── Main Component ──────────────────────────────────────────────

export default function ReportsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('client')

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Reports</h1>
      </div>

      {/* Tab bar */}
      <div className="border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
        <nav className="flex space-x-1 min-w-max" role="tablist">
          {TABS.map((tab) => {
            const Icon = tab.icon
            const active = activeTab === tab.key
            return (
              <button
                key={tab.key}
                role="tab"
                aria-selected={active}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                  active
                    ? 'border-primary-600 text-primary-600 dark:text-primary-400'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            )
          })}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === 'client' && <ClientAnalyticsTab />}
      {activeTab === 'campaign' && <CampaignPerformanceTab />}
      {activeTab === 'mailbox' && <MailboxHealthTab />}
      {activeTab === 'activity' && <DailyActivityTab />}
      {activeTab === 'engagement' && <ContactEngagementTab />}
      {activeTab === 'domain' && <DomainDeliverabilityTab />}
    </div>
  )
}


// =====================================================================
// TAB 1: Client Analytics
// =====================================================================

function ClientAnalyticsTab() {
  const [data, setData] = useState<PaginatedResponse<ClientAnalyticsRow>>({ items: [], total: 0, page: 1, page_size: 50, pages: 0 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [industry, setIndustry] = useState('')
  const [category, setCategory] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [sortBy, setSortBy] = useState('client_name')
  const [sortOrder, setSortOrder] = useState('asc')
  const [page, setPage] = useState(1)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const result = await reportsApi.clientAnalytics({
        search: search || undefined,
        industry: industry || undefined,
        client_category: category || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        page,
        page_size: 50,
      })
      setData(result)
    } catch { /* ignore */ }
    setLoading(false)
  }, [search, industry, category, dateFrom, dateTo, sortBy, sortOrder, page])

  useEffect(() => { fetchData() }, [fetchData])

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      setSortOrder('asc')
    }
    setPage(1)
  }

  const handleExport = async () => {
    try {
      const result = await reportsApi.clientAnalytics({
        search: search || undefined,
        industry: industry || undefined,
        client_category: category || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        export: true,
      })
      exportToXlsx(result.items, 'client-analytics')
    } catch { /* ignore */ }
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search clients..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <select value={industry} onChange={(e) => { setIndustry(e.target.value); setPage(1) }} className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2">
          <option value="">All Industries</option>
          <option value="IT Services and IT Consulting">IT Services</option>
          <option value="Staffing and Recruiting">Staffing</option>
          <option value="Healthcare">Healthcare</option>
          <option value="Financial Services">Financial</option>
          <option value="Manufacturing">Manufacturing</option>
        </select>
        <select value={category} onChange={(e) => { setCategory(e.target.value); setPage(1) }} className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2">
          <option value="">All Categories</option>
          <option value="regular">Regular</option>
          <option value="occasional">Occasional</option>
          <option value="prospect">Prospect</option>
          <option value="dormant">Dormant</option>
        </select>
        <div className="flex items-center gap-1 text-sm text-gray-500">
          <Calendar className="w-4 h-4" />
          <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} className="border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-2 py-1.5 text-sm" />
          <span>-</span>
          <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1) }} className="border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-2 py-1.5 text-sm" />
        </div>
        <button onClick={handleExport} className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
          <Download className="w-4 h-4" /> Export
        </button>
        <button onClick={fetchData} className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <SortHeader label="Client" field="client_name" current={sortBy} order={sortOrder} onSort={handleSort} />
                <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Industry</th>
                <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Category</th>
                <SortHeader label="Contacts" field="contacts" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Leads" field="leads" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Sent" field="sent" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Replies" field="replied" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Bounces" field="bounced" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Placements" field="placements" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Unsubs" field="unsubscribed" current={sortBy} order={sortOrder} onSort={handleSort} />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {loading ? (
                <tr><td colSpan={10} className="px-3 py-12 text-center text-gray-500">Loading...</td></tr>
              ) : data.items.length === 0 ? (
                <tr><td colSpan={10} className="px-3 py-12 text-center text-gray-500">No client data found</td></tr>
              ) : data.items.map((row, i) => (
                <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-3 py-2.5 text-sm font-medium text-gray-900 dark:text-white whitespace-nowrap">{row.client_name}</td>
                  <td className="px-3 py-2.5 text-sm text-gray-500 dark:text-gray-400 max-w-[140px] truncate">{row.industry || '--'}</td>
                  <td className="px-3 py-2.5"><StatusBadge status={row.client_category || 'prospect'} /></td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.contacts}</td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.leads}</td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.sent}</td>
                  <td className="px-3 py-2.5 text-sm text-right">
                    <span className="text-gray-700 dark:text-gray-300">{row.replied}</span>
                    {row.reply_rate > 0 && <span className="ml-1 text-xs text-green-600">({row.reply_rate}%)</span>}
                  </td>
                  <td className="px-3 py-2.5 text-sm text-right">
                    <span className="text-gray-700 dark:text-gray-300">{row.bounced}</span>
                    {row.bounce_rate > 0 && <span className="ml-1 text-xs text-red-500">({row.bounce_rate}%)</span>}
                  </td>
                  <td className="px-3 py-2.5 text-sm text-right">
                    <span className="text-gray-700 dark:text-gray-300">{row.placements}</span>
                    {row.placement_rate > 0 && <span className="ml-1 text-xs text-blue-500">({row.placement_rate}%)</span>}
                  </td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.unsubscribed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />
      </div>
    </div>
  )
}


// =====================================================================
// TAB 2: Campaign Performance
// =====================================================================

function CampaignPerformanceTab() {
  const [data, setData] = useState<PaginatedResponse<CampaignPerformanceRow>>({ items: [], total: 0, page: 1, page_size: 50, pages: 0 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [sortBy, setSortBy] = useState('created_at')
  const [sortOrder, setSortOrder] = useState('desc')
  const [page, setPage] = useState(1)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const result = await reportsApi.campaignPerformance({
        search: search || undefined,
        status: status || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        page,
        page_size: 50,
      })
      setData(result)
    } catch { /* ignore */ }
    setLoading(false)
  }, [search, status, dateFrom, dateTo, sortBy, sortOrder, page])

  useEffect(() => { fetchData() }, [fetchData])

  const handleSort = (field: string) => {
    if (sortBy === field) setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    else { setSortBy(field); setSortOrder('desc') }
    setPage(1)
  }

  const handleExport = async () => {
    try {
      const result = await reportsApi.campaignPerformance({
        search: search || undefined,
        status: status || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        export: true,
      })
      exportToXlsx(result.items, 'campaign-performance')
    } catch { /* ignore */ }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input type="text" placeholder="Search campaigns..." value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-primary-500" />
        </div>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2">
          <option value="">All Statuses</option>
          <option value="draft">Draft</option>
          <option value="active">Active</option>
          <option value="paused">Paused</option>
          <option value="completed">Completed</option>
        </select>
        <div className="flex items-center gap-1 text-sm text-gray-500">
          <Calendar className="w-4 h-4" />
          <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} className="border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-2 py-1.5 text-sm" />
          <span>-</span>
          <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1) }} className="border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-2 py-1.5 text-sm" />
        </div>
        <button onClick={handleExport} className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
          <Download className="w-4 h-4" /> Export
        </button>
        <button onClick={fetchData} className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <SortHeader label="Campaign" field="name" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Status" field="status" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Contacts" field="total_contacts" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Sent" field="sent" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Opened" field="total_opened" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Replied" field="total_replied" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Bounced" field="total_bounced" current={sortBy} order={sortOrder} onSort={handleSort} />
                <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Unsubs</th>
                <SortHeader label="Health" field="health_score" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Created" field="created_at" current={sortBy} order={sortOrder} onSort={handleSort} />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {loading ? (
                <tr><td colSpan={10} className="px-3 py-12 text-center text-gray-500">Loading...</td></tr>
              ) : data.items.length === 0 ? (
                <tr><td colSpan={10} className="px-3 py-12 text-center text-gray-500">No campaigns found</td></tr>
              ) : data.items.map((row) => (
                <tr key={row.campaign_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-3 py-2.5 text-sm font-medium text-gray-900 dark:text-white whitespace-nowrap max-w-[200px] truncate">{row.name}</td>
                  <td className="px-3 py-2.5"><StatusBadge status={row.status} /></td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.total_contacts}</td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.sent}</td>
                  <td className="px-3 py-2.5 text-sm text-right">
                    <span className="text-gray-700 dark:text-gray-300">{row.opened}</span>
                    {row.open_rate > 0 && <span className="ml-1 text-xs text-blue-500">({row.open_rate}%)</span>}
                  </td>
                  <td className="px-3 py-2.5 text-sm text-right">
                    <span className="text-gray-700 dark:text-gray-300">{row.replied}</span>
                    {row.reply_rate > 0 && <span className="ml-1 text-xs text-green-600">({row.reply_rate}%)</span>}
                  </td>
                  <td className="px-3 py-2.5 text-sm text-right">
                    <span className="text-gray-700 dark:text-gray-300">{row.bounced}</span>
                    {row.bounce_rate > 0 && <span className="ml-1 text-xs text-red-500">({row.bounce_rate}%)</span>}
                  </td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.unsubscribed}</td>
                  <td className="px-3 py-2.5"><HealthBar score={row.health_score} /></td>
                  <td className="px-3 py-2.5 text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">{row.created_at ? new Date(row.created_at).toLocaleDateString() : '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />
      </div>
    </div>
  )
}


// =====================================================================
// TAB 3: Mailbox Health
// =====================================================================

function MailboxHealthTab() {
  const [data, setData] = useState<PaginatedResponse<MailboxHealthRow>>({ items: [], total: 0, page: 1, page_size: 50, pages: 0 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [warmup, setWarmup] = useState('')
  const [sortBy, setSortBy] = useState('email')
  const [sortOrder, setSortOrder] = useState('asc')
  const [page, setPage] = useState(1)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const result = await reportsApi.mailboxHealth({
        search: search || undefined,
        warmup_status: warmup || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        page,
        page_size: 50,
      })
      setData(result)
    } catch { /* ignore */ }
    setLoading(false)
  }, [search, warmup, sortBy, sortOrder, page])

  useEffect(() => { fetchData() }, [fetchData])

  const handleSort = (field: string) => {
    if (sortBy === field) setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    else { setSortBy(field); setSortOrder('asc') }
    setPage(1)
  }

  const handleExport = async () => {
    try {
      const result = await reportsApi.mailboxHealth({
        search: search || undefined,
        warmup_status: warmup || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        export: true,
      })
      exportToXlsx(result.items, 'mailbox-health')
    } catch { /* ignore */ }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input type="text" placeholder="Search mailboxes..." value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-primary-500" />
        </div>
        <select value={warmup} onChange={(e) => { setWarmup(e.target.value); setPage(1) }} className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2">
          <option value="">All Warmup</option>
          <option value="active">Active</option>
          <option value="warming_up">Warming Up</option>
          <option value="cold_ready">Cold Ready</option>
          <option value="paused">Paused</option>
          <option value="inactive">Inactive</option>
        </select>
        <button onClick={handleExport} className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
          <Download className="w-4 h-4" /> Export
        </button>
        <button onClick={fetchData} className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <SortHeader label="Email" field="email" current={sortBy} order={sortOrder} onSort={handleSort} />
                <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Provider</th>
                <SortHeader label="Warmup" field="warmup_status" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Conn" field="connection_status" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Today / Limit" field="emails_sent_today" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Total Sent" field="total_emails_sent" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Bounces" field="bounce_count" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Replies" field="reply_count" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Complaints" field="complaint_count" current={sortBy} order={sortOrder} onSort={handleSort} />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {loading ? (
                <tr><td colSpan={9} className="px-3 py-12 text-center text-gray-500">Loading...</td></tr>
              ) : data.items.length === 0 ? (
                <tr><td colSpan={9} className="px-3 py-12 text-center text-gray-500">No mailboxes found</td></tr>
              ) : data.items.map((row) => (
                <tr key={row.mailbox_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-3 py-2.5 text-sm font-medium text-gray-900 dark:text-white whitespace-nowrap">{row.email}</td>
                  <td className="px-3 py-2.5"><StatusBadge status={row.provider || 'other'} /></td>
                  <td className="px-3 py-2.5"><StatusBadge status={row.warmup_status || 'inactive'} /></td>
                  <td className="px-3 py-2.5"><ConnectionDot status={row.connection_status} /></td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.emails_sent_today} / {row.daily_send_limit}</td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.total_emails_sent}</td>
                  <td className="px-3 py-2.5 text-sm text-right">
                    <span className="text-gray-700 dark:text-gray-300">{row.bounce_count}</span>
                    {row.bounce_rate > 0 && <span className="ml-1 text-xs text-red-500">({row.bounce_rate}%)</span>}
                  </td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.reply_count}</td>
                  <td className="px-3 py-2.5 text-sm text-right">
                    <span className="text-gray-700 dark:text-gray-300">{row.complaint_count}</span>
                    {row.complaint_rate > 0 && <span className="ml-1 text-xs text-red-500">({row.complaint_rate}%)</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />
      </div>
    </div>
  )
}


// =====================================================================
// TAB 4: Daily Activity (Chart)
// =====================================================================

function DailyActivityTab() {
  const [data, setData] = useState<DailyActivityResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)
  const [granularity, setGranularity] = useState<'daily' | 'weekly'>('daily')

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const result = await reportsApi.dailyActivity({ days, granularity })
      setData(result)
    } catch { /* ignore */ }
    setLoading(false)
  }, [days, granularity])

  useEffect(() => { fetchData() }, [fetchData])

  const handleExport = () => {
    if (data?.series) exportToXlsx(data.series, 'daily-activity')
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2">
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
          <option value={60}>Last 60 days</option>
          <option value={90}>Last 90 days</option>
        </select>
        <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden text-sm">
          <button onClick={() => setGranularity('daily')} className={`px-3 py-1.5 ${granularity === 'daily' ? 'bg-primary-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300'}`}>Daily</button>
          <button onClick={() => setGranularity('weekly')} className={`px-3 py-1.5 ${granularity === 'weekly' ? 'bg-primary-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300'}`}>Weekly</button>
        </div>
        <button onClick={handleExport} className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
          <Download className="w-4 h-4" /> Export
        </button>
        <button onClick={fetchData} className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Summary cards */}
      {data?.totals && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Sent" value={data.totals.sent} />
          <StatCard label="Opened" value={data.totals.opened} />
          <StatCard label="Replied" value={data.totals.replied} />
          <StatCard label="Bounced" value={data.totals.bounced} />
        </div>
      )}

      {/* Chart */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
        {loading ? (
          <div className="h-80 flex items-center justify-center text-gray-500">Loading chart...</div>
        ) : !data?.series?.length ? (
          <div className="h-80 flex items-center justify-center text-gray-500">No activity data for this period</div>
        ) : (
          <ResponsiveContainer width="100%" height={380}>
            <AreaChart data={data.series} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="gradSent" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradOpened" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradReplied" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradBounced" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="#9ca3af" />
              <YAxis tick={{ fontSize: 12 }} stroke="#9ca3af" />
              <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#fff' }} />
              <Legend />
              <Area type="monotone" dataKey="sent" stroke="#6366f1" fill="url(#gradSent)" strokeWidth={2} name="Sent" />
              <Area type="monotone" dataKey="opened" stroke="#3b82f6" fill="url(#gradOpened)" strokeWidth={2} name="Opened" />
              <Area type="monotone" dataKey="replied" stroke="#22c55e" fill="url(#gradReplied)" strokeWidth={2} name="Replied" />
              <Area type="monotone" dataKey="bounced" stroke="#ef4444" fill="url(#gradBounced)" strokeWidth={2} name="Bounced" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}


// =====================================================================
// TAB 5: Contact Engagement
// =====================================================================

function ContactEngagementTab() {
  const [data, setData] = useState<PaginatedResponse<ContactEngagementRow>>({ items: [], total: 0, page: 1, page_size: 50, pages: 0 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [clientFilter, setClientFilter] = useState('')
  const [minEmails, setMinEmails] = useState(0)
  const [hasReplied, setHasReplied] = useState<string>('')
  const [sortBy, setSortBy] = useState('sent')
  const [sortOrder, setSortOrder] = useState('desc')
  const [page, setPage] = useState(1)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const result = await reportsApi.contactEngagement({
        search: search || undefined,
        client_name: clientFilter || undefined,
        min_emails: minEmails || undefined,
        has_replied: hasReplied === '' ? undefined : hasReplied === 'true',
        sort_by: sortBy,
        sort_order: sortOrder,
        page,
        page_size: 50,
      })
      setData(result)
    } catch { /* ignore */ }
    setLoading(false)
  }, [search, clientFilter, minEmails, hasReplied, sortBy, sortOrder, page])

  useEffect(() => { fetchData() }, [fetchData])

  const handleSort = (field: string) => {
    if (sortBy === field) setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    else { setSortBy(field); setSortOrder('desc') }
    setPage(1)
  }

  const handleExport = async () => {
    try {
      const result = await reportsApi.contactEngagement({
        search: search || undefined,
        client_name: clientFilter || undefined,
        min_emails: minEmails || undefined,
        has_replied: hasReplied === '' ? undefined : hasReplied === 'true',
        sort_by: sortBy,
        sort_order: sortOrder,
        export: true,
      })
      exportToXlsx(result.items, 'contact-engagement')
    } catch { /* ignore */ }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input type="text" placeholder="Search contacts..." value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-primary-500" />
        </div>
        <input type="text" placeholder="Filter by company..." value={clientFilter} onChange={(e) => { setClientFilter(e.target.value); setPage(1) }}
          className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2 w-44" />
        <select value={hasReplied} onChange={(e) => { setHasReplied(e.target.value); setPage(1) }} className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2">
          <option value="">All Contacts</option>
          <option value="true">Has Replied</option>
          <option value="false">No Reply</option>
        </select>
        <select value={minEmails} onChange={(e) => { setMinEmails(Number(e.target.value)); setPage(1) }} className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2">
          <option value={0}>Min emails: Any</option>
          <option value={1}>1+</option>
          <option value={3}>3+</option>
          <option value={5}>5+</option>
        </select>
        <button onClick={handleExport} className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
          <Download className="w-4 h-4" /> Export
        </button>
        <button onClick={fetchData} className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <SortHeader label="Name" field="name" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Email" field="email" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Company" field="company" current={sortBy} order={sortOrder} onSort={handleSort} />
                <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Status</th>
                <SortHeader label="Sent" field="sent" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Opens" field="opens" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Replies" field="replies" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Last Activity" field="last_activity" current={sortBy} order={sortOrder} onSort={handleSort} />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {loading ? (
                <tr><td colSpan={8} className="px-3 py-12 text-center text-gray-500">Loading...</td></tr>
              ) : data.items.length === 0 ? (
                <tr><td colSpan={8} className="px-3 py-12 text-center text-gray-500">No contacts found</td></tr>
              ) : data.items.map((row) => (
                <tr key={row.contact_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-3 py-2.5 text-sm font-medium text-gray-900 dark:text-white whitespace-nowrap">{row.name || '--'}</td>
                  <td className="px-3 py-2.5 text-sm text-gray-500 dark:text-gray-400">{row.email}</td>
                  <td className="px-3 py-2.5 text-sm text-gray-500 dark:text-gray-400 max-w-[160px] truncate">{row.company || '--'}</td>
                  <td className="px-3 py-2.5"><StatusBadge status={row.status} /></td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.sent}</td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.opens}</td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.replies}</td>
                  <td className="px-3 py-2.5 text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">{row.last_activity ? new Date(row.last_activity).toLocaleDateString() : '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />
      </div>
    </div>
  )
}


// =====================================================================
// TAB 6: Domain Deliverability
// =====================================================================

function DomainDeliverabilityTab() {
  const [data, setData] = useState<PaginatedResponse<DomainDeliverabilityRow>>({ items: [], total: 0, page: 1, page_size: 50, pages: 0 })
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)
  const [sortBy, setSortBy] = useState('sent')
  const [sortOrder, setSortOrder] = useState('desc')
  const [page, setPage] = useState(1)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const result = await reportsApi.domainDeliverability({
        days,
        sort_by: sortBy,
        sort_order: sortOrder,
        page,
        page_size: 50,
      })
      setData(result)
    } catch { /* ignore */ }
    setLoading(false)
  }, [days, sortBy, sortOrder, page])

  useEffect(() => { fetchData() }, [fetchData])

  const handleSort = (field: string) => {
    if (sortBy === field) setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    else { setSortBy(field); setSortOrder('desc') }
    setPage(1)
  }

  const handleExport = async () => {
    try {
      const result = await reportsApi.domainDeliverability({
        days,
        sort_by: sortBy,
        sort_order: sortOrder,
        export: true,
      })
      exportToXlsx(result.items, 'domain-deliverability')
    } catch { /* ignore */ }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select value={days} onChange={(e) => { setDays(Number(e.target.value)); setPage(1) }} className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2">
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
          <option value={60}>Last 60 days</option>
          <option value={90}>Last 90 days</option>
          <option value={180}>Last 180 days</option>
        </select>
        <button onClick={handleExport} className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
          <Download className="w-4 h-4" /> Export
        </button>
        <button onClick={fetchData} className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <SortHeader label="Domain" field="domain" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Sent" field="sent" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Opened" field="opened" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Replied" field="replied" current={sortBy} order={sortOrder} onSort={handleSort} />
                <SortHeader label="Bounced" field="bounced" current={sortBy} order={sortOrder} onSort={handleSort} />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {loading ? (
                <tr><td colSpan={5} className="px-3 py-12 text-center text-gray-500">Loading...</td></tr>
              ) : data.items.length === 0 ? (
                <tr><td colSpan={5} className="px-3 py-12 text-center text-gray-500">No domain data found</td></tr>
              ) : data.items.map((row, i) => (
                <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-3 py-2.5 text-sm font-medium text-gray-900 dark:text-white">{row.domain}</td>
                  <td className="px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 text-right">{row.sent}</td>
                  <td className="px-3 py-2.5 text-sm text-right">
                    <span className="text-gray-700 dark:text-gray-300">{row.opened}</span>
                    {row.open_rate > 0 && <span className="ml-1 text-xs text-blue-500">({row.open_rate}%)</span>}
                  </td>
                  <td className="px-3 py-2.5 text-sm text-right">
                    <span className="text-gray-700 dark:text-gray-300">{row.replied}</span>
                    {row.reply_rate > 0 && <span className="ml-1 text-xs text-green-600">({row.reply_rate}%)</span>}
                  </td>
                  <td className="px-3 py-2.5 text-sm text-right">
                    <span className="text-gray-700 dark:text-gray-300">{row.bounced}</span>
                    {row.bounce_rate > 0 && <span className="ml-1 text-xs text-red-500">({row.bounce_rate}%)</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />
      </div>
    </div>
  )
}
