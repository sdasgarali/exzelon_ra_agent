'use client'

import { useEffect, useState } from 'react'
import { warmupApi } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

/* type definitions */
interface MailboxWarmupStatus {
  mailbox_id: number; email: string; display_name: string | null;
  warmup_status: string; is_active: boolean; warmup_day: number;
  warmup_phase: number; phase_name: string; health_score: number;
  daily_limit: number; emails_sent_today: number; total_emails_sent: number;
  bounce_rate: number; reply_rate: number; complaint_rate: number;
  warmup_started_at: string | null; warmup_completed_at: string | null;
  dns_score: number; is_blacklisted: boolean; warmup_profile_id: number | null;
}
interface WarmupStatusData {
  mailboxes: MailboxWarmupStatus[]; total_mailboxes: number;
  warming_up_count: number; cold_ready_count: number; active_count: number;
  paused_count: number; recovering_count: number; avg_health_score: number;
  dns_issues_count: number;
}
interface PhaseConfig { days: number; min_emails: number; max_emails: number }
interface WarmupConfigData {
  phase_1: PhaseConfig; phase_2: PhaseConfig; phase_3: PhaseConfig; phase_4: PhaseConfig;
  bounce_rate_good: number; bounce_rate_bad: number; reply_rate_good: number;
  complaint_rate_bad: number; weight_bounce_rate: number; weight_reply_rate: number;
  weight_complaint_rate: number; weight_age: number; auto_pause_bounce_rate: number;
  auto_pause_complaint_rate: number; min_emails_for_scoring: number;
  active_health_threshold: number; active_min_days: number; total_days: number;
  daily_increment: number;
  [key: string]: any;
}
interface ScheduleDay { day: number; phase: number; phase_name: string; recommended_emails: number }
interface ScheduleData { total_days: number; phases: any[]; schedule: ScheduleDay[] }
interface DailyLog {
  id: number; mailbox_id: number; log_date: string; emails_sent: number;
  emails_received: number; opens: number; replies: number; bounces: number;
  health_score: number; warmup_day: number; phase: number; daily_limit: number;
  bounce_rate: number; reply_rate: number;
}
interface AnalyticsData { mailbox_id: number | null; days: number; daily_logs: DailyLog[]; summary: Record<string, any> }
interface WarmupAlert {
  id: number; mailbox_id: number | null; alert_type: string; severity: string;
  title: string; message: string | null; is_read: boolean; created_at: string | null;
}
interface AlertsData { items: WarmupAlert[]; total: number; unread_count: number }
interface WarmupProfile {
  id: number; name: string; description: string | null; is_default: boolean;
  is_system: boolean; config_json: string | null; created_at: string | null;
}
interface DNSResult {
  id: number; mailbox_id: number; domain: string; spf_valid: boolean;
  dkim_valid: boolean; dmarc_valid: boolean; overall_score: number;
}
interface BlacklistResult {
  id: number; mailbox_id: number; domain: string; ip_address: string | null;
  total_checked: number; total_listed: number; is_clean: boolean;
}

interface WarmupEmailRecord {
  id: number; sender_mailbox_id: number; receiver_mailbox_id: number | null;
  subject: string | null; status: string; tracking_id: string | null;
  ai_generated: boolean; ai_provider: string | null;
  sent_at: string | null; opened_at: string | null; replied_at: string | null;
}
interface WarmupEmailDetail extends WarmupEmailRecord {
  body_html: string | null; body_text: string | null;
  sender_email: string | null; receiver_email: string | null;
}
interface WarmupEmailList { items: WarmupEmailRecord[]; total: number; page: number; limit: number }

type TabId = 'overview' | 'analytics' | 'emails' | 'dns' | 'profiles' | 'alerts' | 'settings'

/* helpers */
const statusColor: Record<string, string> = {
  warming_up: 'bg-yellow-100 text-yellow-800',
  cold_ready: 'bg-green-100 text-green-800',
  active: 'bg-blue-100 text-blue-800',
  paused: 'bg-gray-200 text-gray-700',
  inactive: 'bg-red-100 text-red-800',
  blacklisted: 'bg-red-200 text-red-900',
  recovering: 'bg-purple-100 text-purple-800',
}
function hColor(s: number) { return s >= 80 ? 'bg-green-500' : s >= 60 ? 'bg-yellow-500' : s >= 40 ? 'bg-orange-500' : 'bg-red-500' }
function hText(s: number) { return s >= 80 ? 'text-green-600' : s >= 60 ? 'text-yellow-600' : s >= 40 ? 'text-orange-600' : 'text-red-600' }

