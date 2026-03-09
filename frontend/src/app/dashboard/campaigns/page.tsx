'use client'

import { useState, useEffect, useCallback } from 'react'
import { campaignsApi, contactsApi, leadsApi, mailboxesApi } from '@/lib/api'
import type { Campaign, SequenceStep, CampaignContact } from '@/types/api'
import {
  Plus, Search, MoreVertical, Play, Pause, Copy, Trash2, ChevronDown, ChevronRight,
  Mail, Clock, GitBranch, ArrowUp, ArrowDown, X, Zap, Users, BarChart3, Eye, Settings,
} from 'lucide-react'

type TabView = 'list' | 'detail'

interface StepFormData {
  step_type: 'email' | 'wait' | 'condition'
  subject: string
  body_html: string
  delay_days: number
  delay_hours: number
  reply_to_thread: boolean
  condition_type: string
  condition_window_hours: number
  variants_json: string
}

const defaultStep: StepFormData = {
  step_type: 'email',
  subject: '',
  body_html: '',
  delay_days: 1,
  delay_hours: 0,
  reply_to_thread: true,
  condition_type: '',
  condition_window_hours: 24,
  variants_json: '',
}

const statusColors: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  active: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  paused: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  completed: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  archived: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
}

export default function CampaignsPage() {
  const [view, setView] = useState<TabView>('list')
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)

  // Detail view state
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null)
  const [steps, setSteps] = useState<SequenceStep[]>([])
  const [contacts, setContacts] = useState<CampaignContact[]>([])
  const [detailTab, setDetailTab] = useState<'sequence' | 'contacts' | 'analytics' | 'rules'>('sequence')

  // Create/edit modals
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showStepModal, setShowStepModal] = useState(false)
  const [showEnrollModal, setShowEnrollModal] = useState(false)
  const [editingStep, setEditingStep] = useState<SequenceStep | null>(null)
  const [stepForm, setStepForm] = useState<StepFormData>(defaultStep)
  const [campaignForm, setCampaignForm] = useState({
    name: '', description: '', timezone: 'US/Eastern',
    send_window_start: '09:00', send_window_end: '17:00',
    send_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
    daily_limit: 30,
  })
  const [actionMenu, setActionMenu] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [analytics, setAnalytics] = useState<any>(null)

  // Auto-enrollment rules state
  const [enrollmentRules, setEnrollmentRules] = useState({
    enabled: false,
    validation_status: ['Valid'],
    priority_levels: [] as string[],
    states: [] as string[],
    job_title_keywords: [] as string[],
    sources: [] as string[],
    min_lead_score: null as number | null,
    max_per_run: 50,
    daily_cap: 200,
  })
  const [rulesPreviewCount, setRulesPreviewCount] = useState<number | null>(null)
  const [rulesSaving, setRulesSaving] = useState(false)
  const [rulesMessage, setRulesMessage] = useState<string | null>(null)

  // Enroll state — lead-based
  const [enrollLeads, setEnrollLeads] = useState<any[]>([])
  const [enrollLeadsLoading, setEnrollLeadsLoading] = useState(false)
  const [enrollLeadSearch, setEnrollLeadSearch] = useState('')
  const [enrollLeadPage, setEnrollLeadPage] = useState(1)
  const [enrollLeadPages, setEnrollLeadPages] = useState(1)
  const [expandedLeadIds, setExpandedLeadIds] = useState<Set<number>>(new Set())
  const [leadContacts, setLeadContacts] = useState<Record<number, any[]>>({})
  const [loadingLeadContacts, setLoadingLeadContacts] = useState<Set<number>>(new Set())
  const [selectedContactIds, setSelectedContactIds] = useState<number[]>([])
  const [selectedLeadIds, setSelectedLeadIds] = useState<Set<number>>(new Set())
  const [enrollSearchTimeout, setEnrollSearchTimeout] = useState<NodeJS.Timeout | null>(null)

  const [mailboxes, setMailboxes] = useState<any[]>([])
  const [selectedMailboxIds, setSelectedMailboxIds] = useState<number[]>([])

  const fetchCampaigns = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page, page_size: 20 }
      if (search) params.search = search
      if (statusFilter) params.status = statusFilter
      const data = await campaignsApi.list(params)
      setCampaigns(data.items || [])
      setTotalPages(data.pages || 1)
    } catch {
      setCampaigns([])
    } finally {
      setLoading(false)
    }
  }, [page, search, statusFilter])

  useEffect(() => { fetchCampaigns() }, [fetchCampaigns])

  const openDetail = async (campaign: Campaign) => {
    setSelectedCampaign(campaign)
    setView('detail')
    setDetailTab('sequence')
    try {
      const [stepsData, contactsData] = await Promise.all([
        campaignsApi.listSteps(campaign.campaign_id),
        campaignsApi.listContacts(campaign.campaign_id, { page: 1, page_size: 100 }),
      ])
      setSteps(stepsData || [])
      setContacts(contactsData?.items || [])
      // Load enrollment rules
      const fullCampaign = await campaignsApi.get(campaign.campaign_id)
      setSelectedCampaign(fullCampaign)
      if (fullCampaign.enrollment_rules) {
        setEnrollmentRules({
          enabled: fullCampaign.enrollment_rules.enabled || false,
          validation_status: fullCampaign.enrollment_rules.validation_status || ['Valid'],
          priority_levels: fullCampaign.enrollment_rules.priority_levels || [],
          states: fullCampaign.enrollment_rules.states || [],
          job_title_keywords: fullCampaign.enrollment_rules.job_title_keywords || [],
          sources: fullCampaign.enrollment_rules.sources || [],
          min_lead_score: fullCampaign.enrollment_rules.min_lead_score ?? null,
          max_per_run: fullCampaign.enrollment_rules.max_per_run || 50,
          daily_cap: fullCampaign.enrollment_rules.daily_cap || 200,
        })
      } else {
        setEnrollmentRules({
          enabled: false, validation_status: ['Valid'], priority_levels: [], states: [],
          job_title_keywords: [], sources: [], min_lead_score: null, max_per_run: 50, daily_cap: 200,
        })
      }
      setRulesPreviewCount(null)
      setRulesMessage(null)
    } catch { /* ignore */ }
  }

  const loadAnalytics = async (id: number) => {
    try {
      const data = await campaignsApi.analytics(id)
      setAnalytics(data)
    } catch { setAnalytics(null) }
  }

  const handleCreate = async () => {
    setSaving(true)
    try {
      const payload = {
        ...campaignForm,
        mailbox_ids: selectedMailboxIds,
      }
      const created = await campaignsApi.create(payload)
      setShowCreateModal(false)
      setCampaignForm({ name: '', description: '', timezone: 'US/Eastern', send_window_start: '09:00', send_window_end: '17:00', send_days: ['mon','tue','wed','thu','fri'], daily_limit: 30 })
      setSelectedMailboxIds([])
      await fetchCampaigns()
      openDetail(created)
    } catch { /* ignore */ }
    setSaving(false)
  }

  const handleAction = async (action: string, id: number) => {
    setActionMenu(null)
    try {
      if (action === 'activate') await campaignsApi.activate(id)
      else if (action === 'pause') await campaignsApi.pause(id)
      else if (action === 'resume') await campaignsApi.resume(id)
      else if (action === 'duplicate') await campaignsApi.duplicate(id)
      else if (action === 'delete') await campaignsApi.delete(id)
      fetchCampaigns()
      if (selectedCampaign?.campaign_id === id) {
        const updated = await campaignsApi.get(id)
        setSelectedCampaign(updated)
      }
    } catch { /* ignore */ }
  }

  const handleAddStep = async () => {
    if (!selectedCampaign) return
    setSaving(true)
    try {
      if (editingStep) {
        await campaignsApi.updateStep(selectedCampaign.campaign_id, editingStep.step_id, stepForm)
      } else {
        await campaignsApi.addStep(selectedCampaign.campaign_id, { ...stepForm, step_order: steps.length + 1 })
      }
      const updated = await campaignsApi.listSteps(selectedCampaign.campaign_id)
      setSteps(updated || [])
      setShowStepModal(false)
      setEditingStep(null)
      setStepForm(defaultStep)
    } catch { /* ignore */ }
    setSaving(false)
  }

  const handleDeleteStep = async (stepId: number) => {
    if (!selectedCampaign) return
    try {
      await campaignsApi.deleteStep(selectedCampaign.campaign_id, stepId)
      const updated = await campaignsApi.listSteps(selectedCampaign.campaign_id)
      setSteps(updated || [])
    } catch { /* ignore */ }
  }

  const handleEnroll = async () => {
    if (!selectedCampaign || selectedContactIds.length === 0) return
    setSaving(true)
    try {
      await campaignsApi.enrollContacts(selectedCampaign.campaign_id, selectedContactIds)
      const data = await campaignsApi.listContacts(selectedCampaign.campaign_id, { page: 1, page_size: 100 })
      setContacts(data?.items || [])
      setShowEnrollModal(false)
      setSelectedContactIds([])
    } catch { /* ignore */ }
    setSaving(false)
  }

  const fetchEnrollLeads = async (searchVal: string, pageVal: number) => {
    setEnrollLeadsLoading(true)
    try {
      const params: Record<string, any> = { page: pageVal, page_size: 30 }
      if (searchVal) params.search = searchVal
      const data = await leadsApi.listWithContactCounts(params)
      setEnrollLeads(data?.items || [])
      setEnrollLeadPages(data?.pages || 1)
    } catch { setEnrollLeads([]) }
    setEnrollLeadsLoading(false)
  }

  const openEnrollModal = async () => {
    setShowEnrollModal(true)
    setEnrollLeadSearch('')
    setEnrollLeadPage(1)
    setSelectedContactIds([])
    setSelectedLeadIds(new Set())
    setExpandedLeadIds(new Set())
    setLeadContacts({})
    fetchEnrollLeads('', 1)
  }

  const fetchLeadContacts = async (leadId: number): Promise<any[]> => {
    if (leadContacts[leadId]) return leadContacts[leadId]
    setLoadingLeadContacts(s => new Set(s).add(leadId))
    try {
      const data = await contactsApi.list({ lead_id: leadId, page: 1, page_size: 100 })
      const items = data?.items || []
      setLeadContacts(prev => ({ ...prev, [leadId]: items }))
      return items
    } catch {
      setLeadContacts(prev => ({ ...prev, [leadId]: [] }))
      return []
    } finally {
      setLoadingLeadContacts(s => { const n = new Set(s); n.delete(leadId); return n })
    }
  }

  const toggleLeadExpand = async (leadId: number) => {
    const next = new Set(expandedLeadIds)
    if (next.has(leadId)) {
      next.delete(leadId)
      setExpandedLeadIds(next)
      return
    }
    next.add(leadId)
    setExpandedLeadIds(next)
    await fetchLeadContacts(leadId)
  }

  const toggleLeadCheckbox = async (leadId: number) => {
    const isSelected = selectedLeadIds.has(leadId)
    const nextLeads = new Set(selectedLeadIds)
    if (isSelected) {
      // Uncheck lead — remove all its contacts from selection
      nextLeads.delete(leadId)
      setSelectedLeadIds(nextLeads)
      const contacts = leadContacts[leadId] || []
      const contactIds = contacts.filter(isContactEnrollable).map((c: any) => c.contact_id)
      setSelectedContactIds(ids => ids.filter(id => !contactIds.includes(id)))
    } else {
      // Check lead — fetch contacts if needed, select all eligible, expand
      nextLeads.add(leadId)
      setSelectedLeadIds(nextLeads)
      const contacts = await fetchLeadContacts(leadId)
      const enrollableIds = contacts.filter(isContactEnrollable).map((c: any) => c.contact_id)
      setSelectedContactIds(ids => Array.from(new Set([...ids, ...enrollableIds])))
      setExpandedLeadIds(prev => new Set(prev).add(leadId))
    }
  }

  const isContactEnrollable = (c: any) => {
    return !c.is_archived && c.outreach_status !== 'unsubscribed' && c.validation_status === 'valid'
  }

  const getContactStatusBadge = (c: any) => {
    if (c.is_archived) return { label: 'Archived', cls: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400' }
    if (c.outreach_status === 'unsubscribed') return { label: 'Unsubscribed', cls: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300' }
    if (c.validation_status === 'valid') return { label: 'Valid', cls: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300' }
    if (c.validation_status === 'invalid') return { label: 'Invalid Email', cls: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300' }
    return { label: c.validation_status || 'Pending', cls: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400' }
  }

  const toggleSelectAllForLead = (leadId: number) => {
    const contacts = leadContacts[leadId] || []
    const enrollable = contacts.filter(isContactEnrollable)
    const enrollableIds = enrollable.map((c: any) => c.contact_id)
    const allSelected = enrollableIds.every((id: number) => selectedContactIds.includes(id))
    if (allSelected) {
      setSelectedContactIds(ids => ids.filter(id => !enrollableIds.includes(id)))
      setSelectedLeadIds(prev => { const n = new Set(prev); n.delete(leadId); return n })
    } else {
      setSelectedContactIds(ids => Array.from(new Set([...ids, ...enrollableIds])))
      setSelectedLeadIds(prev => new Set(prev).add(leadId))
    }
  }

  useEffect(() => {
    mailboxesApi.list({ page: 1, page_size: 100 }).then(d => setMailboxes(d?.items || [])).catch(() => {})
  }, [])

  const handleSaveRules = async () => {
    if (!selectedCampaign) return
    setRulesSaving(true)
    setRulesMessage(null)
    try {
      await campaignsApi.update(selectedCampaign.campaign_id, { enrollment_rules: enrollmentRules })
      setRulesMessage('Rules saved successfully')
      setTimeout(() => setRulesMessage(null), 3000)
    } catch { setRulesMessage('Failed to save rules') }
    setRulesSaving(false)
  }

  const handlePreviewRules = async () => {
    if (!selectedCampaign) return
    setRulesMessage(null)
    try {
      const result = await campaignsApi.enrollmentPreview(selectedCampaign.campaign_id, enrollmentRules)
      setRulesPreviewCount(result.count)
    } catch { setRulesMessage('Preview failed') }
  }

  const handleTriggerEnroll = async () => {
    if (!selectedCampaign) return
    setRulesSaving(true)
    setRulesMessage(null)
    try {
      const result = await campaignsApi.triggerAutoEnroll(selectedCampaign.campaign_id)
      setRulesMessage(`Enrolled ${result.enrolled || 0} contacts`)
      // Refresh contacts
      const data = await campaignsApi.listContacts(selectedCampaign.campaign_id, { page: 1, page_size: 100 })
      setContacts(data?.items || [])
      // Refresh campaign to get updated auto_enrolled_today
      const updated = await campaignsApi.get(selectedCampaign.campaign_id)
      setSelectedCampaign(updated)
    } catch (err: any) {
      setRulesMessage(err.response?.data?.detail || 'Auto-enrollment failed')
    }
    setRulesSaving(false)
  }

  const toggleArrayItem = (arr: string[], item: string): string[] => {
    return arr.includes(item) ? arr.filter(i => i !== item) : [...arr, item]
  }

  // List view
  if (view === 'list') {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Campaigns</h1>
            <p className="text-gray-500 dark:text-gray-400 mt-1">Multi-step email sequences</p>
          </div>
          <button onClick={() => setShowCreateModal(true)} className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700">
            <Plus className="w-4 h-4" /> New Campaign
          </button>
        </div>

        {/* Filters */}
        <div className="flex gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} placeholder="Search campaigns..." className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm" />
          </div>
          <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1) }} className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm">
            <option value="">All Status</option>
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="completed">Completed</option>
          </select>
        </div>

        {/* Table */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-gray-500">Loading...</div>
          ) : campaigns.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <Zap className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p className="font-medium">No campaigns yet</p>
              <p className="text-sm mt-1">Create your first multi-step campaign</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900/50">
                <tr>
                  <th className="text-left px-4 py-3 font-medium">Name</th>
                  <th className="text-left px-4 py-3 font-medium">Status</th>
                  <th className="text-right px-4 py-3 font-medium">Contacts</th>
                  <th className="text-right px-4 py-3 font-medium">Sent</th>
                  <th className="text-right px-4 py-3 font-medium">Open %</th>
                  <th className="text-right px-4 py-3 font-medium">Reply %</th>
                  <th className="text-right px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {campaigns.map(c => {
                  const openRate = c.total_sent > 0 ? ((c.total_opened / c.total_sent) * 100).toFixed(1) : '0.0'
                  const replyRate = c.total_sent > 0 ? ((c.total_replied / c.total_sent) * 100).toFixed(1) : '0.0'
                  return (
                    <tr key={c.campaign_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer" onClick={() => openDetail(c)}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900 dark:text-gray-100">{c.name}</div>
                        {c.description && <div className="text-xs text-gray-500 truncate max-w-xs">{c.description}</div>}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColors[c.status] || ''}`}>{c.status}</span>
                      </td>
                      <td className="px-4 py-3 text-right">{c.total_contacts}</td>
                      <td className="px-4 py-3 text-right">{c.total_sent}</td>
                      <td className="px-4 py-3 text-right">{openRate}%</td>
                      <td className="px-4 py-3 text-right">{replyRate}%</td>
                      <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                        <div className="relative inline-block">
                          <button onClick={() => setActionMenu(actionMenu === c.campaign_id ? null : c.campaign_id)} className="p-1 hover:bg-gray-200 dark:hover:bg-gray-600 rounded">
                            <MoreVertical className="w-4 h-4" />
                          </button>
                          {actionMenu === c.campaign_id && (
                            <div className="absolute right-0 top-8 z-10 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg w-40">
                              {c.status === 'draft' && <button onClick={() => handleAction('activate', c.campaign_id)} className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"><Play className="w-3 h-3" /> Activate</button>}
                              {c.status === 'active' && <button onClick={() => handleAction('pause', c.campaign_id)} className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"><Pause className="w-3 h-3" /> Pause</button>}
                              {c.status === 'paused' && <button onClick={() => handleAction('resume', c.campaign_id)} className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"><Play className="w-3 h-3" /> Resume</button>}
                              <button onClick={() => handleAction('duplicate', c.campaign_id)} className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"><Copy className="w-3 h-3" /> Duplicate</button>
                              <button onClick={() => handleAction('delete', c.campaign_id)} className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 text-red-600 flex items-center gap-2"><Trash2 className="w-3 h-3" /> Delete</button>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 border rounded disabled:opacity-50">Prev</button>
            <span className="text-sm text-gray-500">Page {page} of {totalPages}</span>
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="px-3 py-1 border rounded disabled:opacity-50">Next</button>
          </div>
        )}

        {/* Create Campaign Modal */}
        {showCreateModal && (
          <>
            <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowCreateModal(false)} />
            <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-[500px] max-w-[90vw] max-h-[85vh] overflow-y-auto">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-bold dark:text-gray-100">New Campaign</h2>
                <button onClick={() => setShowCreateModal(false)}><X className="w-5 h-5" /></button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Name *</label>
                  <input value={campaignForm.name} onChange={e => setCampaignForm(f => ({ ...f, name: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" placeholder="Campaign name" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Description</label>
                  <textarea value={campaignForm.description} onChange={e => setCampaignForm(f => ({ ...f, description: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" rows={2} />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Send Window Start</label>
                    <input type="time" value={campaignForm.send_window_start} onChange={e => setCampaignForm(f => ({ ...f, send_window_start: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Send Window End</label>
                    <input type="time" value={campaignForm.send_window_end} onChange={e => setCampaignForm(f => ({ ...f, send_window_end: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Daily Limit</label>
                  <input type="number" value={campaignForm.daily_limit} onChange={e => setCampaignForm(f => ({ ...f, daily_limit: parseInt(e.target.value) || 30 }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Mailboxes</label>
                  <div className="border rounded-lg p-2 max-h-32 overflow-y-auto dark:border-gray-600">
                    {mailboxes.map(m => (
                      <label key={m.mailbox_id} className="flex items-center gap-2 py-1 text-sm">
                        <input type="checkbox" checked={selectedMailboxIds.includes(m.mailbox_id)} onChange={e => {
                          if (e.target.checked) setSelectedMailboxIds(ids => [...ids, m.mailbox_id])
                          else setSelectedMailboxIds(ids => ids.filter(i => i !== m.mailbox_id))
                        }} />
                        {m.email}
                      </label>
                    ))}
                    {mailboxes.length === 0 && <p className="text-xs text-gray-500">No mailboxes available</p>}
                  </div>
                </div>
                <div className="flex gap-3 pt-2">
                  <button onClick={() => setShowCreateModal(false)} className="flex-1 px-4 py-2 border rounded-lg">Cancel</button>
                  <button onClick={handleCreate} disabled={!campaignForm.name || saving} className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">
                    {saving ? 'Creating...' : 'Create Campaign'}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    )
  }

  // Detail view
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => { setView('list'); setSelectedCampaign(null) }} className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
          <ChevronDown className="w-5 h-5 rotate-90" />
        </button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{selectedCampaign?.name}</h1>
          <div className="flex items-center gap-3 mt-1">
            <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColors[selectedCampaign?.status || ''] || ''}`}>{selectedCampaign?.status}</span>
            <span className="text-sm text-gray-500">{selectedCampaign?.total_contacts} contacts</span>
            <span className="text-sm text-gray-500">{selectedCampaign?.total_sent} sent</span>
          </div>
        </div>
        <div className="flex gap-2">
          {selectedCampaign?.status === 'draft' && (
            <button onClick={() => handleAction('activate', selectedCampaign.campaign_id)} className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2">
              <Play className="w-4 h-4" /> Activate
            </button>
          )}
          {selectedCampaign?.status === 'active' && (
            <button onClick={() => handleAction('pause', selectedCampaign.campaign_id)} className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 flex items-center gap-2">
              <Pause className="w-4 h-4" /> Pause
            </button>
          )}
          {selectedCampaign?.status === 'paused' && (
            <button onClick={() => handleAction('resume', selectedCampaign.campaign_id)} className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2">
              <Play className="w-4 h-4" /> Resume
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {(['sequence', 'contacts', 'analytics', 'rules'] as const).map(tab => (
          <button key={tab} onClick={() => { setDetailTab(tab); if (tab === 'analytics' && selectedCampaign) loadAnalytics(selectedCampaign.campaign_id) }}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px capitalize ${detailTab === tab ? 'border-primary-600 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
            {tab}
          </button>
        ))}
      </div>

      {/* Sequence Tab */}
      {detailTab === 'sequence' && (
        <div className="space-y-3">
          {steps.length === 0 ? (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-8 text-center">
              <Mail className="w-10 h-10 mx-auto mb-3 text-gray-300" />
              <p className="font-medium text-gray-900 dark:text-gray-100">No steps yet</p>
              <p className="text-sm text-gray-500 mt-1">Add your first email step to build the sequence</p>
            </div>
          ) : (
            steps.map((step, idx) => (
              <div key={step.step_id} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold ${step.step_type === 'email' ? 'bg-blue-500' : step.step_type === 'wait' ? 'bg-yellow-500' : 'bg-purple-500'}`}>
                    {idx + 1}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      {step.step_type === 'email' && <Mail className="w-4 h-4 text-blue-500" />}
                      {step.step_type === 'wait' && <Clock className="w-4 h-4 text-yellow-500" />}
                      {step.step_type === 'condition' && <GitBranch className="w-4 h-4 text-purple-500" />}
                      <span className="font-medium capitalize">{step.step_type}</span>
                      {step.step_type === 'email' && step.subject && <span className="text-sm text-gray-500">— {step.subject}</span>}
                      {step.delay_days > 0 && <span className="text-xs text-gray-400 ml-2">Wait {step.delay_days}d {step.delay_hours}h</span>}
                    </div>
                    {step.step_type === 'email' && (
                      <div className="flex gap-4 mt-1 text-xs text-gray-500">
                        <span>Sent: {step.total_sent}</span>
                        <span>Opened: {step.total_opened}</span>
                        <span>Replied: {step.total_replied}</span>
                        <span>Bounced: {step.total_bounced}</span>
                      </div>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <button onClick={() => { setEditingStep(step); setStepForm({ step_type: step.step_type, subject: step.subject || '', body_html: step.body_html || '', delay_days: step.delay_days, delay_hours: step.delay_hours, reply_to_thread: step.reply_to_thread, condition_type: step.condition_type || '', condition_window_hours: step.condition_window_hours || 24, variants_json: step.variants_json || '' }); setShowStepModal(true) }} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded">
                      <Eye className="w-4 h-4 text-gray-400" />
                    </button>
                    <button onClick={() => handleDeleteStep(step.step_id)} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded">
                      <Trash2 className="w-4 h-4 text-red-400" />
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
          <button onClick={() => { setEditingStep(null); setStepForm(defaultStep); setShowStepModal(true) }} className="w-full py-3 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg text-gray-500 hover:border-primary-500 hover:text-primary-600 flex items-center justify-center gap-2">
            <Plus className="w-4 h-4" /> Add Step
          </button>
        </div>
      )}

      {/* Contacts Tab */}
      {detailTab === 'contacts' && (
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-500">{contacts.length} enrolled contacts</span>
            <button onClick={openEnrollModal} className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 flex items-center gap-2 text-sm">
              <Users className="w-4 h-4" /> Enroll Contacts
            </button>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            {contacts.length === 0 ? (
              <div className="p-8 text-center text-gray-500">No contacts enrolled yet</div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-900/50">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium">Contact</th>
                    <th className="text-left px-4 py-3 font-medium">Status</th>
                    <th className="text-right px-4 py-3 font-medium">Current Step</th>
                    <th className="text-left px-4 py-3 font-medium">Next Send</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {contacts.map(cc => (
                    <tr key={cc.id}>
                      <td className="px-4 py-3">
                        <div className="font-medium">{cc.contact_name || `Contact #${cc.contact_id}`}</div>
                        <div className="text-xs text-gray-500">{cc.contact_email}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${cc.status === 'active' ? 'bg-green-100 text-green-800' : cc.status === 'replied' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'}`}>{cc.status}</span>
                      </td>
                      <td className="px-4 py-3 text-right">{cc.current_step}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">{cc.next_send_at ? new Date(cc.next_send_at).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Analytics Tab */}
      {detailTab === 'analytics' && (
        <div className="space-y-4">
          {!analytics ? (
            <div className="p-8 text-center text-gray-500">Loading analytics...</div>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: 'Total Sent', value: analytics.overall?.total_sent || 0 },
                  { label: 'Opened', value: analytics.overall?.total_opened || 0 },
                  { label: 'Replied', value: analytics.overall?.total_replied || 0 },
                  { label: 'Bounced', value: analytics.overall?.total_bounced || 0 },
                ].map(s => (
                  <div key={s.label} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                    <p className="text-sm text-gray-500">{s.label}</p>
                    <p className="text-2xl font-bold mt-1">{s.value}</p>
                  </div>
                ))}
              </div>
              {analytics.per_step && analytics.per_step.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                  <h3 className="px-4 py-3 font-medium border-b border-gray-200 dark:border-gray-700">Per-Step Metrics</h3>
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-gray-900/50">
                      <tr>
                        <th className="text-left px-4 py-2">Step</th>
                        <th className="text-right px-4 py-2">Sent</th>
                        <th className="text-right px-4 py-2">Open %</th>
                        <th className="text-right px-4 py-2">Reply %</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {analytics.per_step.map((s: any, i: number) => (
                        <tr key={i}>
                          <td className="px-4 py-2">Step {s.step_order}</td>
                          <td className="px-4 py-2 text-right">{s.sent}</td>
                          <td className="px-4 py-2 text-right">{s.open_rate?.toFixed(1) || '0.0'}%</td>
                          <td className="px-4 py-2 text-right">{s.reply_rate?.toFixed(1) || '0.0'}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Rules Tab — Auto-Enrollment */}
      {detailTab === 'rules' && (
        <div className="space-y-4">
          {rulesMessage && (
            <div className={`text-sm px-4 py-2 rounded-lg ${rulesMessage.includes('fail') || rulesMessage.includes('Failed') ? 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400' : 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400'}`}>
              {rulesMessage}
            </div>
          )}

          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5 space-y-5">
            {/* Enable toggle */}
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-medium text-gray-900 dark:text-gray-100">Auto-Enrollment</h3>
                <p className="text-sm text-gray-500 mt-0.5">Automatically enroll matching contacts into this campaign</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={enrollmentRules.enabled}
                onClick={() => setEnrollmentRules(r => ({ ...r, enabled: !r.enabled }))}
                className={`relative inline-flex w-11 h-6 items-center rounded-full transition-colors ${enrollmentRules.enabled ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'}`}
              >
                <span className={`inline-block w-4 h-4 transform rounded-full bg-white shadow transition-transform ${enrollmentRules.enabled ? 'translate-x-5' : 'translate-x-1'}`} />
              </button>
            </div>

            {/* Validation Status */}
            <div>
              <label className="block text-sm font-medium mb-2">Validation Status</label>
              <div className="flex gap-3">
                {['Valid', 'Catch-all'].map(s => (
                  <label key={s} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={enrollmentRules.validation_status.includes(s)} onChange={() => setEnrollmentRules(r => ({ ...r, validation_status: toggleArrayItem(r.validation_status, s) }))} />
                    {s}
                  </label>
                ))}
              </div>
            </div>

            {/* Priority Levels */}
            <div>
              <label className="block text-sm font-medium mb-2">Priority Levels <span className="text-gray-400 font-normal">(empty = all)</span></label>
              <div className="flex flex-wrap gap-3">
                {[
                  { value: 'p1_job_poster', label: 'P1 - Job Poster' },
                  { value: 'p2_hr_ta_recruiter', label: 'P2 - HR/Recruiter' },
                  { value: 'p3_hr_manager', label: 'P3 - HR Manager' },
                  { value: 'p4_ops_leader', label: 'P4 - Ops Leader' },
                  { value: 'p5_functional_manager', label: 'P5 - Functional Mgr' },
                ].map(p => (
                  <label key={p.value} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={enrollmentRules.priority_levels.includes(p.value)} onChange={() => setEnrollmentRules(r => ({ ...r, priority_levels: toggleArrayItem(r.priority_levels, p.value) }))} />
                    {p.label}
                  </label>
                ))}
              </div>
            </div>

            {/* States */}
            <div>
              <label className="block text-sm font-medium mb-1">States <span className="text-gray-400 font-normal">(comma-separated, empty = all)</span></label>
              <input
                value={enrollmentRules.states.join(', ')}
                onChange={e => setEnrollmentRules(r => ({ ...r, states: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))}
                placeholder="TX, CA, NY"
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
              />
            </div>

            {/* Job Title Keywords */}
            <div>
              <label className="block text-sm font-medium mb-1">Job Title Keywords <span className="text-gray-400 font-normal">(comma-separated, empty = all)</span></label>
              <input
                value={enrollmentRules.job_title_keywords.join(', ')}
                onChange={e => setEnrollmentRules(r => ({ ...r, job_title_keywords: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))}
                placeholder="manager, director, supervisor"
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
              />
            </div>

            {/* Contact Sources */}
            <div>
              <label className="block text-sm font-medium mb-2">Contact Sources <span className="text-gray-400 font-normal">(empty = all)</span></label>
              <div className="flex flex-wrap gap-3">
                {['apollo', 'seamless', 'hunter', 'snovio', 'rocketreach', 'pdl', 'proxycurl'].map(s => (
                  <label key={s} className="flex items-center gap-2 text-sm capitalize">
                    <input type="checkbox" checked={enrollmentRules.sources.includes(s)} onChange={() => setEnrollmentRules(r => ({ ...r, sources: toggleArrayItem(r.sources, s) }))} />
                    {s === 'pdl' ? 'PDL' : s === 'snovio' ? 'Snov.io' : s.charAt(0).toUpperCase() + s.slice(1)}
                  </label>
                ))}
              </div>
            </div>

            {/* Numeric fields */}
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Min Lead Score</label>
                <input
                  type="number"
                  value={enrollmentRules.min_lead_score ?? ''}
                  onChange={e => setEnrollmentRules(r => ({ ...r, min_lead_score: e.target.value ? parseInt(e.target.value) : null }))}
                  placeholder="0"
                  min={0} max={100}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Max Per Run</label>
                <input
                  type="number"
                  value={enrollmentRules.max_per_run}
                  onChange={e => setEnrollmentRules(r => ({ ...r, max_per_run: parseInt(e.target.value) || 50 }))}
                  min={1}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Daily Cap</label>
                <input
                  type="number"
                  value={enrollmentRules.daily_cap}
                  onChange={e => setEnrollmentRules(r => ({ ...r, daily_cap: parseInt(e.target.value) || 200 }))}
                  min={1}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
                />
              </div>
            </div>

            {/* Today's stats */}
            {selectedCampaign && (
              <div className="text-sm text-gray-500 bg-gray-50 dark:bg-gray-900/30 rounded-lg px-4 py-2">
                Today: <span className="font-medium text-gray-900 dark:text-gray-100">{selectedCampaign.auto_enrolled_today || 0}</span> / {enrollmentRules.daily_cap} enrolled
              </div>
            )}

            {/* Preview result */}
            {rulesPreviewCount !== null && (
              <div className="text-sm bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-lg px-4 py-2">
                <span className="font-medium">{rulesPreviewCount}</span> contacts match these rules
              </div>
            )}

            {/* Action buttons */}
            <div className="flex gap-3 pt-2 border-t border-gray-200 dark:border-gray-700">
              <button onClick={handlePreviewRules} className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2">
                <Eye className="w-4 h-4" /> Preview
              </button>
              <button onClick={handleSaveRules} disabled={rulesSaving} className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2">
                <Settings className="w-4 h-4" /> {rulesSaving ? 'Saving...' : 'Save Rules'}
              </button>
              {selectedCampaign?.status === 'active' && (
                <button onClick={handleTriggerEnroll} disabled={rulesSaving} className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700 disabled:opacity-50 flex items-center gap-2">
                  <Zap className="w-4 h-4" /> {rulesSaving ? 'Running...' : 'Run Now'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Step Modal */}
      {showStepModal && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowStepModal(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-[550px] max-w-[90vw] max-h-[85vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold">{editingStep ? 'Edit Step' : 'Add Step'}</h2>
              <button onClick={() => setShowStepModal(false)}><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Step Type</label>
                <select value={stepForm.step_type} onChange={e => setStepForm(f => ({ ...f, step_type: e.target.value as any }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600">
                  <option value="email">Email</option>
                  <option value="wait">Wait</option>
                  <option value="condition">Condition</option>
                </select>
              </div>
              {stepForm.step_type === 'email' && (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-1">Subject</label>
                    <input value={stepForm.subject} onChange={e => setStepForm(f => ({ ...f, subject: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" placeholder="Email subject (supports {spintax|options})" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Body (HTML)</label>
                    <textarea value={stepForm.body_html} onChange={e => setStepForm(f => ({ ...f, body_html: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 font-mono text-xs" rows={6} placeholder="<p>Hi {{first_name}},</p>" />
                  </div>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={stepForm.reply_to_thread} onChange={e => setStepForm(f => ({ ...f, reply_to_thread: e.target.checked }))} />
                    <span className="text-sm">Reply to previous thread</span>
                  </label>
                </>
              )}
              {stepForm.step_type === 'condition' && (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-1">Condition</label>
                    <select value={stepForm.condition_type} onChange={e => setStepForm(f => ({ ...f, condition_type: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600">
                      <option value="">Select condition...</option>
                      <option value="opened">Email Opened</option>
                      <option value="clicked">Link Clicked</option>
                      <option value="replied">Replied</option>
                      <option value="no_action">No Action</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Window (hours)</label>
                    <input type="number" value={stepForm.condition_window_hours} onChange={e => setStepForm(f => ({ ...f, condition_window_hours: parseInt(e.target.value) || 24 }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                  </div>
                </>
              )}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Delay (days)</label>
                  <input type="number" value={stepForm.delay_days} onChange={e => setStepForm(f => ({ ...f, delay_days: parseInt(e.target.value) || 0 }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Delay (hours)</label>
                  <input type="number" value={stepForm.delay_hours} onChange={e => setStepForm(f => ({ ...f, delay_hours: parseInt(e.target.value) || 0 }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                </div>
              </div>
              <div className="flex gap-3 pt-2">
                <button onClick={() => setShowStepModal(false)} className="flex-1 px-4 py-2 border rounded-lg">Cancel</button>
                <button onClick={handleAddStep} disabled={saving} className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">
                  {saving ? 'Saving...' : editingStep ? 'Update Step' : 'Add Step'}
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Enroll Modal — Lead-based contact selection */}
      {showEnrollModal && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowEnrollModal(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-[640px] max-w-[95vw] max-h-[85vh] flex flex-col">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h2 className="text-lg font-bold dark:text-gray-100">Enroll Contacts from Leads</h2>
                <p className="text-xs text-gray-500 mt-0.5">Check a lead to select all its eligible contacts, or expand to pick individually</p>
              </div>
              <button onClick={() => setShowEnrollModal(false)}><X className="w-5 h-5" /></button>
            </div>

            {/* Search leads */}
            <div className="relative mb-3">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                value={enrollLeadSearch}
                onChange={e => {
                  const val = e.target.value
                  setEnrollLeadSearch(val)
                  if (enrollSearchTimeout) clearTimeout(enrollSearchTimeout)
                  setEnrollSearchTimeout(setTimeout(() => { setEnrollLeadPage(1); fetchEnrollLeads(val, 1) }, 400))
                }}
                placeholder="Search leads by company, title, or state..."
                className="w-full pl-10 pr-4 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
              />
            </div>

            {/* Leads list with checkboxes and expandable contacts */}
            <div className="border rounded-lg overflow-y-auto flex-1 min-h-0 dark:border-gray-600">
              {enrollLeadsLoading ? (
                <div className="p-6 text-center text-gray-500 text-sm">Loading leads...</div>
              ) : enrollLeads.length === 0 ? (
                <div className="p-6 text-center text-gray-500 text-sm">No leads found</div>
              ) : (
                <div className="divide-y divide-gray-200 dark:divide-gray-700">
                  {enrollLeads.map(lead => {
                    const isExpanded = expandedLeadIds.has(lead.lead_id)
                    const isLeadSelected = selectedLeadIds.has(lead.lead_id)
                    const contacts = leadContacts[lead.lead_id] || []
                    const isLoadingContacts = loadingLeadContacts.has(lead.lead_id)
                    const enrollableContacts = contacts.filter(isContactEnrollable)
                    const allEnrollableSelected = enrollableContacts.length > 0 && enrollableContacts.every((c: any) => selectedContactIds.includes(c.contact_id))
                    const someSelected = enrollableContacts.some((c: any) => selectedContactIds.includes(c.contact_id))

                    return (
                      <div key={lead.lead_id}>
                        {/* Lead row with checkbox */}
                        <div className="flex items-center gap-2 px-3 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                          <input
                            type="checkbox"
                            className="shrink-0"
                            checked={isLeadSelected}
                            ref={el => { if (el) el.indeterminate = !isLeadSelected && someSelected }}
                            onChange={() => toggleLeadCheckbox(lead.lead_id)}
                          />
                          <button
                            className="flex items-center gap-2 flex-1 min-w-0 text-left"
                            onClick={() => toggleLeadExpand(lead.lead_id)}
                          >
                            {isExpanded ? <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" /> : <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />}
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">{lead.client_name}</div>
                              <div className="text-xs text-gray-500 truncate">{lead.job_title}{lead.state ? ` — ${lead.state}` : ''}</div>
                            </div>
                          </button>
                          <span className="text-xs text-gray-400 shrink-0 flex items-center gap-1">
                            <Users className="w-3 h-3" /> {lead.contact_count}
                          </span>
                        </div>

                        {/* Expanded contacts */}
                        {isExpanded && (
                          <div className="bg-gray-50/50 dark:bg-gray-900/30 border-t border-gray-100 dark:border-gray-700">
                            {isLoadingContacts ? (
                              <div className="px-10 py-3 text-xs text-gray-500">Loading contacts...</div>
                            ) : contacts.length === 0 ? (
                              <div className="px-10 py-3 text-xs text-gray-500">No contacts linked to this lead</div>
                            ) : (
                              <>
                                {/* Select all for this lead */}
                                {enrollableContacts.length > 0 && (
                                  <label className="flex items-center gap-2 px-10 py-1.5 text-xs text-primary-600 font-medium cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800">
                                    <input
                                      type="checkbox"
                                      checked={allEnrollableSelected}
                                      ref={el => { if (el) el.indeterminate = someSelected && !allEnrollableSelected }}
                                      onChange={() => toggleSelectAllForLead(lead.lead_id)}
                                    />
                                    Select all eligible ({enrollableContacts.length})
                                  </label>
                                )}
                                {contacts.map((c: any) => {
                                  const enrollable = isContactEnrollable(c)
                                  const badge = getContactStatusBadge(c)
                                  return (
                                    <label
                                      key={c.contact_id}
                                      className={`flex items-center gap-3 px-10 py-2 text-sm ${enrollable ? 'hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer' : 'opacity-60 cursor-not-allowed'}`}
                                    >
                                      <input
                                        type="checkbox"
                                        disabled={!enrollable}
                                        checked={selectedContactIds.includes(c.contact_id)}
                                        onChange={e => {
                                          if (e.target.checked) setSelectedContactIds(ids => [...ids, c.contact_id])
                                          else {
                                            setSelectedContactIds(ids => ids.filter(i => i !== c.contact_id))
                                            setSelectedLeadIds(prev => { const n = new Set(prev); n.delete(lead.lead_id); return n })
                                          }
                                        }}
                                      />
                                      <div className="flex-1 min-w-0">
                                        <span className="font-medium text-gray-900 dark:text-gray-100">{c.first_name} {c.last_name}</span>
                                        <span className="text-gray-500 ml-2 text-xs">{c.email}</span>
                                      </div>
                                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${badge.cls}`}>
                                        {badge.label}
                                      </span>
                                    </label>
                                  )
                                })}
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Pagination for leads */}
            {enrollLeadPages > 1 && (
              <div className="flex items-center justify-center gap-2 mt-2">
                <button
                  onClick={() => { const p = Math.max(1, enrollLeadPage - 1); setEnrollLeadPage(p); fetchEnrollLeads(enrollLeadSearch, p) }}
                  disabled={enrollLeadPage === 1}
                  className="px-2 py-1 text-xs border rounded disabled:opacity-50"
                >Prev</button>
                <span className="text-xs text-gray-500">Page {enrollLeadPage} of {enrollLeadPages}</span>
                <button
                  onClick={() => { const p = Math.min(enrollLeadPages, enrollLeadPage + 1); setEnrollLeadPage(p); fetchEnrollLeads(enrollLeadSearch, p) }}
                  disabled={enrollLeadPage === enrollLeadPages}
                  className="px-2 py-1 text-xs border rounded disabled:opacity-50"
                >Next</button>
              </div>
            )}

            {/* Footer */}
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
              <p className="text-sm text-gray-500">{selectedContactIds.length} contact{selectedContactIds.length !== 1 ? 's' : ''} selected</p>
              <div className="flex gap-3">
                <button onClick={() => setShowEnrollModal(false)} className="px-4 py-2 border rounded-lg text-sm">Cancel</button>
                <button onClick={handleEnroll} disabled={selectedContactIds.length === 0 || saving} className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm">
                  {saving ? 'Enrolling...' : `Enroll ${selectedContactIds.length} Contacts`}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
