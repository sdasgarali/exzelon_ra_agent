'use client'

import { useState, useEffect, useMemo } from 'react'
import { mailboxesApi } from '@/lib/api'
import { useToast } from '@/components/toast'

interface Mailbox {
  mailbox_id: number
  email: string
  display_name: string | null
  provider: string
  smtp_host: string | null
  smtp_port: number
  imap_host: string | null
  imap_port: number
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
  auth_method: string
  oauth_tenant_id: string | null
  oauth_connected: boolean
}

type WizardStep = 'select_provider' | 'google_instructions' | 'google_form' |
  'microsoft_instructions' | 'microsoft_form' |
  'smtp_instructions' | 'smtp_form' | 'settings'

const WIZARD_STEP_NUMBER: Record<WizardStep, number> = {
  select_provider: 1,
  google_instructions: 1,
  google_form: 2,
  microsoft_instructions: 1,
  microsoft_form: 2,
  smtp_instructions: 1,
  smtp_form: 2,
  settings: 3,
}

const WIZARD_TOTAL_STEPS: Record<WizardStep, number> = {
  select_provider: 3,
  google_instructions: 3,
  google_form: 3,
  microsoft_instructions: 3,
  microsoft_form: 3,
  smtp_instructions: 3,
  smtp_form: 3,
  settings: 3,
}

