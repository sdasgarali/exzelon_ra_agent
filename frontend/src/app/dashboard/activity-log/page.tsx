'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/store'
import { activityApi } from '@/lib/api'
import { roleBadgeColor, roleLabel } from '@/lib/roles'
import {
  ScrollText,
  ShieldAlert,
  Users,
  Lock,
  Unlock,
  CheckCircle,
  XCircle,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Search,
  Activity,
  UserCheck,
} from 'lucide-react'

interface LoginHistoryItem {
  log_id: number
  tenant_id: number | null
  user_id: number | null
  email_attempted: string
  success: boolean
  failure_reason: string | null
  ip_address: string | null
  user_agent: string | null
  created_at: string | null
}

interface LoginStats {
  logins_24h: number
  failed_24h: number
  locked_accounts: number
  unique_users_24h: number
  unique_users_7d: number
}

interface AuditEvent {
  log_id: number
  tenant_id: number
  entity_type: string
  entity_id: number
  action: string
  changed_by: string | null
  changed_fields: string | null
  notes: string | null
  created_at: string | null
}

interface ActiveUser {
  user_id: number
  email: string
  full_name: string | null
  role: string
  tenant_id: number | null
  last_login_at: string | null
  logins_30d: number
  is_online: boolean
  is_locked: boolean
}

type Tab = 'login-history' | 'audit-events' | 'active-users'

