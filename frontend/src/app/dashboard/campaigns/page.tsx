'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { campaignsApi, contactsApi, leadsApi, mailboxesApi, emailPreviewApi, pipelinesApi, deliverabilityApi } from '@/lib/api'
import type { Campaign, SequenceStep, CampaignContact } from '@/types/api'
import {
  Plus, Search, MoreVertical, Play, Pause, Copy, Trash2, ChevronDown, ChevronRight,
  Mail, Clock, GitBranch, ArrowUp, ArrowDown, X, Zap, Users, BarChart3, Eye, Settings,
  FileSearch, Loader2, AlertTriangle, Shuffle, MessageSquare, Phone, Linkedin,
  MousePointerClick, Reply, Activity, LayoutList, Workflow,
} from 'lucide-react'
import dynamic from 'next/dynamic'

const SequenceBuilder = dynamic(() => import('@/components/sequence-builder'), { ssr: false })

type TabView = 'list' | 'detail'

interface StepFormData {
  step_type: 'email' | 'wait' | 'condition' | 'sms' | 'call' | 'linkedin'
  subject: string
  body_html: string
  body_text: string
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
  body_text: '',
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
  const [detailTab, setDetailTab] = useState<'overview' | 'mailboxes' | 'leads_contacts' | 'sequence' | 'schedule' | 'rules' | 'activity' | 'analytics'>('overview')

  // Available leads for campaign creation
  const [availableLeads, setAvailableLeads] = useState<any[]>([])
  const [availableLeadsTotal, setAvailableLeadsTotal] = useState(0)
  const [availableLeadsPage, setAvailableLeadsPage] = useState(1)
  const [availableLeadsPages, setAvailableLeadsPages] = useState(1)
  const [availableLeadsSearch, setAvailableLeadsSearch] = useState('')
  const [availableLeadsLoading, setAvailableLeadsLoading] = useState(false)
  const [selectedCreateLeadIds, setSelectedCreateLeadIds] = useState<Set<number>>(new Set())
  const [createPreviewMode, setCreatePreviewMode] = useState(false)
  const [creatingFromLeads, setCreatingFromLeads] = useState(false)

  // Contact schedule state
  const [contactSchedule, setContactSchedule] = useState<any[]>([])
  const [scheduleLoading, setScheduleLoading] = useState(false)

  // Overview edit state
  const [overviewEditing, setOverviewEditing] = useState(false)
  const [overviewForm, setOverviewForm] = useState({ name: '', description: '', sending_speed: 'normal' })
  const [overviewSaving, setOverviewSaving] = useState(false)