const SMTP_REFERENCE_TABLE = [
  { provider: 'Gmail', imap_host: 'imap.gmail.com', imap_port: 993, smtp_host: 'smtp.gmail.com', smtp_port: 587 },
  { provider: 'Microsoft 365', imap_host: 'outlook.office365.com', imap_port: 993, smtp_host: 'smtp.office365.com', smtp_port: 587 },
  { provider: 'Yahoo Mail', imap_host: 'imap.mail.yahoo.com', imap_port: 993, smtp_host: 'smtp.mail.yahoo.com', smtp_port: 465 },
  { provider: 'Zoho Mail', imap_host: 'imap.zoho.com', imap_port: 993, smtp_host: 'smtp.zoho.com', smtp_port: 587 },
  { provider: 'GoDaddy', imap_host: 'imap.secureserver.net', imap_port: 993, smtp_host: 'smtpout.secureserver.net', smtp_port: 465 },
  { provider: 'Namecheap', imap_host: 'mail.privateemail.com', imap_port: 993, smtp_host: 'mail.privateemail.com', smtp_port: 587 },
  { provider: 'Hostinger', imap_host: 'imap.hostinger.com', imap_port: 993, smtp_host: 'smtp.hostinger.com', smtp_port: 587 },
  { provider: 'FastMail', imap_host: 'imap.fastmail.com', imap_port: 993, smtp_host: 'smtp.fastmail.com', smtp_port: 587 },
  { provider: 'ProtonMail Bridge', imap_host: '127.0.0.1', imap_port: 1143, smtp_host: '127.0.0.1', smtp_port: 1025 },
  { provider: 'Amazon SES', imap_host: '\u2014', imap_port: 0, smtp_host: 'email-smtp.{region}.amazonaws.com', smtp_port: 587 },
  { provider: 'SendGrid', imap_host: '\u2014', imap_port: 0, smtp_host: 'smtp.sendgrid.net', smtp_port: 587 },
  { provider: 'Mailgun', imap_host: '\u2014', imap_port: 0, smtp_host: 'smtp.mailgun.org', smtp_port: 587 },
]

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
  const { toast } = useToast()
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
    imap_host: '',
    imap_port: 993,
    warmup_status: 'cold_ready',
    is_active: true,
    daily_send_limit: 30,
    notes: '',
    email_signature_json: '',
    auth_method: 'password' as 'password' | 'oauth2',
    oauth_tenant_id: '',
  })
  const [oauthConnecting, setOauthConnecting] = useState(false)

  // Wizard state
  const [wizardStep, setWizardStep] = useState<WizardStep>('select_provider')
  const [createdMailboxId, setCreatedMailboxId] = useState<number | null>(null)
  const [wizardSubmitting, setWizardSubmitting] = useState(false)
  const [wizardTestResult, setWizardTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [showSmtpRefTable, setShowSmtpRefTable] = useState(false)

  // Handle OAuth callback (query params ?code=...&state=...)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const state = params.get('state')
    if (code && state) {
      // Remove query params from URL to prevent re-processing
      window.history.replaceState({}, '', window.location.pathname)
      ;(async () => {
        try {
          const result = await mailboxesApi.oauthCallback(code, state)
          setTestResult({ success: true, message: result.message || 'OAuth2 connected successfully' })
          fetchData()
        } catch (error: any) {
          setTestResult({
            success: false,
            message: error.response?.data?.detail || 'OAuth2 callback failed',
          })
        }
      })()
    }
  }, [])

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
    } catch (error: any) {
      if (error.code !== 'ERR_CANCELED') {
        console.error('Failed to fetch mailboxes:', error)
      }
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
        const updateData = {
          ...formData,
          email_signature_json: sigJson,
          oauth_tenant_id: formData.oauth_tenant_id || undefined,
        }
        if (!updateData.password) {
          delete (updateData as any).password
        }
        await mailboxesApi.update(editingMailbox.mailbox_id, updateData)
      } else {
        const createData = {
          ...formData,
          email_signature_json: sigJson,
          oauth_tenant_id: formData.oauth_tenant_id || undefined,
        }
        // For OAuth2 mailboxes, password is not required
        if (formData.auth_method === 'oauth2' && !createData.password) {
          delete (createData as any).password
        }
        await mailboxesApi.create(createData)
      }
      setShowAddModal(false)
      setEditingMailbox(null)
      resetForm()
      fetchData()
    } catch (error: any) {
      toast('error', error.response?.data?.detail || 'Failed to save mailbox')
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
      imap_host: mailbox.imap_host || '',
      imap_port: mailbox.imap_port || 993,
      warmup_status: mailbox.warmup_status,
      is_active: mailbox.is_active,
      daily_send_limit: mailbox.daily_send_limit,
      notes: mailbox.notes || '',
      email_signature_json: mailbox.email_signature_json || '',
      auth_method: (mailbox.auth_method || 'password') as 'password' | 'oauth2',
      oauth_tenant_id: mailbox.oauth_tenant_id || '',
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
      toast('error', error.response?.data?.detail || 'Failed to delete mailbox')
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

    // Mark all as testing
    const testingMap: Record<number, 'testing'> = {}
    for (const mailbox of mailboxes) {
      testingMap[mailbox.mailbox_id] = 'testing'
    }
    setConnectionStatus(prev => ({ ...prev, ...testingMap }))

    // Test all connections in parallel
    const results = await Promise.allSettled(
      mailboxes.map(async (mailbox) => {
        try {
          const result = await mailboxesApi.testConnection(mailbox.mailbox_id)
          setConnectionStatus(prev => ({ ...prev, [mailbox.mailbox_id]: result.success ? 'success' : 'failed' }))
          return result.success
        } catch {
          setConnectionStatus(prev => ({ ...prev, [mailbox.mailbox_id]: 'failed' }))
          return false
        }
      })
    )

    let successCount = 0
    let failCount = 0
    for (const result of results) {
      if (result.status === 'fulfilled' && result.value === true) {
        successCount++
      } else {
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
      toast('error', error.response?.data?.detail || 'Failed to update status')
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
      imap_host: '',
      imap_port: 993,
      warmup_status: 'cold_ready',
      is_active: true,
      daily_send_limit: 30,
      notes: '',
      email_signature_json: '',
      auth_method: 'password',
      oauth_tenant_id: '',
    })
    setSigData({ sender_name: '', title: '', phone: '', email: '', company: '', website: '', address: '' })
    setWizardStep('select_provider')
    setCreatedMailboxId(null)
    setWizardSubmitting(false)
    setWizardTestResult(null)
    setShowSmtpRefTable(false)
  }

  // Wizard: create mailbox and auto-test
  const handleWizardCreate = async () => {
    setWizardSubmitting(true)
    setWizardTestResult(null)
    try {
      const hasSig = Object.values(sigData).some(v => v.trim() !== '')
      const sigJson = hasSig ? JSON.stringify(sigData) : ''
      const createData: Record<string, any> = {
        ...formData,
        email_signature_json: sigJson,
        oauth_tenant_id: formData.oauth_tenant_id || undefined,
      }
      if (formData.auth_method === 'oauth2' && !createData.password) {
        delete createData.password
      }
      const result = await mailboxesApi.create(createData)
      const newId = result.mailbox_id
      setCreatedMailboxId(newId)
      // Auto-test connection
      try {
        const testRes = await mailboxesApi.testConnection(newId)
        setWizardTestResult(testRes)
      } catch {
        setWizardTestResult({ success: false, message: 'Mailbox created but connection test failed' })
      }
      setWizardStep('settings')
      fetchData()
    } catch (error: any) {
      toast('error', error.response?.data?.detail || 'Failed to create mailbox')
    } finally {
      setWizardSubmitting(false)
    }
  }

  // Wizard: save settings on final step
  const handleWizardSaveSettings = async () => {
    if (!createdMailboxId) return
    setWizardSubmitting(true)
    try {
      const hasSig = Object.values(sigData).some(v => v.trim() !== '')
      const sigJson = hasSig ? JSON.stringify(sigData) : ''
      await mailboxesApi.update(createdMailboxId, {
        warmup_status: formData.warmup_status,
        daily_send_limit: formData.daily_send_limit,
        is_active: formData.is_active,
        notes: formData.notes,
        email_signature_json: sigJson,
      })
      setShowAddModal(false)
      resetForm()
      fetchData()
      toast('success', 'Mailbox configured successfully')
    } catch (error: any) {
      toast('error', error.response?.data?.detail || 'Failed to save settings')
    } finally {
      setWizardSubmitting(false)
    }
  }

  // Wizard: skip settings
  const handleWizardSkipSettings = () => {
    setShowAddModal(false)
    resetForm()
    fetchData()
  }

  // Wizard: back button
  const handleWizardBack = () => {
    switch (wizardStep) {
      case 'google_instructions': setWizardStep('select_provider'); break
      case 'google_form': setWizardStep('google_instructions'); break
      case 'microsoft_instructions': setWizardStep('select_provider'); break
      case 'microsoft_form': setWizardStep('microsoft_instructions'); break
      case 'smtp_instructions': setWizardStep('select_provider'); break
      case 'smtp_form': setWizardStep('smtp_instructions'); break
      default: setWizardStep('select_provider')
    }
  }

  const handleOAuthConnect = async (mailboxId?: number) => {
    setOauthConnecting(true)
    try {
      const result = await mailboxesApi.oauthInitiate(mailboxId, formData.email || undefined)
      // Open authorization URL — redirect in same window for SPA callback
      window.location.href = result.authorization_url
    } catch (error: any) {
      toast('error', error.response?.data?.detail || 'Failed to initiate OAuth')
      setOauthConnecting(false)
    }
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
                  <div className="flex items-center gap-1.5">
                    {PROVIDER_LABELS[mailbox.provider] || mailbox.provider}
                    {mailbox.auth_method === 'oauth2' && (
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${
                        mailbox.oauth_connected
                          ? 'bg-green-100 text-green-700'
                          : 'bg-amber-100 text-amber-700'
                      }`}>
                        {mailbox.oauth_connected ? 'OAuth' : 'OAuth (not connected)'}
                      </span>
                    )}
                  </div>
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

      {/* Edit Mailbox Modal (existing flow for editing) */}
      {showAddModal && editingMailbox && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-bold mb-4">Edit Mailbox</h2>
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
                <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
                <select value={formData.provider} onChange={(e) => setFormData({ ...formData, provider: e.target.value })} className="w-full px-3 py-2 border rounded-lg">
                  <option value="microsoft_365">Microsoft 365</option>
                  <option value="gmail">Gmail</option>
                  <option value="smtp">Custom SMTP</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Authentication Method</label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="radio" name="auth_method" value="password" checked={formData.auth_method === 'password'} onChange={() => setFormData({ ...formData, auth_method: 'password' })} className="text-blue-600" />
                    <span className="text-sm">Password / App Password</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="radio" name="auth_method" value="oauth2" checked={formData.auth_method === 'oauth2'} onChange={() => setFormData({ ...formData, auth_method: 'oauth2' })} className="text-blue-600" />
                    <span className="text-sm">Microsoft OAuth2</span>
                  </label>
                </div>
              </div>
              {formData.auth_method === 'password' ? (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Password (leave blank to keep current)</label>
                  <input type="password" value={formData.password} onChange={(e) => setFormData({ ...formData, password: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="********" />
                </div>
              ) : (
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Azure AD Tenant ID (optional)</label>
                    <input type="text" value={formData.oauth_tenant_id} onChange={(e) => setFormData({ ...formData, oauth_tenant_id: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="common (multi-tenant)" />
                    <p className="text-xs text-gray-500 mt-1">Leave blank for &quot;common&quot; (works for most M365 tenants)</p>
                  </div>
                  <div className="flex items-center gap-3">
                    {editingMailbox.oauth_connected ? (
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">OAuth Connected</span>
                        <button type="button" onClick={() => handleOAuthConnect(editingMailbox.mailbox_id)} disabled={oauthConnecting} className="text-sm text-blue-600 hover:text-blue-800 underline">
                          {oauthConnecting ? 'Redirecting...' : 'Re-authorize'}
                        </button>
                      </div>
                    ) : (
                      <button type="button" onClick={() => handleOAuthConnect(editingMailbox.mailbox_id)} disabled={oauthConnecting} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2">
                        <svg className="w-5 h-5" viewBox="0 0 21 21" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <rect x="1" y="1" width="9" height="9" fill="#F25022"/><rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>
                          <rect x="1" y="11" width="9" height="9" fill="#00A4EF"/><rect x="11" y="11" width="9" height="9" fill="#FFB900"/>
                        </svg>
                        {oauthConnecting ? 'Redirecting...' : 'Connect with Microsoft'}
                      </button>
                    )}
                  </div>
                </div>
              )}
              {(formData.provider === 'smtp' || formData.provider === 'other') && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">SMTP Host</label>
                    <input type="text" value={formData.smtp_host} onChange={(e) => setFormData({ ...formData, smtp_host: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="smtp.example.com" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">SMTP Port</label>
                    <input type="number" value={formData.smtp_port} onChange={(e) => setFormData({ ...formData, smtp_port: parseInt(e.target.value) })} className="w-full px-3 py-2 border rounded-lg" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">IMAP Host</label>
                    <input type="text" value={formData.imap_host} onChange={(e) => setFormData({ ...formData, imap_host: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="imap.example.com" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">IMAP Port</label>
                    <input type="number" value={formData.imap_port} onChange={(e) => setFormData({ ...formData, imap_port: parseInt(e.target.value) })} className="w-full px-3 py-2 border rounded-lg" />
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
                {Object.values(sigData).some(v => v.trim() !== '') && (
                  <div className="mt-3">
                    <label className="block text-xs font-medium text-gray-500 mb-1">Signature Preview</label>
                    <div className="border rounded-lg p-3 bg-gray-50">
                      <div style={{ borderTop: '1px solid #cccccc', paddingTop: '10px', fontFamily: 'Arial, sans-serif' }}>
                        {sigData.sender_name && <div style={{ fontSize: '14px', fontWeight: 'bold', color: '#333333' }}>{sigData.sender_name}</div>}
                        {sigData.title && <div style={{ fontSize: '13px', color: '#555555' }}>{sigData.title}</div>}
                        {sigData.company && <div style={{ fontSize: '13px', color: '#555555' }}>{sigData.company}</div>}
                        {(sigData.phone || (sigData.email || formData.email)) && (
                          <div style={{ fontSize: '12px', color: '#666666' }}>{[sigData.phone, sigData.email || formData.email].filter(Boolean).join(' | ')}</div>
                        )}
                        {sigData.website && <div style={{ fontSize: '12px' }}><span style={{ color: '#0066cc' }}>{sigData.website}</span></div>}
                        {sigData.address && <div style={{ fontSize: '12px', color: '#666666' }}>{sigData.address}</div>}
                      </div>
                    </div>
                  </div>
                )}
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button type="button" onClick={() => { setShowAddModal(false); setEditingMailbox(null) }} className="px-4 py-2 border rounded-lg hover:bg-gray-50">Cancel</button>
                <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Update Mailbox</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Mailbox Wizard */}
      {showAddModal && !editingMailbox && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            {/* Wizard Header */}
            <div className="flex items-center justify-between px-6 pt-6 pb-4 border-b">
              <div>
                <h2 className="text-xl font-bold text-gray-900">
                  {wizardStep === 'select_provider' && 'Connect Email Account'}
                  {wizardStep === 'google_instructions' && 'Connect Google Account'}
                  {wizardStep === 'google_form' && 'Google Account Credentials'}
                  {wizardStep === 'microsoft_instructions' && 'Connect Microsoft 365 Account'}
                  {wizardStep === 'microsoft_form' && 'Microsoft 365 Setup'}
                  {wizardStep === 'smtp_instructions' && 'Connect via IMAP / SMTP'}
                  {wizardStep === 'smtp_form' && 'IMAP / SMTP Credentials'}
                  {wizardStep === 'settings' && 'Configure Settings'}
                </h2>
                {wizardStep !== 'select_provider' && (
                  <p className="text-sm text-gray-500 mt-0.5">Step {WIZARD_STEP_NUMBER[wizardStep]} of {WIZARD_TOTAL_STEPS[wizardStep]}</p>
                )}
              </div>
              <button onClick={() => { setShowAddModal(false); resetForm() }} className="text-gray-400 hover:text-gray-600">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            <div className="px-6 py-5">
              {/* ── Step: Select Provider ── */}
              {wizardStep === 'select_provider' && (
                <div>
                  <p className="text-gray-600 mb-6">Choose your email provider to get started</p>
                  <div className="grid grid-cols-3 gap-4">
                    {/* Google Card */}
                    <button
                      onClick={() => {
                        setFormData(f => ({ ...f, provider: 'gmail', auth_method: 'password', smtp_host: 'smtp.gmail.com', smtp_port: 587, imap_host: 'imap.gmail.com', imap_port: 993 }))
                        setWizardStep('google_instructions')
                      }}
                      className="flex flex-col items-center p-6 border-2 border-gray-200 rounded-xl hover:border-blue-400 hover:bg-blue-50 transition-all group"
                    >
                      <svg className="w-12 h-12 mb-3" viewBox="0 0 48 48">
                        <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                        <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                        <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                        <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                      </svg>
                      <span className="font-semibold text-gray-900 group-hover:text-blue-700">Google</span>
                      <span className="text-xs text-gray-500 mt-1">Gmail / Google Workspace</span>
                    </button>

                    {/* Microsoft Card */}
                    <button
                      onClick={() => {
                        setFormData(f => ({ ...f, provider: 'microsoft_365', auth_method: 'oauth2', smtp_host: 'smtp.office365.com', smtp_port: 587, imap_host: 'outlook.office365.com', imap_port: 993 }))
                        setWizardStep('microsoft_instructions')
                      }}
                      className="flex flex-col items-center p-6 border-2 border-gray-200 rounded-xl hover:border-blue-400 hover:bg-blue-50 transition-all group"
                    >
                      <svg className="w-12 h-12 mb-3" viewBox="0 0 21 21" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect x="1" y="1" width="9" height="9" fill="#F25022"/>
                        <rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>
                        <rect x="1" y="11" width="9" height="9" fill="#00A4EF"/>
                        <rect x="11" y="11" width="9" height="9" fill="#FFB900"/>
                      </svg>
                      <span className="font-semibold text-gray-900 group-hover:text-blue-700">Microsoft</span>
                      <span className="text-xs text-gray-500 mt-1">Office 365 / Outlook</span>
                    </button>

                    {/* Any Provider Card */}
                    <button
                      onClick={() => {
                        setFormData(f => ({ ...f, provider: 'smtp', auth_method: 'password', smtp_host: '', smtp_port: 587, imap_host: '', imap_port: 993 }))
                        setWizardStep('smtp_instructions')
                      }}
                      className="flex flex-col items-center p-6 border-2 border-gray-200 rounded-xl hover:border-blue-400 hover:bg-blue-50 transition-all group"
                    >
                      <svg className="w-12 h-12 mb-3 text-gray-600 group-hover:text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                      </svg>
                      <span className="font-semibold text-gray-900 group-hover:text-blue-700">Any Provider</span>
                      <span className="text-xs text-gray-500 mt-1">IMAP / SMTP</span>
                    </button>
                  </div>
                </div>
              )}

              {/* ── Step: Google Instructions ── */}
              {wizardStep === 'google_instructions' && (
                <div className="space-y-5">
                  <p className="text-gray-600">Follow these steps to generate an App Password for your Gmail / Google Workspace account</p>

                  <div className="space-y-4">
                    <div className="border rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 flex items-center gap-2">
                        <span className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold">1</span>
                        Enable 2-Step Verification
                      </h4>
                      <div className="mt-2 ml-8 text-sm text-gray-600 space-y-1">
                        <p>Go to <a href="https://myaccount.google.com/security" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">myaccount.google.com/security</a></p>
                        <p>Under &quot;How you sign in to Google&quot;, click <strong>2-Step Verification</strong></p>
                        <p>Follow the prompts to set up (phone number or authenticator app)</p>
                        <p>Click <strong>Turn on</strong></p>
                      </div>
                    </div>

                    <div className="border rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 flex items-center gap-2">
                        <span className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold">2</span>
                        Generate an App Password
                      </h4>
                      <div className="mt-2 ml-8 text-sm text-gray-600 space-y-1">
                        <p>Go to <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">myaccount.google.com/apppasswords</a></p>
                        <p>If you don&apos;t see this page, 2-Step Verification may not be enabled</p>
                        <p>Enter a name (e.g., &quot;Exzelon RA&quot;) and click <strong>Create</strong></p>
                        <p>Copy the 16-character password (shown once &mdash; save it)</p>
                      </div>
                    </div>

                    <div className="border rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 flex items-center gap-2">
                        <span className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold">3</span>
                        Enable IMAP Access
                      </h4>
                      <div className="mt-2 ml-8 text-sm text-gray-600 space-y-1">
                        <p>Open Gmail &rarr; Settings (gear icon) &rarr; <strong>See all settings</strong></p>
                        <p>Go to <strong>Forwarding and POP/IMAP</strong> tab</p>
                        <p>Under &quot;IMAP access&quot;, select <strong>Enable IMAP</strong></p>
                        <p>Click <strong>Save Changes</strong></p>
                        <p className="text-gray-400 text-xs">Note: For Google Workspace, IMAP is enabled by default</p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <p className="text-sm text-blue-800">App Passwords let Exzelon RA send and receive emails on your behalf without sharing your main Google password. Your credentials are encrypted and stored securely.</p>
                  </div>

                  <div className="flex justify-between pt-2">
                    <button onClick={handleWizardBack} className="px-4 py-2 text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-50">Back</button>
                    <button onClick={() => setWizardStep('google_form')} className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                      I&apos;ve completed these steps &rarr; Continue
                    </button>
                  </div>
                </div>
              )}

              {/* ── Step: Google Form ── */}
              {wizardStep === 'google_form' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Email Address *</label>
                    <input type="email" required value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="user@gmail.com" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
                    <input type="text" value={formData.display_name} onChange={(e) => setFormData({ ...formData, display_name: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="First Last" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">App Password *</label>
                    <input type="password" required value={formData.password} onChange={(e) => setFormData({ ...formData, password: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="The 16-character password from step 2" />
                    <p className="text-xs text-gray-500 mt-1">Paste the App Password you generated in Google</p>
                  </div>

                  <div className="bg-gray-50 border rounded-lg p-3">
                    <p className="text-xs text-gray-500">
                      <strong>Auto-configured:</strong> SMTP: smtp.gmail.com:587 &bull; IMAP: imap.gmail.com:993
                    </p>
                  </div>

                  <div className="flex justify-between pt-2">
                    <button onClick={handleWizardBack} className="px-4 py-2 text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-50">Back</button>
                    <button
                      onClick={handleWizardCreate}
                      disabled={wizardSubmitting || !formData.email || !formData.password}
                      className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                    >
                      {wizardSubmitting ? 'Creating...' : 'Connect Google Account'}
                    </button>
                  </div>
                </div>
              )}

              {/* ── Step: Microsoft Instructions ── */}
              {wizardStep === 'microsoft_instructions' && (
                <div className="space-y-5">
                  <p className="text-gray-600">Follow these steps before connecting your Office 365 / Outlook account</p>

                  <div className="bg-amber-50 border border-amber-300 rounded-lg p-3">
                    <p className="text-sm text-amber-800 font-medium">Free Outlook.com / Hotmail accounts are not supported. Only Microsoft 365 business accounts can be connected.</p>
                  </div>

                  <div className="space-y-4">
                    <div className="border rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 flex items-center gap-2">
                        <span className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold">1</span>
                        Enable SMTP Authentication (required)
                      </h4>
                      <div className="mt-2 ml-8 text-sm text-gray-600 space-y-1">
                        <p>Sign in to <a href="https://admin.microsoft.com" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Microsoft 365 Admin Center</a></p>
                        <p>Go to <strong>Users</strong> &rarr; <strong>Active Users</strong> &rarr; Select the email account</p>
                        <p>Click <strong>Mail</strong> tab &rarr; <strong>Manage email apps</strong></p>
                        <p>Check both <strong>IMAP</strong> and <strong>Authenticated SMTP</strong> checkboxes</p>
                        <p>Click <strong>Save changes</strong></p>
                        <p className="text-amber-700 font-medium">Wait approximately 1 hour for changes to propagate</p>
                      </div>
                    </div>

                    <details className="border rounded-lg">
                      <summary className="p-4 cursor-pointer font-semibold text-gray-900 flex items-center gap-2 hover:bg-gray-50">
                        <span className="flex items-center justify-center w-6 h-6 rounded-full bg-gray-100 text-gray-600 text-xs font-bold">2</span>
                        For GoDaddy-hosted Microsoft 365 (optional)
                      </summary>
                      <div className="px-4 pb-4 ml-8 text-sm text-gray-600 space-y-1">
                        <p>Go to GoDaddy Admin &rarr; My Products &rarr; Email and Office</p>
                        <p>Click <strong>Manage</strong> next to your M365 subscription</p>
                        <p>Go to <strong>Advanced Settings</strong></p>
                        <p>Turn on the <strong>SMTP Authentication</strong> toggle</p>
                      </div>
                    </details>
                  </div>

                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <p className="text-sm text-blue-800">Exzelon RA uses Microsoft OAuth2 for secure authentication. You&apos;ll be redirected to Microsoft to sign in &mdash; no passwords are stored on our server.</p>
                  </div>

                  <div className="flex justify-between pt-2">
                    <button onClick={handleWizardBack} className="px-4 py-2 text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-50">Back</button>
                    <button onClick={() => setWizardStep('microsoft_form')} className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                      SMTP is enabled &rarr; Continue
                    </button>
                  </div>
                </div>
              )}

              {/* ── Step: Microsoft Form ── */}
              {wizardStep === 'microsoft_form' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Email Address *</label>
                    <input type="email" required value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="user@company.com" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
                    <input type="text" value={formData.display_name} onChange={(e) => setFormData({ ...formData, display_name: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="First Last" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Azure AD Tenant ID (optional)</label>
                    <input type="text" value={formData.oauth_tenant_id} onChange={(e) => setFormData({ ...formData, oauth_tenant_id: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="common (multi-tenant)" />
                    <p className="text-xs text-gray-500 mt-1">Leave blank for &quot;common&quot; (works for most M365 tenants)</p>
                  </div>

                  <div className="bg-gray-50 border rounded-lg p-3">
                    <p className="text-xs text-gray-500">
                      <strong>Auto-configured:</strong> SMTP: smtp.office365.com:587 &bull; IMAP: outlook.office365.com:993
                    </p>
                  </div>

                  <div className="flex justify-between pt-2">
                    <button onClick={handleWizardBack} className="px-4 py-2 text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-50">Back</button>
                    <button
                      onClick={async () => {
                        if (!formData.email) { toast('error', 'Email address is required'); return }
                        setWizardSubmitting(true)
                        try {
                          const createData: Record<string, any> = {
                            email: formData.email,
                            display_name: formData.display_name || undefined,
                            provider: 'microsoft_365',
                            auth_method: 'oauth2',
                            smtp_host: 'smtp.office365.com',
                            smtp_port: 587,
                            imap_host: 'outlook.office365.com',
                            imap_port: 993,
                            oauth_tenant_id: formData.oauth_tenant_id || undefined,
                          }
                          const result = await mailboxesApi.create(createData)
                          setCreatedMailboxId(result.mailbox_id)
                          fetchData()
                          // Initiate OAuth
                          const oauthResult = await mailboxesApi.oauthInitiate(result.mailbox_id, formData.email)
                          window.location.href = oauthResult.authorization_url
                        } catch (error: any) {
                          toast('error', error.response?.data?.detail || 'Failed to create mailbox')
                          setWizardSubmitting(false)
                        }
                      }}
                      disabled={wizardSubmitting || !formData.email}
                      className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
                    >
                      <svg className="w-5 h-5" viewBox="0 0 21 21" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect x="1" y="1" width="9" height="9" fill="#F25022"/><rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>
                        <rect x="1" y="11" width="9" height="9" fill="#00A4EF"/><rect x="11" y="11" width="9" height="9" fill="#FFB900"/>
                      </svg>
                      {wizardSubmitting ? 'Redirecting...' : 'Connect with Microsoft'}
                    </button>
                  </div>
                </div>
              )}

              {/* ── Step: SMTP Instructions ── */}
              {wizardStep === 'smtp_instructions' && (
                <div className="space-y-5">
                  <p className="text-gray-600">Connect any email provider using IMAP and SMTP credentials</p>

                  <div className="border rounded-lg p-4">
                    <h4 className="font-semibold text-gray-900 mb-2">Requirements</h4>
                    <ul className="text-sm text-gray-600 space-y-1 list-disc ml-5">
                      <li>You need <strong>both IMAP and SMTP</strong> protocols configured</li>
                      <li>Contact your email provider for accurate server details</li>
                    </ul>
                  </div>

                  <div>
                    <button
                      onClick={() => setShowSmtpRefTable(!showSmtpRefTable)}
                      className="flex items-center gap-2 text-sm font-medium text-blue-600 hover:text-blue-800"
                    >
                      <svg className={`w-4 h-4 transition-transform ${showSmtpRefTable ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                      Common provider settings reference
                    </button>
                    {showSmtpRefTable && (
                      <div className="mt-3 border rounded-lg overflow-hidden">
                        <table className="min-w-full text-xs">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-3 py-2 text-left font-medium text-gray-600">Provider</th>
                              <th className="px-3 py-2 text-left font-medium text-gray-600">IMAP Host</th>
                              <th className="px-3 py-2 text-left font-medium text-gray-600">Port</th>
                              <th className="px-3 py-2 text-left font-medium text-gray-600">SMTP Host</th>
                              <th className="px-3 py-2 text-left font-medium text-gray-600">Port</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            {SMTP_REFERENCE_TABLE.map(row => (
                              <tr key={row.provider} className="hover:bg-gray-50">
                                <td className="px-3 py-1.5 font-medium text-gray-800">{row.provider}</td>
                                <td className="px-3 py-1.5 text-gray-600 font-mono">{row.imap_host}</td>
                                <td className="px-3 py-1.5 text-gray-600">{row.imap_port || '\u2014'}</td>
                                <td className="px-3 py-1.5 text-gray-600 font-mono">{row.smtp_host}</td>
                                <td className="px-3 py-1.5 text-gray-600">{row.smtp_port}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <p className="text-sm text-blue-800">If you&apos;re getting an SSL error, try switching between port 587 (STARTTLS) and 465 (SSL/TLS).</p>
                  </div>

                  <div className="flex justify-between pt-2">
                    <button onClick={handleWizardBack} className="px-4 py-2 text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-50">Back</button>
                    <button onClick={() => setWizardStep('smtp_form')} className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                      Continue to Setup
                    </button>
                  </div>
                </div>
              )}

              {/* ── Step: SMTP Form ── */}
              {wizardStep === 'smtp_form' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="col-span-2 md:col-span-1">
                      <h4 className="text-sm font-semibold text-gray-800 mb-3">Account</h4>
                      <div className="space-y-3">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Email Address *</label>
                          <input type="email" required value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="user@example.com" />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
                          <input type="text" value={formData.display_name} onChange={(e) => setFormData({ ...formData, display_name: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="First Last" />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Password / App Password *</label>
                          <input type="password" required value={formData.password} onChange={(e) => setFormData({ ...formData, password: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="********" />
                        </div>
                      </div>
                    </div>
                    <div className="col-span-2 md:col-span-1">
                      <h4 className="text-sm font-semibold text-gray-800 mb-3">Server Settings</h4>
                      <div className="space-y-3">
                        <div className="grid grid-cols-3 gap-2">
                          <div className="col-span-2">
                            <label className="block text-sm font-medium text-gray-700 mb-1">IMAP Host *</label>
                            <input type="text" required value={formData.imap_host} onChange={(e) => setFormData({ ...formData, imap_host: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="imap.example.com" />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">IMAP Port *</label>
                            <input type="number" required value={formData.imap_port} onChange={(e) => setFormData({ ...formData, imap_port: parseInt(e.target.value) || 993 })} className="w-full px-3 py-2 border rounded-lg" />
                          </div>
                        </div>
                        <div className="grid grid-cols-3 gap-2">
                          <div className="col-span-2">
                            <label className="block text-sm font-medium text-gray-700 mb-1">SMTP Host *</label>
                            <input type="text" required value={formData.smtp_host} onChange={(e) => setFormData({ ...formData, smtp_host: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="smtp.example.com" />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">SMTP Port *</label>
                            <input type="number" required value={formData.smtp_port} onChange={(e) => setFormData({ ...formData, smtp_port: parseInt(e.target.value) || 587 })} className="w-full px-3 py-2 border rounded-lg" />
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-between pt-2">
                    <button onClick={handleWizardBack} className="px-4 py-2 text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-50">Back</button>
                    <button
                      onClick={handleWizardCreate}
                      disabled={wizardSubmitting || !formData.email || !formData.password || !formData.smtp_host || !formData.imap_host}
                      className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                    >
                      {wizardSubmitting ? 'Creating...' : 'Connect & Test'}
                    </button>
                  </div>
                </div>
              )}

              {/* ── Step: Settings ── */}
              {wizardStep === 'settings' && (
                <div className="space-y-5">
                  {/* Connection test result */}
                  {wizardTestResult && (
                    <div className={`p-3 rounded-lg ${wizardTestResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                      <div className="flex items-center gap-2">
                        {wizardTestResult.success ? (
                          <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                        ) : (
                          <svg className="w-5 h-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>
                        )}
                        <span className={`text-sm font-medium ${wizardTestResult.success ? 'text-green-800' : 'text-red-800'}`}>
                          {wizardTestResult.success ? 'Connection successful' : wizardTestResult.message}
                        </span>
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
                    <input type="checkbox" id="wizard_is_active" checked={formData.is_active} onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })} className="h-4 w-4 text-blue-600 border-gray-300 rounded" />
                    <label htmlFor="wizard_is_active" className="ml-2 text-sm text-gray-700">Active</label>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                    <textarea value={formData.notes} onChange={(e) => setFormData({ ...formData, notes: e.target.value })} className="w-full px-3 py-2 border rounded-lg" rows={2} placeholder="Optional notes..." />
                  </div>

                  {/* Collapsible Email Signature */}
                  <details className="border rounded-lg">
                    <summary className="p-3 cursor-pointer font-semibold text-gray-800 hover:bg-gray-50">Email Signature</summary>
                    <div className="px-3 pb-3">
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
                      {Object.values(sigData).some(v => v.trim() !== '') && (
                        <div className="mt-3">
                          <label className="block text-xs font-medium text-gray-500 mb-1">Signature Preview</label>
                          <div className="border rounded-lg p-3 bg-gray-50">
                            <div style={{ borderTop: '1px solid #cccccc', paddingTop: '10px', fontFamily: 'Arial, sans-serif' }}>
                              {sigData.sender_name && <div style={{ fontSize: '14px', fontWeight: 'bold', color: '#333333' }}>{sigData.sender_name}</div>}
                              {sigData.title && <div style={{ fontSize: '13px', color: '#555555' }}>{sigData.title}</div>}
                              {sigData.company && <div style={{ fontSize: '13px', color: '#555555' }}>{sigData.company}</div>}
                              {(sigData.phone || (sigData.email || formData.email)) && (
                                <div style={{ fontSize: '12px', color: '#666666' }}>{[sigData.phone, sigData.email || formData.email].filter(Boolean).join(' | ')}</div>
                              )}
                              {sigData.website && <div style={{ fontSize: '12px' }}><span style={{ color: '#0066cc' }}>{sigData.website}</span></div>}
                              {sigData.address && <div style={{ fontSize: '12px', color: '#666666' }}>{sigData.address}</div>}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </details>

                  <div className="flex justify-end space-x-3 pt-2">
                    <button onClick={handleWizardSkipSettings} className="px-4 py-2 text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-50">Skip for now</button>
                    <button
                      onClick={handleWizardSaveSettings}
                      disabled={wizardSubmitting}
                      className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                    >
                      {wizardSubmitting ? 'Saving...' : 'Save & Close'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