/* COMPONENT */
export default function WarmupEnginePage() {
  const { user } = useAuthStore()
  const isSuperAdmin = user?.role === 'super_admin'
  const [activeTab, setActiveTab] = useState<TabId>('overview')
  const [status, setStatus] = useState<WarmupStatusData | null>(null)
  const [config, setConfig] = useState<WarmupConfigData | null>(null)
  const [editConfig, setEditConfig] = useState<WarmupConfigData | null>(null)
  const [schedule, setSchedule] = useState<ScheduleData | null>(null)
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null)
  const [alerts, setAlerts] = useState<AlertsData | null>(null)
  const [profiles, setProfiles] = useState<WarmupProfile[]>([])
  const [dnsResults, setDnsResults] = useState<Record<number, DNSResult>>({})
  const [blacklistResults, setBlacklistResults] = useState<Record<number, BlacklistResult>>({})
  const [loading, setLoading] = useState(true)
  const [assessing, setAssessing] = useState(false)
  const [triggering, setTriggering] = useState(false)
  const [saving, setSaving] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const [analyticsDays, setAnalyticsDays] = useState(30)
  const [alertFilter, setAlertFilter] = useState<string>('all')
  const [alertReadFilter, setAlertReadFilter] = useState<string>('all')
  const [showProfileForm, setShowProfileForm] = useState(false)
  const [newProfile, setNewProfile] = useState({ name: '', description: '', config_json: '{{}}' })
  const [exportFormat, setExportFormat] = useState('csv')
  const [exportDays, setExportDays] = useState(30)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Email Threads state
  const [emailList, setEmailList] = useState<WarmupEmailList | null>(null)
  const [emailPage, setEmailPage] = useState(1)
  const [emailMailboxFilter, setEmailMailboxFilter] = useState<number | undefined>(undefined)
  const [emailDirectionFilter, setEmailDirectionFilter] = useState<string>('all')
  const [emailsLoading, setEmailsLoading] = useState(false)
  const [emailDetail, setEmailDetail] = useState<WarmupEmailDetail | null>(null)
  const [emailDetailLoading, setEmailDetailLoading] = useState(false)

  /* data fetchers */
  const fetchCore = async () => {
    try {
      setLoading(true)
      setError('')
      const [s, c, sc] = await Promise.all([warmupApi.getStatus(), warmupApi.getConfig(), warmupApi.getSchedule()])
      setStatus(s); setConfig(c); setEditConfig({ ...c }); setSchedule(sc)
      try { const u = await warmupApi.getUnreadCount(); setUnreadCount(typeof u === 'number' ? u : u?.count ?? 0) } catch {}
    } catch (e: any) { if (e.code !== 'ERR_CANCELED') { setError(e?.response?.data?.detail || 'Failed to load warmup data') } }
    finally { setLoading(false) }
  }
  const fetchAnalytics = async (days: number) => {
    try { const a = await warmupApi.getAnalytics(days); setAnalytics(a) } catch (e: any) { console.error(e) }
  }
  const fetchAlerts = async () => {
    try { const a = await warmupApi.getAlerts(); setAlerts(a); setUnreadCount(a.unread_count) } catch (e: any) { console.error(e) }
  }
  const fetchProfiles = async () => {
    try { const p = await warmupApi.getProfiles(); setProfiles(p.items || p || []) } catch (e: any) { console.error(e) }
  }

  const fetchEmails = async () => {
    try {
      setEmailsLoading(true)
      const data = await warmupApi.getPeerHistory(emailPage, 50, emailMailboxFilter, emailDirectionFilter === 'all' ? undefined : emailDirectionFilter)
      setEmailList(data)
    } catch (e: any) { console.error(e) }
    finally { setEmailsLoading(false) }
  }

  const openEmailDetail = async (emailId: number) => {
    try {
      setEmailDetailLoading(true)
      const detail = await warmupApi.getPeerEmailDetail(emailId)
      setEmailDetail(detail)
    } catch (e: any) { setError('Failed to load email detail') }
    finally { setEmailDetailLoading(false) }
  }

  useEffect(() => { fetchCore() }, [])
  useEffect(() => { if (activeTab === 'analytics') fetchAnalytics(analyticsDays) }, [activeTab, analyticsDays])
  useEffect(() => { if (activeTab === 'emails') fetchEmails() }, [activeTab, emailPage, emailMailboxFilter, emailDirectionFilter])
  useEffect(() => { if (activeTab === 'alerts') fetchAlerts() }, [activeTab])
  useEffect(() => { if (activeTab === 'profiles') fetchProfiles() }, [activeTab])

  /* actions */
  const handleAssessAll = async () => {
    try { setAssessing(true); await warmupApi.assessAll(); await fetchCore(); setSuccess('All mailboxes assessed') } catch { setError('Assessment failed') } finally { setAssessing(false) }
  }
  const handleAssessOne = async (id: number) => {
    try { await warmupApi.assessMailbox(id); await fetchCore(); setSuccess('Mailbox assessed') } catch { setError('Assessment failed') }
  }
  const handleTriggerCycle = async () => {
    try { setTriggering(true); await warmupApi.triggerPeerWarmup(); await fetchCore(); setSuccess('Warmup cycle triggered') } catch { setError('Trigger failed') } finally { setTriggering(false) }
  }
  const handleRecovery = async (id: number) => {
    try { await warmupApi.startRecovery(id); await fetchCore(); setSuccess('Recovery started') } catch { setError('Recovery failed') }
  }
  const handleSaveConfig = async () => {
    if (!editConfig) return
    try { setSaving(true); await warmupApi.updateConfig(editConfig); setConfig(editConfig); await fetchCore(); setSuccess('Config saved') } catch { setError('Save failed') } finally { setSaving(false) }
  }
  const handleDnsCheck = async (id?: number) => {
    try {
      await warmupApi.runDnsCheck(id)
      if (id) {
        try { const d = await warmupApi.getDnsResults(id); setDnsResults(prev => ({ ...prev, [id]: d.results || d })) } catch {}
      } else {
        for (const mb of (status?.mailboxes || [])) {
          try { const d = await warmupApi.getDnsResults(mb.mailbox_id); setDnsResults(prev => ({ ...prev, [mb.mailbox_id]: d.results || d })) } catch {}
        }
      }
      setSuccess('DNS check complete')
    } catch { setError('DNS check failed') }
  }
  const handleBlacklistCheck = async (id?: number) => {
    try {
      await warmupApi.runBlacklistCheck(id)
      if (id) {
        try { const b = await warmupApi.getBlacklistResults(id); setBlacklistResults(prev => ({ ...prev, [id]: b.results || b })) } catch {}
      } else {
        for (const mb of (status?.mailboxes || [])) {
          try { const b = await warmupApi.getBlacklistResults(mb.mailbox_id); setBlacklistResults(prev => ({ ...prev, [mb.mailbox_id]: b.results || b })) } catch {}
        }
      }
      setSuccess('Blacklist check complete')
    } catch { setError('Blacklist check failed') }
  }
  const handleMarkRead = async (id: number) => {
    try { await warmupApi.markAlertRead(id); await fetchAlerts() } catch {}
  }
  const handleMarkAllRead = async () => {
    try { await warmupApi.markAllAlertsRead(); await fetchAlerts(); setSuccess('All alerts marked read') } catch { setError('Failed to mark alerts') }
  }
  const handleCreateProfile = async () => {
    try {
      await warmupApi.createProfile(newProfile)
      setNewProfile({ name: '', description: '', config_json: '{{}}' }); setShowProfileForm(false)
      await fetchProfiles(); setSuccess('Profile created')
    } catch { setError('Failed to create profile') }
  }
  const handleApplyProfile = async (profileId: number, mailboxId: number) => {
    try { await warmupApi.applyProfile(profileId, mailboxId); await fetchCore(); setSuccess('Profile applied') } catch { setError('Failed to apply profile') }
  }
  const handleExport = async () => {
    try {
      const data = await warmupApi.exportReport(exportFormat, { days: exportDays })
      const blob = data instanceof Blob ? data : new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], { type: exportFormat === 'csv' ? 'text/csv' : 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = `warmup_report.${exportFormat}`; a.click(); URL.revokeObjectURL(url)
      setSuccess('Report downloaded')
    } catch { setError('Export failed') }
  }

  // Clear toasts after 4s
  useEffect(() => { if (error) { const t = setTimeout(() => setError(''), 4000); return () => clearTimeout(t) } }, [error])
  useEffect(() => { if (success) { const t = setTimeout(() => setSuccess(''), 4000); return () => clearTimeout(t) } }, [success])

  /* tabs definition */
  // Helper to resolve mailbox email from ID
  const mailboxEmailMap: Record<number, string> = {}
  for (const mb of (status?.mailboxes || [])) { mailboxEmailMap[mb.mailbox_id] = mb.email }

  const allTabs: { id: TabId; label: string }[] = [
    { id: 'overview', label: 'Overview' }, { id: 'analytics', label: 'Analytics' },
    { id: 'emails', label: 'Email Threads' },
    { id: 'dns', label: 'DNS & Blacklist' }, { id: 'profiles', label: 'Profiles' },
    { id: 'alerts', label: 'Alerts' }, { id: 'settings', label: 'Settings' },
  ]
  const tabs = isSuperAdmin ? allTabs : allTabs.filter(t => ['overview', 'analytics'].includes(t.id))

  if (loading) return <div className="flex items-center justify-center h-64"><div className="text-gray-500">Loading warmup data...</div></div>

  /* RENDER */
  return (
    <div className="space-y-6">
      {/* toast alerts */}
      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded-lg flex justify-between"><span>{error}</span><button onClick={() => setError('')} className="font-bold ml-4">x</button></div>}
      {success && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-2 rounded-lg">{success}</div>}

      {/* tab bar */}
      <div className="border-b border-gray-200">
        <nav className="flex space-x-6 -mb-px">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)}
              className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${activeTab === t.id ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}>
              {t.label}
              {t.id === 'alerts' && unreadCount > 0 && <span className="ml-1.5 inline-flex items-center justify-center px-1.5 py-0.5 text-xs font-bold leading-none text-white bg-red-500 rounded-full">{unreadCount}</span>}
            </button>
          ))}
        </nav>
      </div>

      {/* OVERVIEW TAB */}
      {activeTab === 'overview' && status && (
        <div className="space-y-6">
          {/* header row */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Warmup Engine</h1>
              <p className="text-gray-500 mt-1">Automated mailbox warmup management</p>
            </div>
            <div className="flex items-center gap-3">
              {unreadCount > 0 && <span className="inline-flex items-center gap-1 px-3 py-1 bg-red-100 text-red-700 rounded-full text-sm font-medium">{unreadCount} unread alert{unreadCount > 1 ? 's' : ''}</span>}
              {isSuperAdmin && <button onClick={handleAssessAll} disabled={assessing} className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-50 text-sm font-medium">{assessing ? 'Assessing...' : 'Assess All'}</button>}
              {isSuperAdmin && <button onClick={handleTriggerCycle} disabled={triggering} className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-sm font-medium">{triggering ? 'Triggering...' : 'Trigger Warmup Cycle'}</button>}
            </div>
          </div>

          {/* stats cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <div className="bg-white rounded-lg shadow p-4 border-l-4 border-yellow-400"><div className="text-xs text-gray-500 uppercase tracking-wide">Warming Up</div><div className="text-2xl font-bold text-yellow-600 mt-1">{status.warming_up_count}</div></div>
            <div className="bg-white rounded-lg shadow p-4 border-l-4 border-green-400"><div className="text-xs text-gray-500 uppercase tracking-wide">Cold Ready</div><div className="text-2xl font-bold text-green-600 mt-1">{status.cold_ready_count}</div></div>
            <div className="bg-white rounded-lg shadow p-4 border-l-4 border-blue-400"><div className="text-xs text-gray-500 uppercase tracking-wide">Active</div><div className="text-2xl font-bold text-blue-600 mt-1">{status.active_count}</div></div>
            <div className="bg-white rounded-lg shadow p-4 border-l-4 border-gray-400"><div className="text-xs text-gray-500 uppercase tracking-wide">Paused</div><div className="text-2xl font-bold text-gray-600 mt-1">{status.paused_count}</div></div>
            <div className="bg-white rounded-lg shadow p-4 border-l-4" style={{ borderColor: status.avg_health_score >= 80 ? '#22c55e' : status.avg_health_score >= 60 ? '#eab308' : '#ef4444' }}><div className="text-xs text-gray-500 uppercase tracking-wide">Avg Health</div><div className={`text-2xl font-bold mt-1 ${hText(status.avg_health_score)}`}>{status.avg_health_score?.toFixed(1)}</div></div>
            <div className={`bg-white rounded-lg shadow p-4 border-l-4 ${status.dns_issues_count > 0 ? 'border-red-400' : 'border-green-400'}`}><div className="text-xs text-gray-500 uppercase tracking-wide">DNS Issues</div><div className={`text-2xl font-bold mt-1 ${status.dns_issues_count > 0 ? 'text-red-600' : 'text-green-600'}`}>{status.dns_issues_count}</div></div>
          </div>

          {/* mailbox table */}
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="px-6 py-4 border-b"><h2 className="text-lg font-medium text-gray-900">Mailbox Warmup Status</h2></div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    {['Email','Day / Phase','Health Score','Status','Daily Limit','Bounce %','Reply %','DNS Score','Blacklisted','Profile ID', ...(isSuperAdmin ? ['Actions'] : [])].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {status.mailboxes.length === 0 ? (
                    <tr><td colSpan={isSuperAdmin ? 11 : 10} className="px-4 py-8 text-center text-gray-500">No mailboxes found. Add mailboxes in the Mailboxes page first.</td></tr>
                  ) : status.mailboxes.map(mb => (
                    <tr key={mb.mailbox_id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm">
                        <div className="font-medium text-gray-900">{mb.email}</div>
                        {mb.display_name && <div className="text-xs text-gray-400">{mb.display_name}</div>}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {mb.warmup_day > 0 ? (
                          <><span>Day {mb.warmup_day} / P{mb.warmup_phase}</span><br/><span className="text-xs text-gray-400">{mb.phase_name}</span></>
                        ) : <span className="text-gray-400">-</span>}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <div className="flex items-center gap-2">
                          <div className="w-16 bg-gray-200 rounded-full h-2">
                            <div className={`${hColor(mb.health_score)} h-2 rounded-full`} style={{ width: `${Math.min(100, mb.health_score)}%` }} />
                          </div>
                          <span className={`text-sm font-medium ${hText(mb.health_score)}`}>{mb.health_score.toFixed(1)}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColor[mb.warmup_status] || 'bg-gray-100 text-gray-600'}`}>{mb.warmup_status.replace(/_/g, ' ')}</span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">{mb.emails_sent_today}<span className="text-gray-400">/{mb.daily_limit}</span></td>
                      <td className="px-4 py-3 text-sm text-gray-600">{mb.bounce_rate.toFixed(1)}%</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{mb.reply_rate.toFixed(1)}%</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{mb.dns_score}</td>
                      <td className="px-4 py-3 text-sm">{mb.is_blacklisted ? <span className="text-red-600 font-bold">X</span> : <span className="text-green-600 font-bold">{String.fromCharCode(10003)}</span>}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">{mb.warmup_profile_id ?? '-'}</td>
                      {isSuperAdmin && (
                        <td className="px-4 py-3 text-sm space-x-2">
                          <button onClick={() => handleAssessOne(mb.mailbox_id)} className="text-orange-600 hover:text-orange-800 text-xs font-medium">Assess</button>
                          {(mb.warmup_status === 'paused' || mb.warmup_status === 'blacklisted') && <button onClick={() => handleRecovery(mb.mailbox_id)} className="text-purple-600 hover:text-purple-800 text-xs font-medium">Recovery</button>}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ANALYTICS TAB */}
      {activeTab === 'analytics' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Warmup Analytics</h2>
            <div className="flex gap-2">
              {[7, 14, 30, 90].map(d => (
                <button key={d} onClick={() => setAnalyticsDays(d)}
                  className={`px-3 py-1.5 rounded text-sm font-medium border ${analyticsDays === d ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'}`}>
                  {d}d
                </button>
              ))}
            </div>
          </div>

          {analytics && analytics.daily_logs.length > 0 ? (
            <>
              {/* Emails Sent Line Chart */}
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-sm font-medium text-gray-700 mb-4">Emails Sent Over Time</h3>
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={analytics.daily_logs}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="log_date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="emails_sent" stroke="#6366f1" strokeWidth={2} name="Emails Sent" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Health Score Area Chart */}
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-sm font-medium text-gray-700 mb-4">Health Score Trend</h3>
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart data={analytics.daily_logs}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="log_date" tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend />
                    <Area type="monotone" dataKey="health_score" stroke="#22c55e" fill="#bbf7d0" strokeWidth={2} name="Health Score" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              {/* Bounce vs Reply Bar Chart */}
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-sm font-medium text-gray-700 mb-4">Bounce Rate vs Reply Rate</h3>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={analytics.daily_logs}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="log_date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="bounce_rate" fill="#ef4444" name="Bounce %" />
                    <Bar dataKey="reply_rate" fill="#3b82f6" name="Reply %" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <div className="bg-white rounded-lg shadow p-12 text-center text-gray-500">No analytics data available yet. Warmup daily logs will appear here once mailboxes start warming up.</div>
          )}
        </div>
      )}

      {/* EMAIL THREADS TAB */}
      {activeTab === 'emails' && (
        <EmailThreadsTab
          status={status}
          mailboxEmailMap={mailboxEmailMap}
          emailList={emailList}
          emailsLoading={emailsLoading}
          emailPage={emailPage}
          setEmailPage={setEmailPage}
          emailMailboxFilter={emailMailboxFilter}
          setEmailMailboxFilter={setEmailMailboxFilter}
          emailDirectionFilter={emailDirectionFilter}
          setEmailDirectionFilter={setEmailDirectionFilter}
          fetchEmails={fetchEmails}
          openEmailDetail={openEmailDetail}
          emailDetail={emailDetail}
          emailDetailLoading={emailDetailLoading}
          setEmailDetail={setEmailDetail}
        />
      )}

      {/* DNS & BLACKLIST TAB */}
      {activeTab === 'dns' && status && (
        <div className="space-y-6">
          <h2 className="text-lg font-semibold text-gray-900">DNS &amp; Blacklist Monitoring</h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* DNS Section */}
            <div className="bg-white rounded-lg shadow overflow-hidden">
              <div className="px-6 py-4 border-b flex items-center justify-between">
                <h3 className="font-medium text-gray-900">DNS Health</h3>
                <button onClick={() => handleDnsCheck()} className="px-3 py-1.5 bg-blue-600 text-white rounded text-xs font-medium hover:bg-blue-700">Check All</button>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      {['Email','SPF','DKIM','DMARC','Score',''].map(h => <th key={h || 'action'} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{h}</th>)}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {status.mailboxes.map(mb => {
                      const dns = dnsResults[mb.mailbox_id]
                      return (
                        <tr key={mb.mailbox_id} className="hover:bg-gray-50">
                          <td className="px-3 py-2 font-medium text-gray-900 truncate max-w-[160px]">{mb.email}</td>
                          <td className="px-3 py-2">{dns ? <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${dns.spf_valid ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>{dns.spf_valid ? 'Pass' : 'Fail'}</span> : <span className="text-gray-400">-</span>}</td>
                          <td className="px-3 py-2">{dns ? <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${dns.dkim_valid ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>{dns.dkim_valid ? 'Pass' : 'Fail'}</span> : <span className="text-gray-400">-</span>}</td>
                          <td className="px-3 py-2">{dns ? <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${dns.dmarc_valid ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>{dns.dmarc_valid ? 'Pass' : 'Fail'}</span> : <span className="text-gray-400">-</span>}</td>
                          <td className="px-3 py-2 font-medium">{dns ? dns.overall_score : mb.dns_score}</td>
                          <td className="px-3 py-2"><button onClick={() => handleDnsCheck(mb.mailbox_id)} className="text-blue-600 hover:text-blue-800 text-xs font-medium">Run Check</button></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Blacklist Section */}
            <div className="bg-white rounded-lg shadow overflow-hidden">
              <div className="px-6 py-4 border-b flex items-center justify-between">
                <h3 className="font-medium text-gray-900">Blacklist Monitor</h3>
                <button onClick={() => handleBlacklistCheck()} className="px-3 py-1.5 bg-blue-600 text-white rounded text-xs font-medium hover:bg-blue-700">Check All</button>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      {['Email','Domain','IP','Status','Listed',''].map(h => <th key={h || 'action2'} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{h}</th>)}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {status.mailboxes.map(mb => {
                      const bl = blacklistResults[mb.mailbox_id]
                      return (
                        <tr key={mb.mailbox_id} className="hover:bg-gray-50">
                          <td className="px-3 py-2 font-medium text-gray-900 truncate max-w-[160px]">{mb.email}</td>
                          <td className="px-3 py-2 text-gray-600">{bl ? bl.domain : mb.email.split('@')[1]}</td>
                          <td className="px-3 py-2 text-gray-600">{bl?.ip_address || '-'}</td>
                          <td className="px-3 py-2">{bl ? <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${bl.is_clean ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>{bl.is_clean ? 'Clean' : 'Listed'}</span> : (mb.is_blacklisted ? <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">Listed</span> : <span className="text-gray-400">-</span>)}</td>
                          <td className="px-3 py-2 text-gray-600">{bl ? bl.total_listed : '-'}</td>
                          <td className="px-3 py-2"><button onClick={() => handleBlacklistCheck(mb.mailbox_id)} className="text-blue-600 hover:text-blue-800 text-xs font-medium">Run Check</button></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* PROFILES TAB */}
      {activeTab === 'profiles' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Warmup Profiles</h2>
            <button onClick={() => setShowProfileForm(!showProfileForm)} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">{showProfileForm ? 'Cancel' : 'Create Profile'}</button>
          </div>

          {showProfileForm && (
            <div className="bg-white rounded-lg shadow p-6 space-y-4">
              <h3 className="font-medium text-gray-900">New Profile</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div><label className="block text-xs text-gray-500 mb-1">Name</label><input type="text" value={newProfile.name} onChange={e => setNewProfile({ ...newProfile, name: e.target.value })} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" placeholder="Profile name" /></div>
                <div><label className="block text-xs text-gray-500 mb-1">Description</label><input type="text" value={newProfile.description} onChange={e => setNewProfile({ ...newProfile, description: e.target.value })} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" placeholder="Description" /></div>
              </div>
              <div><label className="block text-xs text-gray-500 mb-1">Config JSON</label><textarea value={newProfile.config_json} onChange={e => setNewProfile({ ...newProfile, config_json: e.target.value })} rows={4} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500" /></div>
              <div className="flex justify-end"><button onClick={handleCreateProfile} disabled={!newProfile.name} className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium">Save Profile</button></div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {profiles.length === 0 ? (
              <div className="col-span-full bg-white rounded-lg shadow p-8 text-center text-gray-500">No profiles yet. Create one above.</div>
            ) : profiles.map(prof => (
              <div key={prof.id} className="bg-white rounded-lg shadow p-5 border border-gray-100">
                <div className="flex items-start justify-between mb-2">
                  <h4 className="font-medium text-gray-900">{prof.name}</h4>
                  <div className="flex gap-1">
                    {prof.is_system && <span className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">System</span>}
                    {prof.is_default && <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">Default</span>}
                  </div>
                </div>
                {prof.description && <p className="text-sm text-gray-500 mb-3">{prof.description}</p>}
                <div className="mt-3 pt-3 border-t">
                  <label className="block text-xs text-gray-500 mb-1">Apply to mailbox:</label>
                  <select onChange={e => { if (e.target.value) handleApplyProfile(prof.id, Number(e.target.value)); e.target.value = '' }} className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm" defaultValue="">
                    <option value="" disabled>Select mailbox...</option>
                    {(status?.mailboxes || []).map(mb => <option key={mb.mailbox_id} value={mb.mailbox_id}>{mb.email}</option>)}
                  </select>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ALERTS TAB */}
      {activeTab === 'alerts' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <h2 className="text-lg font-semibold text-gray-900">Warmup Alerts</h2>
            <button onClick={handleMarkAllRead} className="px-3 py-1.5 bg-gray-600 text-white rounded text-sm font-medium hover:bg-gray-700">Mark All Read</button>
          </div>

          {/* filters */}
          <div className="flex flex-wrap gap-2">
            {[{ v: 'all', l: 'All', c: 'bg-gray-100 text-gray-700' }, { v: 'info', l: 'Info', c: 'bg-blue-100 text-blue-700' }, { v: 'warning', l: 'Warning', c: 'bg-yellow-100 text-yellow-800' }, { v: 'critical', l: 'Critical', c: 'bg-red-100 text-red-700' }].map(f => (
              <button key={f.v} onClick={() => setAlertFilter(f.v)} className={`px-3 py-1.5 rounded text-sm font-medium border ${alertFilter === f.v ? f.c + ' border-current' : 'bg-white text-gray-500 border-gray-300 hover:bg-gray-50'}`}>{f.l}</button>
            ))}
            <div className="border-l border-gray-300 mx-2" />
            {['all', 'unread', 'read'].map(f => (
              <button key={f} onClick={() => setAlertReadFilter(f)} className={`px-3 py-1.5 rounded text-sm font-medium border ${alertReadFilter === f ? 'bg-gray-200 text-gray-800 border-gray-400' : 'bg-white text-gray-500 border-gray-300 hover:bg-gray-50'}`}>{f.charAt(0).toUpperCase() + f.slice(1)}</button>
            ))}
          </div>

          <div className="space-y-2">
            {alerts && alerts.items.length > 0 ? (
              alerts.items
                .filter(a => alertFilter === 'all' || a.severity === alertFilter)
                .filter(a => alertReadFilter === 'all' || (alertReadFilter === 'unread' ? !a.is_read : a.is_read))
                .map(a => {
                  const sevCol = a.severity === 'critical' ? 'bg-red-500' : a.severity === 'warning' ? 'bg-amber-500' : 'bg-blue-500'
                  const sevBg = a.severity === 'critical' ? 'border-red-200' : a.severity === 'warning' ? 'border-amber-200' : 'border-blue-200'
                  return (
                    <div key={a.id} className={`bg-white rounded-lg shadow p-4 border ${sevBg} ${a.is_read ? 'opacity-60' : ''} flex items-start gap-3`}>
                      <div className={`w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0 ${sevCol}`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <h4 className="font-medium text-gray-900 text-sm">{a.title}</h4>
                          <span className="text-xs text-gray-400 ml-2 flex-shrink-0">{a.created_at ? new Date(a.created_at).toLocaleString() : ''}</span>
                        </div>
                        {a.message && <p className="text-sm text-gray-600 mt-1">{a.message}</p>}
                      </div>
                      {!a.is_read && <button onClick={() => handleMarkRead(a.id)} className="text-xs text-blue-600 hover:text-blue-800 font-medium flex-shrink-0">Mark Read</button>}
                    </div>
                  )
                })
            ) : (
              <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">No alerts found.</div>
            )}
          </div>
        </div>
      )}

      {/* SETTINGS TAB */}
      {activeTab === 'settings' && editConfig && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Warmup Settings</h2>
            <button onClick={handleSaveConfig} disabled={saving} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium">{saving ? 'Saving...' : 'Save Config'}</button>
          </div>

          {/* Phase Configuration */}
          <SettingsSection title="Phase Configuration">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {(['phase_1', 'phase_2', 'phase_3', 'phase_4'] as const).map((key, i) => {
                const names = ['Initial', 'Building Trust', 'Scaling Up', 'Full Ramp']
                const phase = (editConfig as any)[key] as PhaseConfig
                return (
                  <div key={key} className="border rounded-lg p-3 bg-gray-50">
                    <div className="text-sm font-medium text-gray-700 mb-2">{names[i]}</div>
                    <ConfigInput label="Days" type="number" value={phase.days} onChange={v => setEditConfig({ ...editConfig, [key]: { ...phase, days: v } })} />
                    <ConfigInput label="Min Emails" type="number" value={phase.min_emails} onChange={v => setEditConfig({ ...editConfig, [key]: { ...phase, min_emails: v } })} />
                    <ConfigInput label="Max Emails" type="number" value={phase.max_emails} onChange={v => setEditConfig({ ...editConfig, [key]: { ...phase, max_emails: v } })} />
                  </div>
                )
              })}
            </div>
          </SettingsSection>

          {/* Thresholds */}
          <SettingsSection title="Thresholds">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <ConfigInput label="Bounce Rate Good (%)" type="number" step="0.1" value={editConfig.bounce_rate_good} onChange={v => setEditConfig({ ...editConfig, bounce_rate_good: v })} />
              <ConfigInput label="Bounce Rate Bad (%)" type="number" step="0.1" value={editConfig.bounce_rate_bad} onChange={v => setEditConfig({ ...editConfig, bounce_rate_bad: v })} />
              <ConfigInput label="Reply Rate Good (%)" type="number" step="0.1" value={editConfig.reply_rate_good} onChange={v => setEditConfig({ ...editConfig, reply_rate_good: v })} />
              <ConfigInput label="Complaint Rate Bad (%)" type="number" step="0.01" value={editConfig.complaint_rate_bad} onChange={v => setEditConfig({ ...editConfig, complaint_rate_bad: v })} />
            </div>
          </SettingsSection>

          {/* Health Score Weights */}
          <SettingsSection title="Health Score Weights">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <ConfigInput label="Bounce Rate" type="number" value={editConfig.weight_bounce_rate} onChange={v => setEditConfig({ ...editConfig, weight_bounce_rate: v })} />
              <ConfigInput label="Reply Rate" type="number" value={editConfig.weight_reply_rate} onChange={v => setEditConfig({ ...editConfig, weight_reply_rate: v })} />
              <ConfigInput label="Complaint Rate" type="number" value={editConfig.weight_complaint_rate} onChange={v => setEditConfig({ ...editConfig, weight_complaint_rate: v })} />
              <ConfigInput label="Age" type="number" value={editConfig.weight_age} onChange={v => setEditConfig({ ...editConfig, weight_age: v })} />
            </div>
          </SettingsSection>

          {/* Auto-Pause & Recovery */}
          <SettingsSection title="Auto-Pause / Recovery">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <ConfigInput label="Auto-Pause Bounce Rate (%)" type="number" step="0.1" value={editConfig.auto_pause_bounce_rate} onChange={v => setEditConfig({ ...editConfig, auto_pause_bounce_rate: v })} />
              <ConfigInput label="Auto-Pause Complaint (%)" type="number" step="0.01" value={editConfig.auto_pause_complaint_rate} onChange={v => setEditConfig({ ...editConfig, auto_pause_complaint_rate: v })} />
              <ConfigInput label="Min Emails for Scoring" type="number" value={editConfig.min_emails_for_scoring} onChange={v => setEditConfig({ ...editConfig, min_emails_for_scoring: v })} />
              <ConfigInput label="Daily Increment" type="number" step="0.1" value={editConfig.daily_increment} onChange={v => setEditConfig({ ...editConfig, daily_increment: v })} />
            </div>
          </SettingsSection>

          {/* Promotion to Active */}
          <SettingsSection title="Promotion to Active">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <ConfigInput label="Health Threshold" type="number" value={editConfig.active_health_threshold} onChange={v => setEditConfig({ ...editConfig, active_health_threshold: v })} />
              <ConfigInput label="Min Days" type="number" value={editConfig.active_min_days} onChange={v => setEditConfig({ ...editConfig, active_min_days: v })} />
              <ConfigInput label="Total Warmup Days" type="number" value={editConfig.total_days} onChange={v => setEditConfig({ ...editConfig, total_days: v })} />
            </div>
          </SettingsSection>

          {/* Export Report */}
          <SettingsSection title="Export Report">
            <div className="flex items-end gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Format</label>
                <select value={exportFormat} onChange={e => setExportFormat(e.target.value)} className="border border-gray-300 rounded px-3 py-2 text-sm">
                  <option value="csv">CSV</option>
                  <option value="json">JSON</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Days</label>
                <input type="number" value={exportDays} onChange={e => setExportDays(Number(e.target.value))} className="border border-gray-300 rounded px-3 py-2 text-sm w-24" />
              </div>
              <button onClick={handleExport} className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium">Download</button>
            </div>
          </SettingsSection>

          {/* Warmup Schedule Chart */}
          {schedule && schedule.schedule.length > 0 && (
            <SettingsSection title="Warmup Ramp-Up Schedule">
              <ResponsiveContainer width="100%" height={250}>
                <AreaChart data={schedule.schedule}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="day" tick={{ fontSize: 11 }} label={{ value: 'Day', position: 'insideBottom', offset: -5 }} />
                  <YAxis tick={{ fontSize: 11 }} label={{ value: 'Emails', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Area type="monotone" dataKey="recommended_emails" stroke="#f97316" fill="#fed7aa" strokeWidth={2} name="Recommended Emails" />
                </AreaChart>
              </ResponsiveContainer>
            </SettingsSection>
          )}
        </div>
      )}
    </div>
  )
}

/* Reusable sub-components */
function SettingsSection({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="bg-white rounded-lg shadow">
      <button onClick={() => setOpen(!open)} className="w-full px-6 py-4 text-left font-medium text-gray-900 flex items-center justify-between border-b border-gray-100">
        <span>{title}</span>
        <span className="text-gray-400 text-sm">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="px-6 py-4">{children}</div>}
    </div>
  )
}

function ConfigInput({ label, type = 'text', step, value, onChange }: { label: string; type?: string; step?: string; value: any; onChange: (v: number) => void }) {
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      <input type={type} step={step} value={value} onChange={e => onChange(Number(e.target.value))} className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
    </div>
  )
}


/* Email Threads Tab Component */
function EmailThreadsTab({
  status, mailboxEmailMap, emailList, emailsLoading, emailPage, setEmailPage,
  emailMailboxFilter, setEmailMailboxFilter, emailDirectionFilter, setEmailDirectionFilter,
  fetchEmails, openEmailDetail, emailDetail, emailDetailLoading, setEmailDetail,
}: {
  status: WarmupStatusData | null
  mailboxEmailMap: Record<number, string>
  emailList: WarmupEmailList | null
  emailsLoading: boolean
  emailPage: number
  setEmailPage: (fn: (p: number) => number) => void
  emailMailboxFilter: number | undefined
  setEmailMailboxFilter: (v: number | undefined) => void
  emailDirectionFilter: string
  setEmailDirectionFilter: (v: string) => void
  fetchEmails: () => void
  openEmailDetail: (id: number) => void
  emailDetail: WarmupEmailDetail | null
  emailDetailLoading: boolean
  setEmailDetail: (v: WarmupEmailDetail | null) => void
}) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-lg font-semibold text-gray-900">Warmup Email Threads</h2>
        <button onClick={fetchEmails} disabled={emailsLoading} className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
          {emailsLoading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4 flex flex-wrap items-end gap-4">
        <div className="w-52">
          <label className="block text-sm font-medium text-gray-700 mb-1">Mailbox</label>
          <select value={emailMailboxFilter ?? ''} onChange={(e) => { setEmailMailboxFilter(e.target.value ? Number(e.target.value) : undefined); setEmailPage(() => 1) }} className="w-full px-3 py-2 border rounded-lg text-sm">
            <option value="">All Mailboxes</option>
            {(status?.mailboxes || []).map(mb => (
              <option key={mb.mailbox_id} value={mb.mailbox_id}>{mb.email}</option>
            ))}
          </select>
        </div>
        <div className="w-40">
          <label className="block text-sm font-medium text-gray-700 mb-1">Direction</label>
          <select value={emailDirectionFilter} onChange={(e) => { setEmailDirectionFilter(e.target.value); setEmailPage(() => 1) }} className="w-full px-3 py-2 border rounded-lg text-sm">
            <option value="all">All</option>
            <option value="sent">Sent (Outgoing)</option>
            <option value="received">Received (Incoming)</option>
          </select>
        </div>
        {emailList && <span className="text-sm text-gray-500 pb-2">{emailList.total} email{emailList.total !== 1 ? 's' : ''} found</span>}
      </div>

      {/* Email Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                {['Direction', 'From', 'To', 'Subject', 'Status', 'Sent At', 'Opened', 'Replied', 'Content'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {emailsLoading ? (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-500">Loading emails...</td></tr>
              ) : emailList && emailList.items.length > 0 ? (
                emailList.items.map(em => {
                  const isSentByFiltered = emailMailboxFilter != null && em.sender_mailbox_id === emailMailboxFilter
                  const isReceivedByFiltered = emailMailboxFilter != null && em.receiver_mailbox_id === emailMailboxFilter
                  return (
                    <tr key={em.id} className={isReceivedByFiltered ? 'bg-blue-50 hover:bg-blue-100' : 'hover:bg-gray-50'}>
                      <td className="px-4 py-3 text-sm">
                        {emailMailboxFilter != null ? (
                          isSentByFiltered ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-orange-100 text-orange-800 border border-orange-200">
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M5 10l7-7m0 0l7 7m-7-7v18" /></svg>
                              OUTGOING
                            </span>
                          ) : isReceivedByFiltered ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-200">
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" /></svg>
                              INCOMING
                            </span>
                          ) : <span className="text-gray-400">-</span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800 border border-green-200">
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
                            SENT
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <div className={`font-medium ${isSentByFiltered ? 'text-orange-700' : 'text-gray-900'}`}>{mailboxEmailMap[em.sender_mailbox_id] || `#${em.sender_mailbox_id}`}</div>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <div className={`${isReceivedByFiltered ? 'font-medium text-blue-700' : 'text-gray-700'}`}>{em.receiver_mailbox_id ? (mailboxEmailMap[em.receiver_mailbox_id] || `#${em.receiver_mailbox_id}`) : '-'}</div>
                      </td>
                      <td className="px-4 py-3 text-sm max-w-[240px]">
                        <button
                          onClick={() => openEmailDetail(em.id)}
                          className="text-left text-blue-600 hover:text-blue-800 hover:underline font-medium truncate block max-w-full"
                          title="Click to view full email"
                        >
                          {em.subject || '(no subject)'}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          em.status === 'SENT' ? 'bg-green-100 text-green-700' :
                          em.status === 'FAILED' ? 'bg-red-100 text-red-700' :
                          em.status === 'BOUNCED' ? 'bg-orange-100 text-orange-700' :
                          'bg-gray-100 text-gray-600'
                        }`}>{em.status}</span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">{em.sent_at ? new Date(em.sent_at).toLocaleString() : '-'}</td>
                      <td className="px-4 py-3 text-sm">
                        {em.opened_at ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-green-100 text-green-800 border border-green-200" title={new Date(em.opened_at).toLocaleString()}>
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 19V5a2 2 0 012-2h14a2 2 0 012 2v14M3 19l6.75-4.5M21 19l-6.75-4.5M3 5l9 6 9-6" /></svg>
                            {new Date(em.opened_at).toLocaleDateString()}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-400 border border-gray-200">
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
                            Not opened
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {em.replied_at ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-800 border border-indigo-200" title={new Date(em.replied_at).toLocaleString()}>
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>
                            {new Date(em.replied_at).toLocaleDateString()}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-400 border border-gray-200">
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
                            No reply
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {em.ai_generated ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-800 border border-purple-200" title={em.ai_provider || 'AI generated'}>
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" /></svg>
                            AI Generated
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500 border border-gray-200">
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>
                            Template
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })
              ) : (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-500">No warmup emails found. Trigger a warmup cycle to start sending.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {emailList && emailList.total > emailList.limit && (
          <div className="px-4 py-3 border-t flex items-center justify-between text-sm">
            <span className="text-gray-500">
              Page {emailList.page} of {Math.ceil(emailList.total / emailList.limit)} ({emailList.total} total)
            </span>
            <div className="flex gap-2">
              <button onClick={() => setEmailPage(p => Math.max(1, p - 1))} disabled={emailPage <= 1} className="px-3 py-1 border rounded text-sm disabled:opacity-40 hover:bg-gray-50">Prev</button>
              <button onClick={() => setEmailPage(p => p + 1)} disabled={emailPage >= Math.ceil(emailList.total / emailList.limit)} className="px-3 py-1 border rounded text-sm disabled:opacity-40 hover:bg-gray-50">Next</button>
            </div>
          </div>
        )}
      </div>

      {/* Email Detail Modal */}
      {(emailDetail || emailDetailLoading) && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={() => { if (!emailDetailLoading) setEmailDetail(null) }}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
            {emailDetailLoading ? (
              <div className="p-12 text-center text-gray-500">Loading email...</div>
            ) : emailDetail && (
              <>
                {/* Modal Header */}
                <div className="px-6 py-4 border-b flex items-start justify-between">
                  <div className="flex-1 min-w-0 pr-4">
                    <h3 className="text-lg font-semibold text-gray-900 truncate">{emailDetail.subject || '(no subject)'}</h3>
                    <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-500">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        emailDetail.status === 'SENT' ? 'bg-green-100 text-green-700' :
                        emailDetail.status === 'FAILED' ? 'bg-red-100 text-red-700' :
                        'bg-gray-100 text-gray-600'
                      }`}>{emailDetail.status}</span>
                      {emailDetail.ai_generated && <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">AI Generated ({emailDetail.ai_provider || 'AI'})</span>}
                      {emailDetail.sent_at && <span>{new Date(emailDetail.sent_at).toLocaleString()}</span>}
                    </div>
                  </div>
                  <button onClick={() => setEmailDetail(null)} className="text-gray-400 hover:text-gray-600 text-xl leading-none p-1">&times;</button>
                </div>

                {/* From / To / Tracking */}
                <div className="px-6 py-3 border-b bg-gray-50 space-y-1.5 text-sm">
                  <div className="flex">
                    <span className="w-20 text-gray-500 font-medium">From:</span>
                    <span className="text-gray-900">{emailDetail.sender_email || mailboxEmailMap[emailDetail.sender_mailbox_id] || `Mailbox #${emailDetail.sender_mailbox_id}`}</span>
                  </div>
                  <div className="flex">
                    <span className="w-20 text-gray-500 font-medium">To:</span>
                    <span className="text-gray-900">{emailDetail.receiver_email || (emailDetail.receiver_mailbox_id ? (mailboxEmailMap[emailDetail.receiver_mailbox_id] || `Mailbox #${emailDetail.receiver_mailbox_id}`) : '-')}</span>
                  </div>
                  <div className="flex items-center gap-4 pt-1 text-xs text-gray-500">
                    <span>Opened: {emailDetail.opened_at ? <span className="text-green-600 font-medium">{new Date(emailDetail.opened_at).toLocaleString()}</span> : <span className="text-gray-400">Not yet</span>}</span>
                    <span>Replied: {emailDetail.replied_at ? <span className="text-blue-600 font-medium">{new Date(emailDetail.replied_at).toLocaleString()}</span> : <span className="text-gray-400">Not yet</span>}</span>
                  </div>
                </div>

                {/* Email Body - rendered safely via sandboxed iframe */}
                <div className="flex-1 overflow-y-auto px-6 py-4 min-h-[200px]">
                  {emailDetail.body_html ? (
                    <iframe
                      sandbox=""
                      srcDoc={emailDetail.body_html}
                      title="Email content"
                      className="w-full border-0 min-h-[250px]"
                      style={{ height: '300px' }}
                      onLoad={(e) => {
                        const iframe = e.target as HTMLIFrameElement
                        if (iframe.contentDocument) {
                          iframe.style.height = (iframe.contentDocument.body.scrollHeight + 20) + 'px'
                        }
                      }}
                    />
                  ) : emailDetail.body_text ? (
                    <pre className="whitespace-pre-wrap text-sm text-gray-800 font-sans">{emailDetail.body_text}</pre>
                  ) : (
                    <div className="text-gray-400 text-center py-8">No email body available</div>
                  )}
                </div>

                {/* Modal Footer */}
                <div className="px-6 py-3 border-t bg-gray-50 flex justify-end">
                  <button onClick={() => setEmailDetail(null)} className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 text-sm font-medium">Close</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
