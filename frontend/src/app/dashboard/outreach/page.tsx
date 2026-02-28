'use client'

import { useState, useEffect } from 'react'
import DOMPurify from 'dompurify'
import { dashboardApi, pipelinesApi, settingsApi, outreachApi } from '@/lib/api'

interface OutreachStats {
  emails_sent: number
  emails_bounced: number
  emails_replied: number
  bounce_rate_percent: number
  reply_rate_percent: number
  total_valid_emails: number
}

interface OutreachEvent {
  event_id: number
  contact_name: string
  client_name: string
  email: string
  date_sent: string
  status: string
  channel: string
  subject: string
  body_html: string
  reply_body: string | null
  reply_subject: string | null
  reply_detected_at: string | null
  sender_mailbox_id: number | null
}

interface ThreadData {
  event_id: number
  contact_name: string | null
  contact_email: string | null
  client_name: string | null
  job_title: string | null
  sender_email: string | null
  sender_name: string | null
  sent_at: string
  subject: string | null
  body_html: string | null
  body_text: string | null
  status: string
  reply_detected_at: string | null
  reply_subject: string | null
  reply_body: string | null
  message_id: string | null
  channel: string | null
}

interface Setting {
  key: string
  value_json: string
}

export default function OutreachPage() {
  const [stats, setStats] = useState<OutreachStats | null>(null)
  const [events, setEvents] = useState<OutreachEvent[]>([])
  const [settings, setSettings] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [checkingReplies, setCheckingReplies] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [mode, setMode] = useState<'mailmerge' | 'send'>('mailmerge')
  const [dryRun, setDryRun] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [threadModal, setThreadModal] = useState<ThreadData | null>(null)
  const [threadLoading, setThreadLoading] = useState(false)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      setLoading(true)
      const [kpis, outreachData, settingsList] = await Promise.all([
        dashboardApi.kpis(),
        dashboardApi.outreachSent({ limit: 50 }),
        settingsApi.list()
      ])
      setStats({
        emails_sent: kpis.emails_sent || 0,
        emails_bounced: kpis.emails_bounced || 0,
        emails_replied: kpis.emails_replied || 0,
        bounce_rate_percent: kpis.bounce_rate_percent || 0,
        reply_rate_percent: kpis.reply_rate_percent || 0,
        total_valid_emails: kpis.total_valid_emails || 0,
      })
      setEvents(outreachData || [])
      const settingsMap: Record<string, any> = {}
      for (const s of settingsList || []) {
        try {
          settingsMap[s.key] = JSON.parse(s.value_json)
        } catch {
          settingsMap[s.key] = s.value_json
        }
      }
      setSettings(settingsMap)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch data')
    } finally {
      setLoading(false)
    }
  }

  const runOutreach = async () => {
    try {
      setRunning(true)
      setError('')
      setSuccess('')
      await pipelinesApi.runOutreach(mode, dryRun)
      if (mode === 'mailmerge') {
        setSuccess('Mailmerge export started! Check the data/exports folder for CSV file.')
      } else {
        setSuccess(`Outreach pipeline started (dry_run=${dryRun})! Check Pipelines page for progress.`)
      }
      setTimeout(() => fetchData(), 2000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start outreach pipeline')
    } finally {
      setRunning(false)
    }
  }

  const handleCheckReplies = async () => {
    try {
      setCheckingReplies(true)
      setError('')
      await outreachApi.checkReplies()
      setSuccess('Reply checking started. Results will appear shortly.')
      setTimeout(() => fetchData(), 5000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to check replies')
    } finally {
      setCheckingReplies(false)
    }
  }

  const openThread = async (eventId: number) => {
    try {
      setThreadLoading(true)
      const thread = await outreachApi.getThread(eventId)
      setThreadModal(thread)
    } catch (err: any) {
      setError('Failed to load thread')
    } finally {
      setThreadLoading(false)
    }
  }

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      sent: 'bg-blue-100 text-blue-800',
      delivered: 'bg-green-100 text-green-800',
      bounced: 'bg-red-100 text-red-800',
      replied: 'bg-purple-100 text-purple-800',
      skipped: 'bg-gray-100 text-gray-800',
    }
    return colors[status?.toLowerCase()] || 'bg-gray-100 text-gray-800'
  }

  const filteredEvents = statusFilter === 'all' ? events : events.filter(e => e.status?.toLowerCase() === statusFilter)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading outreach data...</div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Outreach Management</h1>
          <p className="text-gray-500 mt-1">Send emails and track replies</p>
        </div>
        <button
          onClick={handleCheckReplies}
          disabled={checkingReplies}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
        >
          {checkingReplies ? 'Checking...' : 'Check Replies'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg mb-4">
          {error}
        </div>
      )}

      {success && (
        <div className="bg-green-50 text-green-600 px-4 py-2 rounded-lg mb-4">
          {success}
        </div>
      )}

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <h3 className="font-semibold text-blue-800 mb-2">Outreach Workflow</h3>
        <div className="flex items-center text-sm text-blue-700">
          <span className="px-2 py-1 bg-blue-100 rounded">1. Leads Sourced</span>
          <span className="mx-2">&rarr;</span>
          <span className="px-2 py-1 bg-blue-100 rounded">2. Contacts Enriched</span>
          <span className="mx-2">&rarr;</span>
          <span className="px-2 py-1 bg-blue-100 rounded">3. Emails Validated</span>
          <span className="mx-2">&rarr;</span>
          <span className="px-2 py-1 bg-blue-200 rounded font-semibold">4. Outreach Sent</span>
        </div>
      </div>

      <div className="grid grid-cols-6 gap-4 mb-6">
        <div className="card p-4 text-center border-l-4 border-blue-500">
          <div className="text-2xl font-bold text-blue-600">{stats?.total_valid_emails || 0}</div>
          <div className="text-sm text-gray-500">Valid Emails</div>
        </div>
        <div className="card p-4 text-center border-l-4 border-green-500">
          <div className="text-2xl font-bold text-green-600">{stats?.emails_sent || 0}</div>
          <div className="text-sm text-gray-500">Emails Sent</div>
        </div>
        <div className="card p-4 text-center border-l-4 border-purple-500">
          <div className="text-2xl font-bold text-purple-600">{stats?.emails_replied || 0}</div>
          <div className="text-sm text-gray-500">Replies</div>
        </div>
        <div className="card p-4 text-center border-l-4 border-red-500">
          <div className="text-2xl font-bold text-red-600">{stats?.emails_bounced || 0}</div>
          <div className="text-sm text-gray-500">Bounced</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-gray-800">{stats?.bounce_rate_percent?.toFixed(1) || 0}%</div>
          <div className="text-sm text-gray-500">Bounce Rate</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-gray-800">{stats?.reply_rate_percent?.toFixed(1) || 0}%</div>
          <div className="text-sm text-gray-500">Reply Rate</div>
        </div>
      </div>

      <div className="card p-6 mb-6">
        <h3 className="font-semibold text-gray-800 mb-4">Run Outreach</h3>
        <div className="grid grid-cols-3 gap-6">
          <div>
            <label className="label">Outreach Mode</label>
            <select value={mode} onChange={(e) => setMode(e.target.value as 'mailmerge' | 'send')} className="input">
              <option value="mailmerge">Mailmerge Export (CSV)</option>
              <option value="send">Programmatic Send</option>
            </select>
          </div>
          {mode === 'send' && (
            <div>
              <label className="label">Dry Run</label>
              <div className="flex items-center gap-3">
                <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} className="w-4 h-4" />
                <span className="text-sm text-gray-600">
                  {dryRun ? 'Simulate only' : 'Send real emails'}
                </span>
              </div>
            </div>
          )}
          <div className="flex items-end">
            <button onClick={runOutreach} disabled={running} className="btn-primary">
              {running ? 'Starting...' : mode === 'mailmerge' ? 'Export for Mailmerge' : 'Run Outreach'}
            </button>
          </div>
        </div>
        <div className="mt-4 p-3 bg-gray-50 rounded-lg">
          <h4 className="text-sm font-medium text-gray-700 mb-2">Business Rules Applied:</h4>
          <div className="grid grid-cols-3 gap-4 text-sm text-gray-600">
            <div>Daily Limit: <span className="font-mono">{settings.daily_send_limit || 30}</span></div>
            <div>Cooldown: <span className="font-mono">{settings.cooldown_days || 10} days</span></div>
            <div>Max per Job: <span className="font-mono">{settings.max_contacts_per_company_job || 4}</span></div>
          </div>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h3 className="font-semibold text-gray-800">Recent Outreach Events</h3>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="text-sm border border-gray-300 rounded-lg px-3 py-1">
            <option value="all">All Status</option>
            <option value="sent">Sent</option>
            <option value="replied">Replied</option>
            <option value="bounced">Bounced</option>
            <option value="skipped">Skipped</option>
          </select>
        </div>
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Contact</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Company</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Subject</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Sent At</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Channel</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {filteredEvents.map((event, idx) => (
              <tr key={idx} className="hover:bg-gray-50 cursor-pointer" onClick={() => event.event_id && openThread(event.event_id)}>
                <td className="px-6 py-4 text-sm text-gray-900">{event.contact_name || '-'}</td>
                <td className="px-6 py-4 text-sm text-gray-500">{event.client_name || '-'}</td>
                <td className="px-6 py-4 text-sm text-gray-900 font-mono">{event.email || '-'}</td>
                <td className="px-6 py-4 text-sm text-gray-500 max-w-xs truncate">{event.subject || '-'}</td>
                <td className="px-6 py-4 text-sm text-gray-500">{event.date_sent ? new Date(event.date_sent).toLocaleString() : '-'}</td>
                <td className="px-6 py-4 text-sm text-gray-500">{event.channel || '-'}</td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 text-xs rounded-full ${getStatusBadge(event.status)}`}>
                    {event.status || '-'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filteredEvents.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            No outreach events yet. Run the outreach pipeline to send emails.
          </div>
        )}
      </div>

      {/* Thread Modal */}
      {threadModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto">
            <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-start">
              <div>
                <h3 className="text-lg font-semibold text-gray-800">Email Thread</h3>
                <div className="mt-1 text-sm text-gray-500">
                  <span className="font-medium">{threadModal.contact_name}</span>
                  {threadModal.contact_email && (
                    <span> &lt;{threadModal.contact_email}&gt;</span>
                  )}
                </div>
                {threadModal.client_name && (
                  <div className="text-sm text-gray-400">{threadModal.client_name} {threadModal.job_title && `- ${threadModal.job_title}`}</div>
                )}
              </div>
              <button onClick={() => setThreadModal(null)} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
            </div>
            <div className="p-6">
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                  <span className="text-sm font-medium text-blue-700">Sent</span>
                  <span className="text-xs text-gray-400">
                    {threadModal.sent_at ? new Date(threadModal.sent_at).toLocaleString() : ''}
                  </span>
                  {threadModal.sender_email && (
                    <span className="text-xs text-gray-400">via {threadModal.sender_email}</span>
                  )}
                </div>
                <div className="text-sm font-medium text-gray-700 mb-2">Subject: {threadModal.subject}</div>
                <div
                  className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm"
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(threadModal.body_html || threadModal.body_text || 'No content') }}
                />
              </div>

              {threadModal.reply_body ? (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-3 h-3 rounded-full bg-purple-500"></div>
                    <span className="text-sm font-medium text-purple-700">Replied</span>
                    <span className="text-xs text-gray-400">
                      {threadModal.reply_detected_at ? new Date(threadModal.reply_detected_at).toLocaleString() : ''}
                    </span>
                    {threadModal.reply_body?.toLowerCase().includes('unsubscribe') && (
                      <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs rounded-full">UNSUBSCRIBE</span>
                    )}
                  </div>
                  {threadModal.reply_subject && (
                    <div className="text-sm font-medium text-gray-700 mb-2">Subject: {threadModal.reply_subject}</div>
                  )}
                  <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 text-sm whitespace-pre-wrap">
                    {threadModal.reply_body}
                  </div>
                </div>
              ) : (
                <div className="text-center py-4 text-gray-400 text-sm">No reply received yet</div>
              )}
            </div>
            <div className="px-6 py-3 border-t border-gray-200 flex justify-end">
              <button onClick={() => setThreadModal(null)} className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">Close</button>
            </div>
          </div>
        </div>
      )}

      {threadLoading && (
        <div className="fixed inset-0 bg-black bg-opacity-30 z-50 flex items-center justify-center">
          <div className="bg-white rounded-lg p-6 shadow-lg">
            <div className="text-gray-500">Loading thread...</div>
          </div>
        </div>
      )}
    </div>
  )
}

