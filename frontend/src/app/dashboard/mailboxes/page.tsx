'use client'

import { useState, useEffect, useMemo } from 'react'
import { mailboxesApi } from '@/lib/api'

interface Mailbox {
  mailbox_id: number
  email: string
  display_name: string | null
  provider: string
  smtp_host: string | null
  smtp_port: number
  warmup_status: string
  is_active: boolean
  daily_send_limit: number
  emails_sent_today: number
  total_emails_sent: number
  last_sent_at: string | null
  bounce_count: number
  reply_count: number
  complaint_count: number
  warmup_days_completed: number
  can_send: boolean
  remaining_daily_quota: number
  notes: string | null
  created_at: string
  updated_at: string
  connection_status: string | null
  connection_error: string | null
  last_connection_test_at: string | null
  email_signature_json: string | null
}

interface MailboxStats {
  total_mailboxes: number
  active_mailboxes: number
  cold_ready_mailboxes: number
  warming_up_mailboxes: number
  paused_mailboxes: number
  total_daily_capacity: number
  used_today: number
  available_today: number
  total_emails_sent: number
  total_bounces: number
  total_replies: number
}

const WARMUP_STATUS_LABELS: Record<string, { label: string; color: string }> = {
  warming_up: { label: 'Warming Up', color: 'bg-yellow-100 text-yellow-800' },
  cold_ready: { label: 'Cold Ready', color: 'bg-green-100 text-green-800' },
  active: { label: 'Active', color: 'bg-blue-100 text-blue-800' },
  paused: { label: 'Paused', color: 'bg-gray-100 text-gray-800' },
  inactive: { label: 'Inactive', color: 'bg-gray-100 text-gray-600' },
  blacklisted: { label: 'Blacklisted', color: 'bg-red-100 text-red-800' },
  recovering: { label: 'Recovering', color: 'bg-orange-100 text-orange-800' },
}

const PROVIDER_LABELS: Record<string, string> = {
  microsoft_365: 'Microsoft 365',
  MICROSOFT_365: 'Microsoft 365',
  gmail: 'Gmail',
  GMAIL: 'Gmail',
  smtp: 'Custom SMTP',
  SMTP: 'Custom SMTP',
  other: 'Other',
  OTHER: 'Other',
}

type SortKey = 'email' | 'provider' | 'warmup_status' | 'emails_sent_today' | 'total_emails_sent' | 'connection_status' | 'created_at'
type SortDir = 'asc' | 'desc'