export default function ActivityLogPage() {
  const router = useRouter()
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState<Tab>('login-history')

  // Redirect non-super-admin
  useEffect(() => {
    if (user && user.role !== 'super_admin') {
      router.push('/dashboard')
    }
  }, [user, router])

  // Login History state
  const [loginHistory, setLoginHistory] = useState<LoginHistoryItem[]>([])
  const [loginTotal, setLoginTotal] = useState(0)
  const [loginPage, setLoginPage] = useState(1)
  const [loginLoading, setLoginLoading] = useState(false)
  const [stats, setStats] = useState<LoginStats | null>(null)
  const [emailFilter, setEmailFilter] = useState('')
  const [successFilter, setSuccessFilter] = useState<string>('')
  const [ipFilter, setIpFilter] = useState('')

  // Audit Events state
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([])
  const [auditTotal, setAuditTotal] = useState(0)
  const [auditPage, setAuditPage] = useState(1)
  const [auditLoading, setAuditLoading] = useState(false)
  const [entityTypeFilter, setEntityTypeFilter] = useState('')
  const [actionFilter, setActionFilter] = useState('')
  const [changedByFilter, setChangedByFilter] = useState('')
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())

  // Active Users state
  const [activeUsers, setActiveUsers] = useState<ActiveUser[]>([])
  const [activeUsersTotal, setActiveUsersTotal] = useState(0)
  const [activeUsersPage, setActiveUsersPage] = useState(1)
  const [activeUsersLoading, setActiveUsersLoading] = useState(false)

  const [unlocking, setUnlocking] = useState<number | null>(null)

  const PAGE_SIZE = 50

  const fetchLoginHistory = useCallback(async () => {
    setLoginLoading(true)
    try {
      const params: Record<string, any> = { page: loginPage, page_size: PAGE_SIZE }
      if (emailFilter) params.email = emailFilter
      if (successFilter !== '') params.success = successFilter === 'true'
      if (ipFilter) params.ip_address = ipFilter
      const data = await activityApi.getLoginHistory(params)
      setLoginHistory(data.items || [])
      setLoginTotal(data.total || 0)
    } catch { /* ignore */ }
    setLoginLoading(false)
  }, [loginPage, emailFilter, successFilter, ipFilter])

  const fetchStats = useCallback(async () => {
    try {
      const data = await activityApi.getLoginHistoryStats()
      setStats(data)
    } catch { /* ignore */ }
  }, [])

  const fetchAuditEvents = useCallback(async () => {
    setAuditLoading(true)
    try {
      const params: Record<string, any> = { page: auditPage, page_size: PAGE_SIZE }
      if (entityTypeFilter) params.entity_type = entityTypeFilter
      if (actionFilter) params.action = actionFilter
      if (changedByFilter) params.changed_by = changedByFilter
      const data = await activityApi.getAuthEvents(params)
      setAuditEvents(data.items || [])
      setAuditTotal(data.total || 0)
    } catch { /* ignore */ }
    setAuditLoading(false)
  }, [auditPage, entityTypeFilter, actionFilter, changedByFilter])

  const fetchActiveUsers = useCallback(async () => {
    setActiveUsersLoading(true)
    try {
      const data = await activityApi.getActiveUsers({ page: activeUsersPage, page_size: PAGE_SIZE })
      setActiveUsers(data.items || [])
      setActiveUsersTotal(data.total || 0)
    } catch { /* ignore */ }
    setActiveUsersLoading(false)
  }, [activeUsersPage])

  useEffect(() => {
    if (activeTab === 'login-history') {
      fetchLoginHistory()
      fetchStats()
    } else if (activeTab === 'audit-events') {
      fetchAuditEvents()
    } else {
      fetchActiveUsers()
    }
  }, [activeTab, fetchLoginHistory, fetchStats, fetchAuditEvents, fetchActiveUsers])

  const handleUnlock = async (userId: number) => {
    setUnlocking(userId)
    try {
      await activityApi.unlockUser(userId)
      fetchLoginHistory()
      fetchStats()
      fetchActiveUsers()
    } catch { /* ignore */ }
    setUnlocking(null)
  }

  const toggleExpanded = (logId: number) => {
    setExpandedRows(prev => {
      const next = new Set(prev)
      if (next.has(logId)) next.delete(logId)
      else next.add(logId)
      return next
    })
  }

  const formatDate = (iso: string | null) => {
    if (!iso) return '—'
    const d = new Date(iso)
    return d.toLocaleString()
  }

  const totalLoginPages = Math.ceil(loginTotal / PAGE_SIZE)
  const totalAuditPages = Math.ceil(auditTotal / PAGE_SIZE)
  const totalActivePages = Math.ceil(activeUsersTotal / PAGE_SIZE)

  if (!user || user.role !== 'super_admin') return null

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <ScrollText className="w-7 h-7 text-cyan-400" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Activity Log</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">Login history, audit trail, and user activity</p>
          </div>
        </div>
        <button
          onClick={() => {
            if (activeTab === 'login-history') { fetchLoginHistory(); fetchStats() }
            else if (activeTab === 'audit-events') fetchAuditEvents()
            else fetchActiveUsers()
          }}
          className="flex items-center gap-2 px-3 py-2 text-sm bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-6">
          {[
            { key: 'login-history' as Tab, label: 'Login History', icon: ShieldAlert },
            { key: 'audit-events' as Tab, label: 'Activity Audit', icon: Activity },
            { key: 'active-users' as Tab, label: 'Active Users', icon: UserCheck },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => { setActiveTab(tab.key) }}
              className={`flex items-center gap-2 pb-3 px-1 text-sm font-medium border-b-2 transition ${
                activeTab === tab.key
                  ? 'border-cyan-500 text-cyan-600 dark:text-cyan-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab 1: Login History */}
      {activeTab === 'login-history' && (
        <div className="space-y-4">
          {/* Stats Cards */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard label="Total Logins (24h)" value={stats.logins_24h} icon={<Activity className="w-5 h-5 text-blue-500" />} />
              <StatCard label="Failed (24h)" value={stats.failed_24h} icon={<XCircle className="w-5 h-5 text-red-500" />} color="text-red-600 dark:text-red-400" />
              <StatCard label="Locked Accounts" value={stats.locked_accounts} icon={<Lock className="w-5 h-5 text-orange-500" />} color="text-orange-600 dark:text-orange-400" />
              <StatCard label="Unique Users (24h)" value={stats.unique_users_24h} icon={<Users className="w-5 h-5 text-green-500" />} />
            </div>
          )}

          {/* Filters */}
          <div className="flex flex-wrap gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Filter by email..."
                value={emailFilter}
                onChange={e => { setEmailFilter(e.target.value); setLoginPage(1) }}
                className="pl-9 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
              />
            </div>
            <select
              value={successFilter}
              onChange={e => { setSuccessFilter(e.target.value); setLoginPage(1) }}
              className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            >
              <option value="">All Status</option>
              <option value="true">Success</option>
              <option value="false">Failed</option>
            </select>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Filter by IP..."
                value={ipFilter}
                onChange={e => { setIpFilter(e.target.value); setLoginPage(1) }}
                className="pl-9 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Table */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-700/50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Date/Time</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Email</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Reason</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">IP Address</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">User Agent</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {loginLoading ? (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">Loading...</td></tr>
                ) : loginHistory.length === 0 ? (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">No login history found</td></tr>
                ) : loginHistory.map(r => (
                  <tr key={r.log_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">{formatDate(r.created_at)}</td>
                    <td className="px-4 py-3 text-gray-900 dark:text-white font-medium">{r.email_attempted}</td>
                    <td className="px-4 py-3">
                      {r.success ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 rounded-full">
                          <CheckCircle className="w-3 h-3" /> Success
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400 rounded-full">
                          <XCircle className="w-3 h-3" /> Failed
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{r.failure_reason || '—'}</td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400 font-mono text-xs">{r.ip_address || '—'}</td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400 max-w-[200px] truncate" title={r.user_agent || ''}>
                      {r.user_agent ? r.user_agent.slice(0, 60) + (r.user_agent.length > 60 ? '...' : '') : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <Pagination page={loginPage} total={totalLoginPages} onPageChange={setLoginPage} totalItems={loginTotal} />
        </div>
      )}

      {/* Tab 2: Activity Audit */}
      {activeTab === 'audit-events' && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex flex-wrap gap-3">
            <select
              value={entityTypeFilter}
              onChange={e => { setEntityTypeFilter(e.target.value); setAuditPage(1) }}
              className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            >
              <option value="">All Entity Types</option>
              <option value="auth">Auth</option>
              <option value="user">User</option>
              <option value="contact">Contact</option>
              <option value="lead">Lead</option>
              <option value="campaign">Campaign</option>
              <option value="mailbox">Mailbox</option>
            </select>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Filter by action..."
                value={actionFilter}
                onChange={e => { setActionFilter(e.target.value); setAuditPage(1) }}
                className="pl-9 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
              />
            </div>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Filter by changed_by..."
                value={changedByFilter}
                onChange={e => { setChangedByFilter(e.target.value); setAuditPage(1) }}
                className="pl-9 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Table */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-700/50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Date/Time</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Entity Type</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Entity ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Action</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Changed By</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {auditLoading ? (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">Loading...</td></tr>
                ) : auditEvents.length === 0 ? (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">No audit events found</td></tr>
                ) : auditEvents.map(r => (
                  <tr key={r.log_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">{formatDate(r.created_at)}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded-full ${
                        r.entity_type === 'auth' ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400'
                        : r.entity_type === 'user' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
                        : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                      }`}>
                        {r.entity_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{r.entity_id}</td>
                    <td className="px-4 py-3 text-gray-900 dark:text-white font-medium">{r.action}</td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{r.changed_by || '—'}</td>
                    <td className="px-4 py-3">
                      {(r.changed_fields || r.notes) ? (
                        <button
                          onClick={() => toggleExpanded(r.log_id)}
                          className="text-cyan-600 dark:text-cyan-400 hover:underline text-xs"
                        >
                          {expandedRows.has(r.log_id) ? 'Hide' : 'Show'}
                        </button>
                      ) : '—'}
                      {expandedRows.has(r.log_id) && (
                        <div className="mt-2 p-2 bg-gray-50 dark:bg-gray-900 rounded text-xs font-mono max-w-md break-all">
                          {r.notes && <p className="text-gray-600 dark:text-gray-400 mb-1">{r.notes}</p>}
                          {r.changed_fields && (
                            <pre className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                              {(() => {
                                try { return JSON.stringify(JSON.parse(r.changed_fields), null, 2) }
                                catch { return r.changed_fields }
                              })()}
                            </pre>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination page={auditPage} total={totalAuditPages} onPageChange={setAuditPage} totalItems={auditTotal} />
        </div>
      )}

      {/* Tab 3: Active Users */}
      {activeTab === 'active-users' && (
        <div className="space-y-4">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-700/50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Email</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Full Name</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Role</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Tenant</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Last Login</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Logins (30d)</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {activeUsersLoading ? (
                  <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-500">Loading...</td></tr>
                ) : activeUsers.length === 0 ? (
                  <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-500">No users found</td></tr>
                ) : activeUsers.map(u => (
                  <tr key={u.user_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                    <td className="px-4 py-3 text-gray-900 dark:text-white font-medium">{u.email}</td>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{u.full_name || '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded-full ${roleBadgeColor(u.role)}`}>
                        {roleLabel(u.role)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{u.tenant_id ?? '—'}</td>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">{formatDate(u.last_login_at)}</td>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300 text-center">{u.logins_30d}</td>
                    <td className="px-4 py-3">
                      {u.is_locked ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400 rounded-full">
                          <Lock className="w-3 h-3" /> Locked
                        </span>
                      ) : u.is_online ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 rounded-full">
                          <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" /> Online
                        </span>
                      ) : (
                        <span className="text-xs text-gray-400">Offline</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {u.is_locked && (
                        <button
                          onClick={() => handleUnlock(u.user_id)}
                          disabled={unlocking === u.user_id}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400 rounded hover:bg-orange-200 dark:hover:bg-orange-900/50 transition disabled:opacity-50"
                        >
                          <Unlock className="w-3 h-3" />
                          {unlocking === u.user_id ? 'Unlocking...' : 'Unlock'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination page={activeUsersPage} total={totalActivePages} onPageChange={setActiveUsersPage} totalItems={activeUsersTotal} />
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, icon, color }: { label: string; value: number; icon: React.ReactNode; color?: string }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{label}</span>
        {icon}
      </div>
      <p className={`text-2xl font-bold ${color || 'text-gray-900 dark:text-white'}`}>{value.toLocaleString()}</p>
    </div>
  )
}

function Pagination({ page, total, onPageChange, totalItems }: { page: number; total: number; onPageChange: (p: number) => void; totalItems: number }) {
  if (total <= 1) return null
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-gray-500 dark:text-gray-400">{totalItems.toLocaleString()} total records</span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          className="p-1.5 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="text-sm text-gray-700 dark:text-gray-300">Page {page} of {total}</span>
        <button
          onClick={() => onPageChange(Math.min(total, page + 1))}
          disabled={page >= total}
          className="p-1.5 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
