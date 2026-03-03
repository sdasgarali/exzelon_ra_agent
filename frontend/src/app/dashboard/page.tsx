'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi, pipelinesApi, leadsApi, contactsApi } from '@/lib/api'
import { useToast } from '@/components/toast'
import { useAuthStore } from '@/lib/store'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  Building,
  Users,
  Mail,
  CheckCircle,
  TrendingUp,
  TrendingDown,
  Search,
  UserPlus,
  ShieldCheck,
  Send,
  Activity,
  BarChart3,
  Inbox,
  FileEdit,
  ArrowRight,
} from 'lucide-react'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

// --- Interfaces ---

interface SelectorLead {
  lead_id: number
  client_name: string
  job_title: string
  state: string
  lead_status: string
  contact_count: number
}

interface SelectorContact {
  contact_id: number
  first_name: string
  last_name: string
  email: string
  validation_status: string | null
  client_name: string
}

// --- Helpers ---

const LEAD_STATUS_COLORS: Record<string, string> = {
  open: '#22c55e',
  hunting: '#eab308',
  new: '#94a3b8',
  enriched: '#a855f7',
  validated: '#14b8a6',
  sent: '#6366f1',
  skipped: '#f97316',
  closed: '#ef4444',
}

const VALIDATION_COLORS: Record<string, string> = {
  valid: '#22c55e',
  invalid: '#ef4444',
  catch_all: '#eab308',
  unknown: '#94a3b8',
  pending: '#cbd5e1',
}

function getLeadStatusBadge(status: string) {
  const colors: Record<string, string> = {
    new: 'bg-slate-100 text-slate-800',
    enriched: 'bg-purple-100 text-purple-800',
    validated: 'bg-teal-100 text-teal-800',
    open: 'bg-green-100 text-green-800',
    hunting: 'bg-yellow-100 text-yellow-800',
    sent: 'bg-indigo-100 text-indigo-800',
    skipped: 'bg-orange-100 text-orange-800',
  }
  return colors[status?.toLowerCase()] || 'bg-gray-100 text-gray-800'
}

function getValidationStatusBadge(status: string | null) {
  const colors: Record<string, string> = {
    valid: 'bg-green-100 text-green-800',
    invalid: 'bg-red-100 text-red-800',
    catch_all: 'bg-yellow-100 text-yellow-800',
    unknown: 'bg-gray-100 text-gray-600',
    pending: 'bg-slate-100 text-slate-600',
  }
  return colors[status?.toLowerCase() || 'pending'] || 'bg-gray-100 text-gray-800'
}

// --- StatCard Component ---

function StatCard({
  title,
  value,
  icon: Icon,
  trend,
  trendLabel,
}: {
  title: string
  value: string | number
  icon: any
  trend?: 'up' | 'down'
  trendLabel?: string
}) {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
          {trend && trendLabel && (
            <div className="flex items-center gap-1 mt-2">
              {trend === 'up' ? (
                <TrendingUp className="w-4 h-4 text-green-500" />
              ) : (
                <TrendingDown className="w-4 h-4 text-red-500" />
              )}
              <span
                className={`text-sm ${
                  trend === 'up' ? 'text-green-600' : 'text-red-600'
                }`}
              >
                {trendLabel}
              </span>
            </div>
          )}
        </div>
        <div className="w-12 h-12 rounded-lg bg-primary-100 flex items-center justify-center">
          <Icon className="w-6 h-6 text-primary-600" />
        </div>
      </div>
    </div>
  )
}

// --- Main Dashboard ---

const SELECTOR_PAGE_SIZE = 20

