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
  const [mode, setMode] = useState<'mailmerge' | 'send'>('send')
  const [dryRun, setDryRun] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [channelFilter, setChannelFilter] = useState<string>('')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [threadModal, setThreadModal] = useState<ThreadData | null>(null)
  const [threadLoading, setThreadLoading] = useState(false)

  // Multi-select & delete
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    fetchData()
  }, [statusFilter, channelFilter, debouncedSearch])

  const fetchData = async () => {
    try {
      setLoading(true)
      setError('')
      const outreachParams: Record<string, any> = { limit: 100 }
      if (statusFilter) outreachParams.status = statusFilter
      if (channelFilter) outreachParams.channel = channelFilter
      if (debouncedSearch) outreachParams.search = debouncedSearch

      const [kpis, outreachData, settingsList] = await Promise.all([
        dashboardApi.kpis(),
        dashboardApi.outreachSent(outreachParams),
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
      setSelectedIds(new Set())
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
      if (err.code !== 'ERR_CANCELED') {
        setError(err.response?.data?.detail || 'Failed to fetch data')
      }
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

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === events.length && events.length > 0) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(events.map(e => e.event_id)))
    }
  }

  const isAllSelected = events.length > 0 && selectedIds.size === events.length

  const handleDeleteSelected = async () => {
    try {
      setDeleting(true)
      setError('')
      const response = await outreachApi.deleteEvents(Array.from(selectedIds))
      const count = response?.deleted_count || selectedIds.size
      setSuccess(`${count} outreach event(s) deleted successfully.`)
      setSelectedIds(new Set())
      setShowDeleteModal(false)
      fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete outreach events')
      setShowDeleteModal(false)
    } finally {
      setDeleting(false)
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

  if (loading && events.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading outreach data...</div>
      </div>
    )
  }

  return (
    <div>
      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-md w-full mx-4">
            <div className="flex items-center mb-4">
              <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center mr-3">
                <span className="text-red-600 text-xl">&#9888;</span>
              </div>
              <h3 className="text-lg font-semibold text-gray-800">Confirm Deletion</h3>
            </div>
            <p className="text-gray-600 mb-2">
              You are about to permanently delete <strong>{selectedIds.size}</strong> outreach event(s).
            </p>
            <div className="bg-red-50 border border-red-200 rounded p-3 mb-4">
              <p className="text-sm text-red-800 font-medium">This action cannot be undone.</p>
              <p className="text-sm text-red-700 mt-1">Email send records, reply data, and tracking information will be removed.</p>
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowDeleteModal(false)} disabled={deleting} className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50">Cancel</button>
              <button onClick={handleDeleteSelected} disabled={deleting} className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50">
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Outreach Management</h1>
          <p className="text-gray-500 mt-1">Send emails and track replies</p>
        </div>
        <div className="flex gap-3">
          {selectedIds.size > 0 && (
            <button
              onClick={() => setShowDeleteModal(true)}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium"
            >
              Delete Selected ({selectedIds.size})
            </button>
          )}
          <button
            onClick={handleCheckReplies}
            disabled={checkingReplies}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
          >
            {checkingReplies ? 'Checking...' : 'Check Replies'}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg mb-4 flex justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="font-bold">x</button>
        </div>
      )}

      {success && (
        <div className="bg-green-50 text-green-600 px-4 py-2 rounded-lg mb-4 flex justify-between">
          <span>{success}</span>
          <button onClick={() => setSuccess('')} className="font-bold">x</button>
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
              <option value="send">Programmatic Send</option>
              <option value="mailmerge">Mailmerge Export (CSV)</option>
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
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-semibold text-gray-800">Recent Outreach Events</h3>
            <span className="text-sm text-gray-500">{events.length} event(s)</span>
          </div>
          <div className="flex flex-wrap gap-3 items-center">
            <div className="flex-1 min-w-64">
              <input
                type="text"
                placeholder="Search contact, email, company, subject..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="input w-full"
              />
            </div>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="input w-36">
              <option value="">All Status</option>
              <option value="sent">Sent</option>
              <option value="replied">Replied</option>
              <option value="bounced">Bounced</option>
              <option value="skipped">Skipped</option>
            </select>
            <select value={channelFilter} onChange={(e) => setChannelFilter(e.target.value)} className="input w-36">
              <option value="">All Channels</option>
              <option value="smtp">SMTP</option>
              <option value="mailmerge">Mailmerge</option>
              <option value="api">API</option>
            </select>
          </div>
        </div>

        {/* Selection Bar */}
        {selectedIds.size > 0 && (
          <div className="bg-blue-50 border-b border-blue-200 px-6 py-2 flex items-center justify-between">
            <span className="text-sm text-blue-800 font-medium">{selectedIds.size} event(s) selected</span>
            <button onClick={() => setSelectedIds(new Set())} className="text-sm text-blue-600 hover:text-blue-800">Clear Selection</button>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 w-10">
                  <input type="checkbox" checked={isAllSelected} onChange={toggleSelectAll} className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Contact</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Company</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Subject</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Sent At</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Channel</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {loading ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-500">Loading events...</td></tr>
              ) : events.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-500">No outreach events found. Run the outreach pipeline to send emails.</td></tr>
              ) : (
                events.map((event) => (
                  <tr key={event.event_id} className={'hover:bg-gray-50' + (selectedIds.has(event.event_id) ? ' bg-blue-50' : '')}>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={selectedIds.has(event.event_id)} onChange={() => toggleSelect(event.event_id)} className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900 cursor-pointer" onClick={() => event.event_id && openThread(event.event_id)}>{event.contact_name || '-'}</td>
                    <td className="px-4 py-3 text-sm text-gray-500 cursor-pointer" onClick={() => event.event_id && openThread(event.event_id)}>{event.client_name || '-'}</td>
                    <td className="px-4 py-3 text-sm text-gray-900 font-mono cursor-pointer" onClick={() => event.event_id && openThread(event.event_id)}>{event.email || '-'}</td>
                    <td className="px-4 py-3 text-sm text-gray-500 max-w-xs truncate cursor-pointer" onClick={() => event.event_id && openThread(event.event_id)}>{event.subject || '-'}</td>
                    <td className="px-4 py-3 text-sm text-gray-500">{event.date_sent ? new Date(event.date_sent).toLocaleString() : '-'}</td>
                    <td className="px-4 py-3 text-sm text-gray-500">{event.channel || '-'}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 text-xs rounded-full ${getStatusBadge(event.status)}`}>
                        {event.status || '-'}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
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
