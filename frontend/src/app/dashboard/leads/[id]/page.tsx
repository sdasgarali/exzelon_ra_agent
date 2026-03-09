'use client'

import { useState, useEffect, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { leadsApi, outreachApi, contactsApi } from '@/lib/api'

interface Contact {
  contact_id: number
  first_name: string
  last_name: string
  email: string
  title: string
  priority_level: string
  validation_status: string
  source: string
}

interface OutreachEvent {
  event_id: number
  contact_id: number
  lead_id: number | null
  sender_mailbox_id: number | null
  sent_at: string
  channel: string
  template_id: number | null
  subject: string
  message_id: string | null
  status: string
  bounce_reason: string | null
  reply_detected_at: string | null
  skip_reason: string | null
  body_html: string | null
  body_text: string | null
  reply_subject: string | null
  reply_body: string | null
  created_at: string
  updated_at: string
  contact_name: string | null
  contact_email: string | null
  sender_email: string | null
  sender_name: string | null
}

interface LeadDetail {
  lead_id: number
  client_name: string
  job_title: string
  state: string
  posting_date: string
  job_link: string
  salary_min: number
  salary_max: number
  source: string
  lead_status: string
  ra_name: string
  first_name: string
  last_name: string
  contact_email: string
  contact_phone: string
  contact_count: number
  created_at: string
  updated_at: string
  contacts: Contact[]
  outreach_events: OutreachEvent[]
}

const STATUS_COLORS: Record<string, string> = {
  new: 'bg-slate-100 text-slate-800',
  enriched: 'bg-purple-100 text-purple-800',
  validated: 'bg-teal-100 text-teal-800',
  open: 'bg-green-100 text-green-800',
  hunting: 'bg-yellow-100 text-yellow-800',
  sent: 'bg-indigo-100 text-indigo-800',
  skipped: 'bg-orange-100 text-orange-800',
  closed_hired: 'bg-blue-100 text-blue-800',
  closed_not_hired: 'bg-gray-100 text-gray-800',
}

const EVENT_STATUS_STYLES: Record<string, { bg: string; icon: string }> = {
  sent: { bg: 'bg-indigo-50 border-indigo-200 text-indigo-700', icon: '\u2709' },
  replied: { bg: 'bg-green-50 border-green-200 text-green-700', icon: '\u21A9' },
  bounced: { bg: 'bg-red-50 border-red-200 text-red-700', icon: '\u26A0' },
  skipped: { bg: 'bg-gray-50 border-gray-200 text-gray-600', icon: '\u23ED' },
}

const UNSUBSCRIBE_REGEX = /\b(unsubscribe|remove me|stop emailing|opt out|do not contact)\b/i

function isUnsubscribe(replyBody: string | null, replySubject: string | null): boolean {
  if (replyBody && UNSUBSCRIBE_REGEX.test(replyBody)) return true
  if (replySubject && UNSUBSCRIBE_REGEX.test(replySubject)) return true
  return false
}

/** Auto-resizing iframe for HTML email content */
function EmailHtmlFrame({ html }: { html: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    const iframe = iframeRef.current
    if (!iframe) return
    const doc = iframe.contentDocument || iframe.contentWindow?.document
    if (!doc) return
    doc.open()
    doc.write(
      '<html><head><style>body{margin:0;padding:16px;font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:14px;line-height:1.5;color:#333;word-wrap:break-word}img{max-width:100%}a{color:#4f46e5}</style></head><body>' +
        html +
      '</body></html>'
    )
    doc.close()

    // Auto-resize after content loads
    const resizeIframe = () => {
      try {
        const body = doc.body
        if (body) {
          const height = Math.min(body.scrollHeight + 20, 600)
          iframe.style.height = height + 'px'
        }
      } catch (e) { /* cross-origin guard */ }
    }
    setTimeout(resizeIframe, 100)
    setTimeout(resizeIframe, 500)
  }, [html])

  return (
    <iframe
      ref={iframeRef}
      sandbox="allow-same-origin"
      className="w-full border-0 rounded bg-white min-h-[100px]"
      style={{ height: '200px' }}
      title="Email content"
    />
  )
}