export default function MailboxesPage() {
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([])
  const [stats, setStats] = useState<MailboxStats | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingMailbox, setEditingMailbox] = useState<Mailbox | null>(null)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [connectionStatus, setConnectionStatus] = useState<Record<number, 'success' | 'failed' | 'testing'>>({})
  const [connectionErrors, setConnectionErrors] = useState<Record<number, string>>({})
  const [testingAll, setTestingAll] = useState(false)

  // Search, Filter & Sort state
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [connectionFilter, setConnectionFilter] = useState<string>('')
  const [providerFilter, setProviderFilter] = useState<string>('')
  const [sortKey, setSortKey] = useState<SortKey>('email')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  // Bulk selection state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  // Form state
  // Signature form state
  const [sigData, setSigData] = useState({
    sender_name: '',
    title: '',
    phone: '',
    email: '',
    company: '',
    website: '',
    address: '',
  })

  const [formData, setFormData] = useState({
    email: '',
    display_name: '',
    password: '',
    provider: 'microsoft_365',
    smtp_host: '',
    smtp_port: 587,
    warmup_status: 'cold_ready',
    is_active: true,
    daily_send_limit: 30,
    notes: '',
    email_signature_json: '',
  })

  useEffect(() => {
    fetchData()
  }, [statusFilter, showArchived])

  const fetchData = async () => {
    try {
      setLoading(true)
      const params: Record<string, any> = {}
      if (statusFilter) params.status = statusFilter
      if (showArchived) params.show_archived = true

      const [mailboxData, statsData] = await Promise.all([
        mailboxesApi.list(params),
        mailboxesApi.stats()
      ])
      const items = mailboxData.items || []
      setMailboxes(items)
      setStats(statsData)
      const statusMap: Record<number, 'success' | 'failed'> = {}
      for (const mb of items) {
        if (mb.connection_status === 'successful') statusMap[mb.mailbox_id] = 'success'
        else if (mb.connection_status === 'failed') statusMap[mb.mailbox_id] = 'failed'
      }
      setConnectionStatus(prev => ({ ...statusMap, ...Object.fromEntries(Object.entries(prev).filter(([_, v]) => v === 'testing')) }))
      const errorMap: Record<number, string> = {}
      for (const mb of items) {
        if (mb.connection_error) errorMap[mb.mailbox_id] = mb.connection_error
      }
      setConnectionErrors(prev => ({ ...errorMap, ...prev }))
    } catch (error) {
      console.error('Failed to fetch mailboxes:', error)
    } finally {
      setLoading(false)
    }
  }

  // Client-side filtering + sorting
  const filteredMailboxes = useMemo(() => {
    let result = mailboxes.filter((mb) => {
      if (searchQuery) {
        const q = searchQuery.toLowerCase()
        const match =
          mb.email.toLowerCase().includes(q) ||
          (mb.display_name || '').toLowerCase().includes(q) ||
          (mb.notes || '').toLowerCase().includes(q)
        if (!match) return false
      }
      if (connectionFilter) {
        const connStatus = mb.connection_status || 'untested'
        if (connectionFilter !== connStatus) return false
      }
      if (providerFilter) {
        if (mb.provider.toLowerCase() !== providerFilter.toLowerCase()) return false
      }
      return true
    })

    // Sort
    result.sort((a, b) => {
      let aVal: any, bVal: any
      switch (sortKey) {
        case 'email': aVal = a.email.toLowerCase(); bVal = b.email.toLowerCase(); break
        case 'provider': aVal = a.provider.toLowerCase(); bVal = b.provider.toLowerCase(); break
        case 'warmup_status': aVal = a.warmup_status; bVal = b.warmup_status; break
        case 'emails_sent_today': aVal = a.emails_sent_today; bVal = b.emails_sent_today; break
        case 'total_emails_sent': aVal = a.total_emails_sent; bVal = b.total_emails_sent; break
        case 'connection_status': aVal = a.connection_status || ''; bVal = b.connection_status || ''; break
        case 'created_at': aVal = a.created_at; bVal = b.created_at; break
        default: aVal = a.email; bVal = b.email
      }
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1
      return 0
    })

    return result
  }, [mailboxes, searchQuery, connectionFilter, providerFilter, sortKey, sortDir])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const SortIcon = ({ column }: { column: SortKey }) => {
    if (sortKey !== column) return <span className="ml-1 text-gray-300">&#8597;</span>
    return <span className="ml-1">{sortDir === 'asc' ? '&#9650;' : '&#9660;'}</span>
  }

  // Bulk selection helpers
  const allFilteredSelected = filteredMailboxes.length > 0 && filteredMailboxes.every((mb) => selectedIds.has(mb.mailbox_id))
  const someSelected = selectedIds.size > 0

  const toggleSelectAll = () => {
    if (allFilteredSelected) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filteredMailboxes.map((mb) => mb.mailbox_id)))
    }
  }

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return
    const count = selectedIds.size
    if (!confirm(`Are you sure you want to archive ${count} mailbox${count > 1 ? 'es' : ''}? This cannot be undone.`)) return
    setBulkDeleting(true)
    let deleted = 0
    let failed = 0
    for (const id of Array.from(selectedIds)) {
      try {
        await mailboxesApi.delete(id)
        deleted++
      } catch {
        failed++
      }
    }
    setSelectedIds(new Set())
    setBulkDeleting(false)
    setTestResult({
      success: failed === 0,
      message: `Archived ${deleted} mailbox${deleted !== 1 ? 'es' : ''}${failed > 0 ? `, ${failed} failed` : ''}`,
    })
    fetchData()
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      // Serialize signature data
      const hasSig = Object.values(sigData).some(v => v.trim() !== '')
      const sigJson = hasSig ? JSON.stringify(sigData) : ''

      if (editingMailbox) {
        const updateData = { ...formData, email_signature_json: sigJson }
        if (!updateData.password) {
          delete (updateData as any).password
        }
        await mailboxesApi.update(editingMailbox.mailbox_id, updateData)
      } else {
        await mailboxesApi.create({ ...formData, email_signature_json: sigJson })
      }
      setShowAddModal(false)
      setEditingMailbox(null)
      resetForm()
      fetchData()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to save mailbox')
    }
  }

  const handleEdit = (mailbox: Mailbox) => {
    setEditingMailbox(mailbox)
    setFormData({
      email: mailbox.email,
      display_name: mailbox.display_name || '',
      password: '',
      provider: mailbox.provider,
      smtp_host: mailbox.smtp_host || '',
      smtp_port: mailbox.smtp_port,
      warmup_status: mailbox.warmup_status,
      is_active: mailbox.is_active,
      daily_send_limit: mailbox.daily_send_limit,
      notes: mailbox.notes || '',
      email_signature_json: mailbox.email_signature_json || '',
    })
    // Populate signature fields from saved JSON
    if (mailbox.email_signature_json) {
      try {
        const sig = JSON.parse(mailbox.email_signature_json)
        setSigData({
          sender_name: sig.sender_name || '',
          title: sig.title || '',
          phone: sig.phone || '',
          email: sig.email || '',
          company: sig.company || '',
          website: sig.website || '',
          address: sig.address || '',
        })
      } catch { setSigData({ sender_name: '', title: '', phone: '', email: '', company: '', website: '', address: '' }) }
    } else {
      setSigData({ sender_name: '', title: '', phone: '', email: '', company: '', website: '', address: '' })
    }
    setShowAddModal(true)
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to archive this mailbox?')) return
    try {
      await mailboxesApi.delete(id)
      fetchData()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to delete mailbox')
    }
  }

  const handleTestConnection = async (id: number) => {
    setTestingId(id)
    setTestResult(null)
    setConnectionStatus(prev => ({ ...prev, [id]: 'testing' }))
    setConnectionErrors(prev => ({ ...prev, [id]: '' }))
    try {
      const result = await mailboxesApi.testConnection(id)
      setTestResult(result)
      setConnectionStatus(prev => ({ ...prev, [id]: result.success ? 'success' : 'failed' }))
      if (!result.success) {
        setConnectionErrors(prev => ({ ...prev, [id]: result.message || 'Connection failed' }))
      } else {
        setConnectionErrors(prev => ({ ...prev, [id]: '' }))
      }
    } catch (error: any) {
      const msg = error.response?.data?.detail || 'Test failed'
      setTestResult({ success: false, message: msg })
      setConnectionStatus(prev => ({ ...prev, [id]: 'failed' }))
      setConnectionErrors(prev => ({ ...prev, [id]: msg }))
    } finally {
      setTestingId(null)
    }
  }

  const handleTestAll = async () => {
    setTestingAll(true)
    setTestResult(null)
    let successCount = 0
    let failCount = 0

    for (const mailbox of mailboxes) {
      setConnectionStatus(prev => ({ ...prev, [mailbox.mailbox_id]: 'testing' }))
      try {
        const result = await mailboxesApi.testConnection(mailbox.mailbox_id)
        setConnectionStatus(prev => ({ ...prev, [mailbox.mailbox_id]: result.success ? 'success' : 'failed' }))
        if (result.success) successCount++
        else failCount++
      } catch {
        setConnectionStatus(prev => ({ ...prev, [mailbox.mailbox_id]: 'failed' }))
        failCount++
      }
    }

    setTestingAll(false)
    setTestResult({
      success: failCount === 0,
      message: `Connection test complete: ${successCount} successful, ${failCount} failed`
    })
  }

  const handleStatusChange = async (id: number, newStatus: string) => {
    try {
      await mailboxesApi.updateStatus(id, newStatus)
      fetchData()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to update status')
    }
  }

  const resetForm = () => {
    setFormData({
      email: '',
      display_name: '',
      password: '',
      provider: 'microsoft_365',
      smtp_host: '',
      smtp_port: 587,
      warmup_status: 'cold_ready',
      is_active: true,
      daily_send_limit: 30,
      notes: '',
      email_signature_json: '',
    })
    setSigData({ sender_name: '', title: '', phone: '', email: '', company: '', website: '', address: '' })
  }

  const clearFilters = () => {
    setSearchQuery('')
    setStatusFilter('')
    setConnectionFilter('')
    setProviderFilter('')
    setShowArchived(false)
  }

  const hasActiveFilters = searchQuery || statusFilter || connectionFilter || providerFilter

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading mailboxes...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Sender Mailboxes</h1>
          <p className="text-gray-500">Manage email accounts used for outreach</p>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={handleTestAll}
            disabled={testingAll || mailboxes.length === 0}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
          >
            {testingAll ? 'Testing All...' : 'Test All Connections'}
          </button>
          <button
            onClick={() => { resetForm(); setEditingMailbox(null); setShowAddModal(true) }}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Add Mailbox
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-2xl font-bold text-gray-900">{stats.total_mailboxes}</div>
            <div className="text-sm text-gray-500">Total Mailboxes</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-2xl font-bold text-green-600">{stats.cold_ready_mailboxes}</div>
            <div className="text-sm text-gray-500">Cold Ready</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-2xl font-bold text-yellow-600">{stats.warming_up_mailboxes}</div>
            <div className="text-sm text-gray-500">Warming Up</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-2xl font-bold text-blue-600">{stats.available_today}</div>
            <div className="text-sm text-gray-500">Available Today</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-2xl font-bold text-gray-900">{stats.total_emails_sent}</div>
            <div className="text-sm text-gray-500">Total Sent</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-2xl font-bold text-purple-600">{stats.total_replies}</div>
            <div className="text-sm text-gray-500">Total Replies</div>
          </div>
        </div>
      )}

      {/* Search & Filters Bar */}
      <div className="bg-white p-4 rounded-lg shadow">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-[220px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Search</label>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by email, name, or notes..."
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div className="w-40">
            <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-full px-3 py-2 border rounded-lg">
              <option value="">All Statuses</option>
              <option value="warming_up">Warming Up</option>
              <option value="cold_ready">Cold Ready</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="inactive">Inactive</option>
              <option value="recovering">Recovering</option>
              <option value="blacklisted">Blacklisted</option>
            </select>
          </div>
          <div className="w-40">
            <label className="block text-sm font-medium text-gray-700 mb-1">Connection</label>
            <select value={connectionFilter} onChange={(e) => setConnectionFilter(e.target.value)} className="w-full px-3 py-2 border rounded-lg">
              <option value="">All Connections</option>
              <option value="successful">Successful</option>
              <option value="failed">Failed</option>
              <option value="untested">Not Tested</option>
            </select>
          </div>
          <div className="w-40">
            <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
            <select value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)} className="w-full px-3 py-2 border rounded-lg">
              <option value="">All Providers</option>
              <option value="microsoft_365">Microsoft 365</option>
              <option value="gmail">Gmail</option>
              <option value="smtp">Custom SMTP</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div className="w-40 flex items-end">
            <label className="flex items-center gap-2 cursor-pointer pb-2">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-sm font-medium text-gray-700">Show Archived</span>
            </label>
          </div>
          {hasActiveFilters && (
            <button onClick={clearFilters} className="px-3 py-2 text-sm text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-50">
              Clear All
            </button>
          )}
        </div>
        <div className="mt-3 flex items-center justify-between text-sm text-gray-500">
          <span>Showing {filteredMailboxes.length} of {mailboxes.length} mailbox{mailboxes.length !== 1 ? 'es' : ''}</span>
          {someSelected && <span className="text-blue-600 font-medium">{selectedIds.size} selected</span>}
        </div>
      </div>

      {/* Bulk Actions Bar */}
      {someSelected && (
        <div className="bg-blue-50 border border-blue-200 p-3 rounded-lg flex items-center justify-between">
          <span className="text-sm font-medium text-blue-800">{selectedIds.size} mailbox{selectedIds.size > 1 ? 'es' : ''} selected</span>
          <div className="flex space-x-3">
            <button onClick={() => setSelectedIds(new Set())} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 border rounded-lg bg-white hover:bg-gray-50">
              Deselect All
            </button>
            <button onClick={handleBulkDelete} disabled={bulkDeleting} className="px-3 py-1.5 text-sm text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50">
              {bulkDeleting ? 'Archiving...' : `Archive Selected (${selectedIds.size})`}
            </button>
          </div>
        </div>
      )}

      {/* Test Result Alert */}
      {testResult && (
        <div className={`p-4 rounded-lg ${testResult.success ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
          <div className="flex justify-between items-center">
            <span>{testResult.message}</span>
            <button onClick={() => setTestResult(null)} className="text-sm underline">Dismiss</button>
          </div>
        </div>
      )}

      {/* Mailboxes Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left">
                <input type="checkbox" checked={allFilteredSelected} onChange={toggleSelectAll} className="h-4 w-4 text-blue-600 border-gray-300 rounded cursor-pointer" title="Select all" />
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort('email')}>
                Email <SortIcon column="email" />
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort('provider')}>
                Provider <SortIcon column="provider" />
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort('warmup_status')}>
                Status <SortIcon column="warmup_status" />
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort('emails_sent_today')}>
                Today <SortIcon column="emails_sent_today" />
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort('total_emails_sent')}>
                Total <SortIcon column="total_emails_sent" />
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Metrics</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort('connection_status')}>
                Connection <SortIcon column="connection_status" />
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {filteredMailboxes.map((mailbox) => (
              <tr key={mailbox.mailbox_id} className={`${!mailbox.is_active ? 'bg-gray-50' : ''} ${selectedIds.has(mailbox.mailbox_id) ? 'bg-blue-50' : ''}`}>
                <td className="px-4 py-4">
                  <input type="checkbox" checked={selectedIds.has(mailbox.mailbox_id)} onChange={() => toggleSelect(mailbox.mailbox_id)} className="h-4 w-4 text-blue-600 border-gray-300 rounded cursor-pointer" />
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  <div>
                    <div className="text-sm font-medium text-gray-900">{mailbox.email}</div>
                    {mailbox.display_name && <div className="text-sm text-gray-500">{mailbox.display_name}</div>}
                  </div>
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900">
                  {PROVIDER_LABELS[mailbox.provider] || mailbox.provider}
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  <select
                    value={mailbox.warmup_status}
                    onChange={(e) => handleStatusChange(mailbox.mailbox_id, e.target.value)}
                    className={`text-xs px-2 py-1 rounded-full ${WARMUP_STATUS_LABELS[mailbox.warmup_status]?.color || 'bg-gray-100'}`}
                  >
                    <option value="warming_up">Warming Up</option>
                    <option value="cold_ready">Cold Ready</option>
                    <option value="active">Active</option>
                    <option value="paused">Paused</option>
                    <option value="inactive">Inactive</option>
                    <option value="blacklisted">Blacklisted</option>
                  </select>
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  <div className="text-sm text-gray-900">{mailbox.emails_sent_today} / {mailbox.daily_send_limit}</div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-1">
                    <div className="bg-blue-600 h-2 rounded-full" style={{ width: `${Math.min(100, (mailbox.emails_sent_today / mailbox.daily_send_limit) * 100)}%` }} />
                  </div>
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900">{mailbox.total_emails_sent}</td>
                <td className="px-4 py-4 whitespace-nowrap">
                  <div className="flex space-x-3 text-xs">
                    <span className="text-red-600" title="Bounces">B: {mailbox.bounce_count}</span>
                    <span className="text-green-600" title="Replies">R: {mailbox.reply_count}</span>
                  </div>
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-center">
                  {connectionStatus[mailbox.mailbox_id] === 'testing' && (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">Testing...</span>
                  )}
                  {connectionStatus[mailbox.mailbox_id] === 'success' && (
                    <div className="relative group inline-block">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 cursor-help">Successful</span>
                      {mailbox.last_connection_test_at && (
                        <div className="absolute z-50 bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg shadow-lg w-48 hidden group-hover:block">
                          <div>Tested: {new Date(mailbox.last_connection_test_at).toLocaleString()}</div>
                          <div className="absolute top-full left-1/2 transform -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
                        </div>
                      )}
                    </div>
                  )}
                  {connectionStatus[mailbox.mailbox_id] === 'failed' && (
                    <div className="relative group inline-block">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 cursor-help">Failed</span>
                      {(connectionErrors[mailbox.mailbox_id] || mailbox.connection_error) && (
                        <div className="absolute z-50 bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg shadow-lg w-64 hidden group-hover:block">
                          <div className="font-semibold mb-1">Failure Reason:</div>
                          <div>{connectionErrors[mailbox.mailbox_id] || mailbox.connection_error}</div>
                          {mailbox.last_connection_test_at && (
                            <div className="mt-1 text-gray-400">Tested: {new Date(mailbox.last_connection_test_at).toLocaleString()}</div>
                          )}
                          <div className="absolute top-full left-1/2 transform -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
                        </div>
                      )}
                    </div>
                  )}
                  {!connectionStatus[mailbox.mailbox_id] && (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">Not Tested</span>
                  )}
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-right text-sm font-medium space-x-2">
                  <button onClick={() => handleTestConnection(mailbox.mailbox_id)} disabled={testingId === mailbox.mailbox_id} className="text-green-600 hover:text-green-900 disabled:opacity-50">
                    {testingId === mailbox.mailbox_id ? 'Testing...' : 'Test'}
                  </button>
                  <button onClick={() => handleEdit(mailbox)} className="text-blue-600 hover:text-blue-900">Edit</button>
                  <button onClick={() => handleDelete(mailbox.mailbox_id)} className="text-red-600 hover:text-red-900">Archive</button>
                </td>
              </tr>
            ))}
            {filteredMailboxes.length === 0 && (
              <tr>
                <td colSpan={9} className="px-6 py-8 text-center text-gray-500">
                  {hasActiveFilters ? 'No mailboxes match your filters.' : 'No mailboxes found. Click "Add Mailbox" to create one.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Add/Edit Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-bold mb-4">{editingMailbox ? 'Edit Mailbox' : 'Add New Mailbox'}</h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email Address *</label>
                <input type="email" required value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="sender@example.com" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
                <input type="text" value={formData.display_name} onChange={(e) => setFormData({ ...formData, display_name: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="Brian from Exzelon" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Password {editingMailbox ? '(leave blank to keep current)' : '*'}</label>
                <input type="password" required={!editingMailbox} value={formData.password} onChange={(e) => setFormData({ ...formData, password: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="********" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
                <select value={formData.provider} onChange={(e) => setFormData({ ...formData, provider: e.target.value })} className="w-full px-3 py-2 border rounded-lg">
                  <option value="microsoft_365">Microsoft 365</option>
                  <option value="gmail">Gmail</option>
                  <option value="smtp">Custom SMTP</option>
                  <option value="other">Other</option>
                </select>
              </div>
              {formData.provider === 'smtp' && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">SMTP Host</label>
                    <input type="text" value={formData.smtp_host} onChange={(e) => setFormData({ ...formData, smtp_host: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="smtp.example.com" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">SMTP Port</label>
                    <input type="number" value={formData.smtp_port} onChange={(e) => setFormData({ ...formData, smtp_port: parseInt(e.target.value) })} className="w-full px-3 py-2 border rounded-lg" />
                  </div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Warmup Status</label>
                  <select value={formData.warmup_status} onChange={(e) => setFormData({ ...formData, warmup_status: e.target.value })} className="w-full px-3 py-2 border rounded-lg">
                    <option value="warming_up">Warming Up</option>
                    <option value="cold_ready">Cold Ready</option>
                    <option value="active">Active</option>
                    <option value="paused">Paused</option>
                    <option value="inactive">Inactive</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Daily Send Limit</label>
                  <input type="number" min="1" max="100" value={formData.daily_send_limit} onChange={(e) => setFormData({ ...formData, daily_send_limit: parseInt(e.target.value) })} className="w-full px-3 py-2 border rounded-lg" />
                </div>
              </div>
              <div className="flex items-center">
                <input type="checkbox" id="is_active" checked={formData.is_active} onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })} className="h-4 w-4 text-blue-600 border-gray-300 rounded" />
                <label htmlFor="is_active" className="ml-2 text-sm text-gray-700">Active</label>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                <textarea value={formData.notes} onChange={(e) => setFormData({ ...formData, notes: e.target.value })} className="w-full px-3 py-2 border rounded-lg" rows={2} placeholder="Optional notes..." />
              </div>

              {/* Email Signature Section */}
              <div className="border-t pt-4 mt-4">
                <h3 className="text-md font-semibold text-gray-800 mb-3">Email Signature</h3>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Sender Name</label>
                    <input type="text" value={sigData.sender_name} onChange={(e) => setSigData({ ...sigData, sender_name: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="John Doe" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Title / Role</label>
                    <input type="text" value={sigData.title} onChange={(e) => setSigData({ ...sigData, title: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="Account Manager" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Phone</label>
                    <input type="text" value={sigData.phone} onChange={(e) => setSigData({ ...sigData, phone: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="+1-555-1234" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
                    <input type="email" value={sigData.email || formData.email} onChange={(e) => setSigData({ ...sigData, email: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="john@exzelon.com" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Company Name</label>
                    <input type="text" value={sigData.company} onChange={(e) => setSigData({ ...sigData, company: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="Exzelon Inc." />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Website URL</label>
                    <input type="text" value={sigData.website} onChange={(e) => setSigData({ ...sigData, website: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="https://exzelon.com" />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Address</label>
                    <input type="text" value={sigData.address} onChange={(e) => setSigData({ ...sigData, address: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="123 Business Ave, Suite 100, City, State 12345" />
                  </div>
                </div>

                {/* Live Preview */}
                {Object.values(sigData).some(v => v.trim() !== '') && (
                  <div className="mt-3">
                    <label className="block text-xs font-medium text-gray-500 mb-1">Signature Preview</label>
                    <div className="border rounded-lg p-3 bg-gray-50">
                      <div style={{ borderTop: '1px solid #cccccc', paddingTop: '10px', fontFamily: 'Arial, sans-serif' }}>
                        {sigData.sender_name && <div style={{ fontSize: '14px', fontWeight: 'bold', color: '#333333' }}>{sigData.sender_name}</div>}
                        {sigData.title && <div style={{ fontSize: '13px', color: '#555555' }}>{sigData.title}</div>}
                        {sigData.company && <div style={{ fontSize: '13px', color: '#555555' }}>{sigData.company}</div>}
                        {(sigData.phone || (sigData.email || formData.email)) && (
                          <div style={{ fontSize: '12px', color: '#666666' }}>
                            {[sigData.phone, sigData.email || formData.email].filter(Boolean).join(' | ')}
                          </div>
                        )}
                        {sigData.website && (
                          <div style={{ fontSize: '12px' }}>
                            <span style={{ color: '#0066cc' }}>{sigData.website}</span>
                          </div>
                        )}
                        {sigData.address && (
                          <div style={{ fontSize: '12px', color: '#666666' }}>
                            {sigData.address}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-end space-x-3 pt-4">
                <button type="button" onClick={() => { setShowAddModal(false); setEditingMailbox(null) }} className="px-4 py-2 border rounded-lg hover:bg-gray-50">Cancel</button>
                <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">{editingMailbox ? 'Update' : 'Add'} Mailbox</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