  // Step spam scores
  const [stepSpamScores, setStepSpamScores] = useState<Record<number, { grade: string; score: number }>>({})
  const [spintaxModal, setSpintaxModal] = useState<{ step: SequenceStep } | null>(null)
  const [spintaxVariants, setSpintaxVariants] = useState<string[]>([])
  const [loadingSpintax, setLoadingSpintax] = useState(false)

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
    preview_mode: false,
    scheduled_send_at: '',
    sending_speed: 'normal',
  })
  const [actionMenu, setActionMenu] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [analytics, setAnalytics] = useState<any>(null)
  const [analyticsDateFrom, setAnalyticsDateFrom] = useState('')
  const [analyticsDateTo, setAnalyticsDateTo] = useState('')
  const [showCompareModal, setShowCompareModal] = useState(false)
  const [compareIds, setCompareIds] = useState<number[]>([])
  const [compareData, setCompareData] = useState<any>(null)
  const [compareLoading, setCompareLoading] = useState(false)

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
  const [campaignsEnabled, setCampaignsEnabled] = useState(true)

  // Activity feed state
  const [activityEvents, setActivityEvents] = useState<any[]>([])
  const [activityLoading, setActivityLoading] = useState(false)
  const [activityFilter, setActivityFilter] = useState<string>('all')

  // A/B stats state
  const [abStatsData, setAbStatsData] = useState<Record<number, any>>({})

  // Thread preview state
  const [threadPreview, setThreadPreview] = useState<any>(null)
  const [threadPreviewLoading, setThreadPreviewLoading] = useState(false)
  const [showThreadPreviewModal, setShowThreadPreviewModal] = useState(false)

  // Sequence view mode
  const [sequenceViewMode, setSequenceViewMode] = useState<'list' | 'visual'>('list')

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

  const searchParams = useSearchParams()

  useEffect(() => { fetchCampaigns() }, [fetchCampaigns])

  // Fetch available leads for the create modal
  const fetchAvailableLeads = useCallback(async () => {
    setAvailableLeadsLoading(true)
    try {
      const params: Record<string, any> = { page: availableLeadsPage, page_size: 50, days: 30 }
      if (availableLeadsSearch) params.search = availableLeadsSearch
      const data = await campaignsApi.getAvailableLeads(params)
      setAvailableLeads(data.items || [])
      setAvailableLeadsTotal(data.total || 0)
      setAvailableLeadsPages(data.pages || 1)
      // Auto-select all leads by default
      if (!availableLeadsSearch && availableLeadsPage === 1) {
        setSelectedCreateLeadIds(new Set((data.items || []).map((l: any) => l.lead_id)))
      }
    } catch {
      setAvailableLeads([])
    } finally {
      setAvailableLeadsLoading(false)
    }
  }, [availableLeadsPage, availableLeadsSearch])

  useEffect(() => {
    if (showCreateModal) fetchAvailableLeads()
  }, [showCreateModal, fetchAvailableLeads])

  // Create campaign from selected leads
  const handleCreateFromLeads = async () => {
    if (selectedCreateLeadIds.size === 0) return
    setCreatingFromLeads(true)
    try {
      const data = await campaignsApi.createFromLeads({
        lead_ids: Array.from(selectedCreateLeadIds),
        preview_mode: createPreviewMode,
      })
      setShowCreateModal(false)
      setSelectedCreateLeadIds(new Set())
      setAvailableLeadsSearch('')
      setAvailableLeadsPage(1)
      await fetchCampaigns()
      // Open the newly created campaign
      openDetail(data)
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to create campaign')
    } finally {
      setCreatingFromLeads(false)
    }
  }

  // Fetch contact schedule for a campaign
  const fetchContactSchedule = async (campaignId: number) => {
    setScheduleLoading(true)
    try {
      const data = await campaignsApi.getContactSchedule(campaignId)
      setContactSchedule(data.schedule || [])
    } catch {
      setContactSchedule([])
    } finally {
      setScheduleLoading(false)
    }
  }

  // Auto-open campaign detail when navigated with ?campaign_id=X
  useEffect(() => {
    const cid = searchParams.get('campaign_id')
    if (cid && campaigns.length > 0 && !selectedCampaign) {
      const target = campaigns.find(c => c.campaign_id === Number(cid))
      if (target) openDetail(target)
    }
  }, [campaigns, searchParams]) // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch feature status on mount
  useEffect(() => {
    pipelinesApi.getFeatureStatus()
      .then(fs => setCampaignsEnabled(fs.campaigns_enabled ?? true))
      .catch(() => { /* defaults to enabled */ })
  }, [])

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
      // Fetch spam scores for email steps
      const emailSteps = (stepsData || []).filter((s: SequenceStep) => s.step_type === 'email' && s.subject && s.body_html)
      if (emailSteps.length > 0) {
        Promise.allSettled(
          emailSteps.map((s: SequenceStep) => emailPreviewApi.spamCheck({ subject: s.subject || '', body_html: s.body_html || '' }).then(r => ({ id: s.step_id, grade: r.grade, score: r.score })))
        ).then(results => {
          const scores: Record<number, { grade: string; score: number }> = {}
          for (const r of results) {
            if (r.status === 'fulfilled' && r.value) scores[r.value.id] = { grade: r.value.grade, score: r.value.score }
          }
          setStepSpamScores(scores)
        })
      }
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

  const loadAnalytics = async (id: number, dateFrom?: string, dateTo?: string) => {
    try {
      const data = await campaignsApi.analytics(id, dateFrom || undefined, dateTo || undefined)
      setAnalytics(data)
    } catch { setAnalytics(null) }
  }

  const handleExportCsv = async (id: number) => {
    try {
      const blob = await campaignsApi.exportCsvWithDates(id, analyticsDateFrom || undefined, analyticsDateTo || undefined)
      const url = window.URL.createObjectURL(new Blob([blob]))
      const a = document.createElement('a')
      a.href = url
      a.download = `campaign_${id}_analytics.csv`
      a.click()
      window.URL.revokeObjectURL(url)
    } catch { /* ignore */ }
  }

  const handleCompare = async () => {
    if (compareIds.length < 2) return
    setCompareLoading(true)
    try {
      const data = await campaignsApi.compare(compareIds)
      setCompareData(data)
    } catch { /* ignore */ }
    setCompareLoading(false)
  }

  const fetchActivity = useCallback(async (campaignId: number, filter?: string) => {
    setActivityLoading(true)
    try {
      const params: Record<string, any> = { limit: 50 }
      if (filter && filter !== 'all') params.event_type = filter
      const data = await campaignsApi.activity(campaignId, params)
      setActivityEvents(data?.items || [])
    } catch { setActivityEvents([]) }
    setActivityLoading(false)
  }, [])

  const fetchAbStats = async (campaignId: number, stepId: number) => {
    try {
      const data = await campaignsApi.abStats(campaignId, stepId)
      setAbStatsData(prev => ({ ...prev, [stepId]: data }))
    } catch { /* ignore */ }
  }

  const handleThreadPreview = async (campaignId: number, contactId: number) => {
    setThreadPreviewLoading(true)
    setShowThreadPreviewModal(true)
    try {
      const data = await campaignsApi.threadPreview(campaignId, contactId)
      setThreadPreview(data)
    } catch { setThreadPreview(null) }
    setThreadPreviewLoading(false)
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
      setCampaignForm({ name: '', description: '', timezone: 'US/Eastern', send_window_start: '09:00', send_window_end: '17:00', send_days: ['mon','tue','wed','thu','fri'], daily_limit: 30, preview_mode: false, scheduled_send_at: '', sending_speed: 'normal' })
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
      else if (action === 'complete') await campaignsApi.complete(id)
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

  // Auto-refresh activity feed every 10s when on activity tab
  useEffect(() => {
    if (detailTab !== 'activity' || !selectedCampaign) return
    const interval = setInterval(() => {
      fetchActivity(selectedCampaign.campaign_id, activityFilter)
    }, 10000)
    return () => clearInterval(interval)
  }, [detailTab, selectedCampaign, activityFilter, fetchActivity])

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

        {/* Feature disabled banner */}
        {!campaignsEnabled && (
          <div className="flex items-center gap-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 text-yellow-800 dark:text-yellow-200 px-4 py-3 rounded-lg text-sm">
            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            <span>Campaign execution is disabled for your organization. Contact your administrator to enable it.</span>
          </div>
        )}

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
                  <th className="text-right px-4 py-3 font-medium">Health</th>
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
                      <td className="px-4 py-3 text-right">
                        {c.health_score != null ? (
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                            c.health_score >= 80 ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' :
                            c.health_score >= 50 ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400' :
                            'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                          }`}>
                            {c.health_score >= 80 ? 'Excellent' : c.health_score >= 50 ? 'Fair' : 'Poor'} {c.health_score}
                          </span>
                        ) : (
                          <span className="text-gray-400 text-xs">N/A</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                        <div className="relative inline-block">
                          <button onClick={() => setActionMenu(actionMenu === c.campaign_id ? null : c.campaign_id)} className="p-1 hover:bg-gray-200 dark:hover:bg-gray-600 rounded">
                            <MoreVertical className="w-4 h-4" />
                          </button>
                          {actionMenu === c.campaign_id && (
                            <div className="absolute right-0 top-8 z-10 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg w-40">
                              {c.status === 'draft' && <button onClick={() => handleAction('activate', c.campaign_id)} disabled={!campaignsEnabled} className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 ${!campaignsEnabled ? 'opacity-50 cursor-not-allowed text-gray-400' : 'hover:bg-gray-50 dark:hover:bg-gray-700'}`}><Play className="w-3 h-3" /> Activate</button>}
                              {c.status === 'active' && <button onClick={() => handleAction('pause', c.campaign_id)} className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"><Pause className="w-3 h-3" /> Pause</button>}
                              {c.status === 'paused' && <button onClick={() => handleAction('resume', c.campaign_id)} disabled={!campaignsEnabled} className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 ${!campaignsEnabled ? 'opacity-50 cursor-not-allowed text-gray-400' : 'hover:bg-gray-50 dark:hover:bg-gray-700'}`}><Play className="w-3 h-3" /> Resume</button>}
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

        {/* Create Campaign Modal — Lead Selection Flow */}
        {showCreateModal && (
          <>
            <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowCreateModal(false)} />
            <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-[700px] max-w-[95vw] max-h-[85vh] overflow-y-auto">
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h2 className="text-lg font-bold dark:text-gray-100">New Campaign — Select Leads</h2>
                  <p className="text-sm text-gray-500 mt-0.5">Select leads to auto-create a campaign with contacts, sequence, and mailboxes</p>
                </div>
                <button onClick={() => setShowCreateModal(false)}><X className="w-5 h-5" /></button>
              </div>

              {/* Search & Stats */}
              <div className="flex items-center gap-3 mb-3">
                <input
                  value={availableLeadsSearch}
                  onChange={e => { setAvailableLeadsSearch(e.target.value); setAvailableLeadsPage(1) }}
                  className="flex-1 px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
                  placeholder="Search by job title or company..."
                />
                <span className="text-sm text-gray-500 whitespace-nowrap">
                  {selectedCreateLeadIds.size} of {availableLeadsTotal} selected
                </span>
              </div>

              {/* Leads Table */}
              <div className="border rounded-lg overflow-hidden dark:border-gray-700 mb-4">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 dark:bg-gray-700">
                    <tr>
                      <th className="px-3 py-2 text-left w-8">
                        <input
                          type="checkbox"
                          checked={availableLeads.length > 0 && availableLeads.every(l => selectedCreateLeadIds.has(l.lead_id))}
                          onChange={e => {
                            if (e.target.checked) {
                              setSelectedCreateLeadIds(prev => {
                                const next = new Set(prev)
                                availableLeads.forEach(l => next.add(l.lead_id))
                                return next
                              })
                            } else {
                              setSelectedCreateLeadIds(prev => {
                                const next = new Set(prev)
                                availableLeads.forEach(l => next.delete(l.lead_id))
                                return next
                              })
                            }
                          }}
                          className="w-4 h-4 rounded"
                        />
                      </th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Job Title</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Company</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">State</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Posted</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Contacts</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {availableLeadsLoading ? (
                      <tr><td colSpan={6} className="px-3 py-6 text-center text-gray-500">Loading leads...</td></tr>
                    ) : availableLeads.length === 0 ? (
                      <tr><td colSpan={6} className="px-3 py-6 text-center text-gray-500">No available leads found</td></tr>
                    ) : (
                      availableLeads.map(lead => (
                        <tr key={lead.lead_id} className={`hover:bg-gray-50 dark:hover:bg-gray-700 ${selectedCreateLeadIds.has(lead.lead_id) ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
                          <td className="px-3 py-2">
                            <input
                              type="checkbox"
                              checked={selectedCreateLeadIds.has(lead.lead_id)}
                              onChange={e => {
                                setSelectedCreateLeadIds(prev => {
                                  const next = new Set(prev)
                                  if (e.target.checked) next.add(lead.lead_id)
                                  else next.delete(lead.lead_id)
                                  return next
                                })
                              }}
                              className="w-4 h-4 rounded"
                            />
                          </td>
                          <td className="px-3 py-2 text-gray-900 dark:text-gray-100 max-w-[200px] truncate" title={lead.job_title}>{lead.job_title}</td>
                          <td className="px-3 py-2 text-gray-600 dark:text-gray-400 max-w-[150px] truncate">{lead.client_name}</td>
                          <td className="px-3 py-2 text-gray-500">{lead.state || '-'}</td>
                          <td className="px-3 py-2 text-gray-500">{lead.posting_date ? new Date(lead.posting_date).toLocaleDateString() : '-'}</td>
                          <td className="px-3 py-2"><span className="px-2 py-0.5 text-xs rounded-full bg-purple-100 text-purple-700">{lead.contact_count}</span></td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {availableLeadsPages > 1 && (
                <div className="flex justify-center gap-2 mb-4">
                  <button disabled={availableLeadsPage <= 1} onClick={() => setAvailableLeadsPage(p => p - 1)} className="px-3 py-1 border rounded text-sm disabled:opacity-50">Prev</button>
                  <span className="px-3 py-1 text-sm text-gray-500">Page {availableLeadsPage} of {availableLeadsPages}</span>
                  <button disabled={availableLeadsPage >= availableLeadsPages} onClick={() => setAvailableLeadsPage(p => p + 1)} className="px-3 py-1 border rounded text-sm disabled:opacity-50">Next</button>
                </div>
              )}

              {/* Preview Mode Toggle */}
              <div className="flex items-center justify-between py-2 mb-3 px-1">
                <div>
                  <label className="block text-sm font-medium">Preview & Approve Mode</label>
                  <p className="text-xs text-gray-500">Generate drafts for review instead of sending directly</p>
                </div>
                <button
                  type="button"
                  onClick={() => setCreatePreviewMode(!createPreviewMode)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${createPreviewMode ? 'bg-teal-600' : 'bg-gray-300 dark:bg-gray-600'}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${createPreviewMode ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>

              {/* Actions */}
              <div className="flex items-center justify-between pt-2 border-t dark:border-gray-700">
                <p className="text-sm text-gray-500">
                  {selectedCreateLeadIds.size} lead(s) selected — auto-generates name, 3-step sequence, assigns all active mailboxes
                </p>
                <div className="flex gap-3">
                  <button onClick={() => setShowCreateModal(false)} className="px-4 py-2 border rounded-lg text-sm">Cancel</button>
                  <button
                    onClick={handleCreateFromLeads}
                    disabled={selectedCreateLeadIds.size === 0 || creatingFromLeads}
                    className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm flex items-center gap-2"
                  >
                    {creatingFromLeads ? 'Creating...' : `Create Campaign (${selectedCreateLeadIds.size} leads)`}
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
            {(selectedCampaign as any)?.preview_mode && (
              <span className="px-2 py-1 rounded-full text-xs font-medium bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300">Preview Mode</span>
            )}
            <span className="text-sm text-gray-500">{selectedCampaign?.total_contacts} contacts</span>
            <span className="text-sm text-gray-500">{selectedCampaign?.total_sent} sent</span>
          </div>
        </div>
        <div className="flex gap-2">
          {selectedCampaign?.status === 'draft' && (
            <button onClick={() => handleAction('activate', selectedCampaign.campaign_id)} disabled={!campaignsEnabled} className={`px-4 py-2 text-white rounded-lg flex items-center gap-2 ${!campaignsEnabled ? 'bg-gray-400 cursor-not-allowed' : 'bg-green-600 hover:bg-green-700'}`} title={!campaignsEnabled ? 'Campaign execution is disabled for your organization' : ''}>
              <Play className="w-4 h-4" /> Activate
            </button>
          )}
          {selectedCampaign?.status === 'active' && (
            <button onClick={() => handleAction('pause', selectedCampaign.campaign_id)} className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 flex items-center gap-2">
              <Pause className="w-4 h-4" /> Pause
            </button>
          )}
          {selectedCampaign?.status === 'paused' && (
            <button onClick={() => handleAction('resume', selectedCampaign.campaign_id)} disabled={!campaignsEnabled} className={`px-4 py-2 text-white rounded-lg flex items-center gap-2 ${!campaignsEnabled ? 'bg-gray-400 cursor-not-allowed' : 'bg-green-600 hover:bg-green-700'}`} title={!campaignsEnabled ? 'Campaign execution is disabled for your organization' : ''}>
              <Play className="w-4 h-4" /> Resume
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
        {([
          { key: 'overview', label: 'Overview' },
          { key: 'mailboxes', label: 'Mailboxes' },
          { key: 'leads_contacts', label: 'Leads & Contacts' },
          { key: 'sequence', label: 'Sequence' },
          { key: 'schedule', label: 'Schedule' },
          { key: 'rules', label: 'Rules' },
          { key: 'activity', label: 'Activity' },
          { key: 'analytics', label: 'Analytics' },
        ] as const).map(tab => (
          <button key={tab.key} onClick={() => {
            setDetailTab(tab.key as any)
            if (tab.key === 'analytics' && selectedCampaign) loadAnalytics(selectedCampaign.campaign_id)
            if (tab.key === 'activity' && selectedCampaign) fetchActivity(selectedCampaign.campaign_id, activityFilter)
            if (tab.key === 'leads_contacts' && selectedCampaign) fetchContactSchedule(selectedCampaign.campaign_id)
            if (tab.key === 'schedule' && selectedCampaign) fetchContactSchedule(selectedCampaign.campaign_id)
          }}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap ${detailTab === tab.key ? 'border-primary-600 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {detailTab === 'overview' && selectedCampaign && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Campaign Info Card */}
            <div className="bg-white dark:bg-gray-800 border rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-gray-900 dark:text-gray-100">Campaign Details</h3>
                {!overviewEditing ? (
                  <button
                    onClick={() => {
                      setOverviewForm({
                        name: selectedCampaign.name || '',
                        description: selectedCampaign.description || '',
                        sending_speed: selectedCampaign.sending_speed || 'normal',
                      })
                      setOverviewEditing(true)
                    }}
                    className="text-xs text-primary-600 hover:text-primary-700 font-medium"
                  >
                    Edit
                  </button>
                ) : (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setOverviewEditing(false)}
                      className="text-xs text-gray-500 hover:text-gray-700"
                    >
                      Cancel
                    </button>
                    <button
                      disabled={overviewSaving}
                      onClick={async () => {
                        setOverviewSaving(true)
                        try {
                          const updated = await campaignsApi.update(selectedCampaign.campaign_id, {
                            name: overviewForm.name,
                            description: overviewForm.description || null,
                            sending_speed: overviewForm.sending_speed,
                          })
                          setSelectedCampaign(updated)
                          setCampaigns(prev => prev.map(c => c.campaign_id === updated.campaign_id ? updated : c))
                          setOverviewEditing(false)
                        } catch { /* toast handled by interceptor */ }
                        setOverviewSaving(false)
                      }}
                      className="text-xs bg-primary-600 text-white px-3 py-1 rounded hover:bg-primary-700 disabled:opacity-50"
                    >
                      {overviewSaving ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                )}
              </div>

              {/* Name */}
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Name</label>
                {overviewEditing ? (
                  <input
                    type="text"
                    value={overviewForm.name}
                    onChange={e => setOverviewForm(f => ({ ...f, name: e.target.value }))}
                    className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                  />
                ) : (
                  <p className="text-sm text-gray-900 dark:text-gray-100">{selectedCampaign.name}</p>
                )}
              </div>

              {/* Description */}
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Description</label>
                {overviewEditing ? (
                  <textarea
                    value={overviewForm.description}
                    onChange={e => setOverviewForm(f => ({ ...f, description: e.target.value }))}
                    rows={3}
                    className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                  />
                ) : (
                  <p className="text-sm text-gray-600 dark:text-gray-400">{selectedCampaign.description || 'No description'}</p>
                )}
              </div>

              {/* Campaign Owner */}
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Campaign Owner</label>
                <p className="text-sm text-gray-900 dark:text-gray-100">{selectedCampaign.created_by_name || 'Unknown'}</p>
              </div>

              {/* Sending Speed */}
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Sending Speed</label>
                {overviewEditing ? (
                  <select
                    value={overviewForm.sending_speed}
                    onChange={e => setOverviewForm(f => ({ ...f, sending_speed: e.target.value }))}
                    className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100 capitalize"
                  >
                    <option value="relaxed">Relaxed (120-300s delay)</option>
                    <option value="normal">Normal (30-90s delay)</option>
                    <option value="aggressive">Aggressive (5-15s delay)</option>
                  </select>
                ) : (
                  <span className="text-sm capitalize">{selectedCampaign.sending_speed || 'normal'}</span>
                )}
              </div>

              {/* Status & Mode + Action Buttons */}
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Status</label>
                    <span className={`px-2 py-1 text-xs rounded-full font-medium ${
                      selectedCampaign.status === 'active' ? 'bg-green-100 text-green-800' :
                      selectedCampaign.status === 'paused' ? 'bg-yellow-100 text-yellow-800' :
                      selectedCampaign.status === 'draft' ? 'bg-gray-100 text-gray-800' :
                      selectedCampaign.status === 'completed' ? 'bg-blue-100 text-blue-800' :
                      'bg-red-100 text-red-800'
                    }`}>
                      {selectedCampaign.status}
                    </span>
                  </div>
                  {selectedCampaign.preview_mode && (
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">Mode</label>
                      <span className="px-2 py-1 text-xs rounded-full bg-teal-100 text-teal-800">Preview & Approve</span>
                    </div>
                  )}
                </div>
                {/* Status action buttons — based on allowed transitions */}
                <div className="flex items-center gap-2 flex-wrap">
                  {selectedCampaign.status === 'draft' && (
                    <button
                      onClick={() => handleAction('activate', selectedCampaign.campaign_id)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-green-600 text-white hover:bg-green-700"
                    >
                      <Play className="w-3.5 h-3.5" /> Activate Campaign
                    </button>
                  )}
                  {selectedCampaign.status === 'active' && (
                    <>
                      <button
                        onClick={() => handleAction('pause', selectedCampaign.campaign_id)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-yellow-500 text-white hover:bg-yellow-600"
                      >
                        <Pause className="w-3.5 h-3.5" /> Pause
                      </button>
                      <button
                        onClick={() => handleAction('complete', selectedCampaign.campaign_id)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700"
                      >
                        <BarChart3 className="w-3.5 h-3.5" /> Mark Complete
                      </button>
                    </>
                  )}
                  {selectedCampaign.status === 'paused' && (
                    <>
                      <button
                        onClick={() => handleAction('resume', selectedCampaign.campaign_id)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-green-600 text-white hover:bg-green-700"
                      >
                        <Play className="w-3.5 h-3.5" /> Resume
                      </button>
                      <button
                        onClick={() => handleAction('complete', selectedCampaign.campaign_id)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700"
                      >
                        <BarChart3 className="w-3.5 h-3.5" /> Mark Complete
                      </button>
                    </>
                  )}
                </div>
              </div>

              {selectedCampaign.health_score !== null && selectedCampaign.health_score !== undefined && (
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Health Score</label>
                  <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs rounded-full font-medium ${
                    selectedCampaign.health_score >= 80 ? 'bg-green-100 text-green-800' :
                    selectedCampaign.health_score >= 50 ? 'bg-yellow-100 text-yellow-800' :
                    'bg-red-100 text-red-800'
                  }`}>
                    {selectedCampaign.health_score}%
                  </span>
                </div>
              )}
            </div>

            {/* Quick Stats Card */}
            <div className="bg-white dark:bg-gray-800 border rounded-lg p-4 space-y-3">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">Quick Stats</h3>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{selectedCampaign.total_contacts || 0}</p>
                  <p className="text-xs text-gray-500">Contacts</p>
                </div>
                <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-blue-600">{selectedCampaign.total_sent || 0}</p>
                  <p className="text-xs text-gray-500">Sent</p>
                </div>
                <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-green-600">{selectedCampaign.total_opened || 0}</p>
                  <p className="text-xs text-gray-500">Opened</p>
                </div>
                <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-purple-600">{selectedCampaign.total_replied || 0}</p>
                  <p className="text-xs text-gray-500">Replied</p>
                </div>
              </div>
              {(selectedCampaign.total_sent || 0) > 0 && (
                <div className="pt-2 border-t dark:border-gray-700 space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Open Rate</span>
                    <span className="font-medium">{((selectedCampaign.total_opened || 0) / selectedCampaign.total_sent * 100).toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Reply Rate</span>
                    <span className="font-medium">{((selectedCampaign.total_replied || 0) / selectedCampaign.total_sent * 100).toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Bounce Rate</span>
                    <span className="font-medium">{((selectedCampaign.total_bounced || 0) / selectedCampaign.total_sent * 100).toFixed(1)}%</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Mailboxes Tab */}
      {detailTab === 'mailboxes' && selectedCampaign && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">Assigned Mailboxes</h3>
            <button
              onClick={async () => {
                const allIds = mailboxes.map((m: any) => m.mailbox_id)
                const currentIds = selectedCampaign.mailbox_ids || []
                const newIds = currentIds.length === allIds.length ? [] : allIds
                try {
                  await campaignsApi.update(selectedCampaign.campaign_id, { mailbox_ids: newIds })
                  setSelectedCampaign({ ...selectedCampaign, mailbox_ids: newIds })
                } catch {}
              }}
              className="text-sm text-primary-600 hover:text-primary-700"
            >
              {(selectedCampaign.mailbox_ids || []).length === mailboxes.length ? 'Deselect All' : 'Select All'}
            </button>
          </div>
          <div className="border rounded-lg overflow-hidden dark:border-gray-700">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-4 py-2 text-left w-8"></th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Health</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Daily Limit</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Sent Today</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Warmup</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {mailboxes.map((m: any) => {
                  const isSelected = (selectedCampaign.mailbox_ids || []).includes(m.mailbox_id)
                  return (
                    <tr key={m.mailbox_id} className={`hover:bg-gray-50 dark:hover:bg-gray-700 ${isSelected ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
                      <td className="px-4 py-2">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={async (e) => {
                            const currentIds = selectedCampaign.mailbox_ids || []
                            const newIds = e.target.checked
                              ? [...currentIds, m.mailbox_id]
                              : currentIds.filter((id: number) => id !== m.mailbox_id)
                            try {
                              await campaignsApi.update(selectedCampaign.campaign_id, { mailbox_ids: newIds })
                              setSelectedCampaign({ ...selectedCampaign, mailbox_ids: newIds })
                            } catch {}
                          }}
                          className="w-4 h-4 rounded"
                        />
                      </td>
                      <td className="px-4 py-2 text-gray-900 dark:text-gray-100">{m.email}</td>
                      <td className="px-4 py-2">
                        <span className={`px-2 py-0.5 text-xs rounded-full ${m.health_score >= 80 ? 'bg-green-100 text-green-800' : m.health_score >= 50 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800'}`}>
                          {m.health_score || 0}%
                        </span>
                      </td>
                      <td className="px-4 py-2 text-gray-500">{m.daily_send_limit}</td>
                      <td className="px-4 py-2 text-gray-500">{m.emails_sent_today || 0}</td>
                      <td className="px-4 py-2">
                        <span className={`px-2 py-0.5 text-xs rounded-full ${m.warmup_status === 'completed' ? 'bg-green-100 text-green-800' : m.warmup_status === 'active' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'}`}>
                          {m.warmup_status || 'none'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
                {mailboxes.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-500">No mailboxes available</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Leads & Contacts Tab */}
      {detailTab === 'leads_contacts' && selectedCampaign && (
        <div className="space-y-4">
          {/* Contacts ordered by timezone */}
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">
              Enrolled Contacts <span className="text-sm font-normal text-gray-500">({contactSchedule.length} contacts, ordered East → West)</span>
            </h3>
            <span className="text-xs text-gray-400">Scroll down for enrollment management</span>
          </div>
          {scheduleLoading ? (
            <div className="text-center py-8 text-gray-500">Loading contacts...</div>
          ) : contactSchedule.length === 0 ? (
            <div className="text-center py-8 text-gray-500">No contacts enrolled yet</div>
          ) : (
            <div className="border rounded-lg overflow-hidden dark:border-gray-700">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-700">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Company</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Timezone</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Best Send Time</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Score</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {(() => {
                    let lastTzLabel = ''
                    return contactSchedule.map((cs: any, idx: number) => {
                      const showHeader = cs.timezone_label !== lastTzLabel
                      lastTzLabel = cs.timezone_label
                      return (
                        <React.Fragment key={cs.contact_id}>
                          {showHeader && (
                            <tr className="bg-gray-100 dark:bg-gray-600">
                              <td colSpan={7} className="px-4 py-1.5 text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wider">
                                {cs.timezone_label}
                              </td>
                            </tr>
                          )}
                          <tr className="hover:bg-gray-50 dark:hover:bg-gray-700">
                            <td className="px-4 py-2 text-gray-900 dark:text-gray-100">{cs.name}</td>
                            <td className="px-4 py-2 text-gray-500 max-w-[180px] truncate">{cs.email}</td>
                            <td className="px-4 py-2 text-gray-500">{cs.company || '-'}</td>
                            <td className="px-4 py-2 text-gray-500 text-xs">{cs.timezone_label}</td>
                            <td className="px-4 py-2 text-gray-500 text-xs">{cs.recommended_local_time || '-'}</td>
                            <td className="px-4 py-2">
                              <span className={`px-1.5 py-0.5 text-xs rounded ${cs.combined_score >= 0.8 ? 'bg-green-100 text-green-700' : cs.combined_score >= 0.5 ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-600'}`}>
                                {(cs.combined_score * 100).toFixed(0)}%
                              </span>
                            </td>
                            <td className="px-4 py-2">
                              <span className={`px-2 py-0.5 text-xs rounded-full ${cs.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                                {cs.status}
                              </span>
                            </td>
                          </tr>
                        </React.Fragment>
                      )
                    })
                  })()}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Schedule Tab */}
      {detailTab === 'schedule' && selectedCampaign && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Send Window Config */}
            <div className="bg-white dark:bg-gray-800 border rounded-lg p-4 space-y-3">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">Send Window</h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Start Time</label>
                  <p className="text-sm">{selectedCampaign.send_window_start || '09:00'}</p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">End Time</label>
                  <p className="text-sm">{selectedCampaign.send_window_end || '17:00'}</p>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Send Days</label>
                <div className="flex gap-1 flex-wrap">
                  {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((day, i) => {
                    const dayKey = day.toLowerCase().slice(0, 3)
                    const isActive = (selectedCampaign.send_days || []).includes(dayKey)
                    return (
                      <span key={day} className={`px-2 py-0.5 text-xs rounded ${isActive ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-400'}`}>
                        {day}
                      </span>
                    )
                  })}
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Campaign Timezone</label>
                <p className="text-sm">{selectedCampaign.timezone || 'UTC'}</p>
              </div>
            </div>

            {/* Smart Schedule Info */}
            <div className="bg-white dark:bg-gray-800 border rounded-lg p-4 space-y-3">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">Smart Scheduling</h3>
              <div className="bg-blue-50 dark:bg-blue-900/30 rounded-lg p-3">
                <p className="text-sm text-blue-700 dark:text-blue-300">
                  Emails are sent at optimal local times for each contact based on their timezone.
                  Peak windows: 9-11 AM (highest), 2-3:30 PM (second), 7:30-9 AM (third).
                </p>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Timezone Distribution</label>
                {contactSchedule.length > 0 ? (
                  <div className="space-y-1">
                    {Object.entries(
                      contactSchedule.reduce((acc: Record<string, number>, cs: any) => {
                        acc[cs.timezone_label] = (acc[cs.timezone_label] || 0) + 1
                        return acc
                      }, {})
                    ).map(([tz, count]) => (
                      <div key={tz} className="flex justify-between text-sm">
                        <span className="text-gray-600 dark:text-gray-400">{tz}</span>
                        <span className="font-medium">{count as number} contact{(count as number) !== 1 ? 's' : ''}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">No contacts enrolled</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Sequence Tab */}
      {detailTab === 'sequence' && (
        <div className="space-y-3">
          {/* View mode toggle */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5">
              <button
                onClick={() => setSequenceViewMode('list')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  sequenceViewMode === 'list' ? 'bg-white dark:bg-gray-600 shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <LayoutList className="w-3.5 h-3.5" /> List View
              </button>
              <button
                onClick={() => setSequenceViewMode('visual')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  sequenceViewMode === 'visual' ? 'bg-white dark:bg-gray-600 shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <Workflow className="w-3.5 h-3.5" /> Visual Builder
              </button>
            </div>
          </div>

          {/* Visual Builder */}
          {sequenceViewMode === 'visual' && steps.length > 0 && (
            <SequenceBuilder
              steps={steps}
              spamScores={stepSpamScores}
              onEditStep={(step) => {
                setEditingStep(step)
                setStepForm({
                  step_type: step.step_type as any,
                  subject: step.subject || '',
                  body_html: step.body_html || '',
                  body_text: step.body_text || '',
                  delay_days: step.delay_days,
                  delay_hours: step.delay_hours,
                  reply_to_thread: step.reply_to_thread,
                  condition_type: step.condition_type || '',
                  condition_window_hours: step.condition_window_hours || 24,
                  variants_json: step.variants_json || '',
                })
                setShowStepModal(true)
              }}
            />
          )}

          {/* List View (original) */}
          {sequenceViewMode === 'list' && steps.length === 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-8 text-center">
              <Mail className="w-10 h-10 mx-auto mb-3 text-gray-300" />
              <p className="font-medium text-gray-900 dark:text-gray-100">No steps yet</p>
              <p className="text-sm text-gray-500 mt-1">Add your first email step to build the sequence</p>
            </div>
          )}
          {sequenceViewMode === 'list' && steps.length > 0 && (
            steps.map((step, idx) => (
              <div key={step.step_id} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold ${
                    step.step_type === 'email' ? 'bg-blue-500' :
                    step.step_type === 'wait' ? 'bg-yellow-500' :
                    step.step_type === 'sms' ? 'bg-emerald-500' :
                    step.step_type === 'call' ? 'bg-orange-500' :
                    step.step_type === 'linkedin' ? 'bg-sky-600' :
                    'bg-purple-500'
                  }`}>
                    {idx + 1}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      {step.step_type === 'email' && <Mail className="w-4 h-4 text-blue-500" />}
                      {step.step_type === 'wait' && <Clock className="w-4 h-4 text-yellow-500" />}
                      {step.step_type === 'condition' && <GitBranch className="w-4 h-4 text-purple-500" />}
                      {step.step_type === 'sms' && <MessageSquare className="w-4 h-4 text-emerald-500" />}
                      {step.step_type === 'call' && <Phone className="w-4 h-4 text-orange-500" />}
                      {step.step_type === 'linkedin' && <Linkedin className="w-4 h-4 text-sky-600" />}
                      <span className="font-medium capitalize">{step.step_type}</span>
                      {step.step_type === 'email' && step.subject && <span className="text-sm text-gray-500">— {step.subject}</span>}
                      {step.delay_days > 0 && <span className="text-xs text-gray-400 ml-2">Wait {step.delay_days}d {step.delay_hours}h</span>}
                      {step.step_type === 'email' && stepSpamScores[step.step_id] && (() => {
                        const ss = stepSpamScores[step.step_id]
                        const colors: Record<string, string> = { clean: 'bg-green-100 text-green-700', low_risk: 'bg-yellow-100 text-yellow-700', medium_risk: 'bg-orange-100 text-orange-700', high_risk: 'bg-red-100 text-red-700', spam: 'bg-red-200 text-red-800' }
                        return <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${colors[ss.grade] || 'bg-gray-100 text-gray-600'}`}>Spam: {ss.grade.replace('_', ' ')}</span>
                      })()}
                    </div>
                    {step.step_type === 'email' && (
                      <div className="flex gap-4 mt-1 text-xs text-gray-500">
                        <span>Sent: {step.total_sent}</span>
                        <span>Opened: {step.total_opened}</span>
                        <span>Replied: {step.total_replied}</span>
                        <span>Bounced: {step.total_bounced}</span>
                        {step.variants_json && (
                          <button
                            onClick={(e) => { e.stopPropagation(); selectedCampaign && fetchAbStats(selectedCampaign.campaign_id, step.step_id) }}
                            className="text-primary-600 hover:underline"
                          >A/B Stats</button>
                        )}
                      </div>
                    )}
                    {/* A/B variant stats */}
                    {abStatsData[step.step_id]?.variants && abStatsData[step.step_id].variants.length > 0 && (
                      <div className="mt-2 border-t border-gray-100 dark:border-gray-700 pt-2">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-gray-400">
                              <th className="text-left py-1">Variant</th>
                              <th className="text-right py-1">Sent</th>
                              <th className="text-right py-1">Open%</th>
                              <th className="text-right py-1">Click%</th>
                              <th className="text-right py-1">Reply%</th>
                            </tr>
                          </thead>
                          <tbody>
                            {abStatsData[step.step_id].variants.map((v: any, vi: number) => (
                              <tr key={vi} className="border-t border-gray-50 dark:border-gray-800">
                                <td className="py-1 font-medium">Variant {String.fromCharCode(65 + vi)}</td>
                                <td className="py-1 text-right">{v.sent || 0}</td>
                                <td className="py-1 text-right">{v.open_rate?.toFixed(1) || '0.0'}%</td>
                                <td className="py-1 text-right">{v.click_rate?.toFixed(1) || '0.0'}%</td>
                                <td className="py-1 text-right text-green-600">{v.reply_rate?.toFixed(1) || '0.0'}%</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <button
                          onClick={() => selectedCampaign && campaignsApi.abOptimize(selectedCampaign.campaign_id, step.step_id).then(() => fetchAbStats(selectedCampaign.campaign_id, step.step_id))}
                          className="mt-1 text-xs text-primary-600 hover:underline"
                        >Optimize Winner</button>
                      </div>
                    )}
                  </div>
                  <div className="flex gap-1">
                    {step.step_type === 'email' && (
                      <>
                        <button
                          onClick={async () => {
                            if (!selectedCampaign) return
                            try {
                              const result = await emailPreviewApi.generateDrafts({
                                source: 'campaign',
                                campaign_id: selectedCampaign.campaign_id,
                                step_index: step.step_order,
                              })
                              if (result.batch_id) {
                                window.location.href = `/dashboard/email-preview?batch_id=${result.batch_id}&source=campaign`
                              }
                            } catch (err) { console.error(err) }
                          }}
                          className="p-1 hover:bg-teal-50 dark:hover:bg-teal-900/20 rounded"
                          title="Generate Previews"
                        >
                          <FileSearch className="w-4 h-4 text-teal-500" />
                        </button>
                        <button
                          onClick={async () => {
                            setSpintaxModal({ step })
                            setLoadingSpintax(true)
                            try {
                              const data = await deliverabilityApi.spintaxPreview({ text: step.body_html || '', count: 3, campaign_id: selectedCampaign?.campaign_id })
                              setSpintaxVariants(data.variants || [])
                            } catch { setSpintaxVariants([]) }
                            finally { setLoadingSpintax(false) }
                          }}
                          className="p-1 hover:bg-orange-50 dark:hover:bg-orange-900/20 rounded"
                          title="Preview Spintax Variations"
                        >
                          <Shuffle className="w-4 h-4 text-orange-500" />
                        </button>
                      </>
                    )}
                    <button onClick={() => { setEditingStep(step); setStepForm({ step_type: step.step_type as any, subject: step.subject || '', body_html: step.body_html || '', body_text: step.body_text || '', delay_days: step.delay_days, delay_hours: step.delay_hours, reply_to_thread: step.reply_to_thread, condition_type: step.condition_type || '', condition_window_hours: step.condition_window_hours || 24, variants_json: step.variants_json || '' }); setShowStepModal(true) }} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded">
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

      {/* Contacts Tab (also shows under leads_contacts for enrollment management) */}
      {(detailTab === 'leads_contacts') && (
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
                    <th className="text-right px-4 py-3 font-medium">Actions</th>
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
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => selectedCampaign && handleThreadPreview(selectedCampaign.campaign_id, cc.contact_id)}
                          className="text-xs text-primary-600 hover:underline"
                        >Preview Thread</button>
                      </td>
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
          {/* Date Range + Presets + Actions Bar */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Quick presets */}
            {[
              { label: '7d', days: 7 },
              { label: '30d', days: 30 },
              { label: '90d', days: 90 },
              { label: 'All', days: 0 },
            ].map(p => (
              <button
                key={p.label}
                onClick={() => {
                  if (p.days === 0) {
                    setAnalyticsDateFrom(''); setAnalyticsDateTo('')
                    selectedCampaign && loadAnalytics(selectedCampaign.campaign_id)
                  } else {
                    const from = new Date(Date.now() - p.days * 86400000).toISOString().split('T')[0]
                    const to = new Date().toISOString().split('T')[0]
                    setAnalyticsDateFrom(from); setAnalyticsDateTo(to)
                    selectedCampaign && loadAnalytics(selectedCampaign.campaign_id, from, to)
                  }
                }}
                className="px-2.5 py-1 border rounded text-xs font-medium hover:bg-gray-100 dark:hover:bg-gray-700 dark:border-gray-600"
              >{p.label}</button>
            ))}
            <span className="text-gray-300 dark:text-gray-600">|</span>
            <input
              type="date"
              value={analyticsDateFrom}
              onChange={e => setAnalyticsDateFrom(e.target.value)}
              className="px-3 py-1.5 border rounded-lg text-sm dark:bg-gray-700 dark:border-gray-600"
            />
            <span className="text-gray-400 text-sm">to</span>
            <input
              type="date"
              value={analyticsDateTo}
              onChange={e => setAnalyticsDateTo(e.target.value)}
              className="px-3 py-1.5 border rounded-lg text-sm dark:bg-gray-700 dark:border-gray-600"
            />
            <button
              onClick={() => selectedCampaign && loadAnalytics(selectedCampaign.campaign_id, analyticsDateFrom, analyticsDateTo)}
              className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
            >
              Apply
            </button>
            {(analyticsDateFrom || analyticsDateTo) && (
              <button
                onClick={() => { setAnalyticsDateFrom(''); setAnalyticsDateTo(''); selectedCampaign && loadAnalytics(selectedCampaign.campaign_id) }}
                className="text-sm text-gray-500 hover:text-gray-700 underline"
              >
                Clear
              </button>
            )}
            <div className="ml-auto flex gap-2">
              <button
                onClick={() => selectedCampaign && handleExportCsv(selectedCampaign.campaign_id)}
                className="px-3 py-1.5 border rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700"
                title="Export CSV"
              >
                Export CSV
              </button>
              <button
                onClick={() => setShowCompareModal(true)}
                className="px-3 py-1.5 border rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700"
                title="Compare Campaigns"
              >
                Compare
              </button>
            </div>
          </div>

          {/* Health Score Badge */}
          {selectedCampaign && selectedCampaign.health_score != null && (
            <div className="flex items-center gap-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
              <span className="text-sm text-gray-500">Health Score</span>
              <span className={`text-lg font-bold ${
                selectedCampaign.health_score >= 70 ? 'text-green-600' :
                selectedCampaign.health_score >= 40 ? 'text-yellow-600' : 'text-red-600'
              }`}>
                {selectedCampaign.health_score}/100
              </span>
              <div className="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-full">
                <div
                  className={`h-full rounded-full ${
                    selectedCampaign.health_score >= 70 ? 'bg-green-500' :
                    selectedCampaign.health_score >= 40 ? 'bg-yellow-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${selectedCampaign.health_score}%` }}
                />
              </div>
            </div>
          )}

          {!analytics ? (
            <div className="p-8 text-center text-gray-500">Loading analytics...</div>
          ) : (
            <>
              {/* Stat Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                {[
                  { label: 'Sent', value: analytics.overall?.total_sent || 0, color: 'text-blue-600' },
                  { label: 'Opened', value: analytics.overall?.total_opened || 0, sub: `${analytics.overall?.open_rate || 0}%`, color: 'text-purple-600' },
                  { label: 'Clicked', value: analytics.overall?.total_clicked || 0, sub: `${analytics.overall?.click_rate || 0}%`, color: 'text-cyan-600' },
                  { label: 'Replied', value: analytics.overall?.replied || 0, sub: `${analytics.overall?.reply_rate || 0}%`, color: 'text-green-600' },
                  { label: 'Bounced', value: analytics.overall?.bounced || 0, sub: `${analytics.overall?.bounce_rate || 0}%`, color: 'text-red-600' },
                  { label: 'Active', value: analytics.overall?.active || 0, color: 'text-gray-600' },
                ].map(s => (
                  <div key={s.label} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                    <p className="text-xs text-gray-500">{s.label}</p>
                    <p className={`text-xl font-bold mt-0.5 ${s.color}`}>{s.value}</p>
                    {s.sub && <p className="text-xs text-gray-400 mt-0.5">{s.sub}</p>}
                  </div>
                ))}
              </div>

              {/* Per-Step Metrics */}
              {analytics.steps && analytics.steps.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                  <h3 className="px-4 py-3 font-medium border-b border-gray-200 dark:border-gray-700">Per-Step Metrics</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 dark:bg-gray-900/50">
                        <tr>
                          <th className="text-left px-4 py-2">Step</th>
                          <th className="text-left px-4 py-2">Subject</th>
                          <th className="text-right px-3 py-2">Sent</th>
                          <th className="text-right px-3 py-2">Open %</th>
                          <th className="text-right px-3 py-2">Click %</th>
                          <th className="text-right px-3 py-2">Reply %</th>
                          <th className="text-right px-3 py-2">Bounce %</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                        {analytics.steps.map((s: any, i: number) => (
                          <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                            <td className="px-4 py-2 font-medium">Step {s.step_order}</td>
                            <td className="px-4 py-2 truncate max-w-48 text-gray-500" title={s.subject}>{s.subject || '—'}</td>
                            <td className="px-3 py-2 text-right">{s.sent}</td>
                            <td className="px-3 py-2 text-right">{s.open_rate?.toFixed(1) || '0.0'}%</td>
                            <td className="px-3 py-2 text-right">{s.click_rate?.toFixed(1) || '0.0'}%</td>
                            <td className="px-3 py-2 text-right font-medium text-green-600">{s.reply_rate?.toFixed(1) || '0.0'}%</td>
                            <td className="px-3 py-2 text-right text-red-500">{s.bounce_rate?.toFixed(1) || '0.0'}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Per-Variant Breakdown */}
              {analytics.steps?.some((s: any) => s.variants && s.variants.length > 0) && (
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                  <h3 className="px-4 py-3 font-medium border-b border-gray-200 dark:border-gray-700">A/B Variant Breakdown</h3>
                  <div className="divide-y divide-gray-200 dark:divide-gray-700">
                    {analytics.steps.filter((s: any) => s.variants && s.variants.length > 0).map((s: any) => (
                      <div key={s.step_id} className="p-3">
                        <p className="text-xs text-gray-500 mb-2 font-medium">Step {s.step_order}: {s.subject || '—'}</p>
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-gray-400">
                                <th className="text-left py-1 px-2">Variant</th>
                                <th className="text-right py-1 px-2">Sent</th>
                                <th className="text-right py-1 px-2">Open%</th>
                                <th className="text-right py-1 px-2">Click%</th>
                                <th className="text-right py-1 px-2">Reply%</th>
                                <th className="text-right py-1 px-2">Bounce%</th>
                                <th className="text-center py-1 px-2">Status</th>
                              </tr>
                            </thead>
                            <tbody>
                              {s.variants.map((v: any, vi: number) => {
                                const isLeader = s.variants.length > 1 && v.reply_rate === Math.max(...s.variants.map((x: any) => x.reply_rate || 0))
                                return (
                                  <tr key={vi}>
                                    <td className="py-1 px-2 font-medium">{v.subject || `Variant ${String.fromCharCode(65 + vi)}`}</td>
                                    <td className="py-1 px-2 text-right">{v.sent}</td>
                                    <td className="py-1 px-2 text-right">{v.open_rate?.toFixed(1) || '0.0'}%</td>
                                    <td className="py-1 px-2 text-right">{v.click_rate?.toFixed(1) || '0.0'}%</td>
                                    <td className="py-1 px-2 text-right text-green-600">{v.reply_rate?.toFixed(1) || '0.0'}%</td>
                                    <td className="py-1 px-2 text-right text-red-500">{v.bounce_rate?.toFixed(1) || '0.0'}%</td>
                                    <td className="py-1 px-2 text-center">
                                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                        isLeader ? 'bg-green-100 text-green-700' : v.sent < 30 ? 'bg-gray-100 text-gray-500' : 'bg-yellow-100 text-yellow-700'
                                      }`}>
                                        {isLeader ? 'Leader' : v.sent < 30 ? 'Collecting' : 'Trailing'}
                                      </span>
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Funnel */}
              {analytics.funnel && analytics.funnel.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                  <h3 className="font-medium mb-3">Contact Funnel</h3>
                  <div className="flex items-end gap-2 h-32">
                    {analytics.funnel.map((f: any, i: number) => {
                      const maxContacts = Math.max(...analytics.funnel.map((x: any) => x.contacts_at_step), 1)
                      const height = Math.max(8, (f.contacts_at_step / maxContacts) * 100)
                      return (
                        <div key={i} className="flex-1 flex flex-col items-center gap-1">
                          <span className="text-xs font-medium">{f.contacts_at_step}</span>
                          <div
                            className="w-full bg-blue-500 rounded-t"
                            style={{ height: `${height}%` }}
                            title={`Step ${f.step_order}: ${f.contacts_at_step} contacts`}
                          />
                          <span className="text-xs text-gray-400">S{f.step_order}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Activity Tab */}
      {detailTab === 'activity' && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <select
              value={activityFilter}
              onChange={e => { setActivityFilter(e.target.value); selectedCampaign && fetchActivity(selectedCampaign.campaign_id, e.target.value) }}
              className="px-3 py-1.5 border rounded-lg text-sm dark:bg-gray-700 dark:border-gray-600"
            >
              <option value="all">All Events</option>
              <option value="sent">Sent</option>
              <option value="opened">Opened</option>
              <option value="clicked">Clicked</option>
              <option value="replied">Replied</option>
              <option value="bounced">Bounced</option>
            </select>
            <button
              onClick={() => selectedCampaign && fetchActivity(selectedCampaign.campaign_id, activityFilter)}
              className="px-3 py-1.5 border rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-1"
            >
              <Activity className="w-3 h-3" /> Refresh
            </button>
            <span className="text-xs text-gray-400">Auto-refreshes every 10s</span>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
            {activityLoading ? (
              <div className="p-8 text-center text-gray-500"><Loader2 className="w-5 h-5 animate-spin mx-auto" /></div>
            ) : activityEvents.length === 0 ? (
              <div className="p-8 text-center text-gray-500">No activity yet</div>
            ) : (
              <div className="divide-y divide-gray-100 dark:divide-gray-700 max-h-[500px] overflow-y-auto">
                {activityEvents.map((ev: any) => {
                  const iconMap: Record<string, any> = {
                    sent: <Mail className="w-4 h-4 text-blue-500" />,
                    opened: <Eye className="w-4 h-4 text-purple-500" />,
                    clicked: <MousePointerClick className="w-4 h-4 text-cyan-500" />,
                    replied: <Reply className="w-4 h-4 text-green-500" />,
                    bounced: <AlertTriangle className="w-4 h-4 text-red-500" />,
                  }
                  const colorMap: Record<string, string> = {
                    sent: 'bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400',
                    opened: 'bg-purple-50 text-purple-700 dark:bg-purple-900/20 dark:text-purple-400',
                    clicked: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-900/20 dark:text-cyan-400',
                    replied: 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400',
                    bounced: 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400',
                  }
                  return (
                    <div key={ev.event_id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-700/30">
                      {iconMap[ev.event_type] || <Mail className="w-4 h-4 text-gray-400" />}
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{ev.contact_name}</span>
                        <span className="text-xs text-gray-500 ml-2">{ev.contact_email}</span>
                      </div>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${colorMap[ev.event_type] || 'bg-gray-100 text-gray-600'}`}>
                        {ev.event_type}
                      </span>
                      {ev.step_order && <span className="text-xs text-gray-400">Step {ev.step_order}</span>}
                      <span className="text-xs text-gray-400 whitespace-nowrap">
                        {ev.timestamp ? new Date(ev.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Compare Modal */}
      {showCompareModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-3xl max-h-[80vh] overflow-auto p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Compare Campaigns</h2>
              <button onClick={() => { setShowCompareModal(false); setCompareData(null); setCompareIds([]) }} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>

            {/* Select campaigns */}
            <div className="mb-4">
              <p className="text-sm text-gray-500 mb-2">Select 2-10 campaigns to compare:</p>
              <div className="max-h-40 overflow-y-auto border rounded-lg divide-y dark:border-gray-700 dark:divide-gray-700">
                {campaigns.map(c => (
                  <label key={c.campaign_id} className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-700/30 cursor-pointer text-sm">
                    <input
                      type="checkbox"
                      checked={compareIds.includes(c.campaign_id)}
                      onChange={() => setCompareIds(prev => prev.includes(c.campaign_id) ? prev.filter(id => id !== c.campaign_id) : [...prev, c.campaign_id])}
                    />
                    <span className={`px-2 py-0.5 rounded text-xs ${statusColors[c.status] || ''}`}>{c.status}</span>
                    {c.name}
                  </label>
                ))}
              </div>
              <button
                onClick={handleCompare}
                disabled={compareIds.length < 2 || compareLoading}
                className="mt-3 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
              >
                {compareLoading ? 'Comparing...' : `Compare ${compareIds.length} Campaigns`}
              </button>
            </div>

            {/* Comparison Table */}
            {compareData && compareData.campaigns && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 dark:bg-gray-900/50">
                    <tr>
                      <th className="text-left px-3 py-2">Metric</th>
                      {compareData.campaigns.map((c: any) => (
                        <th key={c.campaign_id} className="text-right px-3 py-2 max-w-32 truncate" title={c.name}>{c.name}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {['total_contacts', 'total_sent', 'open_rate', 'click_rate', 'reply_rate', 'bounce_rate'].map(metric => (
                      <tr key={metric}>
                        <td className="px-3 py-2 font-medium capitalize">{metric.replace(/_/g, ' ')}</td>
                        {compareData.campaigns.map((c: any) => (
                          <td key={c.campaign_id} className="px-3 py-2 text-right">
                            {metric.includes('rate') ? `${c[metric]}%` : c[metric]}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
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
                  <option value="sms">SMS</option>
                  <option value="call">Call</option>
                  <option value="linkedin">LinkedIn</option>
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
              {stepForm.step_type === 'sms' && (
                <div>
                  <label className="block text-sm font-medium mb-1">SMS Body</label>
                  <textarea value={stepForm.body_text} onChange={e => setStepForm(f => ({ ...f, body_text: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" rows={4} placeholder="Hi {{first_name}}, ..." />
                  <p className="text-xs text-gray-400 mt-1">Max 160 chars recommended. Supports {'{{first_name}}'}, {'{{company}}'} placeholders and {'{'} spintax {'}'}</p>
                </div>
              )}
              {stepForm.step_type === 'call' && (
                <div>
                  <label className="block text-sm font-medium mb-1">TwiML URL or Script</label>
                  <input value={stepForm.body_text} onChange={e => setStepForm(f => ({ ...f, body_text: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" placeholder="https://your-domain.com/twiml/script" />
                  <p className="text-xs text-gray-400 mt-1">URL to TwiML instructions for the call, or leave empty for a simple dial</p>
                </div>
              )}
              {stepForm.step_type === 'linkedin' && (
                <div className="bg-sky-50 dark:bg-sky-900/20 border border-sky-200 dark:border-sky-800 rounded-lg p-3">
                  <p className="text-sm text-sky-700 dark:text-sky-300 flex items-center gap-2">
                    <Linkedin className="w-4 h-4" />
                    LinkedIn automation requires a browser extension (coming soon)
                  </p>
                  <p className="text-xs text-sky-600 dark:text-sky-400 mt-1">The campaign engine will skip this step and advance to the next one until the extension is configured.</p>
                </div>
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
      {/* Thread Preview Modal */}
      {showThreadPreviewModal && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowThreadPreviewModal(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-[600px] max-w-[90vw] max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-semibold text-lg">Email Thread Preview</h3>
                {threadPreview && <p className="text-sm text-gray-500">{threadPreview.contact_name}</p>}
              </div>
              <button onClick={() => setShowThreadPreviewModal(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            {threadPreviewLoading ? (
              <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
            ) : !threadPreview?.steps?.length ? (
              <p className="text-sm text-gray-500 text-center py-8">No steps to preview</p>
            ) : (
              <div className="space-y-3">
                {threadPreview.steps.map((step: any, i: number) => (
                  <div key={i}>
                    {step.step_type === 'email' ? (
                      <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                        <div className="bg-gray-50 dark:bg-gray-900/50 px-4 py-2 flex items-center gap-2">
                          <Mail className="w-4 h-4 text-blue-500" />
                          <span className="text-xs font-medium text-gray-500">Step {step.step_order} — Email</span>
                        </div>
                        <div className="px-4 py-3">
                          <p className="font-medium text-sm mb-2">{step.subject || '(no subject)'}</p>
                          <div className="text-sm text-gray-600 dark:text-gray-400 prose prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: step.body_html || '' }} />
                        </div>
                      </div>
                    ) : step.step_type === 'wait' ? (
                      <div className="flex items-center justify-center py-2">
                        <div className="flex items-center gap-2 text-xs text-gray-400 bg-gray-50 dark:bg-gray-900/30 px-3 py-1.5 rounded-full">
                          <Clock className="w-3 h-3" />
                          Wait {step.delay_days}d {step.delay_hours}h
                        </div>
                      </div>
                    ) : step.step_type === 'condition' ? (
                      <div className="flex items-center justify-center py-2">
                        <div className="flex items-center gap-2 text-xs text-purple-500 bg-purple-50 dark:bg-purple-900/20 px-3 py-1.5 rounded-full">
                          <GitBranch className="w-3 h-3" />
                          If {step.condition_type} within {step.condition_window_hours}h
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-center py-2">
                        <div className="flex items-center gap-2 text-xs text-gray-400 bg-gray-50 dark:bg-gray-900/30 px-3 py-1.5 rounded-full capitalize">
                          {step.step_type} step
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {/* Spintax Preview Modal */}
      {spintaxModal && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setSpintaxModal(null)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-[500px] max-w-[90vw] max-h-[70vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold flex items-center gap-2">
                <Shuffle className="w-4 h-4 text-orange-500" />
                Spintax Preview
              </h3>
              <button onClick={() => setSpintaxModal(null)} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
            </div>
            {loadingSpintax ? (
              <div className="flex items-center justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-gray-400" /></div>
            ) : spintaxVariants.length <= 1 ? (
              <p className="text-sm text-gray-500 text-center py-4">No spintax patterns found in this step</p>
            ) : (
              <div className="space-y-3">
                {spintaxVariants.map((v, i) => (
                  <div key={i} className="p-3 border border-gray-200 dark:border-gray-700 rounded-lg">
                    <div className="text-xs text-gray-400 mb-1 font-medium">Variant #{i + 1}</div>
                    <div className="text-sm text-gray-700 dark:text-gray-300" dangerouslySetInnerHTML={{ __html: v }} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
