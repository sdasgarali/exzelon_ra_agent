'use client'

import { useState, useEffect, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { mailboxesApi, deliverabilityApi, outreachRolesApi } from '@/lib/api'
import type { MailboxHealthDetail } from '@/types/api'
import { useAuthStore } from '@/lib/store'
import { useToast } from '@/components/toast'
import DOMPurify from 'dompurify'

// Derive a display logo from a website domain (Google favicon service) when the
// tenant has no explicit logo uploaded. Returns '' if no usable domain.
function websiteLogo(website?: string | null): string {
  if (!website) return ''
  try {
    const url = website.startsWith('http') ? website : `https://${website}`
    const host = new URL(url).hostname.replace(/^www\./, '')
    return host ? `https://www.google.com/s2/favicons?domain=${host}&sz=128` : ''
  } catch {
    return ''
  }
}

interface Mailbox {
  mailbox_id: number
  email: string
  display_name: string | null
  sender_first_name: string | null
  sender_last_name: string | null
  phone: string | null
  linkedin_url: string | null
  provider: string
  smtp_host: string | null
  smtp_port: number
  imap_host: string | null
  imap_port: number
  warmup_status: string
  is_active: boolean
  is_archived: boolean
  daily_send_limit: number
  emails_sent_today: number
  total_emails_sent: number
  warmup_emails_sent: number
  outreach_emails_sent: number
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
  outreach_role_id: number | null
  outreach_role_name: string | null
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
  role_counts: Record<string, number>
}

const WARMUP_STATUS_LABELS: Record<string, { label: string; color: string; tooltip: string }> = {
  inactive: { label: 'Inactive', color: 'bg-gray-100 text-gray-600', tooltip: 'Mailbox created but warmup has not started yet. Will auto-start on next assessment.' },
  warming_up: { label: 'Warming Up', color: 'bg-yellow-100 text-yellow-800', tooltip: 'Warmup in progress — gradually increasing send volume over 30 days across 4 phases.' },
  cold_ready: { label: 'Cold Ready', color: 'bg-green-100 text-green-800', tooltip: 'Warmup complete. Monitoring health for 7+ days before promoting to Active.' },
  active: { label: 'Active', color: 'bg-blue-100 text-blue-800', tooltip: 'Fully warmed up and ready for production sending. Health score 80+.' },
  paused: { label: 'Paused', color: 'bg-gray-100 text-gray-800', tooltip: 'Auto-paused due to high bounce rate (>5%) or complaint rate (>0.3%). Needs investigation.' },
  blacklisted: { label: 'Blacklisted', color: 'bg-red-100 text-red-800', tooltip: 'Domain or IP found on email blacklists. Sending is blocked until resolved.' },
  recovering: { label: 'Recovering', color: 'bg-orange-100 text-orange-800', tooltip: 'Previously paused, now recovering with reduced send volume.' },
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
  const router = useRouter()
  const isSuperAdmin = useAuthStore((s) => s.isSuperAdmin())
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

  // Mailbox health data
  const [mailboxHealthMap, setMailboxHealthMap] = useState<Record<number, MailboxHealthDetail>>({})

  // Outreach Roles state
  interface OutreachRole {
    role_id: number
    role_name: string
    description: string | null
    purpose: string | null
    is_system: boolean
    mailbox_count: number
  }
  const [outreachRoles, setOutreachRoles] = useState<OutreachRole[]>([])
  const [showRolesModal, setShowRolesModal] = useState(false)
  const [roleFormData, setRoleFormData] = useState({ role_name: '', description: '', purpose: '' })
  const [editingRole, setEditingRole] = useState<OutreachRole | null>(null)
  const [roleSaving, setRoleSaving] = useState(false)

  // Bulk selection state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [showBulkUpdateModal, setShowBulkUpdateModal] = useState(false)
  const [bulkUpdating, setBulkUpdating] = useState(false)
  const [bulkUpdateForm, setBulkUpdateForm] = useState({ is_active: '', daily_send_limit: '', warmup_status: '' })

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
    logo_url: '',
  })
  // Email Signature section: view-only by default; pencil unlocks inline edit.
  const [sigEditMode, setSigEditMode] = useState(false)
  const [sigSaving, setSigSaving] = useState(false)

  // Auto-populate signature fields from tenant data and mailbox info
  const autoPopulateSigData = (
    existingSig: typeof sigData,
    mailboxEmail: string,
    displayName: string,
  ) => {
    const tenant = useAuthStore.getState().user?.tenant
    return {
      sender_name: existingSig.sender_name || displayName || '',
      title: existingSig.title || '',
      phone: existingSig.phone || '',
      email: existingSig.email || mailboxEmail || '',
      company: existingSig.company || tenant?.name || '',
      website: existingSig.website || tenant?.website || '',
      address: existingSig.address || tenant?.company_address || '',
      // Always source a logo: saved value → tenant logo → derived from website.
      logo_url: existingSig.logo_url || tenant?.logo_url || websiteLogo(tenant?.website),
    }
  }

  const [formData, setFormData] = useState({
    email: '',
    display_name: '',
    sender_first_name: '',
    sender_last_name: '',
    phone: '',
    linkedin_url: '',
    password: '',
    provider: 'microsoft_365',
    smtp_host: '',
    smtp_port: 587,
    imap_host: '',
    imap_port: 993,
    warmup_status: 'inactive',
    is_active: true,
    daily_send_limit: 30,
    notes: '',
    email_signature_json: '',
    auth_method: 'password' as 'password' | 'oauth2',
    oauth_tenant_id: '',
    outreach_role_id: null as number | null,
  })
  const [oauthConnecting, setOauthConnecting] = useState(false)

  // Wizard state
  const [wizardStep, setWizardStep] = useState<WizardStep>('select_provider')
  const [createdMailboxId, setCreatedMailboxId] = useState<number | null>(null)
  const [wizardSubmitting, setWizardSubmitting] = useState(false)
  const [wizardTestResult, setWizardTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [showSmtpRefTable, setShowSmtpRefTable] = useState(false)

  // Detail modal state
  const [detailMailboxId, setDetailMailboxId] = useState<number | null>(null)
  const [detailData, setDetailData] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailTab, setDetailTab] = useState<'overview' | 'campaigns' | 'warmup' | 'settings'>('overview')

  const fetchMailboxDetail = async (id: number) => {
    setDetailMailboxId(id)
    setDetailLoading(true)
    setDetailTab('overview')
    setDetailData(null)
    try {
      const data = await mailboxesApi.getDetail(id)
      setDetailData(data)
    } catch (error: any) {
      toast('error', error.response?.data?.detail || 'Failed to load mailbox detail')
      setDetailMailboxId(null)
    } finally {
      setDetailLoading(false)
    }
  }

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

      const [mailboxData, statsData, rolesData] = await Promise.all([
        mailboxesApi.list(params),
        mailboxesApi.stats(),
        outreachRolesApi.list().catch(() => []),
      ])
      setOutreachRoles(rolesData)
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
      // Fetch health data for each mailbox in background
      if (items.length > 0) {
        Promise.allSettled(
          items.map((mb: Mailbox) => deliverabilityApi.mailboxHealth(mb.mailbox_id).then(h => ({ id: mb.mailbox_id, data: h })))
        ).then(results => {
          const healthMap: Record<number, MailboxHealthDetail> = {}
          for (const r of results) {
            if (r.status === 'fulfilled' && r.value) {
              healthMap[r.value.id] = r.value.data
            }
          }
          setMailboxHealthMap(healthMap)
        })
      }
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
        case 'connection_status': {
          const connOrder: Record<string, number> = { success: 0, successful: 0, failed: 1 }
          const aConn = connectionStatus[a.mailbox_id] || a.connection_status || ''
          const bConn = connectionStatus[b.mailbox_id] || b.connection_status || ''
          aVal = connOrder[aConn] ?? 2
          bVal = connOrder[bConn] ?? 2
          break
        }
        case 'created_at': aVal = a.created_at; bVal = b.created_at; break
        default: aVal = a.email; bVal = b.email
      }
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1
      return 0
    })

    return result
  }, [mailboxes, searchQuery, connectionFilter, providerFilter, sortKey, sortDir, connectionStatus])

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
    return sortDir === 'asc' ? <span className="ml-1">&#9650;</span> : <span className="ml-1">&#9660;</span>
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

  const handleBulkUpdate = async () => {
    const updates: Record<string, any> = {}
    if (bulkUpdateForm.is_active !== '') updates.is_active = bulkUpdateForm.is_active === 'true'
    if (bulkUpdateForm.daily_send_limit !== '') updates.daily_send_limit = parseInt(bulkUpdateForm.daily_send_limit)
    if (bulkUpdateForm.warmup_status !== '') updates.warmup_status = bulkUpdateForm.warmup_status
    if (Object.keys(updates).length === 0) return
    setBulkUpdating(true)
    try {
      await mailboxesApi.bulkUpdate(Array.from(selectedIds), updates)
      toast('success', `Updated ${selectedIds.size} mailbox(es)`)
      setShowBulkUpdateModal(false)
      setBulkUpdateForm({ is_active: '', daily_send_limit: '', warmup_status: '' })
      setSelectedIds(new Set())
      fetchData()
    } catch (err: any) {
      toast('error', err?.response?.data?.detail || 'Bulk update failed')
    } finally {
      setBulkUpdating(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const profileError = validateSenderProfile()
    if (profileError) { toast('error', profileError); return }
    try {
      // Serialize signature data (Title/Role, phone and logo are derived)
      const sigJson = serializeSig()

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
      sender_first_name: mailbox.sender_first_name || '',
      sender_last_name: mailbox.sender_last_name || '',
      phone: mailbox.phone || '',
      linkedin_url: mailbox.linkedin_url || '',
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
      outreach_role_id: mailbox.outreach_role_id,
    })
    // Populate signature fields from saved JSON, backfill empty fields from tenant
    const displayName = mailbox.display_name || [mailbox.sender_first_name, mailbox.sender_last_name].filter(Boolean).join(' ')
    let parsedSig = { sender_name: '', title: '', phone: '', email: '', company: '', website: '', address: '', logo_url: '' }
    if (mailbox.email_signature_json) {
      try {
        const sig = JSON.parse(mailbox.email_signature_json)
        parsedSig = {
          sender_name: sig.sender_name || '',
          title: sig.title || '',
          phone: sig.phone || '',
          email: sig.email || '',
          company: sig.company || '',
          website: sig.website || '',
          address: sig.address || '',
          logo_url: sig.logo_url || '',
        }
      } catch { /* keep defaults */ }
    }
    setSigEditMode(false)
    setSigData(autoPopulateSigData(parsedSig, mailbox.email, displayName))
    setShowAddModal(true)
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to archive this mailbox?')) return
    try {
      await mailboxesApi.delete(id)
      fetchData()
    } catch (error: any) {
      toast('error', error.response?.data?.detail || 'Failed to archive mailbox')
    }
  }

  const handleRestore = async (id: number) => {
    if (!confirm('Restore this mailbox? It will be unarchived and activated.')) return
    try {
      await mailboxesApi.restore(id)
      toast('success', 'Mailbox restored and activated')
      fetchData()
    } catch (error: any) {
      toast('error', error.response?.data?.detail || 'Failed to restore mailbox')
    }
  }

  const handlePermanentDelete = async (id: number) => {
    if (!confirm('PERMANENTLY DELETE this mailbox? This action is irreversible and all data will be lost.')) return
    try {
      await mailboxesApi.permanentDelete(id)
      toast('success', 'Mailbox permanently deleted')
      fetchData()
    } catch (error: any) {
      toast('error', error.response?.data?.detail || 'Failed to permanently delete mailbox')
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


  const resetForm = () => {
    setFormData({
      email: '',
      display_name: '',
      sender_first_name: '',
      sender_last_name: '',
      phone: '',
      linkedin_url: '',
      password: '',
      provider: 'microsoft_365',
      smtp_host: '',
      smtp_port: 587,
      imap_host: '',
      imap_port: 993,
      warmup_status: 'inactive',
      is_active: true,
      daily_send_limit: 30,
      notes: '',
      email_signature_json: '',
      auth_method: 'password',
      oauth_tenant_id: '',
      outreach_role_id: null,
    })
    setSigData(autoPopulateSigData(
      { sender_name: '', title: '', phone: '', email: '', company: '', website: '', address: '', logo_url: '' },
      '', ''
    ))
    setSigEditMode(false)
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
      const sigJson = serializeSig()
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
      // Auto-populate signature with display name + email now that they're known
      const displayName = formData.display_name || [formData.sender_first_name, formData.sender_last_name].filter(Boolean).join(' ')
      setSigData(prev => autoPopulateSigData(prev, formData.email, displayName))
      setWizardStep('settings')
      fetchData()
    } catch (error: any) {
      toast('error', error.response?.data?.detail || 'Failed to create mailbox')
    } finally {
      setWizardSubmitting(false)
    }
  }

  // ── Sender Profile / Signature helpers ────────────────────────────────
  const roleDesc = (roleId: number | null): string => {
    if (!roleId) return ''
    const r = outreachRoles.find(x => x.role_id === roleId)
    return (r?.description || r?.role_name || '').trim()
  }

  // US phone: keep digits only, format progressively as (555) 123-4567
  const formatUsPhone = (input: string): string => {
    let d = input.replace(/\D/g, '')
    if (d.length === 11 && d.startsWith('1')) d = d.slice(1)
    d = d.slice(0, 10)
    if (d.length === 0) return ''
    if (d.length < 4) return `(${d}`
    if (d.length < 7) return `(${d.slice(0, 3)}) ${d.slice(3)}`
    return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`
  }
  const isValidUsPhone = (input: string): boolean => {
    const d = input.replace(/\D/g, '')
    return d.length === 10 || (d.length === 11 && d.startsWith('1'))
  }

  // Effective signature = editable fields + derived Title (Role description),
  // phone (Sender Profile), and tenant logo.
  const effectiveSig = () => ({
    ...sigData,
    title: roleDesc(formData.outreach_role_id),
    phone: formData.phone || sigData.phone || '',
    logo_url: sigData.logo_url || useAuthStore.getState().user?.tenant?.logo_url || websiteLogo(useAuthStore.getState().user?.tenant?.website),
  })

  const serializeSig = (): string => {
    const s = effectiveSig()
    return Object.values(s).some(v => (v || '').toString().trim() !== '') ? JSON.stringify(s) : ''
  }

  // Build a sanitized HTML signature block (mirrors backend render_signature_html).
  const buildSignatureHtml = (): string => {
    const s = effectiveSig()
    const esc = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
    const parts: string[] = []
    if (s.logo_url) {
      const logo = s.logo_url.startsWith('http') ? s.logo_url : `https://${s.logo_url}`
      parts.push(`<img src="${esc(logo)}" alt="${esc(s.company || '')}" style="max-height:48px;max-width:200px;margin-bottom:8px;border:0;display:block;" />`)
    }
    if (s.sender_name) parts.push(`<strong style="font-size:14px;color:#333;">${esc(s.sender_name)}</strong>`)
    if (s.title) parts.push(`<span style="font-size:13px;color:#555;">${esc(s.title)}</span>`)
    if (s.company) parts.push(`<span style="font-size:13px;color:#555;">${esc(s.company)}</span>`)
    const contact: string[] = []
    if (s.phone) contact.push(esc(s.phone))
    if (s.email) contact.push(`<a href="mailto:${esc(s.email)}" style="color:#0066cc;text-decoration:none;">${esc(s.email)}</a>`)
    if (contact.length) parts.push(`<span style="font-size:12px;color:#666;">${contact.join(' | ')}</span>`)
    if (s.website) {
      const url = s.website.startsWith('http') ? s.website : `https://${s.website}`
      parts.push(`<a href="${esc(url)}" style="font-size:12px;color:#0066cc;text-decoration:none;">${esc(s.website)}</a>`)
    }
    if (s.address) parts.push(`<span style="font-size:12px;color:#666;">${esc(s.address)}</span>`)
    if (!parts.length) return ''
    const html = `<div style="padding-top:12px;border-top:1px solid #ccc;font-family:Arial,sans-serif;">${parts.join('<br>')}</div>`
    return typeof window !== 'undefined' ? DOMPurify.sanitize(html) : html
  }

  // Validate the mandatory Sender Profile fields; returns an error message or null.
  const validateSenderProfile = (): string | null => {
    if (!formData.sender_first_name.trim() || !formData.sender_last_name.trim()) return 'First and last name are required.'
    if (!formData.phone.trim() || !isValidUsPhone(formData.phone)) return 'A valid US phone number is required, e.g. (555) 123-4567.'
    if (!formData.outreach_role_id) return 'Role is required.'
    return null
  }

  // Inline save of just the Email Signature (+ phone) for the mailbox being edited.
  const handleSaveSignature = async () => {
    const targetId = editingMailbox?.mailbox_id ?? createdMailboxId
    if (!targetId) { setSigEditMode(false); return }
    setSigSaving(true)
    try {
      await mailboxesApi.update(targetId, {
        email_signature_json: serializeSig(),
        phone: formData.phone || undefined,
      })
      toast('success', 'Signature saved')
      setSigEditMode(false)
      fetchData()
    } catch (err: any) {
      toast('error', err?.response?.data?.detail || 'Failed to save signature')
    } finally {
      setSigSaving(false)
    }
  }

  // Wizard: save settings on final step
  const handleWizardSaveSettings = async () => {
    if (!createdMailboxId) return
    const profileError = validateSenderProfile()
    if (profileError) { toast('error', profileError); return }
    setWizardSubmitting(true)
    try {
      const sigJson = serializeSig()
      await mailboxesApi.update(createdMailboxId, {
        sender_first_name: formData.sender_first_name,
        sender_last_name: formData.sender_last_name,
        phone: formData.phone || undefined,
        daily_send_limit: formData.daily_send_limit,
        is_active: formData.is_active,
        notes: formData.notes,
        email_signature_json: sigJson,
        outreach_role_id: formData.outreach_role_id,
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
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Sender Mailboxes</h1>
          <p className="text-gray-500">Manage email accounts used for outreach</p>
        </div>
        <div className="flex space-x-3">
          {isSuperAdmin && (
            <button
              onClick={() => { setEditingRole(null); setRoleFormData({ role_name: '', description: '', purpose: '' }); setShowRolesModal(true) }}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
            >
              Manage Roles
            </button>
          )}
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
          {/* Role Count Cards */}
          {stats.role_counts && Object.entries(stats.role_counts).map(([roleName, count]) => (
            <div key={roleName} className="bg-white p-4 rounded-lg shadow border-l-4 border-indigo-400">
              <div className="text-2xl font-bold text-indigo-600">{count}</div>
              <div className="text-sm text-gray-500">Total {roleName}s</div>
            </div>
          ))}
        </div>
      )}

      {/* Search & Filters Bar */}
      <div className="bg-white p-4 rounded-lg shadow">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-0 sm:min-w-[220px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Search</label>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by email, name, or notes..."
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div className="w-full sm:w-40">
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
          <div className="w-full sm:w-40">
            <label className="block text-sm font-medium text-gray-700 mb-1">Connection</label>
            <select value={connectionFilter} onChange={(e) => setConnectionFilter(e.target.value)} className="w-full px-3 py-2 border rounded-lg">
              <option value="">All Connections</option>
              <option value="successful">Successful</option>
              <option value="failed">Failed</option>
              <option value="untested">Not Tested</option>
            </select>
          </div>
          <div className="w-full sm:w-40">
            <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
            <select value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)} className="w-full px-3 py-2 border rounded-lg">
              <option value="">All Providers</option>
              <option value="microsoft_365">Microsoft 365</option>
              <option value="gmail">Gmail</option>
              <option value="smtp">Custom SMTP</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div className="w-full sm:w-40 flex items-end">
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

      {/* OAuth Upgrade Banner */}
      {mailboxes.some(mb => mb.auth_method === 'password' && mb.connection_status === 'failed') && (
        <div className="bg-amber-50 border border-amber-200 p-3 rounded-lg flex items-center gap-3">
          <svg className="w-5 h-5 text-amber-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <div className="flex-1">
            <p className="text-sm text-amber-800">
              <strong>Some mailboxes are using password authentication and failing.</strong> Switch to <strong>OAuth2</strong> for a more reliable connection that won&apos;t break when passwords change.
              Click any mailbox &rarr; select <em>Microsoft OAuth2</em> &rarr; click <em>Connect with Microsoft 365</em>.
            </p>
          </div>
        </div>
      )}

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
            {isSuperAdmin && (
              <button onClick={() => setShowBulkUpdateModal(true)} className="px-3 py-1.5 text-sm text-white bg-indigo-600 rounded-lg hover:bg-indigo-700">
                Bulk Update ({selectedIds.size})
              </button>
            )}
          </div>
        </div>
      )}

      {/* Bulk Update Modal */}
      {showBulkUpdateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-bold mb-1">Bulk Update {selectedIds.size} Mailbox{selectedIds.size > 1 ? 'es' : ''}</h2>
            <p className="text-sm text-gray-500 mb-4">Only filled fields will be updated.</p>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Active Status</label>
                <select value={bulkUpdateForm.is_active} onChange={e => setBulkUpdateForm(f => ({ ...f, is_active: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm">
                  <option value="">— No change —</option>
                  <option value="true">Active</option>
                  <option value="false">Inactive</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Daily Send Limit</label>
                <input type="number" value={bulkUpdateForm.daily_send_limit} onChange={e => setBulkUpdateForm(f => ({ ...f, daily_send_limit: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Leave blank to skip" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Warmup Status</label>
                <select value={bulkUpdateForm.warmup_status} onChange={e => setBulkUpdateForm(f => ({ ...f, warmup_status: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm">
                  <option value="">— No change —</option>
                  <option value="inactive">Inactive</option>
                  <option value="warming_up">Warming Up</option>
                  <option value="active">Active</option>
                  <option value="paused">Paused</option>
                  <option value="cold_ready">Cold Ready</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => { setShowBulkUpdateModal(false); setBulkUpdateForm({ is_active: '', daily_send_limit: '', warmup_status: '' }) }} className="px-4 py-2 text-sm border rounded-lg hover:bg-gray-50">Cancel</button>
              <button onClick={handleBulkUpdate} disabled={bulkUpdating || (bulkUpdateForm.is_active === '' && bulkUpdateForm.daily_send_limit === '' && bulkUpdateForm.warmup_status === '')} className="px-4 py-2 text-sm text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                {bulkUpdating ? 'Updating...' : 'Update'}
              </button>
            </div>
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
        <div className="overflow-x-auto">
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
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort('warmup_status')} title="Warmup lifecycle: Inactive → Warming Up (30 days) → Cold Ready → Active. Managed automatically by the warmup engine.">
                Status <SortIcon column="warmup_status" />
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Role</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort('emails_sent_today')}>
                Today <SortIcon column="emails_sent_today" />
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort('total_emails_sent')} title="Outreach emails only (excludes warmup). Warmup count shown below.">
                Outreach <SortIcon column="total_emails_sent" />
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase" title="Weighted health score (0-100): 35% bounce rate + 25% reply rate + 25% complaint rate + 15% account age. Grades: A+ (90+), A (80+), B (60+), C (40+), D (&lt;40).">Health</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase" title="Percentage of sent emails that bounced. Auto-pauses warmup if bounce rate exceeds 5%.">Bounce %</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase" title="Percentage of sent emails that received a reply. Higher is better — indicates good sender reputation.">Reply %</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase" title="Percentage of sent emails marked as spam by recipients. Auto-pauses warmup if complaint rate exceeds 0.3%.">Complaint %</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase" title="Engagement tier based on recipient interactions: Hot (60%+ — replies &amp; clicks), Warm (30%+ — some signals), Cold (10%+ — minimal activity), Dead (&lt;10% — no engagement or all bounced).">Engagement</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort('connection_status')}>
                Connection <SortIcon column="connection_status" />
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {filteredMailboxes.map((mailbox) => (
              <tr key={mailbox.mailbox_id} className={`${!mailbox.is_active ? 'bg-gray-50' : ''} ${selectedIds.has(mailbox.mailbox_id) ? 'bg-blue-50' : ''} hover:bg-gray-50 cursor-pointer`} onClick={() => fetchMailboxDetail(mailbox.mailbox_id)}>
                <td className="px-4 py-4" onClick={(e) => e.stopPropagation()}>
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
                  <span className={`text-xs px-2 py-1 rounded-full cursor-help ${WARMUP_STATUS_LABELS[mailbox.warmup_status]?.color || 'bg-gray-100'}`} title={WARMUP_STATUS_LABELS[mailbox.warmup_status]?.tooltip || ''}>
                    {WARMUP_STATUS_LABELS[mailbox.warmup_status]?.label || mailbox.warmup_status}
                  </span>
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  {mailbox.outreach_role_name ? (
                    <span className="text-xs px-2 py-1 rounded-full bg-indigo-100 text-indigo-800">{mailbox.outreach_role_name}</span>
                  ) : (
                    <span className="text-xs text-gray-400">—</span>
                  )}
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  <div className="text-sm text-gray-900">{mailbox.emails_sent_today} / {mailbox.daily_send_limit}</div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-1">
                    <div className="bg-blue-600 h-2 rounded-full" style={{ width: `${Math.min(100, (mailbox.emails_sent_today / mailbox.daily_send_limit) * 100)}%` }} />
                  </div>
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  <div className="text-sm font-medium text-gray-900">{mailbox.outreach_emails_sent}</div>
                  {mailbox.warmup_emails_sent > 0 && (
                    <div className="text-xs text-gray-400">{mailbox.warmup_emails_sent} warmup</div>
                  )}
                </td>
                {/* Health Score + Grade */}
                <td className="px-4 py-4 whitespace-nowrap">
                  {mailboxHealthMap[mailbox.mailbox_id] ? (() => {
                    const h = mailboxHealthMap[mailbox.mailbox_id]
                    const gradeColors: Record<string, string> = { A: 'bg-green-100 text-green-800', B: 'bg-blue-100 text-blue-800', C: 'bg-yellow-100 text-yellow-800', D: 'bg-orange-100 text-orange-800', F: 'bg-red-100 text-red-800' }
                    return (
                      <div className="flex items-center gap-1.5">
                        <div className="w-16 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${h.health_score >= 80 ? 'bg-green-500' : h.health_score >= 60 ? 'bg-yellow-500' : h.health_score >= 40 ? 'bg-orange-500' : 'bg-red-500'}`} style={{ width: `${h.health_score}%` }} />
                        </div>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${gradeColors[h.health_grade] || 'bg-gray-100 text-gray-800'}`}>{h.health_grade}</span>
                      </div>
                    )
                  })() : <span className="text-xs text-gray-400">-</span>}
                </td>
                {/* Bounce % */}
                <td className="px-4 py-4 whitespace-nowrap text-xs">
                  {mailboxHealthMap[mailbox.mailbox_id] ? (
                    <span className={mailboxHealthMap[mailbox.mailbox_id].bounce_rate_pct > 5 ? 'text-red-600 font-medium' : 'text-gray-600'}>
                      {mailboxHealthMap[mailbox.mailbox_id].bounce_rate_pct}%
                    </span>
                  ) : <span className="text-gray-400">-</span>}
                </td>
                {/* Reply % */}
                <td className="px-4 py-4 whitespace-nowrap text-xs">
                  {mailboxHealthMap[mailbox.mailbox_id] ? (
                    <span className="text-green-600">{mailboxHealthMap[mailbox.mailbox_id].reply_rate_pct}%</span>
                  ) : <span className="text-gray-400">-</span>}
                </td>
                {/* Complaint % */}
                <td className="px-4 py-4 whitespace-nowrap text-xs">
                  {mailboxHealthMap[mailbox.mailbox_id] ? (
                    <span className={mailboxHealthMap[mailbox.mailbox_id].complaint_rate_pct > 0.3 ? 'text-red-600 font-medium' : 'text-gray-600'}>
                      {mailboxHealthMap[mailbox.mailbox_id].complaint_rate_pct}%
                      {mailboxHealthMap[mailbox.mailbox_id].complaint_rate_pct > 0.3 && ' ⚠'}
                    </span>
                  ) : <span className="text-gray-400">-</span>}
                </td>
                {/* Engagement */}
                <td className="px-4 py-4 whitespace-nowrap text-xs">
                  {mailboxHealthMap[mailbox.mailbox_id] ? (() => {
                    const rate = mailboxHealthMap[mailbox.mailbox_id].engagement_rate
                    const tier = rate >= 0.6 ? 'hot' : rate >= 0.3 ? 'warm' : rate >= 0.1 ? 'cold' : 'dead'
                    const tierColors: Record<string, string> = { hot: 'bg-red-100 text-red-700', warm: 'bg-orange-100 text-orange-700', cold: 'bg-blue-100 text-blue-700', dead: 'bg-gray-100 text-gray-500' }
                    const tierTooltips: Record<string, string> = {
                      hot: `Hot (${(rate * 100).toFixed(0)}%) — Strong engagement: replies and clicks detected`,
                      warm: `Warm (${(rate * 100).toFixed(0)}%) — Moderate engagement: some interaction signals`,
                      cold: `Cold (${(rate * 100).toFixed(0)}%) — Low engagement: minimal recipient activity`,
                      dead: `Dead (${(rate * 100).toFixed(0)}%) — No engagement: all bounced or no interactions`,
                    }
                    return <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium cursor-help ${tierColors[tier]}`} title={tierTooltips[tier]}>{tier}</span>
                  })() : <span className="text-gray-400">-</span>}
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
                <td className="px-4 py-4 whitespace-nowrap text-right text-sm font-medium space-x-2" onClick={(e) => e.stopPropagation()}>
                  {showArchived ? (
                    /* Archived view: Super Admin gets Restore + Permanent Delete */
                    isSuperAdmin ? (
                      <>
                        <button onClick={() => handleRestore(mailbox.mailbox_id)} className="text-green-600 hover:text-green-900">Restore</button>
                        <button onClick={() => handlePermanentDelete(mailbox.mailbox_id)} className="text-red-600 hover:text-red-900">Delete Permanently</button>
                      </>
                    ) : (
                      <span className="text-gray-400 text-xs">Super Admin required</span>
                    )
                  ) : (
                    /* Active view: normal actions */
                    <>
                      <button onClick={() => handleTestConnection(mailbox.mailbox_id)} disabled={testingId === mailbox.mailbox_id} className="text-green-600 hover:text-green-900 disabled:opacity-50">
                        {testingId === mailbox.mailbox_id ? 'Testing...' : 'Test'}
                      </button>
                      <button onClick={() => handleEdit(mailbox)} className="text-blue-600 hover:text-blue-900">Edit</button>
                      <button onClick={() => handleDelete(mailbox.mailbox_id)} className="text-red-600 hover:text-red-900">Archive</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {filteredMailboxes.length === 0 && (
              <tr>
                <td colSpan={13} className="px-6 py-8 text-center text-gray-500">
                  {hasActiveFilters ? 'No mailboxes match your filters.' : 'No mailboxes found. Click "Add Mailbox" to create one.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

      {/* Edit Mailbox Modal (existing flow for editing) */}
      {showAddModal && editingMailbox && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-bold mb-4">Edit Mailbox</h2>
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Identity */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email Address *</label>
                <input type="email" required value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="sender@example.com" />
              </div>

              {/* Section 1: Sender Profile */}
              <div className="border rounded-lg p-4">
                <h3 className="text-md font-semibold text-gray-800 mb-3">Sender Profile</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">First Name *</label>
                    <input type="text" required value={formData.sender_first_name} onChange={(e) => { const v = e.target.value; setFormData(f => ({ ...f, sender_first_name: v, display_name: [v, f.sender_last_name].filter(Boolean).join(' ') })) }} className="w-full px-3 py-2 border rounded-lg" placeholder="Brian" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Last Name *</label>
                    <input type="text" required value={formData.sender_last_name} onChange={(e) => { const v = e.target.value; setFormData(f => ({ ...f, sender_last_name: v, display_name: [f.sender_first_name, v].filter(Boolean).join(' ') })) }} className="w-full px-3 py-2 border rounded-lg" placeholder="Smith" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Phone Number *</label>
                    <input type="tel" required inputMode="tel" value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: formatUsPhone(e.target.value) })} className={`w-full px-3 py-2 border rounded-lg ${formData.phone && !isValidUsPhone(formData.phone) ? 'border-red-400' : ''}`} placeholder="(555) 123-4567" />
                    {formData.phone && !isValidUsPhone(formData.phone) && <p className="text-xs text-red-600 mt-1">Enter a valid US phone number.</p>}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Role *</label>
                    <div className="flex gap-2">
                      <select required value={formData.outreach_role_id ?? ''} onChange={(e) => setFormData({ ...formData, outreach_role_id: e.target.value ? parseInt(e.target.value) : null })} className="w-full px-3 py-2 border rounded-lg">
                        <option value="">— Select Role —</option>
                        {outreachRoles.map((r) => (<option key={r.role_id} value={r.role_id}>{r.role_name}</option>))}
                      </select>
                      <button type="button" onClick={() => { setEditingRole(null); setRoleFormData({ role_name: '', description: '', purpose: '' }); setShowRolesModal(true) }} className="px-3 py-2 border rounded-lg text-gray-600 hover:bg-gray-50 text-sm whitespace-nowrap" title="Manage Roles">Manage</button>
                    </div>
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block text-sm font-medium text-gray-700 mb-1">LinkedIn Profile URL</label>
                    <input type="url" value={formData.linkedin_url} onChange={(e) => setFormData({ ...formData, linkedin_url: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="https://linkedin.com/in/username" />
                  </div>
                </div>
                <div className="flex items-center mt-3">
                  <input type="checkbox" id="is_active" checked={formData.is_active} onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })} className="h-4 w-4 text-blue-600 border-gray-300 rounded" />
                  <label htmlFor="is_active" className="ml-2 text-sm text-gray-700">Active</label>
                </div>
                <div className="mt-3">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                  <textarea value={formData.notes} onChange={(e) => setFormData({ ...formData, notes: e.target.value })} className="w-full px-3 py-2 border rounded-lg" rows={2} placeholder="Optional notes..." />
                </div>
              </div>

              {/* Section 2: Email Signature */}
              <div className="border rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-md font-semibold text-gray-800">Email Signature</h3>
                  {!sigEditMode ? (
                    <button type="button" onClick={() => setSigEditMode(true)} className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1" title="Edit signature">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                      Edit
                    </button>
                  ) : (
                    <div className="flex gap-2">
                      <button type="button" onClick={handleSaveSignature} disabled={sigSaving} className="text-sm px-3 py-1 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">{sigSaving ? 'Saving…' : 'Save'}</button>
                      <button type="button" onClick={() => { setSigEditMode(false); if (editingMailbox) handleEdit(editingMailbox) }} className="text-sm px-3 py-1 border rounded-lg hover:bg-gray-50">Cancel</button>
                    </div>
                  )}
                </div>

                {sigEditMode && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Title / Role <span className="text-gray-400 font-normal">(from Role)</span></label>
                      <input type="text" readOnly value={roleDesc(formData.outreach_role_id)} className="w-full px-3 py-1.5 border rounded-lg text-sm bg-gray-50 text-gray-600" placeholder="Select a Role above" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Phone <span className="text-gray-400 font-normal">(from Sender Profile)</span></label>
                      <input type="text" readOnly value={formData.phone} className="w-full px-3 py-1.5 border rounded-lg text-sm bg-gray-50 text-gray-600" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Sender Name</label>
                      <input type="text" value={sigData.sender_name} onChange={(e) => setSigData({ ...sigData, sender_name: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="John Doe" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Signature Email</label>
                      <input type="email" value={sigData.email} onChange={(e) => setSigData({ ...sigData, email: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="john@company.com" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Company Name <span className="text-gray-400 font-normal">(from tenant)</span></label>
                      <input type="text" value={sigData.company} onChange={(e) => setSigData({ ...sigData, company: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="Your Company Inc." />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Website URL <span className="text-gray-400 font-normal">(from tenant)</span></label>
                      <input type="text" value={sigData.website} onChange={(e) => setSigData({ ...sigData, website: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="https://yourcompany.com" />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Address <span className="text-gray-400 font-normal">(from tenant)</span></label>
                      <input type="text" value={sigData.address} onChange={(e) => setSigData({ ...sigData, address: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="123 Business Ave, Suite 100, City, State 12345" />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Logo URL <span className="text-gray-400 font-normal">(from tenant)</span></label>
                      <input type="text" value={sigData.logo_url} onChange={(e) => setSigData({ ...sigData, logo_url: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="https://yourcompany.com/logo.png" />
                    </div>
                  </div>
                )}

                <label className="block text-xs font-medium text-gray-500 mb-1">Signature Preview (HTML)</label>
                <iframe title="Signature preview" sandbox="" srcDoc={buildSignatureHtml() || '<span style="color:#9ca3af;font-size:12px;font-family:Arial,sans-serif;">No signature content yet</span>'} className="w-full border rounded-lg bg-white" style={{ height: '150px' }} />
              </div>

              {/* Section 3: Outreach Profile */}
              <div className="border rounded-lg p-4">
                <h3 className="text-md font-semibold text-gray-800 mb-3">Outreach Profile</h3>
                <div className="space-y-4">
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
                      <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                        <p className="text-xs text-green-800"><strong>OAuth2 is recommended.</strong> Password changes won&apos;t break your connection. Tokens refresh automatically.</p>
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
                            {oauthConnecting ? 'Redirecting...' : 'Connect with Microsoft 365'}
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                  {(formData.provider === 'smtp' || formData.provider === 'other') && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Warmup Status</label>
                      <div className="w-full px-3 py-2 border rounded-lg bg-gray-50 text-gray-600" title={WARMUP_STATUS_LABELS[formData.warmup_status]?.tooltip || ''}>
                        <span className={`text-xs px-2 py-1 rounded-full ${WARMUP_STATUS_LABELS[formData.warmup_status]?.color || 'bg-gray-100'}`}>
                          {WARMUP_STATUS_LABELS[formData.warmup_status]?.label || formData.warmup_status}
                        </span>
                        <span className="text-xs text-gray-400 ml-2">Managed by warmup engine</span>
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Daily Send Limit</label>
                      <input type="number" min="1" max="100" value={formData.daily_send_limit} onChange={(e) => setFormData({ ...formData, daily_send_limit: parseInt(e.target.value) })} className="w-full px-3 py-2 border rounded-lg" />
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex justify-end space-x-3 pt-2">
                <button type="button" onClick={() => { setShowAddModal(false); setEditingMailbox(null); setSigEditMode(false) }} className="px-4 py-2 border rounded-lg hover:bg-gray-50">Cancel</button>
                <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Update Mailbox</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ===== Mailbox Detail Modal ===== */}
      {detailMailboxId !== null && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg w-full max-w-3xl max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b">
              <div>
                <h2 className="text-lg font-bold text-gray-900">
                  {detailData?.mailbox?.email || 'Mailbox Detail'}
                </h2>
                {detailData?.mailbox?.display_name && (
                  <p className="text-sm text-gray-500">{detailData.mailbox.display_name}</p>
                )}
              </div>
              <button onClick={() => { setDetailMailboxId(null); setDetailData(null) }} className="text-gray-400 hover:text-gray-600">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            {/* Tabs */}
            <div className="flex border-b px-6">
              {(['overview', 'campaigns', 'warmup', 'settings'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setDetailTab(tab)}
                  className={`px-4 py-3 text-sm font-medium border-b-2 -mb-px capitalize ${
                    detailTab === tab
                      ? 'border-blue-600 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Content */}
            <div className="px-6 py-5">
              {detailLoading ? (
                <div className="flex items-center justify-center h-48">
                  <div className="text-gray-500">Loading detail...</div>
                </div>
              ) : detailData ? (
                <>
                  {/* ── Tab: Overview ── */}
                  {detailTab === 'overview' && (() => {
                    const mb = detailData.mailbox
                    const os = detailData.outreach_stats
                    const health = mailboxHealthMap[mb.mailbox_id]
                    const quotaPct = mb.daily_send_limit > 0 ? Math.min(100, (mb.emails_sent_today / mb.daily_send_limit) * 100) : 0
                    const quotaColor = quotaPct >= 90 ? 'bg-red-500' : quotaPct >= 70 ? 'bg-yellow-500' : 'bg-green-500'
                    return (
                      <div className="space-y-5">
                        {/* Stat cards */}
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                          <div className="bg-blue-50 rounded-lg p-4">
                            <div className="text-2xl font-bold text-blue-700">{mb.outreach_emails_sent}</div>
                            <div className="text-xs text-blue-600 mt-1">Outreach Emails</div>
                          </div>
                          <div className="bg-purple-50 rounded-lg p-4">
                            <div className="text-2xl font-bold text-purple-700">{mb.warmup_emails_sent}</div>
                            <div className="text-xs text-purple-600 mt-1">Warmup Emails</div>
                          </div>
                          <div className="bg-green-50 rounded-lg p-4">
                            <div className="text-2xl font-bold text-green-700">
                              {os.sent > 0 ? ((os.replied / os.sent) * 100).toFixed(1) : '0.0'}%
                            </div>
                            <div className="text-xs text-green-600 mt-1">Reply Rate</div>
                          </div>
                        </div>

                        {/* Daily Quota */}
                        <div className="bg-white border rounded-lg p-4">
                          <div className="flex justify-between items-center mb-2">
                            <span className="text-sm font-medium text-gray-700">Daily Quota</span>
                            <span className="text-sm text-gray-500">{mb.emails_sent_today} / {mb.daily_send_limit}</span>
                          </div>
                          <div className="w-full bg-gray-200 rounded-full h-3">
                            <div className={`${quotaColor} h-3 rounded-full transition-all`} style={{ width: `${quotaPct}%` }} />
                          </div>
                        </div>

                        {/* Deliverability Health */}
                        {health && (
                          <div className="bg-white border rounded-lg p-4">
                            <h4 className="text-sm font-medium text-gray-700 mb-3">Deliverability Health</h4>
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                              <div>
                                <div className="text-lg font-bold text-gray-900">{health.health_score}</div>
                                <div className="text-xs text-gray-500">Health Score</div>
                              </div>
                              <div>
                                <div className={`text-lg font-bold ${health.bounce_rate_pct > 5 ? 'text-red-600' : 'text-gray-900'}`}>{health.bounce_rate_pct}%</div>
                                <div className="text-xs text-gray-500">Bounce Rate</div>
                              </div>
                              <div>
                                <div className={`text-lg font-bold ${health.complaint_rate_pct > 0.3 ? 'text-red-600' : 'text-gray-900'}`}>{health.complaint_rate_pct}%</div>
                                <div className="text-xs text-gray-500">Complaint Rate</div>
                              </div>
                              <div>
                                <div className="text-lg font-bold text-gray-900">{(health.engagement_rate * 100).toFixed(0)}%</div>
                                <div className="text-xs text-gray-500">Engagement</div>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Outreach Breakdown */}
                        <div className="bg-white border rounded-lg p-4">
                          <h4 className="text-sm font-medium text-gray-700 mb-3">Outreach Breakdown</h4>
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                            <div>
                              <div className="text-lg font-bold text-gray-900">{os.sent}</div>
                              <div className="text-xs text-gray-500">Sent</div>
                            </div>
                            <div>
                              <div className="text-lg font-bold text-green-600">{os.replied}</div>
                              <div className="text-xs text-gray-500">Replied</div>
                            </div>
                            <div>
                              <div className="text-lg font-bold text-red-600">{os.bounced}</div>
                              <div className="text-xs text-gray-500">Bounced</div>
                            </div>
                            <div>
                              <div className="text-lg font-bold text-gray-400">{os.skipped}</div>
                              <div className="text-xs text-gray-500">Skipped</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )
                  })()}

                  {/* ── Tab: Campaigns ── */}
                  {detailTab === 'campaigns' && (
                    <div className="space-y-3">
                      {detailData.campaigns.length === 0 ? (
                        <div className="text-center py-12 text-gray-500">No campaigns using this mailbox yet</div>
                      ) : (
                        detailData.campaigns.map((c: any) => {
                          const statusColors: Record<string, string> = {
                            active: 'bg-green-100 text-green-800',
                            draft: 'bg-gray-100 text-gray-600',
                            paused: 'bg-yellow-100 text-yellow-800',
                            completed: 'bg-blue-100 text-blue-800',
                            archived: 'bg-gray-100 text-gray-500',
                          }
                          return (
                            <div
                              key={c.campaign_id}
                              className="border rounded-lg p-4 hover:bg-blue-50 hover:border-blue-200 cursor-pointer transition-colors"
                              onClick={() => router.push(`/dashboard/campaigns?campaign_id=${c.campaign_id}`)}
                            >
                              <div className="flex items-center justify-between">
                                <div>
                                  <div className="font-medium text-gray-900 hover:text-blue-700">{c.name}</div>
                                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium mt-1 ${statusColors[c.status] || 'bg-gray-100'}`}>
                                    {c.status}
                                  </span>
                                </div>
                                <div className="flex items-center gap-4">
                                  <div className="text-right text-sm">
                                    <div className="text-gray-900">{c.total_sent} sent</div>
                                    <div className="text-green-600">{c.total_replied} replied</div>
                                  </div>
                                  <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                                </div>
                              </div>
                            </div>
                          )
                        })
                      )}
                    </div>
                  )}

                  {/* ── Tab: Warmup ── */}
                  {detailTab === 'warmup' && (() => {
                    const mb = detailData.mailbox
                    return (
                      <div className="space-y-4">
                        {/* Warmup summary */}
                        <div className="bg-white border rounded-lg p-4">
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                            <div>
                              <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${WARMUP_STATUS_LABELS[mb.warmup_status]?.color || 'bg-gray-100'}`}>
                                {WARMUP_STATUS_LABELS[mb.warmup_status]?.label || mb.warmup_status}
                              </span>
                              <div className="text-xs text-gray-500 mt-1">Status</div>
                            </div>
                            <div>
                              <div className="text-lg font-bold text-gray-900">{mb.warmup_days_completed}</div>
                              <div className="text-xs text-gray-500">Days Done</div>
                            </div>
                            <div>
                              <div className="text-sm font-medium text-gray-900">{mb.warmup_started_at ? new Date(mb.warmup_started_at).toLocaleDateString() : '-'}</div>
                              <div className="text-xs text-gray-500">Started</div>
                            </div>
                            <div>
                              <div className="text-sm font-medium text-gray-900">{mb.warmup_completed_at ? new Date(mb.warmup_completed_at).toLocaleDateString() : '-'}</div>
                              <div className="text-xs text-gray-500">Completed</div>
                            </div>
                          </div>
                        </div>

                        {/* Daily log table */}
                        {detailData.warmup_logs.length === 0 ? (
                          <div className="text-center py-8 text-gray-500">No warmup logs in the last 30 days</div>
                        ) : (
                          <div className="border rounded-lg overflow-hidden">
                            <table className="min-w-full text-xs">
                              <thead className="bg-gray-50">
                                <tr>
                                  <th className="px-3 py-2 text-left font-medium text-gray-600">Date</th>
                                  <th className="px-3 py-2 text-left font-medium text-gray-600">Day</th>
                                  <th className="px-3 py-2 text-left font-medium text-gray-600">Phase</th>
                                  <th className="px-3 py-2 text-left font-medium text-gray-600">Sent</th>
                                  <th className="px-3 py-2 text-left font-medium text-gray-600">Received</th>
                                  <th className="px-3 py-2 text-left font-medium text-gray-600">Opens</th>
                                  <th className="px-3 py-2 text-left font-medium text-gray-600">Replies</th>
                                  <th className="px-3 py-2 text-left font-medium text-gray-600">Bounces</th>
                                  <th className="px-3 py-2 text-left font-medium text-gray-600">Health</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gray-100">
                                {detailData.warmup_logs.map((log: any, i: number) => (
                                  <tr key={i} className="hover:bg-gray-50">
                                    <td className="px-3 py-2 text-gray-800">{log.log_date}</td>
                                    <td className="px-3 py-2 text-gray-600">{log.warmup_day}</td>
                                    <td className="px-3 py-2 text-gray-600">{log.phase}</td>
                                    <td className="px-3 py-2 text-gray-800">{log.emails_sent}</td>
                                    <td className="px-3 py-2 text-gray-600">{log.emails_received}</td>
                                    <td className="px-3 py-2 text-gray-600">{log.opens}</td>
                                    <td className="px-3 py-2 text-green-600">{log.replies}</td>
                                    <td className="px-3 py-2 text-red-600">{log.bounces}</td>
                                    <td className="px-3 py-2">
                                      <span className={`font-medium ${log.health_score >= 80 ? 'text-green-600' : log.health_score >= 60 ? 'text-yellow-600' : 'text-red-600'}`}>
                                        {log.health_score}
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    )
                  })()}

                  {/* ── Tab: Settings (read-only) ── */}
                  {detailTab === 'settings' && (() => {
                    const mb = detailData.mailbox
                    let sigPreview: any = null
                    if (mb.email_signature_json) {
                      try { sigPreview = JSON.parse(mb.email_signature_json) } catch {}
                    }
                    return (
                      <div className="space-y-4">
                        {/* Connection */}
                        <div className="bg-white border rounded-lg p-4">
                          <h4 className="text-sm font-medium text-gray-700 mb-3">Connection</h4>
                          <div className="grid grid-cols-2 gap-y-2 text-sm">
                            <div className="text-gray-500">Provider</div>
                            <div className="text-gray-900">{PROVIDER_LABELS[mb.provider] || mb.provider}</div>
                            <div className="text-gray-500">Auth Method</div>
                            <div className="text-gray-900">{mb.auth_method === 'oauth2' ? 'OAuth2' : 'Password'}{mb.oauth_connected ? ' (Connected)' : ''}</div>
                            <div className="text-gray-500">SMTP</div>
                            <div className="text-gray-900 font-mono text-xs">{mb.smtp_host || '-'}:{mb.smtp_port}</div>
                            <div className="text-gray-500">IMAP</div>
                            <div className="text-gray-900 font-mono text-xs">{mb.imap_host || '-'}:{mb.imap_port}</div>
                            <div className="text-gray-500">Daily Limit</div>
                            <div className="text-gray-900">{mb.daily_send_limit}</div>
                            <div className="text-gray-500">Connection Status</div>
                            <div>
                              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                                mb.connection_status === 'successful' ? 'bg-green-100 text-green-800' :
                                mb.connection_status === 'failed' ? 'bg-red-100 text-red-800' :
                                'bg-gray-100 text-gray-500'
                              }`}>
                                {mb.connection_status || 'untested'}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Email Signature */}
                        {sigPreview && Object.values(sigPreview).some((v: any) => v) && (
                          <div className="bg-white border rounded-lg p-4">
                            <h4 className="text-sm font-medium text-gray-700 mb-3">Email Signature</h4>
                            <div className="border rounded-lg p-3 bg-gray-50">
                              <div style={{ borderTop: '1px solid #cccccc', paddingTop: '10px', fontFamily: 'Arial, sans-serif' }}>
                                {sigPreview.sender_name && <div style={{ fontSize: '14px', fontWeight: 'bold', color: '#333333' }}>{sigPreview.sender_name}</div>}
                                {sigPreview.title && <div style={{ fontSize: '13px', color: '#555555' }}>{sigPreview.title}</div>}
                                {sigPreview.company && <div style={{ fontSize: '13px', color: '#555555' }}>{sigPreview.company}</div>}
                                {(sigPreview.phone || sigPreview.email) && (
                                  <div style={{ fontSize: '12px', color: '#666666' }}>{[sigPreview.phone, sigPreview.email].filter(Boolean).join(' | ')}</div>
                                )}
                                {sigPreview.website && <div style={{ fontSize: '12px' }}><span style={{ color: '#0066cc' }}>{sigPreview.website}</span></div>}
                                {sigPreview.address && <div style={{ fontSize: '12px', color: '#666666' }}>{sigPreview.address}</div>}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Notes */}
                        {mb.notes && (
                          <div className="bg-white border rounded-lg p-4">
                            <h4 className="text-sm font-medium text-gray-700 mb-2">Notes</h4>
                            <p className="text-sm text-gray-600">{mb.notes}</p>
                          </div>
                        )}

                        {/* Metadata */}
                        <div className="bg-white border rounded-lg p-4">
                          <h4 className="text-sm font-medium text-gray-700 mb-3">Metadata</h4>
                          <div className="grid grid-cols-2 gap-y-2 text-sm">
                            <div className="text-gray-500">Mailbox ID</div>
                            <div className="text-gray-900 font-mono">{mb.mailbox_id}</div>
                            <div className="text-gray-500">Created</div>
                            <div className="text-gray-900">{new Date(mb.created_at).toLocaleString()}</div>
                            <div className="text-gray-500">Updated</div>
                            <div className="text-gray-900">{new Date(mb.updated_at).toLocaleString()}</div>
                            <div className="text-gray-500">Last Sent</div>
                            <div className="text-gray-900">{mb.last_sent_at ? new Date(mb.last_sent_at).toLocaleString() : 'Never'}</div>
                          </div>
                        </div>
                      </div>
                    )
                  })()}
                </>
              ) : null}
            </div>
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
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
                        <p>Enter a name (e.g., &quot;NeuraLeads&quot;) and click <strong>Create</strong></p>
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
                    <p className="text-sm text-blue-800">App Passwords let NeuraLeads AI Agent send and receive emails on your behalf without sharing your main Google password. Your credentials are encrypted and stored securely.</p>
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
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
                      <input type="text" value={formData.sender_first_name} onChange={(e) => { const v = e.target.value; setFormData(f => ({ ...f, sender_first_name: v, display_name: [v, f.sender_last_name].filter(Boolean).join(' ') })) }} className="w-full px-3 py-2 border rounded-lg" placeholder="Brian" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                      <input type="text" value={formData.sender_last_name} onChange={(e) => { const v = e.target.value; setFormData(f => ({ ...f, sender_last_name: v, display_name: [f.sender_first_name, v].filter(Boolean).join(' ') })) }} className="w-full px-3 py-2 border rounded-lg" placeholder="Smith" />
                    </div>
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

                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-2">
                    <p className="text-sm text-blue-800 font-medium">Why OAuth2?</p>
                    <ul className="text-sm text-blue-800 space-y-1 ml-4 list-disc">
                      <li><strong>Password-independent</strong> &mdash; changing your M365 password won&apos;t disconnect your mailbox</li>
                      <li><strong>More secure</strong> &mdash; no passwords stored, uses auto-refreshing tokens</li>
                      <li><strong>M365 compliant</strong> &mdash; works even when Microsoft blocks Basic Auth</li>
                      <li><strong>One-click setup</strong> &mdash; sign in once, stay connected indefinitely</li>
                    </ul>
                    <p className="text-xs text-blue-600 mt-1">You&apos;ll be redirected to Microsoft to sign in. No passwords are stored on our server.</p>
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
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
                      <input type="text" value={formData.sender_first_name} onChange={(e) => { const v = e.target.value; setFormData(f => ({ ...f, sender_first_name: v, display_name: [v, f.sender_last_name].filter(Boolean).join(' ') })) }} className="w-full px-3 py-2 border rounded-lg" placeholder="Brian" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                      <input type="text" value={formData.sender_last_name} onChange={(e) => { const v = e.target.value; setFormData(f => ({ ...f, sender_last_name: v, display_name: [f.sender_first_name, v].filter(Boolean).join(' ') })) }} className="w-full px-3 py-2 border rounded-lg" placeholder="Smith" />
                    </div>
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
                            sender_first_name: formData.sender_first_name || undefined,
                            sender_last_name: formData.sender_last_name || undefined,
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
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="col-span-2 md:col-span-1">
                      <h4 className="text-sm font-semibold text-gray-800 mb-3">Account</h4>
                      <div className="space-y-3">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Email Address *</label>
                          <input type="email" required value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="user@example.com" />
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
                            <input type="text" value={formData.sender_first_name} onChange={(e) => { const v = e.target.value; setFormData(f => ({ ...f, sender_first_name: v, display_name: [v, f.sender_last_name].filter(Boolean).join(' ') })) }} className="w-full px-3 py-2 border rounded-lg" placeholder="Brian" />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                            <input type="text" value={formData.sender_last_name} onChange={(e) => { const v = e.target.value; setFormData(f => ({ ...f, sender_last_name: v, display_name: [f.sender_first_name, v].filter(Boolean).join(' ') })) }} className="w-full px-3 py-2 border rounded-lg" placeholder="Smith" />
                          </div>
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
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                          <div className="col-span-2">
                            <label className="block text-sm font-medium text-gray-700 mb-1">IMAP Host *</label>
                            <input type="text" required value={formData.imap_host} onChange={(e) => setFormData({ ...formData, imap_host: e.target.value })} className="w-full px-3 py-2 border rounded-lg" placeholder="imap.example.com" />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">IMAP Port *</label>
                            <input type="number" required value={formData.imap_port} onChange={(e) => setFormData({ ...formData, imap_port: parseInt(e.target.value) || 993 })} className="w-full px-3 py-2 border rounded-lg" />
                          </div>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
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

                  {/* Section 1: Sender Profile */}
                  <div className="border rounded-lg p-4">
                    <h3 className="text-md font-semibold text-gray-800 mb-3">Sender Profile</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">First Name *</label>
                        <input type="text" required value={formData.sender_first_name} onChange={(e) => { const v = e.target.value; setFormData(f => ({ ...f, sender_first_name: v, display_name: [v, f.sender_last_name].filter(Boolean).join(' ') })) }} className="w-full px-3 py-2 border rounded-lg" placeholder="Brian" />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Last Name *</label>
                        <input type="text" required value={formData.sender_last_name} onChange={(e) => { const v = e.target.value; setFormData(f => ({ ...f, sender_last_name: v, display_name: [f.sender_first_name, v].filter(Boolean).join(' ') })) }} className="w-full px-3 py-2 border rounded-lg" placeholder="Smith" />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Phone Number *</label>
                        <input type="tel" required inputMode="tel" value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: formatUsPhone(e.target.value) })} className={`w-full px-3 py-2 border rounded-lg ${formData.phone && !isValidUsPhone(formData.phone) ? 'border-red-400' : ''}`} placeholder="(555) 123-4567" />
                        {formData.phone && !isValidUsPhone(formData.phone) && <p className="text-xs text-red-600 mt-1">Enter a valid US phone number.</p>}
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Role *</label>
                        <div className="flex gap-2">
                          <select required value={formData.outreach_role_id ?? ''} onChange={(e) => setFormData({ ...formData, outreach_role_id: e.target.value ? parseInt(e.target.value) : null })} className="w-full px-3 py-2 border rounded-lg">
                            <option value="">— Select Role —</option>
                            {outreachRoles.map((r) => (<option key={r.role_id} value={r.role_id}>{r.role_name}</option>))}
                          </select>
                          <button type="button" onClick={() => { setEditingRole(null); setRoleFormData({ role_name: '', description: '', purpose: '' }); setShowRolesModal(true) }} className="px-3 py-2 border rounded-lg text-gray-600 hover:bg-gray-50 text-sm whitespace-nowrap" title="Manage Roles">Manage</button>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center mt-3">
                      <input type="checkbox" id="wizard_is_active" checked={formData.is_active} onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })} className="h-4 w-4 text-blue-600 border-gray-300 rounded" />
                      <label htmlFor="wizard_is_active" className="ml-2 text-sm text-gray-700">Active</label>
                    </div>
                    <div className="mt-3">
                      <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                      <textarea value={formData.notes} onChange={(e) => setFormData({ ...formData, notes: e.target.value })} className="w-full px-3 py-2 border rounded-lg" rows={2} placeholder="Optional notes..." />
                    </div>
                  </div>

                  {/* Section 2: Email Signature */}
                  <div className="border rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-md font-semibold text-gray-800">Email Signature</h3>
                      {!sigEditMode ? (
                        <button type="button" onClick={() => setSigEditMode(true)} className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1" title="Edit signature">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                          Edit
                        </button>
                      ) : (
                        <div className="flex gap-2">
                          <button type="button" onClick={handleSaveSignature} disabled={sigSaving} className="text-sm px-3 py-1 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">{sigSaving ? 'Saving…' : 'Save'}</button>
                          <button type="button" onClick={() => setSigEditMode(false)} className="text-sm px-3 py-1 border rounded-lg hover:bg-gray-50">Done</button>
                        </div>
                      )}
                    </div>
                    {sigEditMode && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">Title / Role <span className="text-gray-400 font-normal">(from Role)</span></label>
                          <input type="text" readOnly value={roleDesc(formData.outreach_role_id)} className="w-full px-3 py-1.5 border rounded-lg text-sm bg-gray-50 text-gray-600" placeholder="Select a Role above" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">Phone <span className="text-gray-400 font-normal">(from Sender Profile)</span></label>
                          <input type="text" readOnly value={formData.phone} className="w-full px-3 py-1.5 border rounded-lg text-sm bg-gray-50 text-gray-600" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">Sender Name</label>
                          <input type="text" value={sigData.sender_name} onChange={(e) => setSigData({ ...sigData, sender_name: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="John Doe" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">Signature Email</label>
                          <input type="email" value={sigData.email} onChange={(e) => setSigData({ ...sigData, email: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="john@company.com" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">Company Name <span className="text-gray-400 font-normal">(from tenant)</span></label>
                          <input type="text" value={sigData.company} onChange={(e) => setSigData({ ...sigData, company: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="Your Company Inc." />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">Website URL <span className="text-gray-400 font-normal">(from tenant)</span></label>
                          <input type="text" value={sigData.website} onChange={(e) => setSigData({ ...sigData, website: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="https://yourcompany.com" />
                        </div>
                        <div className="sm:col-span-2">
                          <label className="block text-xs font-medium text-gray-600 mb-1">Address <span className="text-gray-400 font-normal">(from tenant)</span></label>
                          <input type="text" value={sigData.address} onChange={(e) => setSigData({ ...sigData, address: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="123 Business Ave, Suite 100, City, State 12345" />
                        </div>
                        <div className="sm:col-span-2">
                          <label className="block text-xs font-medium text-gray-600 mb-1">Logo URL <span className="text-gray-400 font-normal">(from tenant)</span></label>
                          <input type="text" value={sigData.logo_url} onChange={(e) => setSigData({ ...sigData, logo_url: e.target.value })} className="w-full px-3 py-1.5 border rounded-lg text-sm" placeholder="https://yourcompany.com/logo.png" />
                        </div>
                      </div>
                    )}
                    <label className="block text-xs font-medium text-gray-500 mb-1">Signature Preview (HTML)</label>
                    <iframe title="Signature preview" sandbox="" srcDoc={buildSignatureHtml() || '<span style="color:#9ca3af;font-size:12px;font-family:Arial,sans-serif;">No signature content yet</span>'} className="w-full border rounded-lg bg-white" style={{ height: '150px' }} />
                  </div>

                  {/* Section 3: Outreach Profile */}
                  <div className="border rounded-lg p-4">
                    <h3 className="text-md font-semibold text-gray-800 mb-3">Outreach Profile</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Warmup Status</label>
                        <div className="w-full px-3 py-2 border rounded-lg bg-gray-50 text-gray-600">
                          <span className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-700">Inactive</span>
                          <span className="text-xs text-gray-400 ml-2">Auto-starts after connection</span>
                        </div>
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Daily Send Limit</label>
                        <input type="number" min="1" max="100" value={formData.daily_send_limit} onChange={(e) => setFormData({ ...formData, daily_send_limit: parseInt(e.target.value) })} className="w-full px-3 py-2 border rounded-lg" />
                      </div>
                    </div>
                  </div>

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

      {/* Manage Roles Modal */}
      {showRolesModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowRolesModal(false)}>
          <div className="bg-white rounded-lg p-6 max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold text-gray-900">Manage Outreach Roles</h2>
              <button onClick={() => setShowRolesModal(false)} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
            </div>

            {/* Existing Roles */}
            <div className="space-y-2 mb-6">
              {outreachRoles.length === 0 && <p className="text-sm text-gray-500">No roles defined yet.</p>}
              {outreachRoles.map((role) => (
                <div key={role.role_id} className="flex items-center justify-between p-3 border rounded-lg">
                  <div>
                    <div className="font-medium text-gray-900 flex items-center gap-2">
                      {role.role_name}
                      {role.is_system && <span className="text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded">System</span>}
                    </div>
                    {role.description && <div className="text-xs text-gray-500"><span className="font-medium">Description:</span> {role.description}</div>}
                    {role.purpose && <div className="text-xs text-gray-500"><span className="font-medium">Purpose:</span> {role.purpose}</div>}
                    <div className="text-xs text-gray-400 mt-0.5">{role.mailbox_count} mailbox{role.mailbox_count !== 1 ? 'es' : ''}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => { setEditingRole(role); setRoleFormData({ role_name: role.role_name, description: role.description || '', purpose: role.purpose || '' }) }}
                      className="text-xs px-2 py-1 text-blue-600 hover:bg-blue-50 rounded"
                    >
                      Edit
                    </button>
                    {!role.is_system && (
                      <button
                        onClick={async () => {
                          if (!confirm(`Delete role "${role.role_name}"? Mailboxes using this role will be unassigned.`)) return
                          try {
                            await outreachRolesApi.delete(role.role_id)
                            toast('success', `Role "${role.role_name}" deleted`)
                            fetchData()
                          } catch (err: any) {
                            toast('error', err.response?.data?.detail || 'Failed to delete role')
                          }
                        }}
                        className="text-xs px-2 py-1 text-red-600 hover:bg-red-50 rounded"
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Add / Edit Form */}
            <div className="border-t pt-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">{editingRole ? 'Edit Role' : 'Add New Role'}</h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Role / Title <span className="text-red-500">*</span></label>
                  <input
                    type="text"
                    value={roleFormData.role_name}
                    onChange={(e) => setRoleFormData({ ...roleFormData, role_name: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg text-sm"
                    placeholder="e.g. Account Executive"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
                  <input
                    type="text"
                    value={roleFormData.description}
                    onChange={(e) => setRoleFormData({ ...roleFormData, description: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg text-sm"
                    placeholder="Shown as the Title / Role in the email signature"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Purpose</label>
                  <textarea
                    value={roleFormData.purpose}
                    onChange={(e) => setRoleFormData({ ...roleFormData, purpose: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg text-sm"
                    rows={2}
                    placeholder="What this role is used for (e.g. sources candidates for open roles)"
                  />
                </div>
                <div className="flex justify-end gap-2">
                  {editingRole && (
                    <button
                      onClick={() => { setEditingRole(null); setRoleFormData({ role_name: '', description: '', purpose: '' }) }}
                      className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 border rounded-lg"
                    >
                      Cancel
                    </button>
                  )}
                  <button
                    disabled={!roleFormData.role_name.trim() || roleSaving}
                    onClick={async () => {
                      setRoleSaving(true)
                      try {
                        if (editingRole) {
                          await outreachRolesApi.update(editingRole.role_id, roleFormData)
                          toast('success', 'Role updated')
                        } else {
                          await outreachRolesApi.create(roleFormData)
                          toast('success', 'Role created')
                        }
                        setEditingRole(null)
                        setRoleFormData({ role_name: '', description: '', purpose: '' })
                        fetchData()
                      } catch (err: any) {
                        toast('error', err.response?.data?.detail || 'Failed to save role')
                      } finally {
                        setRoleSaving(false)
                      }
                    }}
                    className="px-4 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {roleSaving ? 'Saving...' : editingRole ? 'Update Role' : 'Add Role'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