export default function DashboardPage() {
  const router = useRouter()
  const { toast } = useToast()
  const user = useAuthStore((s) => s.user)
  const [quickLoading, setQuickLoading] = useState<string | null>(null)
  const [confirmAction, setConfirmAction] = useState<string | null>(null)

  // --- Lead Selector State ---
  const [showLeadSelector, setShowLeadSelector] = useState(false)
  const [selectorPipeline, setSelectorPipeline] = useState<'enrich' | 'outreach'>('enrich')
  const [selectorLeads, setSelectorLeads] = useState<SelectorLead[]>([])
  const [selectorLoading, setSelectorLoading] = useState(false)
  const [selectorSearch, setSelectorSearch] = useState('')
  const [selectorStatus, setSelectorStatus] = useState('')
  const [selectorPage, setSelectorPage] = useState(1)
  const [selectorTotal, setSelectorTotal] = useState(0)
  const [selectorSelected, setSelectorSelected] = useState<Set<number>>(new Set())
  const [showRunAllLeadsConfirm, setShowRunAllLeadsConfirm] = useState(false)

  // --- Contact Selector State ---
  const [showContactSelector, setShowContactSelector] = useState(false)
  const [contactSelectorContacts, setContactSelectorContacts] = useState<SelectorContact[]>([])
  const [contactSelectorLoading, setContactSelectorLoading] = useState(false)
  const [contactSelectorSearch, setContactSelectorSearch] = useState('')
  const [contactSelectorValidationStatus, setContactSelectorValidationStatus] = useState('')
  const [contactSelectorPage, setContactSelectorPage] = useState(1)
  const [contactSelectorTotal, setContactSelectorTotal] = useState(0)
  const [contactSelectorSelected, setContactSelectorSelected] = useState<Set<number>>(new Set())
  const [showRunAllContactsConfirm, setShowRunAllContactsConfirm] = useState(false)

  // --- Queries ---
  const { data: kpis, isLoading } = useQuery({
    queryKey: ['dashboard-kpis'],
    queryFn: () => dashboardApi.kpis(),
  })

  const { data: trends } = useQuery({
    queryKey: ['dashboard-trends'],
    queryFn: () => dashboardApi.trends(30),
  })

  const { data: stats } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: () => dashboardApi.stats(),
  })

  // --- Selector Fetch Functions ---

  const fetchSelectorLeads = useCallback(async (search: string, status: string, page: number) => {
    setSelectorLoading(true)
    try {
      const params: Record<string, any> = {
        page,
        page_size: SELECTOR_PAGE_SIZE,
        sort_by: 'created_at',
        sort_order: 'desc',
      }
      if (search) params.search = search
      if (status) params.status = status
      const response = await leadsApi.list(params)
      setSelectorLeads(response.items || [])
      setSelectorTotal(response.total || 0)
    } catch {
      toast('error', 'Failed to fetch leads')
    } finally {
      setSelectorLoading(false)
    }
  }, [toast])

  const fetchSelectorContacts = useCallback(async (search: string, validationStatus: string, page: number) => {
    setContactSelectorLoading(true)
    try {
      const params: Record<string, any> = {
        page,
        page_size: SELECTOR_PAGE_SIZE,
        sort_by: 'created_at',
        sort_order: 'desc',
      }
      if (search) params.search = search
      if (validationStatus) params.validation_status = validationStatus
      const response = await contactsApi.list(params)
      setContactSelectorContacts(response.items || [])
      setContactSelectorTotal(response.total || 0)
    } catch {
      toast('error', 'Failed to fetch contacts')
    } finally {
      setContactSelectorLoading(false)
    }
  }, [toast])

  // --- Debounced Search Effects ---

  const [debouncedSelectorSearch, setDebouncedSelectorSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSelectorSearch(selectorSearch), 300)
    return () => clearTimeout(timer)
  }, [selectorSearch])

  useEffect(() => {
    if (showLeadSelector) {
      fetchSelectorLeads(debouncedSelectorSearch, selectorStatus, selectorPage)
    }
  }, [showLeadSelector, debouncedSelectorSearch, selectorStatus, selectorPage, fetchSelectorLeads])

  const [debouncedContactSearch, setDebouncedContactSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedContactSearch(contactSelectorSearch), 300)
    return () => clearTimeout(timer)
  }, [contactSelectorSearch])

  useEffect(() => {
    if (showContactSelector) {
      fetchSelectorContacts(debouncedContactSearch, contactSelectorValidationStatus, contactSelectorPage)
    }
  }, [showContactSelector, debouncedContactSearch, contactSelectorValidationStatus, contactSelectorPage, fetchSelectorContacts])

  // --- Open Selectors ---

  const openLeadSelector = (pipeline: 'enrich' | 'outreach') => {
    setSelectorPipeline(pipeline)
    setSelectorSelected(new Set())
    setSelectorSearch('')
    setSelectorStatus('')
    setSelectorPage(1)
    setShowLeadSelector(true)
  }

  const openContactSelector = () => {
    setContactSelectorSelected(new Set())
    setContactSelectorSearch('')
    setContactSelectorValidationStatus('')
    setContactSelectorPage(1)
    setShowContactSelector(true)
  }

  // --- Toggle Helpers ---

  const toggleSelectorLead = (id: number) => {
    setSelectorSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectorSelectAll = () => {
    const pageIds = selectorLeads.map(l => l.lead_id)
    const allSelected = pageIds.every(id => selectorSelected.has(id))
    setSelectorSelected(prev => {
      const next = new Set(prev)
      if (allSelected) pageIds.forEach(id => next.delete(id))
      else pageIds.forEach(id => next.add(id))
      return next
    })
  }

  const toggleSelectorContact = (id: number) => {
    setContactSelectorSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleContactSelectAll = () => {
    const pageIds = contactSelectorContacts.map(c => c.contact_id)
    const allSelected = pageIds.every(id => contactSelectorSelected.has(id))
    setContactSelectorSelected(prev => {
      const next = new Set(prev)
      if (allSelected) pageIds.forEach(id => next.delete(id))
      else pageIds.forEach(id => next.add(id))
      return next
    })
  }

  // --- Pipeline Handler Functions ---

  const handleRunWithSelectedLeads = async (runAll: boolean) => {
    if (runAll) {
      setShowRunAllLeadsConfirm(true)
      return
    }
    const leadIds = Array.from(selectorSelected)
    setShowLeadSelector(false)
    setQuickLoading(selectorPipeline)
    try {
      if (selectorPipeline === 'enrich') {
        await pipelinesApi.runContactEnrichment(leadIds)
        toast('success', `Contact enrichment started for ${leadIds.length} selected leads`)
      } else {
        await pipelinesApi.runOutreach('mailmerge', true, leadIds)
        toast('success', `Mailmerge export started for ${leadIds.length} selected leads`)
      }
      router.push('/dashboard/pipelines')
    } catch {
      toast('error', `Failed to start ${selectorPipeline === 'enrich' ? 'contact enrichment' : 'outreach'}`)
    }
    setQuickLoading(null)
  }

  const confirmRunAllLeads = async () => {
    setShowRunAllLeadsConfirm(false)
    setShowLeadSelector(false)
    setQuickLoading(selectorPipeline)
    try {
      if (selectorPipeline === 'enrich') {
        await pipelinesApi.runContactEnrichment()
        toast('success', 'Contact enrichment started for all leads')
      } else {
        await pipelinesApi.runOutreach('mailmerge', true)
        toast('success', 'Mailmerge export started for all leads')
      }
      router.push('/dashboard/pipelines')
    } catch {
      toast('error', `Failed to start ${selectorPipeline === 'enrich' ? 'contact enrichment' : 'outreach'}`)
    }
    setQuickLoading(null)
  }

  const handleRunWithSelectedContacts = async (runAll: boolean) => {
    if (runAll) {
      setShowRunAllContactsConfirm(true)
      return
    }
    const contactIds = Array.from(contactSelectorSelected)
    setShowContactSelector(false)
    setQuickLoading('validate')
    try {
      await pipelinesApi.runEmailValidationSelected(contactIds)
      toast('success', `Email validation started for ${contactIds.length} selected contacts`)
      router.push('/dashboard/pipelines')
    } catch {
      toast('error', 'Failed to start email validation')
    }
    setQuickLoading(null)
  }

  const confirmRunAllContacts = async () => {
    setShowRunAllContactsConfirm(false)
    setShowContactSelector(false)
    setQuickLoading('validate')
    try {
      await pipelinesApi.runEmailValidation()
      toast('success', 'Email validation started for all contacts')
      router.push('/dashboard/pipelines')
    } catch {
      toast('error', 'Failed to start email validation')
    }
    setQuickLoading(null)
  }

  // --- Chart Data ---

  const trendChartData = (() => {
    if (!trends?.daily_leads || !trends?.daily_outreach) return []
    const dateMap = new Map<string, { date: string; leads: number; outreach: number }>()
    trends.daily_leads.forEach((d: { date: string; count: number }) => {
      dateMap.set(d.date, { date: d.date, leads: d.count, outreach: 0 })
    })
    trends.daily_outreach.forEach((d: { date: string; count: number }) => {
      const existing = dateMap.get(d.date)
      if (existing) existing.outreach = d.count
      else dateMap.set(d.date, { date: d.date, leads: 0, outreach: d.count })
    })
    return Array.from(dateMap.values()).sort((a, b) => a.date.localeCompare(b.date))
  })()

  const funnelSteps = [
    { label: 'Leads', value: kpis?.total_leads || 0, color: 'bg-indigo-500' },
    { label: 'Contacts', value: kpis?.total_contacts || 0, color: 'bg-purple-500' },
    { label: 'Valid Emails', value: kpis?.total_valid_emails || 0, color: 'bg-cyan-500' },
    { label: 'Emails Sent', value: kpis?.emails_sent || 0, color: 'bg-orange-500' },
    { label: 'Replied', value: kpis?.total_replied || 0, color: 'bg-green-500' },
  ]

  const leadStatusData = stats?.leads?.by_status
    ? Object.entries(stats.leads.by_status).map(([name, value]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value: value as number,
        fill: LEAD_STATUS_COLORS[name] || '#94a3b8',
      }))
    : []

  const validationData = stats?.contacts?.by_validation_status
    ? Object.entries(stats.contacts.by_validation_status).map(([name, value]) => ({
        name: name === 'catch_all' ? 'Catch All' : name.charAt(0).toUpperCase() + name.slice(1),
        value: value as number,
        fill: VALIDATION_COLORS[name] || '#94a3b8',
      }))
    : []

  // --- Selector computed values ---

  const selectorTotalPages = Math.ceil(selectorTotal / SELECTOR_PAGE_SIZE) || 1
  const pageLeadIds = selectorLeads.map(l => l.lead_id)
  const allPageSelected = pageLeadIds.length > 0 && pageLeadIds.every(id => selectorSelected.has(id))

  const contactSelectorTotalPages = Math.ceil(contactSelectorTotal / SELECTOR_PAGE_SIZE) || 1
  const pageContactIds = contactSelectorContacts.map(c => c.contact_id)
  const allContactPageSelected = pageContactIds.length > 0 && pageContactIds.every(id => contactSelectorSelected.has(id))

  // --- Render ---

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading dashboard...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
        <p className="text-gray-600 mt-1">Overview of your cold-email automation</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Companies Identified"
          value={kpis?.total_companies_identified || 0}
          icon={Building}
        />
        <StatCard
          title="Total Contacts"
          value={kpis?.total_contacts || 0}
          icon={Users}
        />
        <StatCard
          title="Valid Emails"
          value={kpis?.total_valid_emails || 0}
          icon={CheckCircle}
        />
        <StatCard
          title="Emails Sent"
          value={kpis?.emails_sent || 0}
          icon={Mail}
        />
      </div>

      {/* Performance Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Bounce Rate</h3>
          <div className="flex items-end gap-2">
            <span className="text-4xl font-bold text-primary-600">
              {kpis?.bounce_rate_percent || 0}%
            </span>
            <span className="text-sm text-gray-500 mb-1">Target: &lt;2%</span>
          </div>
          <div className="mt-4 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full ${
                (kpis?.bounce_rate_percent || 0) <= 2
                  ? 'bg-green-500'
                  : 'bg-red-500'
              }`}
              style={{ width: `${Math.min(kpis?.bounce_rate_percent || 0, 100)}%` }}
            />
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Reply Rate</h3>
          <div className="flex items-end gap-2">
            <span className="text-4xl font-bold text-primary-600">
              {kpis?.reply_rate_percent || 0}%
            </span>
          </div>
          <div className="mt-4 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-primary-500"
              style={{ width: `${Math.min(kpis?.reply_rate_percent || 0, 100)}%` }}
            />
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Total Leads</h3>
          <div className="flex items-end gap-2">
            <span className="text-4xl font-bold text-primary-600">
              {kpis?.total_leads || 0}
            </span>
          </div>
        </div>
      </div>

      {/* Quick Actions — admin and operator only */}
      {user?.role !== 'viewer' && (
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Quick Actions</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="flex flex-col">
              <button
                className={`text-white rounded-lg px-4 py-2 font-medium flex items-center justify-center gap-2 ${
                  quickLoading === 'sourcing'
                    ? 'bg-indigo-400 animate-pulse cursor-not-allowed'
                    : 'bg-indigo-600 hover:bg-indigo-700'
                }`}
                disabled={quickLoading !== null}
                onClick={() => setConfirmAction('sourcing')}
              >
                <Search className="w-4 h-4" />
                {quickLoading === 'sourcing' ? 'Starting...' : 'Run Lead Sourcing'}
              </button>
              <p className="text-xs text-gray-500 mt-2">Scrape job postings from Indeed, LinkedIn, and Glassdoor</p>
            </div>
            <div className="flex flex-col">
              <button
                className={`text-white rounded-lg px-4 py-2 font-medium flex items-center justify-center gap-2 ${
                  quickLoading === 'enrich'
                    ? 'bg-purple-400 animate-pulse cursor-not-allowed'
                    : 'bg-purple-600 hover:bg-purple-700'
                }`}
                disabled={quickLoading !== null}
                onClick={() => openLeadSelector('enrich')}
              >
                <UserPlus className="w-4 h-4" />
                {quickLoading === 'enrich' ? 'Starting...' : 'Enrich Contacts'}
              </button>
              <p className="text-xs text-gray-500 mt-2">Find decision-maker contacts for selected leads</p>
            </div>
            <div className="flex flex-col">
              <button
                className={`text-white rounded-lg px-4 py-2 font-medium flex items-center justify-center gap-2 ${
                  quickLoading === 'validate'
                    ? 'bg-cyan-400 animate-pulse cursor-not-allowed'
                    : 'bg-cyan-600 hover:bg-cyan-700'
                }`}
                disabled={quickLoading !== null}
                onClick={() => openContactSelector()}
              >
                <ShieldCheck className="w-4 h-4" />
                {quickLoading === 'validate' ? 'Starting...' : 'Validate Emails'}
              </button>
              <p className="text-xs text-gray-500 mt-2">Validate selected contact email addresses</p>
            </div>
            <div className="flex flex-col">
              <button
                className={`text-white rounded-lg px-4 py-2 font-medium flex items-center justify-center gap-2 ${
                  quickLoading === 'outreach'
                    ? 'bg-orange-400 animate-pulse cursor-not-allowed'
                    : 'bg-orange-600 hover:bg-orange-700'
                }`}
                disabled={quickLoading !== null}
                onClick={() => openLeadSelector('outreach')}
              >
                <Send className="w-4 h-4" />
                {quickLoading === 'outreach' ? 'Starting...' : 'Export Mailmerge'}
              </button>
              <p className="text-xs text-gray-500 mt-2">Generate mail merge CSV for selected leads</p>
            </div>
          </div>
        </div>
      )}

      {/* 30-Day Activity Trends */}
      {trendChartData.length > 0 && (
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">30-Day Activity Trends</h3>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={trendChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: string) => {
                  const d = new Date(v)
                  return `${d.getMonth() + 1}/${d.getDate()}`
                }}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                labelFormatter={(v: string) => new Date(v).toLocaleDateString()}
              />
              <Legend />
              <Area
                type="monotone"
                dataKey="leads"
                stroke="#6366f1"
                fill="#c7d2fe"
                strokeWidth={2}
                name="Leads Sourced"
              />
              <Area
                type="monotone"
                dataKey="outreach"
                stroke="#f97316"
                fill="#fed7aa"
                strokeWidth={2}
                name="Emails Sent"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Pipeline Funnel */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-6">Pipeline Funnel</h3>
        <div className="flex items-center justify-between px-4">
          {funnelSteps.map((step, i) => {
            const prevValue = i > 0 ? funnelSteps[i - 1].value : null
            const convRate = prevValue && prevValue > 0
              ? ((step.value / prevValue) * 100).toFixed(1)
              : null
            return (
              <div key={step.label} className="flex items-center">
                {i > 0 && (
                  <div className="flex flex-col items-center mx-3">
                    <ArrowRight className="w-5 h-5 text-gray-400" />
                    {convRate && (
                      <span className="text-xs text-gray-500 mt-1">{convRate}%</span>
                    )}
                  </div>
                )}
                <div className="flex flex-col items-center">
                  <div className={`w-16 h-16 ${step.color} rounded-full flex items-center justify-center text-white font-bold text-lg`}>
                    {step.value}
                  </div>
                  <span className="text-sm font-medium text-gray-700 mt-2">{step.label}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Distribution Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Lead Status Distribution */}
        {leadStatusData.length > 0 && (
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">Lead Status Distribution</h3>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={leadStatusData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={80} />
                <Tooltip />
                <Bar dataKey="value" name="Leads" radius={[0, 4, 4, 0]}>
                  {leadStatusData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Contact Validation Breakdown */}
        {validationData.length > 0 && (
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">Contact Validation Breakdown</h3>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={validationData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={3}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {validationData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* System Health */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="card flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
              <Inbox className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Active Mailboxes</p>
              <p className="text-lg font-bold">{stats.mailboxes?.active || 0}<span className="text-sm font-normal text-gray-400">/{stats.mailboxes?.total || 0}</span></p>
            </div>
          </div>
          <div className="card flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-yellow-100 flex items-center justify-center">
              <Activity className="w-5 h-5 text-yellow-600" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Warming Up</p>
              <p className="text-lg font-bold">{stats.mailboxes?.warming_up || 0}</p>
            </div>
          </div>
          <div className="card flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
              <FileEdit className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Active Templates</p>
              <p className="text-lg font-bold">{stats.templates?.active_count || 0}<span className="text-sm font-normal text-gray-400">/{stats.templates?.total || 0}</span></p>
            </div>
          </div>
          <div className="card flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
              <BarChart3 className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Lead Sources</p>
              <p className="text-lg font-bold">{stats.leads?.by_source ? Object.keys(stats.leads.by_source).length : 0}</p>
            </div>
          </div>
        </div>
      )}

      {/* ===== Confirmation Dialogs ===== */}

      {/* Lead Sourcing (still uses simple ConfirmDialog) */}
      <ConfirmDialog
        open={confirmAction === 'sourcing'}
        onClose={() => setConfirmAction(null)}
        title="Run Lead Sourcing?"
        message="This will scrape job postings from all configured sources (Indeed, LinkedIn, Glassdoor). New leads will be deduplicated against existing records."
        confirmLabel="Run Pipeline"
        variant="info"
        loading={quickLoading === 'sourcing'}
        onConfirm={async () => {
          setQuickLoading('sourcing')
          try {
            await pipelinesApi.runLeadSourcing(['linkedin', 'indeed'])
            toast('success', 'Lead sourcing pipeline started')
            setConfirmAction(null)
            router.push('/dashboard/pipelines')
          } catch { toast('error', 'Failed to start lead sourcing') }
          setQuickLoading(null)
        }}
      />

      {/* "Run for All Leads" warning */}
      <ConfirmDialog
        open={showRunAllLeadsConfirm}
        onClose={() => setShowRunAllLeadsConfirm(false)}
        title={`Run ${selectorPipeline === 'enrich' ? 'Contact Enrichment' : 'Mailmerge Export'} for ALL leads?`}
        message={`This will process all ${selectorTotal} available leads. API credits may be consumed. Are you sure you want to continue?`}
        confirmLabel="Run for All"
        variant="warning"
        onConfirm={confirmRunAllLeads}
      />

      {/* "Validate All Contacts" warning */}
      <ConfirmDialog
        open={showRunAllContactsConfirm}
        onClose={() => setShowRunAllContactsConfirm(false)}
        title="Run Email Validation for ALL contacts?"
        message={`This will validate all ${contactSelectorTotal} contacts with unvalidated emails. API credits will be consumed. Are you sure?`}
        confirmLabel="Validate All"
        variant="warning"
        onConfirm={confirmRunAllContacts}
      />

      {/* ===== Lead Selector Modal ===== */}
      {showLeadSelector && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full mx-4 max-h-[85vh] flex flex-col">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-semibold text-gray-800">
                {selectorPipeline === 'enrich'
                  ? 'Select Leads for Contact Enrichment'
                  : 'Select Leads for Mailmerge Export'}
              </h3>
              <p className="text-sm text-gray-500 mt-1">
                Choose specific leads or run for all. {selectorTotal} total leads available.
              </p>
            </div>

            {/* Search & Filters */}
            <div className="px-6 py-3 border-b bg-gray-50 flex gap-3">
              <input
                type="text"
                placeholder="Search company or job title..."
                value={selectorSearch}
                onChange={(e) => { setSelectorSearch(e.target.value); setSelectorPage(1) }}
                className="input flex-1"
              />
              <select
                value={selectorStatus}
                onChange={(e) => { setSelectorStatus(e.target.value); setSelectorPage(1) }}
                className="input w-40"
              >
                <option value="">All Statuses</option>
                <option value="new">New</option>
                <option value="enriched">Enriched</option>
                <option value="validated">Validated</option>
                <option value="open">Open</option>
                <option value="sent">Sent</option>
              </select>
            </div>

            {/* Selection Info */}
            {selectorSelected.size > 0 && (
              <div className="px-6 py-2 bg-blue-50 border-b flex items-center justify-between">
                <span className="text-sm text-blue-800 font-medium">{selectorSelected.size} lead(s) selected</span>
                <button
                  onClick={() => setSelectorSelected(new Set())}
                  className="text-sm text-blue-600 hover:text-blue-800"
                >
                  Clear selection
                </button>
              </div>
            )}

            {/* Lead List */}
            <div className="overflow-y-auto flex-1">
              {selectorLoading ? (
                <div className="text-center py-8 text-gray-500">Loading leads...</div>
              ) : selectorLeads.length === 0 ? (
                <div className="text-center py-8 text-gray-500">No leads found.</div>
              ) : (
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-4 py-2 w-10">
                        <input type="checkbox" checked={allPageSelected} onChange={toggleSelectorSelectAll} className="w-4 h-4" />
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Company / Job</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Contacts</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {selectorLeads.map((lead) => (
                      <tr
                        key={lead.lead_id}
                        className={`cursor-pointer ${selectorSelected.has(lead.lead_id) ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                        onClick={() => toggleSelectorLead(lead.lead_id)}
                      >
                        <td className="px-4 py-2">
                          <input
                            type="checkbox"
                            checked={selectorSelected.has(lead.lead_id)}
                            onChange={() => toggleSelectorLead(lead.lead_id)}
                            onClick={(e) => e.stopPropagation()}
                            className="w-4 h-4"
                          />
                        </td>
                        <td className="px-4 py-2 text-xs font-mono text-gray-500">#{lead.lead_id}</td>
                        <td className="px-4 py-2">
                          <div className="text-sm font-medium text-gray-800">{lead.client_name}</div>
                          <div className="text-xs text-gray-500">{lead.job_title}</div>
                        </td>
                        <td className="px-4 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${getLeadStatusBadge(lead.lead_status)}`}>
                            {lead.lead_status}
                          </span>
                        </td>
                        <td className="px-4 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            lead.contact_count > 0 ? 'bg-purple-100 text-purple-800' : 'bg-gray-100 text-gray-500'
                          }`}>
                            {lead.contact_count || 0}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Pagination */}
            <div className="px-6 py-2 border-t bg-gray-50 flex items-center justify-between text-sm">
              <span className="text-gray-500">Page {selectorPage} of {selectorTotalPages} ({selectorTotal} leads)</span>
              <div className="flex gap-2">
                <button onClick={() => setSelectorPage(p => Math.max(1, p - 1))} disabled={selectorPage === 1} className="px-3 py-1 border rounded disabled:opacity-50 hover:bg-gray-100">Previous</button>
                <button onClick={() => setSelectorPage(p => Math.min(selectorTotalPages, p + 1))} disabled={selectorPage >= selectorTotalPages} className="px-3 py-1 border rounded disabled:opacity-50 hover:bg-gray-100">Next</button>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-between items-center">
              <button onClick={() => setShowLeadSelector(false)} className="btn-secondary">Cancel</button>
              <div className="flex gap-3">
                <button
                  onClick={() => handleRunWithSelectedLeads(true)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 text-sm font-medium"
                >
                  Run for All Leads
                </button>
                <button
                  onClick={() => handleRunWithSelectedLeads(false)}
                  disabled={selectorSelected.size === 0}
                  className={`px-4 py-2 rounded-lg text-white text-sm font-medium disabled:opacity-50 ${
                    selectorPipeline === 'enrich'
                      ? 'bg-purple-600 hover:bg-purple-700'
                      : 'bg-orange-600 hover:bg-orange-700'
                  }`}
                >
                  Run for Selected ({selectorSelected.size})
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===== Contact Selector Modal ===== */}
      {showContactSelector && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full mx-4 max-h-[85vh] flex flex-col">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-semibold text-gray-800">
                Select Contacts for Email Validation
              </h3>
              <p className="text-sm text-gray-500 mt-1">
                Choose specific contacts or validate all. {contactSelectorTotal} total contacts available.
              </p>
            </div>

            {/* Search & Filters */}
            <div className="px-6 py-3 border-b bg-gray-50 flex gap-3">
              <input
                type="text"
                placeholder="Search name or email..."
                value={contactSelectorSearch}
                onChange={(e) => { setContactSelectorSearch(e.target.value); setContactSelectorPage(1) }}
                className="input flex-1"
              />
              <select
                value={contactSelectorValidationStatus}
                onChange={(e) => { setContactSelectorValidationStatus(e.target.value); setContactSelectorPage(1) }}
                className="input w-40"
              >
                <option value="">All Statuses</option>
                <option value="pending">Pending</option>
                <option value="valid">Valid</option>
                <option value="invalid">Invalid</option>
                <option value="catch_all">Catch-All</option>
                <option value="unknown">Unknown</option>
              </select>
            </div>

            {/* Selection Info */}
            {contactSelectorSelected.size > 0 && (
              <div className="px-6 py-2 bg-blue-50 border-b flex items-center justify-between">
                <span className="text-sm text-blue-800 font-medium">{contactSelectorSelected.size} contact(s) selected</span>
                <button
                  onClick={() => setContactSelectorSelected(new Set())}
                  className="text-sm text-blue-600 hover:text-blue-800"
                >
                  Clear selection
                </button>
              </div>
            )}

            {/* Contact List */}
            <div className="overflow-y-auto flex-1">
              {contactSelectorLoading ? (
                <div className="text-center py-8 text-gray-500">Loading contacts...</div>
              ) : contactSelectorContacts.length === 0 ? (
                <div className="text-center py-8 text-gray-500">No contacts found.</div>
              ) : (
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-4 py-2 w-10">
                        <input type="checkbox" checked={allContactPageSelected} onChange={toggleContactSelectAll} className="w-4 h-4" />
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name / Email</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Validation</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Company</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {contactSelectorContacts.map((contact) => (
                      <tr
                        key={contact.contact_id}
                        className={`cursor-pointer ${contactSelectorSelected.has(contact.contact_id) ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                        onClick={() => toggleSelectorContact(contact.contact_id)}
                      >
                        <td className="px-4 py-2">
                          <input
                            type="checkbox"
                            checked={contactSelectorSelected.has(contact.contact_id)}
                            onChange={() => toggleSelectorContact(contact.contact_id)}
                            onClick={(e) => e.stopPropagation()}
                            className="w-4 h-4"
                          />
                        </td>
                        <td className="px-4 py-2 text-xs font-mono text-gray-500">#{contact.contact_id}</td>
                        <td className="px-4 py-2">
                          <div className="text-sm font-medium text-gray-800">{contact.first_name} {contact.last_name}</div>
                          <div className="text-xs text-gray-500">{contact.email}</div>
                        </td>
                        <td className="px-4 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${getValidationStatusBadge(contact.validation_status)}`}>
                            {contact.validation_status || 'pending'}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-sm text-gray-600">
                          {contact.client_name || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Pagination */}
            <div className="px-6 py-2 border-t bg-gray-50 flex items-center justify-between text-sm">
              <span className="text-gray-500">Page {contactSelectorPage} of {contactSelectorTotalPages} ({contactSelectorTotal} contacts)</span>
              <div className="flex gap-2">
                <button onClick={() => setContactSelectorPage(p => Math.max(1, p - 1))} disabled={contactSelectorPage === 1} className="px-3 py-1 border rounded disabled:opacity-50 hover:bg-gray-100">Previous</button>
                <button onClick={() => setContactSelectorPage(p => Math.min(contactSelectorTotalPages, p + 1))} disabled={contactSelectorPage >= contactSelectorTotalPages} className="px-3 py-1 border rounded disabled:opacity-50 hover:bg-gray-100">Next</button>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-between items-center">
              <button onClick={() => setShowContactSelector(false)} className="btn-secondary">Cancel</button>
              <div className="flex gap-3">
                <button
                  onClick={() => handleRunWithSelectedContacts(true)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 text-sm font-medium"
                >
                  Run for All Contacts
                </button>
                <button
                  onClick={() => handleRunWithSelectedContacts(false)}
                  disabled={contactSelectorSelected.size === 0}
                  className="px-4 py-2 rounded-lg text-white text-sm font-medium disabled:opacity-50 bg-cyan-600 hover:bg-cyan-700"
                >
                  Validate Selected ({contactSelectorSelected.size})
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