export default function LeadDetailPage() {
  const params = useParams()
  const router = useRouter()
  const leadId = Number(params.id)

  const [lead, setLead] = useState<LeadDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [expandedEvent, setExpandedEvent] = useState<number | null>(null)
  const [sendingOutreach, setSendingOutreach] = useState(false)
  const [dryRun, setDryRun] = useState(true)
  const [removingContact, setRemovingContact] = useState<number | null>(null)
  const [checkingReplies, setCheckingReplies] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('all')

  // Link contact modal
  const [showLinkModal, setShowLinkModal] = useState(false)
  const [linkSearch, setLinkSearch] = useState('')
  const [linkResults, setLinkResults] = useState<any[]>([])
  const [linkSearching, setLinkSearching] = useState(false)
  const [linking, setLinking] = useState(false)
  const linkSearchTimeout = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    if (leadId) fetchLeadDetail()
  }, [leadId])

  const fetchLeadDetail = async () => {
    try {
      setLoading(true)
      const data = await leadsApi.getDetail(leadId)
      setLead(data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch lead details')
    } finally {
      setLoading(false)
    }
  }

  const handleRemoveContact = async (contactId: number) => {
    try {
      setRemovingContact(contactId)
      await leadsApi.manageContacts(leadId, { remove_contact_ids: [contactId] })
      setSuccess('Contact removed from this lead')
      fetchLeadDetail()
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to remove contact')
    } finally {
      setRemovingContact(null)
    }
  }

  const handleSendOutreach = async () => {
    try {
      setSendingOutreach(true)
      const result = await leadsApi.runOutreach(leadId, dryRun)
      if (dryRun) {
        setSuccess('Dry run complete: ' + (result.message || JSON.stringify(result)))
      } else {
        setSuccess('Outreach sent successfully!')
        fetchLeadDetail()
      }
      setTimeout(() => setSuccess(''), 5000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send outreach')
    } finally {
      setSendingOutreach(false)
    }
  }

  const handleCheckReplies = async () => {
    try {
      setCheckingReplies(true)
      setError('')
      const result = await outreachApi.checkReplies()
      const msg = result.message || `Checked ${result.checked || 0} events, found ${result.replies_found || 0} replies`
      setSuccess(msg)
      fetchLeadDetail()
      setTimeout(() => setSuccess(''), 5000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to check replies')
    } finally {
      setCheckingReplies(false)
    }
  }

  // Search contacts for linking (search by company name by default)
  const handleLinkSearch = (query: string) => {
    setLinkSearch(query)
    if (linkSearchTimeout.current) clearTimeout(linkSearchTimeout.current)
    if (!query || query.length < 2) { setLinkResults([]); return }
    linkSearchTimeout.current = setTimeout(async () => {
      try {
        setLinkSearching(true)
        const results = await contactsApi.list({ search: query, page_size: 20 })
        const items = Array.isArray(results) ? results : (results?.items || [])
        // Filter out already-linked contacts
        const existingIds = new Set((lead?.contacts || []).map((c: any) => c.contact_id))
        setLinkResults(items.filter((c: any) => !existingIds.has(c.contact_id)))
      } catch { setLinkResults([]) }
      finally { setLinkSearching(false) }
    }, 300)
  }

  const handleLinkContact = async (contactId: number) => {
    try {
      setLinking(true)
      await leadsApi.manageContacts(leadId, { add_contact_ids: [contactId] })
      setSuccess('Contact linked to this lead!')
      fetchLeadDetail()
      setShowLinkModal(false)
      setLinkSearch('')
      setLinkResults([])
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to link contact')
    } finally {
      setLinking(false)
    }
  }

  const openLinkModal = () => {
    setShowLinkModal(true)
    // Pre-search by company name
    if (lead?.client_name) {
      handleLinkSearch(lead.client_name)
    }
  }

  const formatDate = (d: string | null) => {
    if (!d) return '-'
    try { return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) }
    catch { return d }
  }

  const formatDateTime = (d: string | null) => {
    if (!d) return '-'
    try { return new Date(d).toLocaleString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
    catch { return d }
  }

  const formatSalary = (min: number | null, max: number | null) => {
    if (!min && !max) return '-'
    const fmt = (v: number) => '$' + v.toLocaleString()
    if (min && max) return fmt(min) + ' - ' + fmt(max)
    if (min) return fmt(min) + '+'
    return 'Up to ' + fmt(max!)
  }

  // Filter events by status
  const filteredEvents = lead?.outreach_events.filter(evt => {
    if (statusFilter === 'all') return true
    return evt.status === statusFilter
  }) || []

  // Count by status
  const statusCounts = lead?.outreach_events.reduce((acc, evt) => {
    acc[evt.status] = (acc[evt.status] || 0) + 1
    return acc
  }, {} as Record<string, number>) || {}

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-gray-500">Loading lead details...</div>
      </div>
    )
  }

  if (error && !lead) {
    return (
      <div className="max-w-4xl mx-auto py-8">
        <div className="bg-red-50 text-red-600 px-4 py-3 rounded-lg mb-4">{error}</div>
        <button onClick={() => router.push('/dashboard/leads')} className="btn-secondary">Back to Leads</button>
      </div>
    )
  }

  if (!lead) return null

  return (
    <div className="max-w-6xl mx-auto">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-gray-500 mb-4">
        <Link href="/dashboard/leads" className="hover:text-blue-600">Leads</Link>
        <span>/</span>
        <span className="text-gray-800 font-medium">#{lead.lead_id} - {lead.client_name}</span>
      </div>

      {/* Alerts */}
      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg mb-4 flex justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="font-bold">x</button>
        </div>
      )}
      {success && (
        <div className="bg-green-50 text-green-600 px-4 py-2 rounded-lg mb-4">{success}</div>
      )}

      {/* Lead Info Card */}
      <div className="card p-6 mb-6">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">{lead.client_name}</h1>
            <p className="text-lg text-gray-600 mt-1">{lead.job_title}</p>
          </div>
          <span className={'px-3 py-1 rounded-full text-sm font-medium ' + (STATUS_COLORS[lead.lead_status] || 'bg-gray-100 text-gray-800')}>
            {lead.lead_status}
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">State:</span>
            <span className="ml-2 font-medium">{lead.state || '-'}</span>
          </div>
          <div>
            <span className="text-gray-500">Posted:</span>
            <span className="ml-2 font-medium">{formatDate(lead.posting_date)}</span>
          </div>
          <div>
            <span className="text-gray-500">Salary:</span>
            <span className="ml-2 font-medium">{formatSalary(lead.salary_min, lead.salary_max)}</span>
          </div>
          <div>
            <span className="text-gray-500">Source:</span>
            <span className="ml-2"><span className="px-2 py-0.5 bg-gray-100 rounded text-xs">{lead.source}</span></span>
          </div>
          <div>
            <span className="text-gray-500">Created:</span>
            <span className="ml-2 font-medium">{formatDate(lead.created_at)}</span>
          </div>
          <div>
            <span className="text-gray-500">Updated:</span>
            <span className="ml-2 font-medium">{formatDate(lead.updated_at)}</span>
          </div>
          {lead.job_link && (
            <div className="col-span-2">
              <span className="text-gray-500">Job Link:</span>
              <a href={lead.job_link} target="_blank" rel="noopener noreferrer" className="ml-2 text-blue-600 hover:underline">View Posting</a>
            </div>
          )}
        </div>
      </div>

      {/* Link Contact Modal */}
      {showLinkModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-lg w-full mx-4 max-h-[80vh] flex flex-col">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold text-gray-800">Link Contact to Lead</h3>
              <button onClick={() => { setShowLinkModal(false); setLinkSearch(''); setLinkResults([]) }} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
            </div>

            <div className="mb-3">
              <input
                value={linkSearch}
                onChange={e => handleLinkSearch(e.target.value)}
                className="input w-full"
                placeholder="Search contacts by name, email, or company..."
                autoFocus
              />
            </div>

            <div className="flex-1 overflow-y-auto min-h-0">
              {linkSearching && <p className="text-sm text-gray-500 text-center py-4">Searching...</p>}

              {!linkSearching && linkResults.length > 0 && (
                <div className="divide-y divide-gray-100">
                  {linkResults.map((c: any) => (
                    <div key={c.contact_id} className="flex items-center justify-between py-3 px-2 hover:bg-gray-50 rounded">
                      <div>
                        <p className="text-sm font-medium text-gray-900">{c.first_name} {c.last_name}</p>
                        <p className="text-xs text-gray-500">{c.email} {c.client_name ? `— ${c.client_name}` : ''}</p>
                        {c.title && <p className="text-xs text-gray-400">{c.title}</p>}
                      </div>
                      <button
                        onClick={() => handleLinkContact(c.contact_id)}
                        disabled={linking}
                        className="px-3 py-1 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                      >
                        Link
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {!linkSearching && linkSearch.length >= 2 && linkResults.length === 0 && (
                <div className="text-center py-6">
                  <p className="text-sm text-gray-500 mb-2">No matching contacts found.</p>
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-left">
                    <p className="text-sm font-medium text-blue-800 mb-1">Need to add a new contact?</p>
                    <p className="text-sm text-blue-700 mb-2">
                      Create the contact first on the{' '}
                      <Link href="/dashboard/contacts" className="underline font-medium">Contacts page</Link>{' '}
                      under the company <strong>{lead.client_name}</strong>, then come back here to link them.
                    </p>
                    <Link href="/dashboard/contacts" className="inline-block px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
                      Go to Contacts Page
                    </Link>
                  </div>
                </div>
              )}

              {!linkSearching && linkSearch.length < 2 && (
                <p className="text-sm text-gray-400 text-center py-4">Type at least 2 characters to search.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Contacts Section */}
      <div className="card mb-6">
        <div className="px-6 py-4 border-b flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-800">
            Contacts ({lead.contacts.length})
          </h2>
          <button
            onClick={openLinkModal}
            className="px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
          >
            + Link Contact
          </button>
        </div>
        {lead.contacts.length === 0 ? (
          <div className="px-6 py-8 text-center text-gray-500">
            <p>No contacts linked to this lead.</p>
            <p className="text-sm mt-2">Run Contact Enrichment to discover contacts, or{' '}
              <button onClick={openLinkModal} className="text-blue-600 hover:underline font-medium">link an existing contact</button> manually.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Priority</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Validation</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {lead.contacts.map((c) => (
                  <tr key={c.contact_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium text-gray-900">{c.first_name} {c.last_name}</div>
                      <div className="text-xs text-gray-500">{c.title || '-'}</div>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <a href={'mailto:' + c.email} className="text-blue-600 hover:underline">{c.email}</a>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-700">
                        {c.priority_level ? c.priority_level.split('_')[0].toUpperCase() : '-'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={'text-xs px-2 py-1 rounded-full ' + (
                        c.validation_status === 'valid' ? 'bg-green-100 text-green-800' :
                        c.validation_status === 'invalid' ? 'bg-red-100 text-red-800' :
                        'bg-gray-100 text-gray-600'
                      )}>
                        {c.validation_status || 'pending'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{c.source || '-'}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleRemoveContact(c.contact_id)}
                        disabled={removingContact === c.contact_id}
                        className="text-xs text-red-600 hover:text-red-800 disabled:opacity-50"
                      >
                        {removingContact === c.contact_id ? 'Removing...' : 'Remove'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Outreach Section - Inbox Style */}
      <div className="card mb-6">
        <div className="px-6 py-4 border-b">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-lg font-semibold text-gray-800">
              Outreach ({lead.outreach_events.length} events)
            </h2>
            <div className="flex items-center gap-3">
              <button
                onClick={handleCheckReplies}
                disabled={checkingReplies}
                className="border border-gray-300 text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-50 disabled:opacity-50 text-sm font-medium"
              >
                {checkingReplies ? 'Checking...' : 'Check Replies'}
              </button>
              <label className="flex items-center gap-2 text-sm text-gray-600">
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                  className="w-4 h-4"
                />
                Dry Run
              </label>
              <button
                onClick={handleSendOutreach}
                disabled={sendingOutreach || lead.contacts.length === 0}
                className="bg-indigo-600 text-white px-4 py-1.5 rounded-lg hover:bg-indigo-700 disabled:opacity-50 text-sm font-medium"
              >
                {sendingOutreach ? 'Sending...' : 'Send Outreach'}
              </button>
            </div>
          </div>
          {/* Status filter tabs */}
          <div className="flex gap-1">
            {[
              { key: 'all', label: 'All', count: lead.outreach_events.length },
              { key: 'sent', label: 'Sent', count: statusCounts['sent'] || 0 },
              { key: 'replied', label: 'Replied', count: statusCounts['replied'] || 0 },
              { key: 'bounced', label: 'Bounced', count: statusCounts['bounced'] || 0 },
              { key: 'skipped', label: 'Skipped', count: statusCounts['skipped'] || 0 },
            ].filter(t => t.key === 'all' || t.count > 0).map(tab => (
              <button
                key={tab.key}
                onClick={() => setStatusFilter(tab.key)}
                className={
                  'px-3 py-1 rounded-full text-xs font-medium transition-colors ' +
                  (statusFilter === tab.key
                    ? 'bg-indigo-100 text-indigo-700'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200')
                }
              >
                {tab.label} ({tab.count})
              </button>
            ))}
          </div>
        </div>

        {filteredEvents.length === 0 ? (
          <div className="px-6 py-8 text-center text-gray-500">
            {lead.outreach_events.length === 0
              ? 'No outreach events yet. Click "Send Outreach" to email contacts linked to this lead.'
              : 'No events match the selected filter.'}
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {filteredEvents.map((evt) => {
              const isExpanded = expandedEvent === evt.event_id
              const style = EVENT_STATUS_STYLES[evt.status] || EVENT_STATUS_STYLES.sent
              const hasReply = !!evt.reply_body
              const isUnsub = isUnsubscribe(evt.reply_body, evt.reply_subject)

              return (
                <div key={evt.event_id}>
                  {/* Inbox row */}
                  <div
                    onClick={() => setExpandedEvent(isExpanded ? null : evt.event_id)}
                    className={'px-6 py-3 flex items-center gap-4 cursor-pointer transition-colors ' +
                      (isExpanded ? 'bg-indigo-50/50' : 'hover:bg-gray-50') +
                      (hasReply && !isExpanded ? ' font-medium' : '')
                    }
                  >
                    {/* Status icon */}
                    <div className={'w-8 h-8 rounded-full flex items-center justify-center text-sm border ' + style.bg}>
                      {style.icon}
                    </div>

                    {/* From/To */}
                    <div className="min-w-[180px] max-w-[220px]">
                      <div className="text-sm text-gray-900 truncate">
                        {evt.sender_name || evt.sender_email || 'Sender'}
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {'\u2192 ' + (evt.contact_name || evt.contact_email || 'Contact #' + evt.contact_id)}
                      </div>
                    </div>

                    {/* Subject */}
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-gray-800 truncate">
                        {evt.subject || '(no subject)'}
                      </div>
                      {hasReply && (
                        <div className="text-xs text-green-600 truncate mt-0.5">
                          Reply: {evt.reply_body?.slice(0, 80)}...
                        </div>
                      )}
                    </div>

                    {/* Badges */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {isUnsub && (
                        <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-semibold rounded-full">
                          UNSUBSCRIBED
                        </span>
                      )}
                      {hasReply && !isUnsub && (
                        <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs font-medium rounded-full">
                          Replied
                        </span>
                      )}
                      <span className={'px-2 py-0.5 text-xs rounded-full border ' + style.bg}>
                        {evt.status}
                      </span>
                    </div>

                    {/* Date */}
                    <div className="text-xs text-gray-400 w-[110px] text-right flex-shrink-0">
                      {formatDateTime(evt.sent_at)}
                    </div>

                    {/* Expand chevron */}
                    <span className="text-gray-400 text-xs flex-shrink-0">
                      {isExpanded ? '\u25B2' : '\u25BC'}
                    </span>
                  </div>

                  {/* Expanded thread view */}
                  {isExpanded && (
                    <div className="px-6 pb-5 pt-2 bg-gray-50/50">
                      {/* Sent email block */}
                      <div className="border-l-4 border-indigo-400 bg-white rounded-r-lg shadow-sm mb-4">
                        <div className="px-4 py-3 border-b border-gray-100">
                          <div className="flex justify-between items-start">
                            <div className="text-sm">
                              <span className="font-semibold text-gray-800">From:</span>{' '}
                              <span className="text-gray-700">
                                {evt.sender_name || 'Unknown'}{' '}
                                {evt.sender_email && <span className="text-gray-400">&lt;{evt.sender_email}&gt;</span>}
                              </span>
                            </div>
                            <div className="text-xs text-gray-400">{formatDateTime(evt.sent_at)}</div>
                          </div>
                          <div className="text-sm mt-1">
                            <span className="font-semibold text-gray-800">To:</span>{' '}
                            <span className="text-gray-700">
                              {evt.contact_name || 'Unknown'}{' '}
                              {evt.contact_email && <span className="text-gray-400">&lt;{evt.contact_email}&gt;</span>}
                            </span>
                          </div>
                          {evt.subject && (
                            <div className="text-sm mt-1">
                              <span className="font-semibold text-gray-800">Subject:</span>{' '}
                              <span className="text-gray-700">{evt.subject}</span>
                            </div>
                          )}
                        </div>
                        <div className="px-4 py-3">
                          {evt.body_html ? (
                            <EmailHtmlFrame html={evt.body_html} />
                          ) : evt.body_text ? (
                            <div className="text-sm text-gray-700 whitespace-pre-wrap">{evt.body_text}</div>
                          ) : (
                            <div className="text-sm text-gray-400 italic">No email content stored.</div>
                          )}
                        </div>
                      </div>

                      {/* Reply block */}
                      {evt.reply_body && (
                        <div className={'border-l-4 bg-white rounded-r-lg shadow-sm ' +
                          (isUnsub ? 'border-red-400' : 'border-green-400')
                        }>
                          <div className="px-4 py-3 border-b border-gray-100">
                            <div className="flex justify-between items-start">
                              <div className="text-sm">
                                <span className="font-semibold text-gray-800">From:</span>{' '}
                                <span className="text-gray-700">
                                  {evt.contact_name || 'Unknown'}{' '}
                                  {evt.contact_email && <span className="text-gray-400">&lt;{evt.contact_email}&gt;</span>}
                                </span>
                              </div>
                              <div className="flex items-center gap-2">
                                {isUnsub && (
                                  <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-semibold rounded-full">
                                    UNSUBSCRIBED
                                  </span>
                                )}
                                <span className="text-xs text-gray-400">{formatDateTime(evt.reply_detected_at)}</span>
                              </div>
                            </div>
                            <div className="text-sm mt-1">
                              <span className="font-semibold text-gray-800">To:</span>{' '}
                              <span className="text-gray-700">
                                {evt.sender_name || 'Unknown'}{' '}
                                {evt.sender_email && <span className="text-gray-400">&lt;{evt.sender_email}&gt;</span>}
                              </span>
                            </div>
                            {evt.reply_subject && (
                              <div className="text-sm mt-1">
                                <span className="font-semibold text-gray-800">Subject:</span>{' '}
                                <span className="text-gray-700">{evt.reply_subject}</span>
                              </div>
                            )}
                          </div>
                          <div className="px-4 py-3">
                            <div className="text-sm text-gray-700 whitespace-pre-wrap">{evt.reply_body}</div>
                          </div>
                        </div>
                      )}

                      {/* Bounce info */}
                      {evt.bounce_reason && (
                        <div className="border-l-4 border-red-400 bg-red-50 rounded-r-lg p-4 mt-4">
                          <div className="text-sm font-medium text-red-800">Bounce Reason</div>
                          <div className="text-sm text-red-700 mt-1">{evt.bounce_reason}</div>
                        </div>
                      )}

                      {/* Skip reason */}
                      {evt.skip_reason && (
                        <div className="border-l-4 border-gray-300 bg-gray-50 rounded-r-lg p-4 mt-4">
                          <div className="text-sm font-medium text-gray-700">Skip Reason</div>
                          <div className="text-sm text-gray-600 mt-1">{evt.skip_reason}</div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
