'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import DOMPurify from 'dompurify'
import { campaignsApi, contactsApi, leadsApi, mailboxesApi, emailPreviewApi, pipelinesApi, deliverabilityApi, templatesApi, api } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import type { Campaign, SequenceStep, CampaignContact, RenderingCheckResult, HumanizeResult, SpintaxPreviewResult, TemplateScorecardResult, TemplateFixesResult, ApplyFixesResult } from '@/types/api'
import {
  Plus, Search, MoreVertical, Play, Pause, Copy, Trash2, ChevronDown, ChevronRight,
  Mail, Clock, GitBranch, ArrowUp, ArrowDown, X, Zap, Users, BarChart3, Eye, Settings,
  FileSearch, Loader2, AlertTriangle, Shuffle, MessageSquare, Phone, Linkedin,
  MousePointerClick, Reply, Activity, LayoutList, Workflow, Send,
  Brain, Upload, PenLine, Table2, ArrowLeft, CheckCircle2, XCircle, FileText, Link2, Download,
  Filter, ChevronUp, ChevronsUpDown,
  Sparkles, RefreshCw, Wrench, Monitor, Info, GripVertical, CheckCircle,
  Bold, Italic, Underline, AlignLeft, AlignCenter, AlignRight, List, ListOrdered, Palette,
} from 'lucide-react'
import dynamic from 'next/dynamic'
import { ContactsWizard } from '@/components/contacts-wizard'

const SequenceBuilder = dynamic(() => import('@/components/sequence-builder'), { ssr: false })

// ─── Available Leads Filter Constants ─────────────────────────────
const LEAD_STATUS_OPTIONS = [
  { value: 'new', label: 'New' },
  { value: 'enriched', label: 'Enriched' },
  { value: 'validated', label: 'Validated' },
  { value: 'open', label: 'Open' },
  { value: 'hunting', label: 'Hunting' },
  { value: 'sent', label: 'Sent' },
  { value: 'skipped', label: 'Skipped' },
  { value: 'closed_hired', label: 'Closed-Hired' },
  { value: 'closed_not_hired', label: 'Closed-Not-Hired' },
  { value: 'closed_test', label: 'Closed-Test' },
]

const LEAD_SOURCE_OPTIONS = ['jsearch', 'apollo', 'indeed', 'linkedin', 'glassdoor', 'theirstack', 'serpapi', 'adzuna', 'searchapi', 'usajobs', 'jooble', 'jobdatafeeds', 'coresignal', 'mock', 'import']

const EMPLOYMENT_TYPE_OPTIONS = ['Full-time', 'Contract', 'Part-time', 'Temporary', 'Internship']

const WIZARD_US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
]

type AvailableLeadsSortField = 'job_title' | 'client_name' | 'state' | 'employment_type' | 'posting_date' | 'source'

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

const TIMEZONE_OPTIONS = [
  { value: 'US/Eastern', label: 'Eastern (ET)' },
  { value: 'US/Central', label: 'Central (CT)' },
  { value: 'US/Mountain', label: 'Mountain (MT)' },
  { value: 'US/Pacific', label: 'Pacific (PT)' },
  { value: 'America/Anchorage', label: 'Alaska (AKT)' },
  { value: 'Pacific/Honolulu', label: 'Hawaii (HT)' },
  { value: 'UTC', label: 'UTC' },
]

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const

const statusColors: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  active: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  paused: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  completed: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  archived: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  previewing: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300',
  sending: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
}

/** Compute a user-friendly display label that combines status + preview_mode */
function getCampaignDisplayStatus(c: { status: string; preview_mode?: boolean }): { label: string; colorKey: string; description: string } {
  if (c.status === 'active' && c.preview_mode) {
    return { label: 'Previewing', colorKey: 'previewing', description: 'Generating drafts for review' }
  }
  if (c.status === 'active') {
    return { label: 'Sending', colorKey: 'sending', description: 'Sending emails to contacts' }
  }
  if (c.status === 'paused' && c.preview_mode) {
    return { label: 'Paused', colorKey: 'paused', description: 'Preview mode — paused' }
  }
  if (c.status === 'paused') {
    return { label: 'Paused', colorKey: 'paused', description: 'Campaign paused' }
  }
  if (c.status === 'draft') {
    return { label: 'Draft', colorKey: 'draft', description: 'Not yet activated' }
  }
  if (c.status === 'completed') {
    return { label: 'Completed', colorKey: 'completed', description: 'All contacts processed' }
  }
  if (c.status === 'archived') {
    return { label: 'Archived', colorKey: 'archived', description: 'Campaign archived' }
  }
  return { label: c.status, colorKey: c.status, description: '' }
}

// ─── Step Modal Intelligence Panel Constants ─────────────────────
const STEP_PLACEHOLDERS = [
  { tag: '{{contact_first_name}}', label: 'Recipient first name' },
  { tag: '{{sender_first_name}}', label: 'Sender first name' },
  { tag: '{{job_title}}', label: 'Job title from lead' },
  { tag: '{{job_location}}', label: 'Job location' },
  { tag: '{{company_name}}', label: 'Company name' },
  { tag: '{{signature}}', label: 'Mailbox email signature' },
  { tag: '{{logo_url}}', label: 'Company logo URL' },
  { tag: '{{unsubscribe_link}}', label: 'Unsubscribe link' },
]

const STEP_DIMENSION_LABELS: Record<string, string> = {
  spam_risk: 'Spam Risk', rendering: 'Rendering', humanization: 'Humanization',
  personalization: 'Personalization', subject_quality: 'Subject Quality',
  clarity: 'Clarity', cta_quality: 'CTA Quality', compliance: 'Compliance',
  content_entropy: 'Content Entropy', word_count: 'Word Count',
}

const STEP_DIMENSION_ORDER = [
  'spam_risk', 'rendering', 'humanization', 'personalization', 'subject_quality',
  'clarity', 'cta_quality', 'compliance', 'content_entropy', 'word_count',
]

type StepIntelligenceTab = 'placeholders' | 'scorecard' | 'fixes' | 'spam' | 'rendering' | 'humanize' | 'spintax'

const STEP_INTEL_TABS: { id: StepIntelligenceTab; label: string; icon: typeof Info }[] = [
  { id: 'placeholders', label: 'Vars', icon: Info },
  { id: 'scorecard', label: 'Score', icon: BarChart3 },
  { id: 'fixes', label: 'Fixes', icon: Wrench },
  { id: 'spam', label: 'Spam', icon: AlertTriangle },
  { id: 'rendering', label: 'Render', icon: Monitor },
  { id: 'humanize', label: 'Human', icon: Brain },
  { id: 'spintax', label: 'Spintax', icon: Shuffle },
]

function stepSpamBadgeColor(grade: string) {
  switch (grade) {
    case 'clean': return 'bg-green-100 text-green-800'
    case 'low_risk': return 'bg-yellow-100 text-yellow-800'
    case 'medium_risk': return 'bg-orange-100 text-orange-800'
    case 'high_risk': return 'bg-red-100 text-red-800'
    case 'spam': return 'bg-red-200 text-red-900'
    default: return 'bg-gray-100 text-gray-700'
  }
}

function stepScoreColor(score: number): string {
  if (score >= 80) return '#22c55e'
  if (score >= 60) return '#eab308'
  if (score >= 40) return '#f97316'
  return '#ef4444'
}

function StepScoreGauge({ score, size = 120 }: { score: number; size?: number }) {
  const radius = (size - 16) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference
  const color = stepScoreColor(score)
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#e5e7eb" strokeWidth="8" />
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth="8" strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round" className="transition-all duration-700" />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-2xl font-bold" style={{ color }}>{Math.round(score)}</span>
      </div>
    </div>
  )
}

export default function CampaignsPage() {
  const router = useRouter()
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
  const [expandedLeads, setExpandedLeads] = useState<Set<number | string>>(new Set())
  const [detailTab, setDetailTab] = useState<'overview' | 'mailboxes' | 'leads_contacts' | 'sequence' | 'schedule' | 'rules' | 'activity' | 'analytics'>('overview')

  // Available leads for campaign creation
  const [availableLeads, setAvailableLeads] = useState<any[]>([])
  const [availableLeadsTotal, setAvailableLeadsTotal] = useState(0)
  const [availableLeadsPage, setAvailableLeadsPage] = useState(1)
  const [availableLeadsPageSize, setAvailableLeadsPageSize] = useState(50)
  const [availableLeadsPages, setAvailableLeadsPages] = useState(1)
  const [availableLeadsSearch, setAvailableLeadsSearch] = useState('')
  const [availableLeadsLoading, setAvailableLeadsLoading] = useState(false)
  const [availableLeadsDays, setAvailableLeadsDays] = useState(7)
  const [selectedCreateLeadIds, setSelectedCreateLeadIds] = useState<Set<number>>(new Set())
  const [createPreviewMode, setCreatePreviewMode] = useState(false)
  const [creatingFromLeads, setCreatingFromLeads] = useState(false)
  const [createScheduleExpanded, setCreateScheduleExpanded] = useState(false)
  const [contactsWizardLead, setContactsWizardLead] = useState<{lead_id: number; client_name: string; job_title: string} | null>(null)

  // Available leads filters
  const [alFilterStatus, setAlFilterStatus] = useState('')
  const [alFilterSource, setAlFilterSource] = useState('')
  const [alFilterEmploymentType, setAlFilterEmploymentType] = useState('')
  const [alFilterState, setAlFilterState] = useState<string[]>([])
  const [alFilterIndustry, setAlFilterIndustry] = useState<string[]>([])
  const [alFilterCompanySize, setAlFilterCompanySize] = useState<string[]>([])
  const [alFilterExcludeKeywords, setAlFilterExcludeKeywords] = useState<string[]>([])
  const [alFilterTitle, setAlFilterTitle] = useState<string[]>([])
  const [alShowMoreFilters, setAlShowMoreFilters] = useState(false)
  const [alFilterOptions, setAlFilterOptions] = useState<{ industries: string[]; company_sizes: string[]; exclusion_keywords: { it_keywords: string[]; staffing_keywords: string[] }; job_titles: string[]; job_title_categories?: Record<string, string[]> }>({ industries: [], company_sizes: [], exclusion_keywords: { it_keywords: [], staffing_keywords: [] }, job_titles: [] })
  const [alSortBy, setAlSortBy] = useState<AvailableLeadsSortField>('posting_date')
  const [alSortOrder, setAlSortOrder] = useState<'asc' | 'desc'>('desc')

  // Contact schedule state
  const [contactSchedule, setContactSchedule] = useState<any[]>([])
  const [scheduleLoading, setScheduleLoading] = useState(false)

  // Mailbox campaign stats + health
  const [mailboxStats, setMailboxStats] = useState<any[]>([])
  const [mailboxStatsLoading, setMailboxStatsLoading] = useState(false)
  const [mailboxHealthMap, setMailboxHealthMap] = useState<Record<number, any>>({})

  // Overview edit state
  const [overviewEditing, setOverviewEditing] = useState(false)
  const [overviewForm, setOverviewForm] = useState({ name: '', description: '', sending_speed: 'normal' })
  const [overviewSaving, setOverviewSaving] = useState(false)

  // Multi-schedule state
  const [campaignSchedules, setCampaignSchedules] = useState<any[]>([])
  const [schedulesLoading, setSchedulesLoading] = useState(false)
  const [scheduleModalOpen, setScheduleModalOpen] = useState(false)
  const [scheduleModalMode, setScheduleModalMode] = useState<'add' | 'edit'>('add')
  const [editingScheduleId, setEditingScheduleId] = useState<number | null>(null)
  const [scheduleFormData, setScheduleFormData] = useState({
    start_date: new Date().toISOString().split('T')[0],
    end_date: '',
    send_window_start: '09:00',
    send_window_end: '17:00',
    send_days: ['mon', 'tue', 'wed', 'thu', 'fri'] as string[],
    timezone: 'US/Eastern',
    label: '',
    no_end_date: true,
  })
  const [scheduleSaving, setScheduleSaving] = useState(false)

  // Step spam scores
  const [stepSpamScores, setStepSpamScores] = useState<Record<number, { grade: string; score: number }>>({})
  const [spintaxModal, setSpintaxModal] = useState<{ step: SequenceStep } | null>(null)
  const [spintaxVariants, setSpintaxVariants] = useState<string[]>([])
  const [loadingSpintax, setLoadingSpintax] = useState(false)

  // AI Personalization Preview
  const [aiPreviewResults, setAiPreviewResults] = useState<any[] | null>(null)
  const [aiPreviewLoading, setAiPreviewLoading] = useState(false)
  const [showAIPreviewModal, setShowAIPreviewModal] = useState(false)

  // Template selection for step modal
  const [stepTemplates, setStepTemplates] = useState<any[]>([])
  const [stepTemplatesLoading, setStepTemplatesLoading] = useState(false)
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [activeOutreachTemplateId, setActiveOutreachTemplateId] = useState<number | null>(null)
  const [activeFollowupTemplateId, setActiveFollowupTemplateId] = useState<number | null>(null)

  // Step-level spam + deliverability check in modal
  const [modalSpamResult, setModalSpamResult] = useState<any>(null)
  const [modalSpamLoading, setModalSpamLoading] = useState(false)
  const [modalDeliverabilityResult, setModalDeliverabilityResult] = useState<any>(null)
  const [modalDeliverabilityLoading, setModalDeliverabilityLoading] = useState(false)

  // Step intelligence panel state
  const [stepIntelTab, setStepIntelTab] = useState<StepIntelligenceTab>('placeholders')
  const [stepSpamSuggestions, setStepSpamSuggestions] = useState<{original: string; replacement: string}[]>([])
  const [stepSpamReduceResult, setStepSpamReduceResult] = useState<{before_score: number; after_score: number; before_grade: string; after_grade: string; delta: number} | null>(null)
  const [stepRenderingResult, setStepRenderingResult] = useState<RenderingCheckResult | null>(null)
  const [stepRenderingLoading, setStepRenderingLoading] = useState(false)
  const [stepHumanizeResult, setStepHumanizeResult] = useState<HumanizeResult | null>(null)
  const [stepHumanizeLoading, setStepHumanizeLoading] = useState(false)
  const [stepHumanizeIntensity, setStepHumanizeIntensity] = useState<string>('medium')
  const [stepSpintaxResult, setStepSpintaxResult] = useState<SpintaxPreviewResult | null>(null)
  const [stepSpintaxLoading, setStepSpintaxLoading] = useState(false)
  const [stepScorecardResult, setStepScorecardResult] = useState<TemplateScorecardResult | null>(null)
  const [stepScorecardLoading, setStepScorecardLoading] = useState(false)
  const [stepExpandedDimensions, setStepExpandedDimensions] = useState<Set<string>>(new Set())
  const [stepFixesResult, setStepFixesResult] = useState<TemplateFixesResult | null>(null)
  const [stepFixesLoading, setStepFixesLoading] = useState(false)
  const [stepApplyingFixes, setStepApplyingFixes] = useState(false)
  const [stepSelectedFixIds, setStepSelectedFixIds] = useState<Set<string>>(new Set())
  const [stepApplyResult, setStepApplyResult] = useState<ApplyFixesResult | null>(null)
  const [stepRewriting, setStepRewriting] = useState(false)
  const [stepShowPreview, setStepShowPreview] = useState(false)
  const [stepSpamResult, setStepSpamResult] = useState<{score: number; grade: string; flagged_words: any[]; suggestions: {original: string; replacement: string}[]} | null>(null)
  const [stepSpamLoading, setStepSpamLoading] = useState(false)

  // Refs for step modal fields
  const stepBodyRef = useRef<HTMLTextAreaElement>(null)
  const stepSubjectRef = useRef<HTMLInputElement>(null)

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

  // Health detail popover state
  const [healthDetail, setHealthDetail] = useState<any>(null)
  const [healthDetailLoading, setHealthDetailLoading] = useState(false)
  const [healthDetailOpen, setHealthDetailOpen] = useState<'sidebar' | 'analytics' | null>(null)

  const fetchHealthDetail = useCallback(async (campaignId: number, location: 'sidebar' | 'analytics') => {
    if (healthDetailOpen === location) {
      setHealthDetailOpen(null)
      return
    }
    setHealthDetailOpen(location)
    setHealthDetailLoading(true)
    try {
      const data = await campaignsApi.health(campaignId)
      setHealthDetail(data)
    } catch {
      setHealthDetail(null)
    } finally {
      setHealthDetailLoading(false)
    }
  }, [healthDetailOpen])

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

  // Mailbox tab search/sort
  const [mailboxSearch, setMailboxSearch] = useState('')
  const [mailboxSortCol, setMailboxSortCol] = useState<string>('')
  const [mailboxSortDir, setMailboxSortDir] = useState<'asc' | 'desc'>('asc')

  // Contact removal state
  const [removeContactIds, setRemoveContactIds] = useState<Set<number>>(new Set())

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

  // Wizard step state
  const [createStep, setCreateStep] = useState<'source' | 'ai_check' | 'pipeline_running' | 'csv_upload' | 'csv_preview' | 'manual_entry' | 'google_sheet' | 'google_preview' | 'select_leads'>('source')
  const [autoSelectLeadIds, setAutoSelectLeadIds] = useState<number[]>([])

  // AI check (existing leads check before pipeline)
  const [aiCheckLoading, setAiCheckLoading] = useState(false)
  const [aiCheckLeadCount, setAiCheckLeadCount] = useState(0)

  // Pipeline running
  const [pipelineRunning, setPipelineRunning] = useState(false)
  const [pipelineStatus, setPipelineStatus] = useState('')
  const [pipelineProgress, setPipelineProgress] = useState(0)
  const [pipelineFailed, setPipelineFailed] = useState(false)

  // CSV upload
  const csvFileRef = useRef<HTMLInputElement>(null)
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvUploading, setCsvUploading] = useState(false)
  const [csvPreviewData, setCsvPreviewData] = useState<any>(null)
  const [csvImporting, setCsvImporting] = useState(false)
  const [csvSkipDuplicates, setCsvSkipDuplicates] = useState(true)

  // Manual entry
  interface ManualEntry { client_name: string; job_title: string; state: string; job_link: string; salary_min: string; salary_max: string; first_name: string; last_name: string; email: string; phone: string; title: string }
  const emptyEntry: ManualEntry = { client_name: '', job_title: '', state: '', job_link: '', salary_min: '', salary_max: '', first_name: '', last_name: '', email: '', phone: '', title: '' }
  const [manualEntries, setManualEntries] = useState<ManualEntry[]>([{ ...emptyEntry }])
  const [manualSubmitting, setManualSubmitting] = useState(false)

  // Google Sheet
  const [googleSheetUrl, setGoogleSheetUrl] = useState('')
  const [googleSheetLoading, setGoogleSheetLoading] = useState(false)
  const [googleSheetPreview, setGoogleSheetPreview] = useState<any>(null)
  const [googleSheetImporting, setGoogleSheetImporting] = useState(false)
  const [googleSkipDuplicates, setGoogleSkipDuplicates] = useState(true)

  // Bulk selection (Super Admin only)
  const { user } = useAuthStore()
  const isSuperAdmin = user?.role === 'super_admin'
  const [selectedCampaignIds, setSelectedCampaignIds] = useState<Set<number>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const fetchCampaigns = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page, page_size: 20 }
      if (search) params.search = search
      if (statusFilter) params.status = statusFilter
      const data = await campaignsApi.list(params)
      setCampaigns(data.items || [])
      setTotalPages(data.pages || 1)
      setSelectedCampaignIds(new Set())
    } catch {
      setCampaigns([])
    } finally {
      setLoading(false)
    }
  }, [page, search, statusFilter])

  const searchParams = useSearchParams()

  useEffect(() => { fetchCampaigns() }, [fetchCampaigns])

  // Fetch available leads for the create modal
  // Build filter params for available-leads API
  const buildAlFilterParams = useCallback(() => {
    const params: Record<string, any> = { days: availableLeadsDays }
    if (availableLeadsSearch) params.search = availableLeadsSearch
    if (alFilterStatus) params.status = alFilterStatus
    if (alFilterSource) params.source = alFilterSource
    if (alFilterEmploymentType) params.employment_type = alFilterEmploymentType
    if (alFilterState.length > 0) params.state = alFilterState
    if (alFilterIndustry.length > 0) params.industry = alFilterIndustry
    if (alFilterCompanySize.length > 0) params.company_size = alFilterCompanySize
    if (alFilterExcludeKeywords.length > 0) params.exclude_keywords = alFilterExcludeKeywords
    if (alFilterTitle.length > 0) params.title = alFilterTitle
    if (alSortBy !== 'posting_date') params.sort_by = alSortBy
    if (alSortOrder !== 'desc') params.sort_order = alSortOrder
    return params
  }, [availableLeadsDays, availableLeadsSearch, alFilterStatus, alFilterSource, alFilterEmploymentType, alFilterState, alFilterIndustry, alFilterCompanySize, alFilterExcludeKeywords, alFilterTitle, alSortBy, alSortOrder])

  const fetchAvailableLeads = useCallback(async () => {
    setAvailableLeadsLoading(true)
    try {
      const params: Record<string, any> = { ...buildAlFilterParams(), page: availableLeadsPage, page_size: availableLeadsPageSize === 0 ? Math.max(availableLeadsTotal, 500) : availableLeadsPageSize }
      if (autoSelectLeadIds.length > 0) params.prioritize_ids = autoSelectLeadIds
      const data = await campaignsApi.getAvailableLeads(params)
      setAvailableLeads(data.items || [])
      setAvailableLeadsTotal(data.total || 0)
      setAvailableLeadsPages(data.pages || 1)
      // Auto-select imported lead IDs if coming from import, otherwise select all
      if (autoSelectLeadIds.length > 0) {
        setSelectedCreateLeadIds(new Set(autoSelectLeadIds))
      } else if (!availableLeadsSearch && !alFilterStatus && !alFilterSource && !alFilterEmploymentType && alFilterState.length === 0 && alFilterIndustry.length === 0 && alFilterCompanySize.length === 0 && alFilterExcludeKeywords.length === 0 && alFilterTitle.length === 0 && availableLeadsPage === 1) {
        const allIds = new Set<number>((data.items || []).map((l: any) => l.lead_id))
        if ((data.pages || 1) > 1 && (data.total || 0) > 0) {
          try {
            const allData = await campaignsApi.getAvailableLeads({ ...buildAlFilterParams(), page: 1, page_size: data.total })
            ;(allData.items || []).forEach((l: any) => allIds.add(l.lead_id))
          } catch { /* fallback: only page 1 selected */ }
        }
        setSelectedCreateLeadIds(allIds)
      }
    } catch {
      setAvailableLeads([])
    } finally {
      setAvailableLeadsLoading(false)
    }
  }, [availableLeadsPage, availableLeadsPageSize, availableLeadsSearch, availableLeadsDays, autoSelectLeadIds, buildAlFilterParams, alFilterStatus, alFilterSource, alFilterEmploymentType, alFilterState, alFilterIndustry, alFilterCompanySize, alFilterExcludeKeywords, alFilterTitle])

  useEffect(() => {
    if (showCreateModal && createStep === 'select_leads') fetchAvailableLeads()
  }, [showCreateModal, createStep, fetchAvailableLeads])

  // Fetch dynamic filter options (industries, company_sizes) when entering select_leads
  useEffect(() => {
    if (showCreateModal && createStep === 'select_leads') {
      leadsApi.filterOptions().then((opts: any) => {
        setAlFilterOptions({
          industries: opts.industries || [],
          company_sizes: opts.company_sizes || [],
          exclusion_keywords: opts.exclusion_keywords || { it_keywords: [], staffing_keywords: [] },
          job_titles: opts.job_titles || [],
          job_title_categories: opts.job_title_categories || undefined,
        })
      }).catch(() => {})
    }
  }, [showCreateModal, createStep])

  // Open create modal with wizard reset
  const openCreateModal = () => {
    setCreateStep('source')
    setAutoSelectLeadIds([])
    setAiCheckLoading(false); setAiCheckLeadCount(0)
    setPipelineRunning(false); setPipelineStatus(''); setPipelineProgress(0); setPipelineFailed(false)
    setCsvFile(null); setCsvPreviewData(null); setCsvSkipDuplicates(true)
    setManualEntries([{ ...emptyEntry }])
    setGoogleSheetUrl(''); setGoogleSheetPreview(null); setGoogleSkipDuplicates(true)
    setAvailableLeadsDays(7)
    setAlFilterStatus(''); setAlFilterSource(''); setAlFilterEmploymentType('')
    setAlFilterState([]); setAlFilterIndustry([]); setAlFilterCompanySize([])
    setAlFilterExcludeKeywords([]); setAlFilterTitle([])
    setAlShowMoreFilters(false)
    setAlSortBy('posting_date'); setAlSortOrder('desc')
    setShowCreateModal(true)
  }

  // Wizard handlers
  // Step 1: Check existing leads in DB before running pipeline
  const handleAiLeadCheck = async () => {
    setCreateStep('ai_check')
    setAiCheckLoading(true)
    setAiCheckLeadCount(0)
    try {
      const data = await campaignsApi.getAvailableLeads({ page: 1, page_size: 1, days: 30 })
      const total = data.total || 0
      setAiCheckLeadCount(total)
    } catch {
      setAiCheckLeadCount(0)
    } finally {
      setAiCheckLoading(false)
    }
  }

  // Step 2: Use existing leads directly (skip pipeline)
  const handleUseExistingLeads = () => {
    setAvailableLeadsDays(30)
    setCreateStep('select_leads')
  }

  // Step 3: Run the actual lead sourcing pipeline
  const handleStartPipeline = async () => {
    setCreateStep('pipeline_running')
    setPipelineRunning(true)
    setPipelineStatus('Starting lead sourcing...')
    setPipelineProgress(5)
    setPipelineFailed(false)
    try {
      await pipelinesApi.runLeadSourcing(['linkedin', 'indeed'])
      // Poll for completion — runs endpoint returns a flat array, uses pipeline_name/limit params
      let attempts = 0
      const maxAttempts = 200
      const poll = async () => {
        while (attempts < maxAttempts) {
          attempts++
          await new Promise(r => setTimeout(r, 3000))
          try {
            const allRuns: any[] = await pipelinesApi.runs({ limit: 10 })
            const lsRuns = allRuns.filter((r: any) => r.pipeline_name === 'lead_sourcing')
            const latest = lsRuns[0]
            if (!latest) continue
            const s = latest.status?.toLowerCase()
            if (s === 'completed') {
              setPipelineProgress(100)
              setPipelineStatus(`Lead sourcing complete! ${latest.records_success || 0} leads found`)
              setPipelineRunning(false)
              setTimeout(() => {
                setAvailableLeadsDays(7)
                setCreateStep('select_leads')
              }, 1500)
              return
            } else if (s === 'failed') {
              setPipelineStatus(latest.error_message || 'Lead sourcing failed')
              setPipelineRunning(false)
              setPipelineFailed(true)
              return
            } else {
              const backendPct = latest.progress_pct || 0
              const timePct = Math.min(85, 5 + (attempts / maxAttempts) * 80)
              const progress = Math.max(backendPct, timePct)
              setPipelineProgress(progress)
              setPipelineStatus(`Sourcing leads... (${Math.round(progress)}%)`)
            }
          } catch { /* continue polling */ }
        }
        setPipelineStatus('Timed out waiting for pipeline')
        setPipelineRunning(false)
        setPipelineFailed(true)
      }
      await poll()
    } catch (err: any) {
      setPipelineStatus(err?.response?.data?.detail || 'Failed to start pipeline')
      setPipelineRunning(false)
      setPipelineFailed(true)
    }
  }

  const handleCsvFileSelect = async (file: File) => {
    setCsvFile(file)
    setCsvUploading(true)
    try {
      const preview = await leadsApi.importPreview(file)
      setCsvPreviewData(preview)
      setCreateStep('csv_preview')
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to preview CSV')
    } finally {
      setCsvUploading(false)
    }
  }

  const handleCsvImport = async () => {
    if (!csvFile) return
    setCsvImporting(true)
    try {
      const result = await leadsApi.importCsv(csvFile, csvSkipDuplicates)
      setAutoSelectLeadIds(result.imported_lead_ids || [])
      setAvailableLeadsDays(365)
      setCreateStep('select_leads')
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to import CSV')
    } finally {
      setCsvImporting(false)
    }
  }

  const handleManualSubmit = async () => {
    const validEntries = manualEntries.filter(e => e.client_name.trim() && e.job_title.trim())
    if (validEntries.length === 0) return
    setManualSubmitting(true)
    const leadIds: number[] = []
    try {
      for (const entry of validEntries) {
        const leadData: any = {
          client_name: entry.client_name.trim(),
          job_title: entry.job_title.trim(),
          state: entry.state.trim().slice(0, 2).toUpperCase(),
          job_link: entry.job_link.trim() || undefined,
          source: 'manual',
          posting_date: new Date().toISOString().split('T')[0],
        }
        if (entry.salary_min) leadData.salary_min = parseFloat(entry.salary_min)
        if (entry.salary_max) leadData.salary_max = parseFloat(entry.salary_max)
        const lead = await leadsApi.create(leadData)
        leadIds.push(lead.lead_id)

        // If email provided, create a contact and link it
        if (entry.email.trim()) {
          try {
            await api.post('/contacts', {
              client_name: entry.client_name.trim(),
              first_name: entry.first_name.trim() || 'Unknown',
              last_name: entry.last_name.trim() || 'Contact',
              email: entry.email.trim(),
              phone: entry.phone.trim() || undefined,
              title: entry.title.trim() || entry.job_title.trim(),
              lead_id: lead.lead_id,
              source: 'manual',
            })
          } catch { /* contact creation is best-effort */ }
        }
      }
      setAutoSelectLeadIds(leadIds)
      setAvailableLeadsDays(365)
      setCreateStep('select_leads')
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to create leads')
    } finally {
      setManualSubmitting(false)
    }
  }

  const handleGoogleSheetPreview = async () => {
    if (!googleSheetUrl.trim()) return
    setGoogleSheetLoading(true)
    try {
      const preview = await leadsApi.importGoogleSheetPreview(googleSheetUrl.trim())
      setGoogleSheetPreview(preview)
      setCreateStep('google_preview')
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to preview Google Sheet')
    } finally {
      setGoogleSheetLoading(false)
    }
  }

  const handleGoogleSheetImport = async () => {
    setGoogleSheetImporting(true)
    try {
      const result = await leadsApi.importGoogleSheet(googleSheetUrl.trim(), googleSkipDuplicates)
      setAutoSelectLeadIds(result.imported_lead_ids || [])
      setAvailableLeadsDays(365)
      setCreateStep('select_leads')
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to import Google Sheet')
    } finally {
      setGoogleSheetImporting(false)
    }
  }

  // Create campaign from selected leads
  const handleCreateFromLeads = async () => {
    if (selectedCreateLeadIds.size === 0) return
    setCreatingFromLeads(true)
    try {
      const data = await campaignsApi.createFromLeads({
        lead_ids: Array.from(selectedCreateLeadIds),
        preview_mode: createPreviewMode,
        timezone: campaignForm.timezone,
        send_window_start: campaignForm.send_window_start,
        send_window_end: campaignForm.send_window_end,
        send_days: campaignForm.send_days,
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

  // Fetch campaign schedule entries
  const fetchSchedules = async (campaignId: number) => {
    setSchedulesLoading(true)
    try {
      const data = await campaignsApi.listSchedules(campaignId)
      setCampaignSchedules(data.schedules || [])
    } catch {
      setCampaignSchedules([])
    } finally {
      setSchedulesLoading(false)
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

  const fetchMailboxStats = async (campaignId: number) => {
    setMailboxStatsLoading(true)
    try {
      const data = await campaignsApi.getMailboxStats(campaignId)
      setMailboxStats(data || [])
      // Fetch health for each mailbox in parallel
      if (data && data.length > 0) {
        Promise.allSettled(
          data.map((m: any) => deliverabilityApi.mailboxHealth(m.mailbox_id).then((h: any) => ({ id: m.mailbox_id, data: h })))
        ).then(results => {
          const hMap: Record<number, any> = {}
          for (const r of results) {
            if (r.status === 'fulfilled' && r.value) hMap[r.value.id] = r.value.data
          }
          setMailboxHealthMap(hMap)
        })
      }
    } catch {
      setMailboxStats([])
    } finally {
      setMailboxStatsLoading(false)
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

  // Auto-open wizard at select_leads step when navigated with ?create_from_leads=1,2,3
  useEffect(() => {
    const fromLeads = searchParams.get('create_from_leads')
    if (fromLeads) {
      const ids = fromLeads.split(',').map(Number).filter(n => !isNaN(n) && n > 0)
      if (ids.length > 0) {
        setAutoSelectLeadIds(ids)
        setAvailableLeadsDays(365)
        setShowCreateModal(true)
        setCreateStep('select_leads')
      }
      // Clear the param from URL
      const url = new URL(window.location.href)
      url.searchParams.delete('create_from_leads')
      router.replace(url.pathname + url.search, { scroll: false })
    }
  }, [searchParams]) // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch feature status on mount
  useEffect(() => {
    pipelinesApi.getFeatureStatus()
      .then(fs => setCampaignsEnabled(fs.campaigns_enabled ?? true))
      .catch(() => { /* defaults to enabled */ })
  }, [])

  const openDetail = async (campaign: Campaign) => {
    setSelectedCampaign(campaign)
    setExpandedLeads(new Set())
    setRemoveContactIds(new Set())
    setMailboxSearch('')
    setMailboxSortCol('')
    setHealthDetailOpen(null)
    setHealthDetail(null)
    setView('detail')
    setDetailTab('overview')
    try {
      const [stepsData, contactsData] = await Promise.all([
        campaignsApi.listSteps(campaign.campaign_id),
        campaignsApi.listContacts(campaign.campaign_id, { page: 1, page_size: 1000 }),
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

  const handleRemoveContacts = async (contactIds: number[]) => {
    if (!selectedCampaign || contactIds.length === 0) return
    if (!confirm(`Remove ${contactIds.length} contact(s) from this campaign?`)) return
    try {
      await campaignsApi.removeContacts(selectedCampaign.campaign_id, contactIds)
      setContacts(prev => prev.filter(c => !contactIds.includes(c.contact_id)))
      setRemoveContactIds(new Set())
    } catch { /* ignore */ }
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

  const togglePreviewMode = async (campaignId: number, currentPreviewMode: boolean) => {
    try {
      const updated = await campaignsApi.update(campaignId, { preview_mode: !currentPreviewMode })
      setSelectedCampaign(updated)
      setCampaigns(prev => prev.map(c => c.campaign_id === updated.campaign_id ? updated : c))
    } catch { /* ignore */ }
  }

  const toggleSelectAll = () => {
    if (selectedCampaignIds.size === campaigns.length) {
      setSelectedCampaignIds(new Set())
    } else {
      setSelectedCampaignIds(new Set(campaigns.map(c => c.campaign_id)))
    }
  }

  const toggleSelect = (id: number) => {
    setSelectedCampaignIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleBulkArchive = async () => {
    if (selectedCampaignIds.size === 0) return
    if (!confirm(`Archive ${selectedCampaignIds.size} campaign(s)? Their contacts will be disassociated and become available for other campaigns.`)) return
    setBulkDeleting(true)
    try {
      await campaignsApi.bulkArchive(Array.from(selectedCampaignIds))
      setSelectedCampaignIds(new Set())
      fetchCampaigns()
    } catch { /* ignore */ }
    setBulkDeleting(false)
  }

  const openStepModal = (step: SequenceStep | null) => {
    if (step) {
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
      setSelectedTemplateId(step.template_id || null)
    } else {
      setEditingStep(null)
      setStepForm(defaultStep)
      setSelectedTemplateId(null)
    }
    // Reset modal checks
    setModalSpamResult(null)
    setModalDeliverabilityResult(null)
    resetStepIntelligence()
    setShowStepModal(true)
    // Fetch templates
    setStepTemplatesLoading(true)
    templatesApi.list().then((data: any) => {
      setStepTemplates(data.items || [])
      setActiveOutreachTemplateId(data.active_outreach_template_id || null)
      setActiveFollowupTemplateId(data.active_followup_template_id || null)
      const allItems = data.items || []
      if (!step) {
        // Auto-load template for new email steps
        // Step 1 (first email) → active outreach template (prefer tenant's industry)
        // Step 3+ (subsequent emails) → active followup template (prefer tenant's industry)
        const emailStepsCount = steps.filter(s => s.step_type === 'email').length
        const isFirstEmail = emailStepsCount === 0
        const targetCategory = isFirstEmail ? 'outreach' : 'followup'
        const fallbackId = isFirstEmail
          ? data.active_outreach_template_id
          : data.active_followup_template_id

        // Prefer active template matching tenant's industry in the target category
        const tenantIndustry = user?.tenant?.industry
        const industryActive = tenantIndustry
          ? allItems.find(
              (t: any) => t.status === 'active' && t.category === targetCategory && t.industry === tenantIndustry
            )
          : null
        const autoTemplateId = industryActive?.template_id || fallbackId

        if (autoTemplateId) {
          const tpl = allItems.find((t: any) => t.template_id === autoTemplateId)
          if (tpl) {
            setSelectedTemplateId(tpl.template_id)
            setStepForm(f => ({
              ...f,
              subject: tpl.subject || f.subject,
              body_html: tpl.body_html || f.body_html,
              body_text: tpl.body_text || f.body_text,
            }))
          }
        }
      } else if (step.template_id) {
        // Editing existing step with a linked template — auto-load its content
        const tpl = allItems.find((t: any) => t.template_id === step.template_id)
        if (tpl) {
          setStepForm(f => ({
            ...f,
            subject: tpl.subject || f.subject,
            body_html: tpl.body_html || f.body_html,
            body_text: tpl.body_text || f.body_text,
          }))
        }
      }
    }).catch(() => {}).finally(() => setStepTemplatesLoading(false))
  }

  const handleModalSpamCheck = async () => {
    setModalSpamLoading(true)
    setModalSpamResult(null)
    try {
      const result = await emailPreviewApi.spamCheck({
        subject: stepForm.subject,
        body_html: stepForm.body_html,
      })
      setModalSpamResult(result)
    } catch { /* ignore */ }
    setModalSpamLoading(false)
  }

  const handleModalDeliverabilityCheck = async () => {
    setModalDeliverabilityLoading(true)
    setModalDeliverabilityResult(null)
    try {
      // Use first assigned mailbox or 0 as fallback
      const mailboxId = selectedMailboxIds[0] || 0
      const result = await emailPreviewApi.deliverabilityScore({
        mailbox_id: mailboxId,
        subject: stepForm.subject,
        body_html: stepForm.body_html,
      })
      setModalDeliverabilityResult(result)
    } catch { /* ignore */ }
    setModalDeliverabilityLoading(false)
  }

  // ─── Step Intelligence Panel Handlers ──────────────────────────
  const resetStepIntelligence = useCallback(() => {
    setStepSpamResult(null)
    setStepSpamReduceResult(null)
    setStepRenderingResult(null)
    setStepHumanizeResult(null)
    setStepSpintaxResult(null)
    setStepScorecardResult(null)
    setStepFixesResult(null)
    setStepSelectedFixIds(new Set())
    setStepApplyResult(null)
    setStepExpandedDimensions(new Set())
    setStepShowPreview(false)
    setStepIntelTab('placeholders')
  }, [])

  const handleStepSpamCheck = useCallback(async () => {
    if (!stepForm.subject && !stepForm.body_html) return
    setStepSpamLoading(true)
    try {
      const data = await emailPreviewApi.spamCheck({ subject: stepForm.subject, body_html: stepForm.body_html })
      setStepSpamResult(data)
    } catch (err) { console.error(err) }
    finally { setStepSpamLoading(false) }
  }, [stepForm.subject, stepForm.body_html])

  const handleStepApplyAllSpamFixes = useCallback(async () => {
    if (!stepSpamResult?.suggestions || stepSpamResult.suggestions.length === 0) return
    try {
      const data = await deliverabilityApi.spamReduce({
        subject: stepForm.subject,
        body_html: stepForm.body_html,
        replacements: stepSpamResult.suggestions.map(s => ({ original: s.original, replacement: s.replacement })),
      })
      setStepSpamReduceResult({ before_score: data.before_score, after_score: data.after_score, before_grade: data.before_grade, after_grade: data.after_grade, delta: data.delta })
      setStepForm(prev => ({ ...prev, subject: data.new_subject, body_html: data.new_body_html }))
      setStepSpamResult(prev => prev ? { ...prev, suggestions: [] } : null)
    } catch (err) { console.error(err) }
  }, [stepForm.subject, stepForm.body_html, stepSpamResult])

  const handleStepSingleSpamFix = useCallback(async (original: string, replacement: string) => {
    try {
      const data = await deliverabilityApi.spamReduce({
        subject: stepForm.subject,
        body_html: stepForm.body_html,
        replacements: [{ original, replacement }],
      })
      setStepForm(prev => ({ ...prev, subject: data.new_subject, body_html: data.new_body_html }))
      setStepSpamResult(prev => {
        if (!prev) return null
        return { ...prev, suggestions: prev.suggestions.filter(s => s.original !== original) }
      })
    } catch (err) { console.error(err) }
  }, [stepForm.subject, stepForm.body_html])

  const handleStepRenderingCheck = useCallback(async () => {
    if (!stepForm.body_html) return
    setStepRenderingLoading(true)
    try {
      const data = await deliverabilityApi.renderingCheck({ body_html: stepForm.body_html })
      setStepRenderingResult(data)
    } catch (err) { console.error(err) }
    finally { setStepRenderingLoading(false) }
  }, [stepForm.body_html])

  const handleStepHumanize = useCallback(async () => {
    if (!stepForm.body_html) return
    setStepHumanizeLoading(true)
    try {
      const data = await deliverabilityApi.humanize({
        subject: stepForm.subject,
        body_html: stepForm.body_html,
        body_text: stepForm.body_text || '',
        intensity: stepHumanizeIntensity,
      })
      setStepHumanizeResult(data)
    } catch (err) { console.error(err) }
    finally { setStepHumanizeLoading(false) }
  }, [stepForm.subject, stepForm.body_html, stepForm.body_text, stepHumanizeIntensity])

  const handleStepApplyHumanize = useCallback(() => {
    if (!stepHumanizeResult) return
    setStepForm(prev => ({
      ...prev,
      subject: stepHumanizeResult.subject,
      body_html: stepHumanizeResult.body_html,
      body_text: stepHumanizeResult.body_text || prev.body_text,
    }))
    resetStepIntelligence()
  }, [stepHumanizeResult, resetStepIntelligence])

  const handleStepSpintaxPreview = useCallback(async () => {
    if (!stepForm.body_html) return
    setStepSpintaxLoading(true)
    try {
      const data = await deliverabilityApi.spintaxPreview({ text: stepForm.body_html, count: 5 })
      setStepSpintaxResult(data)
    } catch (err) { console.error(err) }
    finally { setStepSpintaxLoading(false) }
  }, [stepForm.body_html])

  const handleStepScorecard = useCallback(async () => {
    if (!stepForm.subject && !stepForm.body_html) return
    setStepScorecardLoading(true)
    try {
      const data = await templatesApi.score({ subject: stepForm.subject, body_html: stepForm.body_html, body_text: stepForm.body_text || '' })
      setStepScorecardResult(data)
    } catch (err) { console.error(err) }
    finally { setStepScorecardLoading(false) }
  }, [stepForm.subject, stepForm.body_html, stepForm.body_text])

  const handleStepGetFixes = useCallback(async () => {
    if (!stepForm.subject && !stepForm.body_html) return
    setStepFixesLoading(true)
    setStepApplyResult(null)
    try {
      const data = await templatesApi.fixes({ subject: stepForm.subject, body_html: stepForm.body_html, body_text: stepForm.body_text || '' })
      setStepFixesResult(data)
      const autoIds = new Set<string>(data.fixes.filter((f: any) => f.auto_fixable).map((f: any) => f.id))
      setStepSelectedFixIds(autoIds)
    } catch (err) { console.error(err) }
    finally { setStepFixesLoading(false) }
  }, [stepForm.subject, stepForm.body_html, stepForm.body_text])

  const handleStepApplySelectedFixes = useCallback(async () => {
    if (stepSelectedFixIds.size === 0) return
    setStepApplyingFixes(true)
    try {
      const data = await templatesApi.applyFixes({
        subject: stepForm.subject,
        body_html: stepForm.body_html,
        body_text: stepForm.body_text || '',
        fix_ids: Array.from(stepSelectedFixIds),
      })
      setStepForm(prev => ({
        ...prev,
        subject: data.subject,
        body_html: data.body_html,
        body_text: data.body_text || prev.body_text,
      }))
      setStepApplyResult(data)
      setStepFixesResult(null)
      setStepSelectedFixIds(new Set())
      setStepScorecardResult(null)
    } catch (err) { console.error(err) }
    finally { setStepApplyingFixes(false) }
  }, [stepForm.subject, stepForm.body_html, stepForm.body_text, stepSelectedFixIds])

  const handleStepAiRewrite = useCallback(async () => {
    if (!stepForm.body_html) return
    setStepRewriting(true)
    try {
      const data = await deliverabilityApi.humanize({
        subject: stepForm.subject,
        body_html: stepForm.body_html,
        body_text: stepForm.body_text || '',
        intensity: 'heavy',
      })
      setStepForm(prev => ({
        ...prev,
        subject: data.subject,
        body_html: data.body_html,
        body_text: data.body_text || prev.body_text,
      }))
      resetStepIntelligence()
    } catch (err) { console.error(err) }
    finally { setStepRewriting(false) }
  }, [stepForm.subject, stepForm.body_html, stepForm.body_text, resetStepIntelligence])

  const applyStepFormatting = useCallback((tag: string, attr?: string) => {
    const el = stepBodyRef.current
    if (!el) return
    const start = el.selectionStart ?? 0
    const end = el.selectionEnd ?? 0
    if (start === end) return
    const selected = el.value.slice(start, end)
    const openTag = attr ? `<${tag} ${attr}>` : `<${tag}>`
    const closeTag = `</${tag}>`
    const newVal = el.value.slice(0, start) + openTag + selected + closeTag + el.value.slice(end)
    setStepForm(prev => ({ ...prev, body_html: newVal }))
    requestAnimationFrame(() => {
      el.focus()
      const newPos = start + openTag.length + selected.length + closeTag.length
      el.setSelectionRange(newPos, newPos)
    })
  }, [])

  const handleStepPlaceholderClick = useCallback((tag: string) => {
    const el = stepBodyRef.current
    if (!el) {
      setStepForm(prev => ({ ...prev, body_html: prev.body_html + tag }))
      return
    }
    const start = el.selectionStart ?? el.value.length
    const end = el.selectionEnd ?? start
    const before = el.value.slice(0, start)
    const after = el.value.slice(end)
    setStepForm(prev => ({ ...prev, body_html: before + tag + after }))
    requestAnimationFrame(() => {
      el.focus()
      const pos = start + tag.length
      el.setSelectionRange(pos, pos)
    })
  }, [])

  // Drag-and-drop handlers for placeholders
  const handlePlaceholderDragStart = useCallback((e: React.DragEvent, tag: string) => {
    e.dataTransfer.setData('text/plain', tag)
    e.dataTransfer.effectAllowed = 'copy'
  }, [])

  const handleDropOnBody = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const tag = e.dataTransfer.getData('text/plain')
    if (!tag) return
    const el = stepBodyRef.current
    if (!el) {
      setStepForm(prev => ({ ...prev, body_html: prev.body_html + tag }))
      return
    }
    // Get drop position from caret position in textarea
    el.focus()
    const start = el.selectionStart ?? el.value.length
    const before = el.value.slice(0, start)
    const after = el.value.slice(start)
    setStepForm(prev => ({ ...prev, body_html: before + tag + after }))
    requestAnimationFrame(() => {
      el.focus()
      const pos = start + tag.length
      el.setSelectionRange(pos, pos)
    })
  }, [])

  const handleDropOnSubject = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const tag = e.dataTransfer.getData('text/plain')
    if (!tag) return
    const el = stepSubjectRef.current
    if (!el) {
      setStepForm(prev => ({ ...prev, subject: prev.subject + tag }))
      return
    }
    el.focus()
    const start = el.selectionStart ?? el.value.length
    const before = el.value.slice(0, start)
    const after = el.value.slice(start)
    setStepForm(prev => ({ ...prev, subject: before + tag + after }))
    requestAnimationFrame(() => {
      el.focus()
      const pos = start + tag.length
      el.setSelectionRange(pos, pos)
    })
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }, [])

  // Auto-load intelligence tab data
  useEffect(() => {
    if (!showStepModal || (!stepForm.body_html && !stepForm.subject)) return
    if (stepIntelTab === 'rendering' && !stepRenderingResult && !stepRenderingLoading) handleStepRenderingCheck()
    if (stepIntelTab === 'scorecard' && !stepScorecardResult && !stepScorecardLoading) handleStepScorecard()
  }, [stepIntelTab, showStepModal]) // eslint-disable-line react-hooks/exhaustive-deps

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
      const data = await campaignsApi.listContacts(selectedCampaign.campaign_id, { page: 1, page_size: 1000 })
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
      const data = await campaignsApi.listContacts(selectedCampaign.campaign_id, { page: 1, page_size: 1000 })
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
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Campaigns</h1>
            <p className="text-gray-500 dark:text-gray-400 mt-1">Multi-step email sequences</p>
          </div>
          <button onClick={openCreateModal} className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700">
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
          <div className="relative flex-1 min-w-0 sm:min-w-[200px]">
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

        {/* Bulk action bar */}
        {isSuperAdmin && selectedCampaignIds.size > 0 && (
          <div className="flex items-center gap-3 bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 px-4 py-2.5 rounded-lg">
            <span className="text-sm font-medium text-primary-700 dark:text-primary-300">
              {selectedCampaignIds.size} selected
            </span>
            <button
              onClick={handleBulkArchive}
              disabled={bulkDeleting}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
            >
              {bulkDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
              Archive Selected ({selectedCampaignIds.size})
            </button>
            <button onClick={() => setSelectedCampaignIds(new Set())} className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
              Clear
            </button>
          </div>
        )}

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
            <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900/50">
                <tr>
                  {isSuperAdmin && (
                    <th className="w-10 px-4 py-3">
                      <input
                        type="checkbox"
                        checked={campaigns.length > 0 && selectedCampaignIds.size === campaigns.length}
                        onChange={toggleSelectAll}
                        className="rounded border-gray-300"
                      />
                    </th>
                  )}
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
                      {isSuperAdmin && (
                        <td className="w-10 px-4 py-3" onClick={e => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selectedCampaignIds.has(c.campaign_id)}
                            onChange={() => toggleSelect(c.campaign_id)}
                            className="rounded border-gray-300"
                          />
                        </td>
                      )}
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900 dark:text-gray-100">{c.name}</div>
                        {c.description && <div className="text-xs text-gray-500 truncate max-w-xs">{c.description}</div>}
                      </td>
                      <td className="px-4 py-3">
                        {(() => {
                          const ds = getCampaignDisplayStatus(c)
                          return (
                            <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${statusColors[ds.colorKey] || ''}`} title={ds.description}>
                              {c.preview_mode && c.status !== 'completed' && c.status !== 'archived' && <Eye className="w-3 h-3" />}
                              {ds.label}
                            </span>
                          )
                        })()}
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
            </div>
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

        {/* Create Campaign Modal — Multi-Step Wizard */}
        {showCreateModal && (
          <>
            <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowCreateModal(false)} />
            <div className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 max-h-[85vh] overflow-y-auto mx-4 ${createStep === 'select_leads' ? 'w-full max-w-[1100px]' : 'w-full max-w-[700px]'}`}>
              {/* Header */}
              <div className="flex justify-between items-center mb-4">
                <div className="flex items-center gap-3">
                  {createStep !== 'source' && (
                    <button
                      onClick={() => {
                        if (createStep === 'select_leads' && autoSelectLeadIds.length > 0) { setAutoSelectLeadIds([]); setCreateStep('source') }
                        else if (createStep === 'csv_preview') setCreateStep('csv_upload')
                        else if (createStep === 'google_preview') setCreateStep('google_sheet')
                        else setCreateStep('source')
                      }}
                      className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                    >
                      <ArrowLeft className="w-5 h-5" />
                    </button>
                  )}
                  <div>
                    <h2 className="text-lg font-bold dark:text-gray-100">
                      {createStep === 'source' && 'New Campaign — Choose Lead Source'}
                      {createStep === 'ai_check' && 'New Campaign — AI Lead Hunting'}
                      {createStep === 'pipeline_running' && 'New Campaign — AI Lead Hunting'}
                      {createStep === 'csv_upload' && 'New Campaign — CSV Upload'}
                      {createStep === 'csv_preview' && 'New Campaign — Preview CSV'}
                      {createStep === 'manual_entry' && 'New Campaign — Manual Entry'}
                      {createStep === 'google_sheet' && 'New Campaign — Google Sheet'}
                      {createStep === 'google_preview' && 'New Campaign — Preview Sheet'}
                      {createStep === 'select_leads' && 'New Campaign — Select Leads'}
                    </h2>
                    <p className="text-sm text-gray-500 mt-0.5">
                      {createStep === 'source' && 'How would you like to add leads to this campaign?'}
                      {createStep === 'ai_check' && 'Checking available leads in database...'}
                      {createStep === 'pipeline_running' && 'Sourcing leads from job boards...'}
                      {createStep === 'csv_upload' && 'Upload a CSV file with your leads'}
                      {createStep === 'csv_preview' && 'Review your data before importing'}
                      {createStep === 'manual_entry' && 'Enter lead details manually'}
                      {createStep === 'google_sheet' && 'Import leads from a public Google Sheet'}
                      {createStep === 'google_preview' && 'Review your sheet data before importing'}
                      {createStep === 'select_leads' && 'Select leads to auto-create a campaign with contacts, sequence, and mailboxes'}
                    </p>
                  </div>
                </div>
                <button onClick={() => setShowCreateModal(false)}><X className="w-5 h-5" /></button>
              </div>

              {/* Step: Source Selection */}
              {createStep === 'source' && (
                <div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
                    {/* AI Lead Hunting Agent */}
                    <button
                      onClick={handleAiLeadCheck}
                      className="group relative p-5 rounded-xl border-2 border-blue-200 dark:border-blue-800 hover:border-blue-400 dark:hover:border-blue-600 transition-all text-left hover:shadow-lg"
                    >
                      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center mb-3">
                        <Brain className="w-6 h-6 text-white" />
                      </div>
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">AI Lead Hunting Agent</h3>
                      <p className="text-xs text-gray-500">Auto-source leads from Indeed, LinkedIn, Glassdoor and more</p>
                    </button>

                    {/* CSV Upload */}
                    <button
                      onClick={() => setCreateStep('csv_upload')}
                      className="group relative p-5 rounded-xl border-2 border-green-200 dark:border-green-800 hover:border-green-400 dark:hover:border-green-600 transition-all text-left hover:shadow-lg"
                    >
                      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center mb-3">
                        <Upload className="w-6 h-6 text-white" />
                      </div>
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">CSV Upload</h3>
                      <p className="text-xs text-gray-500">Import leads from a spreadsheet CSV file</p>
                    </button>

                    {/* Manual Entry */}
                    <button
                      onClick={() => setCreateStep('manual_entry')}
                      className="group relative p-5 rounded-xl border-2 border-orange-200 dark:border-orange-800 hover:border-orange-400 dark:hover:border-orange-600 transition-all text-left hover:shadow-lg"
                    >
                      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center mb-3">
                        <PenLine className="w-6 h-6 text-white" />
                      </div>
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">Manual Entry</h3>
                      <p className="text-xs text-gray-500">Type in lead details one by one</p>
                    </button>

                    {/* Google Sheet */}
                    <button
                      onClick={() => setCreateStep('google_sheet')}
                      className="group relative p-5 rounded-xl border-2 border-teal-200 dark:border-teal-800 hover:border-teal-400 dark:hover:border-teal-600 transition-all text-left hover:shadow-lg"
                    >
                      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center mb-3">
                        <Table2 className="w-6 h-6 text-white" />
                      </div>
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">Google Sheet</h3>
                      <p className="text-xs text-gray-500">Import directly from a public Google Sheets URL</p>
                    </button>
                  </div>

                  <div className="text-center">
                    <button
                      onClick={() => { setAvailableLeadsDays(7); setCreateStep('select_leads') }}
                      className="text-sm text-primary-600 hover:text-primary-700 dark:text-primary-400 hover:underline"
                    >
                      or skip and select from existing leads
                    </button>
                  </div>
                </div>
              )}

              {/* Step: AI Check — show existing leads count, offer pipeline if < 50 */}
              {createStep === 'ai_check' && (
                <div className="flex flex-col items-center justify-center py-10">
                  {aiCheckLoading ? (
                    <>
                      <Brain className="w-16 h-16 text-blue-500 animate-pulse mb-4" />
                      <p className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">Searching available leads...</p>
                      <div className="w-full max-w-md bg-gray-200 dark:bg-gray-700 rounded-full h-3 mb-4">
                        <div className="h-3 rounded-full bg-blue-500 animate-pulse" style={{ width: '60%' }} />
                      </div>
                    </>
                  ) : aiCheckLeadCount >= 50 ? (
                    <>
                      <CheckCircle2 className="w-16 h-16 text-green-500 mb-4" />
                      <p className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
                        {aiCheckLeadCount.toLocaleString()} leads available
                      </p>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 text-center max-w-sm">
                        You have plenty of leads ready for campaign selection. No need to run the pipeline.
                      </p>
                      <button
                        onClick={handleUseExistingLeads}
                        className="px-6 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium mb-3"
                      >
                        Select from {aiCheckLeadCount.toLocaleString()} Leads
                      </button>
                      <button
                        onClick={handleStartPipeline}
                        className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:underline"
                      >
                        Run pipeline anyway to find more leads
                      </button>
                    </>
                  ) : (
                    <>
                      <AlertTriangle className="w-16 h-16 text-amber-500 mb-4" />
                      <p className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
                        Only {aiCheckLeadCount} lead{aiCheckLeadCount !== 1 ? 's' : ''} available
                      </p>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 text-center max-w-sm">
                        Would you like to run the AI Lead Sourcing pipeline to find more leads from job boards? This may take 5-10 minutes.
                      </p>
                      <div className="flex gap-3">
                        <button
                          onClick={handleStartPipeline}
                          className="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
                        >
                          Yes, Source More Leads
                        </button>
                        {aiCheckLeadCount > 0 && (
                          <button
                            onClick={handleUseExistingLeads}
                            className="px-5 py-2.5 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 text-sm font-medium"
                          >
                            Use {aiCheckLeadCount} Lead{aiCheckLeadCount !== 1 ? 's' : ''}
                          </button>
                        )}
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Step: Pipeline Running */}
              {createStep === 'pipeline_running' && (
                <div className="flex flex-col items-center justify-center py-10">
                  {pipelineRunning ? (
                    <Brain className="w-16 h-16 text-blue-500 animate-pulse mb-4" />
                  ) : pipelineFailed ? (
                    <XCircle className="w-16 h-16 text-red-500 mb-4" />
                  ) : (
                    <CheckCircle2 className="w-16 h-16 text-green-500 mb-4" />
                  )}
                  <p className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">{pipelineStatus}</p>

                  {/* Progress bar */}
                  <div className="w-full max-w-md bg-gray-200 dark:bg-gray-700 rounded-full h-3 mb-4">
                    <div
                      className={`h-3 rounded-full transition-all duration-500 ${pipelineFailed ? 'bg-red-500' : pipelineProgress >= 100 ? 'bg-green-500' : 'bg-blue-500'}`}
                      style={{ width: `${pipelineProgress}%` }}
                    />
                  </div>

                  {pipelineRunning && (
                    <div className="flex gap-2 mt-2">
                      {['Indeed', 'LinkedIn', 'Glassdoor', 'Google Jobs'].map(src => (
                        <span key={src} className="px-2 py-1 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400">{src}</span>
                      ))}
                    </div>
                  )}

                  {pipelineFailed && (
                    <button onClick={handleStartPipeline} className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
                      Try Again
                    </button>
                  )}
                </div>
              )}

              {/* Step: CSV Upload */}
              {createStep === 'csv_upload' && (
                <div>
                  <div
                    className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl p-10 text-center cursor-pointer hover:border-green-400 dark:hover:border-green-600 transition-colors"
                    onClick={() => csvFileRef.current?.click()}
                    onDragOver={e => { e.preventDefault(); e.stopPropagation() }}
                    onDrop={e => {
                      e.preventDefault(); e.stopPropagation()
                      const file = e.dataTransfer.files?.[0]
                      if (file && file.name.endsWith('.csv')) handleCsvFileSelect(file)
                    }}
                  >
                    {csvUploading ? (
                      <Loader2 className="w-12 h-12 text-green-500 animate-spin mx-auto mb-3" />
                    ) : (
                      <Upload className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                    )}
                    <p className="text-gray-700 dark:text-gray-300 font-medium mb-1">
                      {csvUploading ? 'Analyzing file...' : 'Drop your CSV file here or click to browse'}
                    </p>
                    <p className="text-xs text-gray-500">Accepts .csv files</p>
                  </div>
                  <input
                    ref={csvFileRef}
                    type="file"
                    accept=".csv"
                    className="hidden"
                    onChange={e => {
                      const file = e.target.files?.[0]
                      if (file) handleCsvFileSelect(file)
                    }}
                  />
                  <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Expected columns:</p>
                    <p className="text-xs text-gray-500 mb-0.5"><span className="font-medium">Lead:</span> Company Name, Job Title, State, Position Type, Job Link, Source, Posting Date, Salary Min, Salary Max</p>
                    <p className="text-xs text-gray-500"><span className="font-medium">Contact:</span> First Name, Last Name, Email, Phone, Contact Title</p>
                  </div>
                  <button
                    onClick={() => leadsApi.downloadTemplate()}
                    className="mt-3 w-full flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    <Download className="w-4 h-4" /> Download CSV Template
                  </button>
                </div>
              )}

              {/* Step: CSV Preview */}
              {createStep === 'csv_preview' && csvPreviewData && (
                <div>
                  {/* File badge */}
                  <div className="flex items-center gap-2 mb-3">
                    <FileText className="w-4 h-4 text-green-600" />
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{csvPreviewData.filename || csvFile?.name}</span>
                  </div>

                  {/* Stats */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
                    <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-center">
                      <p className="text-2xl font-bold text-blue-600">{csvPreviewData.total_rows}</p>
                      <p className="text-xs text-gray-500">Total Rows</p>
                    </div>
                    <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg text-center">
                      <p className="text-2xl font-bold text-green-600">{csvPreviewData.new_count}</p>
                      <p className="text-xs text-gray-500">New Leads</p>
                    </div>
                    <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg text-center">
                      <p className="text-2xl font-bold text-yellow-600">{csvPreviewData.duplicate_count}</p>
                      <p className="text-xs text-gray-500">Duplicates</p>
                    </div>
                  </div>

                  {/* Preview table */}
                  <div className="border rounded-lg overflow-hidden dark:border-gray-700 mb-4 max-h-[250px] overflow-y-auto overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50 dark:bg-gray-700 sticky top-0">
                        <tr>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Row</th>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Company</th>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Job Title</th>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Contact</th>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                        {(csvPreviewData.preview || []).map((row: any) => (
                          <tr key={row.row_number} className={row.is_duplicate ? 'bg-yellow-50 dark:bg-yellow-900/10' : ''}>
                            <td className="px-2 py-1.5 text-gray-500">{row.row_number}</td>
                            <td className="px-2 py-1.5 max-w-[120px] truncate">{row.company_name}</td>
                            <td className="px-2 py-1.5 max-w-[120px] truncate">{row.job_title}</td>
                            <td className="px-2 py-1.5 max-w-[100px] truncate">{row.contact_name || <span className="text-gray-400">—</span>}</td>
                            <td className="px-2 py-1.5 max-w-[130px] truncate">{row.email || <span className="text-gray-400">—</span>}</td>
                            <td className="px-2 py-1.5">
                              {row.is_duplicate ? (
                                <span className="text-yellow-600 text-xs">Duplicate</span>
                              ) : (
                                <span className="text-green-600 text-xs">New</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Skip duplicates */}
                  <label className="flex items-center gap-2 mb-4 cursor-pointer">
                    <input type="checkbox" checked={csvSkipDuplicates} onChange={e => setCsvSkipDuplicates(e.target.checked)} className="w-4 h-4 rounded" />
                    <span className="text-sm text-gray-700 dark:text-gray-300">Skip duplicate leads ({csvPreviewData.duplicate_count} found)</span>
                  </label>

                  {/* Import button */}
                  <button
                    onClick={handleCsvImport}
                    disabled={csvImporting || csvPreviewData.new_count === 0}
                    className="w-full px-4 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium flex items-center justify-center gap-2"
                  >
                    {csvImporting ? <><Loader2 className="w-4 h-4 animate-spin" /> Importing...</> : `Import ${csvSkipDuplicates ? csvPreviewData.new_count : csvPreviewData.total_rows} Leads`}
                  </button>
                </div>
              )}

              {/* Step: Manual Entry */}
              {createStep === 'manual_entry' && (
                <div>
                  <div className="space-y-4 max-h-[400px] overflow-y-auto pr-1 mb-4">
                    {manualEntries.map((entry, idx) => (
                      <div key={idx} className="border dark:border-gray-700 rounded-lg p-4">
                        <div className="flex items-center justify-between mb-3">
                          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Entry #{idx + 1}</span>
                          {manualEntries.length > 1 && (
                            <button onClick={() => setManualEntries(prev => prev.filter((_, i) => i !== idx))} className="text-red-500 hover:text-red-700 text-xs">Remove</button>
                          )}
                        </div>
                        {/* Contact fields — primary */}
                        <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">Contact Details</p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
                          <input value={entry.first_name} onChange={e => { const v = [...manualEntries]; v[idx] = { ...v[idx], first_name: e.target.value }; setManualEntries(v) }}
                            placeholder="First Name *" className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" />
                          <input value={entry.last_name} onChange={e => { const v = [...manualEntries]; v[idx] = { ...v[idx], last_name: e.target.value }; setManualEntries(v) }}
                            placeholder="Last Name *" className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" />
                          <input value={entry.email} onChange={e => { const v = [...manualEntries]; v[idx] = { ...v[idx], email: e.target.value }; setManualEntries(v) }}
                            placeholder="Email *" type="email" className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" />
                          <input value={entry.phone} onChange={e => { const v = [...manualEntries]; v[idx] = { ...v[idx], phone: e.target.value }; setManualEntries(v) }}
                            placeholder="Phone" className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" />
                        </div>
                        {/* Lead fields */}
                        <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">Lead / Job Details</p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <input value={entry.client_name} onChange={e => { const v = [...manualEntries]; v[idx] = { ...v[idx], client_name: e.target.value }; setManualEntries(v) }}
                            placeholder="Company Name *" className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" />
                          <input value={entry.job_title} onChange={e => { const v = [...manualEntries]; v[idx] = { ...v[idx], job_title: e.target.value }; setManualEntries(v) }}
                            placeholder="Job Title *" className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" />
                          <input value={entry.state} onChange={e => { const v = [...manualEntries]; v[idx] = { ...v[idx], state: e.target.value }; setManualEntries(v) }}
                            placeholder="State (e.g. TX)" maxLength={2} className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" />
                          <input value={entry.job_link} onChange={e => { const v = [...manualEntries]; v[idx] = { ...v[idx], job_link: e.target.value }; setManualEntries(v) }}
                            placeholder="Job Link (optional)" className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" />
                          <input value={entry.salary_min} onChange={e => { const v = [...manualEntries]; v[idx] = { ...v[idx], salary_min: e.target.value }; setManualEntries(v) }}
                            placeholder="Salary Min" type="number" className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" />
                          <input value={entry.salary_max} onChange={e => { const v = [...manualEntries]; v[idx] = { ...v[idx], salary_max: e.target.value }; setManualEntries(v) }}
                            placeholder="Salary Max" type="number" className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" />
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="flex items-center justify-between">
                    <button
                      onClick={() => setManualEntries(prev => [...prev, { ...emptyEntry }])}
                      className="text-sm text-primary-600 hover:text-primary-700 dark:text-primary-400 flex items-center gap-1"
                    >
                      <Plus className="w-4 h-4" /> Add Another
                    </button>
                    <button
                      onClick={handleManualSubmit}
                      disabled={manualSubmitting || !manualEntries.some(e => e.client_name.trim() && e.job_title.trim())}
                      className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-50 text-sm flex items-center gap-2"
                    >
                      {manualSubmitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Creating...</> : `Create ${manualEntries.filter(e => e.client_name.trim() && e.job_title.trim()).length} Lead(s)`}
                    </button>
                  </div>
                </div>
              )}

              {/* Step: Google Sheet */}
              {createStep === 'google_sheet' && (
                <div>
                  <div className="relative mb-4">
                    <Link2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      value={googleSheetUrl}
                      onChange={e => setGoogleSheetUrl(e.target.value)}
                      placeholder="https://docs.google.com/spreadsheets/d/..."
                      className="w-full pl-10 pr-4 py-3 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
                    />
                  </div>

                  <div className="p-3 bg-teal-50 dark:bg-teal-900/20 rounded-lg mb-4 border border-teal-200 dark:border-teal-800">
                    <p className="text-xs text-teal-800 dark:text-teal-300 font-medium mb-1">Important</p>
                    <p className="text-xs text-teal-700 dark:text-teal-400">The sheet must be publicly accessible. Go to File &rarr; Share &rarr; &quot;Anyone with the link&quot; can view.</p>
                  </div>

                  <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg mb-4">
                    <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Expected columns:</p>
                    <p className="text-xs text-gray-500 mb-0.5"><span className="font-medium">Lead:</span> Company Name, Job Title, State, Position Type, Job Link, Source, Posting Date, Salary Min, Salary Max</p>
                    <p className="text-xs text-gray-500"><span className="font-medium">Contact:</span> First Name, Last Name, Email, Phone, Contact Title</p>
                  </div>

                  <button
                    onClick={handleGoogleSheetPreview}
                    disabled={googleSheetLoading || !googleSheetUrl.trim()}
                    className="w-full px-4 py-2.5 bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50 text-sm font-medium flex items-center justify-center gap-2 mb-3"
                  >
                    {googleSheetLoading ? <><Loader2 className="w-4 h-4 animate-spin" /> Loading Sheet...</> : 'Preview Sheet'}
                  </button>
                  <button
                    onClick={() => leadsApi.downloadTemplate()}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    <Download className="w-4 h-4" /> Download CSV/Sheet Template
                  </button>
                </div>
              )}

              {/* Step: Google Preview */}
              {createStep === 'google_preview' && googleSheetPreview && (
                <div>
                  {/* Stats */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
                    <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-center">
                      <p className="text-2xl font-bold text-blue-600">{googleSheetPreview.total_rows}</p>
                      <p className="text-xs text-gray-500">Total Rows</p>
                    </div>
                    <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg text-center">
                      <p className="text-2xl font-bold text-green-600">{googleSheetPreview.new_count}</p>
                      <p className="text-xs text-gray-500">New Leads</p>
                    </div>
                    <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg text-center">
                      <p className="text-2xl font-bold text-yellow-600">{googleSheetPreview.duplicate_count}</p>
                      <p className="text-xs text-gray-500">Duplicates</p>
                    </div>
                  </div>

                  {/* Preview table */}
                  <div className="border rounded-lg overflow-hidden dark:border-gray-700 mb-4 max-h-[250px] overflow-y-auto overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50 dark:bg-gray-700 sticky top-0">
                        <tr>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Row</th>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Company</th>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Job Title</th>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Contact</th>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                          <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                        {(googleSheetPreview.preview || []).map((row: any) => (
                          <tr key={row.row_number} className={row.is_duplicate ? 'bg-yellow-50 dark:bg-yellow-900/10' : ''}>
                            <td className="px-2 py-1.5 text-gray-500">{row.row_number}</td>
                            <td className="px-2 py-1.5 max-w-[120px] truncate">{row.company_name}</td>
                            <td className="px-2 py-1.5 max-w-[120px] truncate">{row.job_title}</td>
                            <td className="px-2 py-1.5 max-w-[100px] truncate">{row.contact_name || <span className="text-gray-400">—</span>}</td>
                            <td className="px-2 py-1.5 max-w-[130px] truncate">{row.email || <span className="text-gray-400">—</span>}</td>
                            <td className="px-2 py-1.5">
                              {row.is_duplicate ? (
                                <span className="text-yellow-600 text-xs">Duplicate</span>
                              ) : (
                                <span className="text-green-600 text-xs">New</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Skip duplicates */}
                  <label className="flex items-center gap-2 mb-4 cursor-pointer">
                    <input type="checkbox" checked={googleSkipDuplicates} onChange={e => setGoogleSkipDuplicates(e.target.checked)} className="w-4 h-4 rounded" />
                    <span className="text-sm text-gray-700 dark:text-gray-300">Skip duplicate leads ({googleSheetPreview.duplicate_count} found)</span>
                  </label>

                  {/* Import button */}
                  <button
                    onClick={handleGoogleSheetImport}
                    disabled={googleSheetImporting || googleSheetPreview.new_count === 0}
                    className="w-full px-4 py-2.5 bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50 text-sm font-medium flex items-center justify-center gap-2"
                  >
                    {googleSheetImporting ? <><Loader2 className="w-4 h-4 animate-spin" /> Importing...</> : `Import ${googleSkipDuplicates ? googleSheetPreview.new_count : googleSheetPreview.total_rows} Leads`}
                  </button>
                </div>
              )}

              {/* Step: Select Leads (existing flow) */}
              {createStep === 'select_leads' && (
                <div>
                  {/* Success banner if coming from import */}
                  {autoSelectLeadIds.length > 0 && (
                    <div className="flex items-center gap-2 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg mb-3">
                      <CheckCircle2 className="w-4 h-4 text-green-600" />
                      <span className="text-sm text-green-800 dark:text-green-300">{autoSelectLeadIds.length} leads imported and pre-selected</span>
                    </div>
                  )}

                  {/* Search, Days Filter & Stats */}
                  <div className="flex items-center gap-3 mb-2">
                    <div className="relative flex-1">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        value={availableLeadsSearch}
                        onChange={e => { setAvailableLeadsSearch(e.target.value); setAvailableLeadsPage(1) }}
                        className="w-full pl-9 pr-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
                        placeholder="Search by job title, company, or contact email..."
                      />
                    </div>
                    <select
                      value={availableLeadsDays}
                      onChange={e => { setAvailableLeadsDays(Number(e.target.value)); setAvailableLeadsPage(1); setSelectedCreateLeadIds(new Set()) }}
                      className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
                    >
                      <option value={7}>Last 7 days</option>
                      <option value={14}>Last 14 days</option>
                      <option value={30}>Last 30 days</option>
                      <option value={60}>Last 60 days</option>
                      <option value={90}>Last 90 days</option>
                      <option value={180}>Last 6 months</option>
                      <option value={365}>Last year</option>
                    </select>
                    <select
                      value={availableLeadsPageSize}
                      onChange={e => { setAvailableLeadsPageSize(Number(e.target.value)); setAvailableLeadsPage(1); setSelectedCreateLeadIds(new Set()) }}
                      className="px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
                    >
                      <option value={0}>All</option>
                      <option value={100}>100</option>
                      <option value={50}>50</option>
                      <option value={25}>25</option>
                    </select>
                    <span className="text-sm text-gray-500 whitespace-nowrap">
                      {selectedCreateLeadIds.size} of {availableLeadsTotal} selected
                    </span>
                  </div>

                  {/* Filters Row */}
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <select
                      value={alFilterStatus}
                      onChange={e => { setAlFilterStatus(e.target.value); setAvailableLeadsPage(1) }}
                      className={`px-2 py-1.5 border rounded-lg text-sm dark:bg-gray-700 dark:border-gray-600 ${alFilterStatus ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/30' : ''}`}
                    >
                      <option value="">All Statuses</option>
                      {LEAD_STATUS_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                    </select>
                    <select
                      value={alFilterSource}
                      onChange={e => { setAlFilterSource(e.target.value); setAvailableLeadsPage(1) }}
                      className={`px-2 py-1.5 border rounded-lg text-sm dark:bg-gray-700 dark:border-gray-600 ${alFilterSource ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/30' : ''}`}
                    >
                      <option value="">All Sources</option>
                      {LEAD_SOURCE_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <select
                      value={alFilterEmploymentType}
                      onChange={e => { setAlFilterEmploymentType(e.target.value); setAvailableLeadsPage(1) }}
                      className={`px-2 py-1.5 border rounded-lg text-sm dark:bg-gray-700 dark:border-gray-600 ${alFilterEmploymentType ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/30' : ''}`}
                    >
                      <option value="">All Types</option>
                      {EMPLOYMENT_TYPE_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <button
                      type="button"
                      onClick={() => setAlShowMoreFilters(!alShowMoreFilters)}
                      className={`px-2 py-1.5 border rounded-lg text-sm flex items-center gap-1 ${alShowMoreFilters || alFilterState.length > 0 || alFilterIndustry.length > 0 || alFilterCompanySize.length > 0 || alFilterExcludeKeywords.length > 0 || alFilterTitle.length > 0 ? 'border-blue-400 bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : 'text-gray-600 dark:text-gray-400 dark:bg-gray-700 dark:border-gray-600'}`}
                    >
                      <Filter className="w-3.5 h-3.5" />
                      More{(alFilterState.length + alFilterIndustry.length + alFilterCompanySize.length + alFilterExcludeKeywords.length + alFilterTitle.length) > 0 && ` (${alFilterState.length + alFilterIndustry.length + alFilterCompanySize.length + alFilterExcludeKeywords.length + alFilterTitle.length})`}
                      {alShowMoreFilters ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                    </button>
                    {(alFilterStatus || alFilterSource || alFilterEmploymentType || alFilterState.length > 0 || alFilterIndustry.length > 0 || alFilterCompanySize.length > 0 || alFilterExcludeKeywords.length > 0 || alFilterTitle.length > 0) && (
                      <button
                        type="button"
                        onClick={() => { setAlFilterStatus(''); setAlFilterSource(''); setAlFilterEmploymentType(''); setAlFilterState([]); setAlFilterIndustry([]); setAlFilterCompanySize([]); setAlFilterExcludeKeywords([]); setAlFilterTitle([]); setAvailableLeadsPage(1) }}
                        className="text-xs text-red-600 hover:text-red-700 hover:underline"
                      >
                        Clear filters
                      </button>
                    )}
                  </div>

                  {/* Expandable multi-select filters */}
                  {alShowMoreFilters && (
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2 mb-2 p-2 bg-gray-50 dark:bg-gray-800 rounded-lg border dark:border-gray-700">
                      {(() => {
                        const WizardMultiSelect = ({ label, options, selected, onChange }: { label: string; options: string[]; selected: string[]; onChange: (v: string[]) => void }) => {
                          const [open, setOpen] = useState(false)
                          const ref = useRef<HTMLDivElement>(null)
                          useEffect(() => {
                            const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
                            document.addEventListener('mousedown', handler)
                            return () => document.removeEventListener('mousedown', handler)
                          }, [])
                          return (
                            <div ref={ref} className="relative">
                              <button type="button" onClick={() => setOpen(!open)} className={`w-full px-2 py-1.5 border rounded-lg text-sm text-left flex items-center justify-between dark:bg-gray-700 dark:border-gray-600 ${selected.length > 0 ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/30' : ''}`}>
                                <span className="truncate">{selected.length === 0 ? `All ${label}` : `${label} (${selected.length})`}</span>
                                <span className="text-gray-400 ml-1 text-xs">{open ? '▲' : '▼'}</span>
                              </button>
                              {open && (
                                <div className="absolute z-50 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                                  <div className="flex gap-2 px-2 py-1.5 border-b bg-gray-50 dark:bg-gray-700 sticky top-0">
                                    <button type="button" onClick={() => { onChange([...options]); setAvailableLeadsPage(1) }} className="text-xs text-blue-600 hover:underline">All</button>
                                    <button type="button" onClick={() => { onChange([]); setAvailableLeadsPage(1) }} className="text-xs text-gray-500 hover:underline">Clear</button>
                                  </div>
                                  {options.map(opt => (
                                    <label key={opt} className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer text-sm">
                                      <input type="checkbox" checked={selected.includes(opt)} onChange={() => { onChange(selected.includes(opt) ? selected.filter(v => v !== opt) : [...selected, opt]); setAvailableLeadsPage(1) }} className="w-3.5 h-3.5 rounded" />
                                      {opt}
                                    </label>
                                  ))}
                                  {options.length === 0 && <div className="px-2 py-1.5 text-xs text-gray-400">No options</div>}
                                </div>
                              )}
                            </div>
                          )
                        }
                        const WizardSearchableMultiSelect = ({ label, options, selected, onChange, grouped }: { label: string; options: string[] | { category: string; items: string[] }[]; selected: string[]; onChange: (v: string[]) => void; grouped?: boolean }) => {
                          const [open, setOpen] = useState(false)
                          const [searchText, setSearchText] = useState('')
                          const ref = useRef<HTMLDivElement>(null)
                          useEffect(() => {
                            const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
                            document.addEventListener('mousedown', handler)
                            return () => document.removeEventListener('mousedown', handler)
                          }, [])
                          const allItems: string[] = grouped
                            ? (options as { category: string; items: string[] }[]).flatMap(g => g.items)
                            : (options as string[])
                          const filterBySearch = (items: string[]) =>
                            searchText ? items.filter(i => i.toLowerCase().includes(searchText.toLowerCase())) : items
                          return (
                            <div ref={ref} className="relative">
                              <button type="button" onClick={() => setOpen(!open)} className={`w-full px-2 py-1.5 border rounded-lg text-sm text-left flex items-center justify-between dark:bg-gray-700 dark:border-gray-600 ${selected.length > 0 ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/30' : ''}`}>
                                <span className="truncate">{selected.length === 0 ? `All ${label}` : `${label} (${selected.length})`}</span>
                                <span className="text-gray-400 ml-1 text-xs">{open ? '▲' : '▼'}</span>
                              </button>
                              {open && (
                                <div className="absolute z-50 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg max-h-60 overflow-y-auto min-w-0 sm:min-w-[220px]">
                                  <div className="flex gap-2 px-2 py-1.5 border-b bg-gray-50 dark:bg-gray-700 sticky top-0 z-10">
                                    <button type="button" onClick={() => { onChange([...allItems]); setAvailableLeadsPage(1) }} className="text-xs text-blue-600 hover:underline">All</button>
                                    <button type="button" onClick={() => { onChange([]); setAvailableLeadsPage(1) }} className="text-xs text-gray-500 hover:underline">Clear</button>
                                  </div>
                                  <div className="px-2 py-1.5 border-b sticky top-[33px] bg-white dark:bg-gray-800 z-10">
                                    <input type="text" placeholder="Search..." value={searchText} onChange={(e) => setSearchText(e.target.value)} className="w-full text-sm border border-gray-200 dark:border-gray-600 rounded px-2 py-1 focus:outline-none focus:border-blue-400 dark:bg-gray-700" />
                                  </div>
                                  {grouped ? (
                                    (options as { category: string; items: string[] }[]).map(group => {
                                      const filtered = filterBySearch(group.items)
                                      if (filtered.length === 0) return null
                                      return (
                                        <div key={group.category}>
                                          <div className="px-2 py-1 text-xs font-semibold text-gray-500 uppercase bg-gray-50 dark:bg-gray-700 border-b dark:border-gray-600">{group.category}</div>
                                          {filtered.map(opt => (
                                            <label key={opt} className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer text-sm">
                                              <input type="checkbox" checked={selected.includes(opt)} onChange={() => { onChange(selected.includes(opt) ? selected.filter(v => v !== opt) : [...selected, opt]); setAvailableLeadsPage(1) }} className="w-3.5 h-3.5 rounded" />
                                              {opt}
                                            </label>
                                          ))}
                                        </div>
                                      )
                                    })
                                  ) : (
                                    filterBySearch(allItems).map(opt => (
                                      <label key={opt} className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer text-sm">
                                        <input type="checkbox" checked={selected.includes(opt)} onChange={() => { onChange(selected.includes(opt) ? selected.filter(v => v !== opt) : [...selected, opt]); setAvailableLeadsPage(1) }} className="w-3.5 h-3.5 rounded" />
                                        {opt}
                                      </label>
                                    ))
                                  )}
                                  {allItems.length === 0 && <div className="px-2 py-1.5 text-xs text-gray-400">No options</div>}
                                  {allItems.length > 0 && filterBySearch(allItems).length === 0 && <div className="px-2 py-1.5 text-xs text-gray-400">No matches</div>}
                                </div>
                              )}
                            </div>
                          )
                        }
                        return (
                          <>
                            <WizardMultiSelect label="States" options={WIZARD_US_STATES} selected={alFilterState} onChange={setAlFilterState} />
                            <WizardMultiSelect label="Industries" options={alFilterOptions.industries} selected={alFilterIndustry} onChange={setAlFilterIndustry} />
                            <WizardMultiSelect label="Company Size" options={alFilterOptions.company_sizes} selected={alFilterCompanySize} onChange={setAlFilterCompanySize} />
                            <WizardSearchableMultiSelect
                              label="Exclusions"
                              grouped
                              options={[
                                { category: 'IT / Tech', items: alFilterOptions.exclusion_keywords.it_keywords },
                                { category: 'Staffing / Agency', items: alFilterOptions.exclusion_keywords.staffing_keywords },
                              ]}
                              selected={alFilterExcludeKeywords}
                              onChange={setAlFilterExcludeKeywords}
                            />
                            <WizardSearchableMultiSelect
                              label="Titles"
                              grouped={!!alFilterOptions.job_title_categories && Object.keys(alFilterOptions.job_title_categories).length > 0}
                              options={alFilterOptions.job_title_categories && Object.keys(alFilterOptions.job_title_categories).length > 0
                                ? Object.entries(alFilterOptions.job_title_categories).sort(([a], [b]) => a.localeCompare(b)).map(([category, items]) => ({ category, items: items.sort() }))
                                : alFilterOptions.job_titles}
                              selected={alFilterTitle}
                              onChange={setAlFilterTitle}
                            />
                          </>
                        )
                      })()}
                    </div>
                  )}

                  {/* Leads Table */}
                  <div className="border rounded-lg overflow-hidden dark:border-gray-700 mb-4 overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 dark:bg-gray-700">
                        <tr>
                          <th className="px-3 py-2 text-left">
                            <label className="flex items-center gap-1.5 cursor-pointer">
                              <input
                                type="checkbox"
                                ref={el => {
                                  if (el) {
                                    const allChecked = selectedCreateLeadIds.size > 0 && selectedCreateLeadIds.size >= availableLeadsTotal
                                    const someChecked = selectedCreateLeadIds.size > 0 && !allChecked
                                    el.indeterminate = someChecked
                                  }
                                }}
                                checked={selectedCreateLeadIds.size > 0 && selectedCreateLeadIds.size >= availableLeadsTotal}
                                onChange={async () => {
                                  if (selectedCreateLeadIds.size > 0) {
                                    setSelectedCreateLeadIds(new Set())
                                  } else {
                                    try {
                                      const allData = await campaignsApi.getAvailableLeads({ ...buildAlFilterParams(), page: 1, page_size: Math.max(availableLeadsTotal, 200) })
                                      setSelectedCreateLeadIds(new Set((allData.items || []).map((l: any) => l.lead_id)))
                                    } catch {
                                      setSelectedCreateLeadIds(new Set(availableLeads.map(l => l.lead_id)))
                                    }
                                  }
                                }}
                                className="w-4 h-4 rounded"
                              />
                              <span className="text-xs font-medium text-gray-500 uppercase">All</span>
                            </label>
                          </th>
                          {([
                            { key: 'job_title', label: 'Job Title' },
                            { key: 'client_name', label: 'Company' },
                            { key: 'state', label: 'State' },
                            { key: 'employment_type', label: 'Type' },
                            { key: 'posting_date', label: 'Posted' },
                            { key: 'source', label: 'Source' },
                          ] as { key: AvailableLeadsSortField; label: string }[]).map(col => (
                            <th
                              key={col.key}
                              className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:text-gray-700 dark:hover:text-gray-300 select-none"
                              onClick={() => { if (alSortBy === col.key) { setAlSortOrder(o => o === 'asc' ? 'desc' : 'asc') } else { setAlSortBy(col.key); setAlSortOrder('asc') } setAvailableLeadsPage(1) }}
                            >
                              <span className="flex items-center gap-1">
                                {col.label}
                                {alSortBy === col.key ? (
                                  alSortOrder === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
                                ) : (
                                  <ChevronsUpDown className="w-3 h-3 opacity-30" />
                                )}
                              </span>
                            </th>
                          ))}
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Contacts</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                        {availableLeadsLoading ? (
                          <tr><td colSpan={9} className="px-3 py-6 text-center text-gray-500">Loading leads...</td></tr>
                        ) : availableLeads.length === 0 ? (
                          <tr><td colSpan={9} className="px-3 py-6 text-center text-gray-500">No available leads found</td></tr>
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
                              <td className="px-3 py-2 text-gray-900 dark:text-gray-100 max-w-[180px] truncate" title={lead.job_title}>{lead.job_title}</td>
                              <td className="px-3 py-2 text-gray-600 dark:text-gray-400 max-w-[130px] truncate">{lead.client_name}</td>
                              <td className="px-3 py-2 text-gray-500">{lead.state || '-'}</td>
                              <td className="px-3 py-2">
                                {lead.employment_type ? (
                                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                                    lead.employment_type === 'Full-time' ? 'bg-green-100 text-green-700' :
                                    lead.employment_type === 'Contract' ? 'bg-orange-100 text-orange-700' :
                                    lead.employment_type === 'Part-time' ? 'bg-blue-100 text-blue-700' :
                                    lead.employment_type === 'Temporary' ? 'bg-yellow-100 text-yellow-700' :
                                    'bg-gray-100 text-gray-700'
                                  }`}>{lead.employment_type}</span>
                                ) : <span className="text-gray-400">-</span>}
                              </td>
                              <td className="px-3 py-2 text-gray-500">{lead.posting_date ? new Date(lead.posting_date).toLocaleDateString() : '-'}</td>
                              <td className="px-3 py-2 text-gray-500 text-xs">{lead.source || '-'}</td>
                              <td className="px-3 py-2">
                                <button type="button" onClick={(e) => {
                                  e.stopPropagation()
                                  setContactsWizardLead({ lead_id: lead.lead_id, client_name: lead.client_name, job_title: lead.job_title })
                                }} className={`px-2 py-0.5 text-xs rounded-full cursor-pointer ${
                                  lead.contact_count > 0 ? 'bg-purple-100 text-purple-700 hover:bg-purple-200' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                                }`}>
                                  {lead.contact_count}
                                </button>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* Pagination */}
                  {availableLeadsPageSize !== 0 && availableLeadsPages > 1 && (
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

                  {/* Configure Schedule (collapsible) */}
                  <div className="border dark:border-gray-700 rounded-lg mb-3">
                    <button
                      type="button"
                      onClick={() => setCreateScheduleExpanded(!createScheduleExpanded)}
                      className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded-lg"
                    >
                      <div className="flex items-center gap-2">
                        <Clock className="w-4 h-4 text-gray-400" />
                        <span>Configure Schedule</span>
                        <span className="text-xs text-gray-400 font-normal">
                          {campaignForm.send_days.map(d => d.charAt(0).toUpperCase() + d.slice(1)).join(', ')}, {campaignForm.send_window_start}-{campaignForm.send_window_end}, {TIMEZONE_OPTIONS.find(t => t.value === campaignForm.timezone)?.label || campaignForm.timezone}
                        </span>
                      </div>
                      {createScheduleExpanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                    </button>
                    {createScheduleExpanded && (
                      <div className="px-3 pb-3 space-y-3 border-t dark:border-gray-700 pt-3">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <div>
                            <label className="block text-xs font-medium text-gray-500 mb-1">Start Time</label>
                            <input
                              type="time"
                              value={campaignForm.send_window_start}
                              onChange={e => setCampaignForm(f => ({ ...f, send_window_start: e.target.value }))}
                              className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-500 mb-1">End Time</label>
                            <input
                              type="time"
                              value={campaignForm.send_window_end}
                              onChange={e => setCampaignForm(f => ({ ...f, send_window_end: e.target.value }))}
                              className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                            />
                          </div>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500 mb-1">Send Days</label>
                          <div className="flex gap-1 flex-wrap">
                            {DAY_LABELS.map(day => {
                              const dayKey = day.toLowerCase().slice(0, 3)
                              const isActive = campaignForm.send_days.includes(dayKey)
                              return (
                                <button
                                  key={day}
                                  type="button"
                                  onClick={() => {
                                    setCampaignForm(f => ({
                                      ...f,
                                      send_days: f.send_days.includes(dayKey)
                                        ? f.send_days.filter(d => d !== dayKey)
                                        : [...f.send_days, dayKey],
                                    }))
                                  }}
                                  className={`px-2 py-0.5 text-xs rounded cursor-pointer hover:opacity-80 ${
                                    isActive ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-400'
                                  }`}
                                >
                                  {day}
                                </button>
                              )
                            })}
                          </div>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500 mb-1">Timezone</label>
                          <select
                            value={campaignForm.timezone}
                            onChange={e => setCampaignForm(f => ({ ...f, timezone: e.target.value }))}
                            className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                          >
                            {TIMEZONE_OPTIONS.map(tz => (
                              <option key={tz.value} value={tz.value}>{tz.label}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                    )}
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
              )}
            </div>
          </>
        )}

        {/* Contacts Wizard for available-leads */}
        {contactsWizardLead && (
          <ContactsWizard
            lead={contactsWizardLead}
            onClose={() => setContactsWizardLead(null)}
            onContactAdded={() => fetchAvailableLeads()}
          />
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
            {(() => {
              const ds = getCampaignDisplayStatus(selectedCampaign as any || { status: '' })
              return (
                <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${statusColors[ds.colorKey] || ''}`} title={ds.description}>
                  {(selectedCampaign as any)?.preview_mode && selectedCampaign?.status !== 'completed' && selectedCampaign?.status !== 'archived' && <Eye className="w-3 h-3" />}
                  {ds.label}
                </span>
              )
            })()}
            {(selectedCampaign as any)?.preview_mode && selectedCampaign?.status === 'active' && (
              <span className="text-xs text-teal-600 dark:text-teal-400">Drafts generated for review — not sending</span>
            )}
            <span className="text-sm text-gray-500">{selectedCampaign?.total_contacts} contacts</span>
            <span className="text-sm text-gray-500">{selectedCampaign?.total_sent} sent</span>
          </div>
        </div>
        <div className="flex gap-2 items-center">
          {/* Preview/Live mode toggle — available when active or paused */}
          {selectedCampaign && (selectedCampaign.status === 'active' || selectedCampaign.status === 'paused') && (
            <button
              onClick={() => togglePreviewMode(selectedCampaign.campaign_id, (selectedCampaign as any).preview_mode)}
              className={`px-3 py-2 rounded-lg flex items-center gap-2 text-sm font-medium border transition-colors ${
                (selectedCampaign as any)?.preview_mode
                  ? 'border-teal-300 bg-teal-50 text-teal-700 hover:bg-teal-100 dark:border-teal-700 dark:bg-teal-900/20 dark:text-teal-300 dark:hover:bg-teal-900/30'
                  : 'border-green-300 bg-green-50 text-green-700 hover:bg-green-100 dark:border-green-700 dark:bg-green-900/20 dark:text-green-300 dark:hover:bg-green-900/30'
              }`}
              title={(selectedCampaign as any)?.preview_mode ? 'Click to switch to Live Sending mode' : 'Click to switch to Preview & Approve mode'}
            >
              {(selectedCampaign as any)?.preview_mode ? (
                <><Eye className="w-4 h-4" /> Preview Mode</>
              ) : (
                <><Send className="w-4 h-4" /> Live Sending</>
              )}
            </button>
          )}
          <div className="h-6 w-px bg-gray-300 dark:bg-gray-600" />
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
            if (tab.key === 'schedule' && selectedCampaign) { fetchSchedules(selectedCampaign.campaign_id); fetchContactSchedule(selectedCampaign.campaign_id) }
            if (tab.key === 'mailboxes' && selectedCampaign) fetchMailboxStats(selectedCampaign.campaign_id)
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

              {/* Campaign State + Mode Toggle + Action Buttons */}
              <div className="space-y-2">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Campaign State</label>
                  {(() => {
                    const ds = getCampaignDisplayStatus(selectedCampaign)
                    return (
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs rounded-full font-medium ${statusColors[ds.colorKey] || ''}`}>
                          {selectedCampaign.preview_mode && selectedCampaign.status !== 'completed' && selectedCampaign.status !== 'archived' && <Eye className="w-3 h-3" />}
                          {ds.label}
                        </span>
                        <span className="text-xs text-gray-500">{ds.description}</span>
                      </div>
                    )
                  })()}
                </div>
                {/* Send Mode toggle */}
                {(selectedCampaign.status === 'active' || selectedCampaign.status === 'paused' || selectedCampaign.status === 'draft') && (
                  <div className="flex items-center justify-between py-2 px-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div>
                      <p className="text-xs font-medium text-gray-700 dark:text-gray-300">
                        {selectedCampaign.preview_mode ? 'Preview & Approve Mode' : 'Live Sending Mode'}
                      </p>
                      <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">
                        {selectedCampaign.preview_mode
                          ? 'Generates drafts for review before sending'
                          : 'Sends emails directly to contacts'}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => togglePreviewMode(selectedCampaign.campaign_id, selectedCampaign.preview_mode)}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        selectedCampaign.preview_mode ? 'bg-teal-600' : 'bg-green-600'
                      }`}
                      title={selectedCampaign.preview_mode ? 'Switch to Live Sending' : 'Switch to Preview & Approve'}
                    >
                      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        selectedCampaign.preview_mode ? 'translate-x-6' : 'translate-x-1'
                      }`} />
                    </button>
                  </div>
                )}
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
                <div className="relative">
                  <label className="block text-xs font-medium text-gray-500 mb-1">Health Score</label>
                  <button
                    onClick={() => fetchHealthDetail(selectedCampaign.campaign_id, 'sidebar')}
                    className={`inline-flex items-center gap-1 px-2 py-1 text-xs rounded-full font-medium cursor-pointer hover:opacity-80 ${
                      selectedCampaign.health_score >= 80 ? 'bg-green-100 text-green-800' :
                      selectedCampaign.health_score >= 50 ? 'bg-yellow-100 text-yellow-800' :
                      'bg-red-100 text-red-800'
                    }`}
                  >
                    {selectedCampaign.health_score}%
                  </button>
                  {healthDetailOpen === 'sidebar' && (
                    <div className="absolute left-0 top-full mt-1 z-20 w-80 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-4">
                      {healthDetailLoading ? (
                        <div className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="w-4 h-4 animate-spin" /> Loading...</div>
                      ) : healthDetail && healthDetail.score != null ? (
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-semibold">{healthDetail.label || 'Health'}</span>
                            <span className={`text-lg font-bold ${healthDetail.score >= 80 ? 'text-green-600' : healthDetail.score >= 50 ? 'text-yellow-600' : 'text-red-600'}`}>{healthDetail.score}/100</span>
                          </div>
                          <div className="space-y-2">
                            {['deliverability', 'engagement', 'volume'].map(key => {
                              const val = healthDetail.components?.[key] ?? 0
                              const weight = key === 'deliverability' ? 40 : key === 'engagement' ? 35 : 25
                              return (
                                <div key={key}>
                                  <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400 mb-0.5">
                                    <span className="capitalize">{key}</span>
                                    <span>{Math.round(val)}/100 ({Math.round(val * weight / 100)}/{weight} pts)</span>
                                  </div>
                                  <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full">
                                    <div className={`h-full rounded-full ${val >= 70 ? 'bg-green-500' : val >= 40 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${val}%` }} />
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                          {healthDetail.explanation?.length > 0 && (
                            <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5 border-t pt-2">
                              {healthDetail.explanation.map((line: string, i: number) => <p key={i}>{line}</p>)}
                            </div>
                          )}
                          {healthDetail.recommendations?.length > 0 && (
                            <div className="text-xs space-y-1 border-t pt-2">
                              <p className="font-medium text-gray-700 dark:text-gray-300">Recommendations</p>
                              {healthDetail.recommendations.map((rec: string, i: number) => (
                                <p key={i} className="text-gray-500 dark:text-gray-400 flex gap-1"><span>•</span><span>{rec}</span></p>
                              ))}
                            </div>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-gray-500">Unable to load health details.</p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Quick Stats Card */}
            <div className="bg-white dark:bg-gray-800 border rounded-lg p-4 space-y-3">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">Quick Stats</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
      {detailTab === 'mailboxes' && selectedCampaign && (() => {
        const assignedIds = selectedCampaign.mailbox_ids || []
        // Build merged list: all tenant mailboxes with campaign stats overlaid
        const merged = mailboxes.map((m: any) => {
          const stats = mailboxStats.find((s: any) => s.mailbox_id === m.mailbox_id)
          return stats ? { ...m, ...stats } : m
        })
        // Filter by search
        const searched = mailboxSearch
          ? merged.filter((m: any) => (m.email || '').toLowerCase().includes(mailboxSearch.toLowerCase()))
          : merged
        // Sort
        const sorted = mailboxSortCol ? [...searched].sort((a: any, b: any) => {
          let av: any, bv: any
          switch (mailboxSortCol) {
            case 'email': av = (a.email || '').toLowerCase(); bv = (b.email || '').toLowerCase(); break
            case 'health': av = mailboxHealthMap[a.mailbox_id]?.health_score ?? -1; bv = mailboxHealthMap[b.mailbox_id]?.health_score ?? -1; break
            case 'warmup': av = a.warmup_status || ''; bv = b.warmup_status || ''; break
            case 'sent': av = a.campaign_sent || 0; bv = b.campaign_sent || 0; break
            case 'opened': av = a.campaign_opened || 0; bv = b.campaign_opened || 0; break
            case 'clicked': av = a.campaign_clicked || 0; bv = b.campaign_clicked || 0; break
            case 'replied': av = a.campaign_replied || 0; bv = b.campaign_replied || 0; break
            case 'bounced': av = a.campaign_bounced || 0; bv = b.campaign_bounced || 0; break
            case 'unsub': av = a.campaign_unsubscribed || 0; bv = b.campaign_unsubscribed || 0; break
            default: return 0
          }
          if (av < bv) return mailboxSortDir === 'asc' ? -1 : 1
          if (av > bv) return mailboxSortDir === 'asc' ? 1 : -1
          return 0
        }) : searched
        // Totals from assigned mailboxes that have stats
        const assignedWithStats = merged.filter((m: any) => assignedIds.includes(m.mailbox_id))
        const totals = assignedWithStats.reduce((acc: any, m: any) => ({
          sent: acc.sent + (m.campaign_sent || 0),
          opened: acc.opened + (m.campaign_opened || 0),
          clicked: acc.clicked + (m.campaign_clicked || 0),
          replied: acc.replied + (m.campaign_replied || 0),
          bounced: acc.bounced + (m.campaign_bounced || 0),
          unsub: acc.unsub + (m.campaign_unsubscribed || 0),
        }), { sent: 0, opened: 0, clicked: 0, replied: 0, bounced: 0, unsub: 0 })

        const toggleSort = (col: string) => {
          if (mailboxSortCol === col) {
            setMailboxSortDir(d => d === 'asc' ? 'desc' : 'asc')
          } else {
            setMailboxSortCol(col)
            setMailboxSortDir('asc')
          }
        }
        const SortIcon = ({ col }: { col: string }) => {
          if (mailboxSortCol !== col) return <ChevronsUpDown className="w-3 h-3 inline ml-0.5 opacity-30" />
          return mailboxSortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-0.5" /> : <ChevronDown className="w-3 h-3 inline ml-0.5" />
        }

        return (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">Mailboxes <span className="text-sm font-normal text-gray-500">({assignedIds.length} assigned of {mailboxes.length})</span></h3>
            <div className="flex items-center gap-3">
              <button
                onClick={() => fetchMailboxStats(selectedCampaign.campaign_id)}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Refresh
              </button>
              <button
                onClick={async () => {
                  const allIds = mailboxes.map((m: any) => m.mailbox_id)
                  const newIds = assignedIds.length === allIds.length ? [] : allIds
                  try {
                    await campaignsApi.update(selectedCampaign.campaign_id, { mailbox_ids: newIds })
                    setSelectedCampaign({ ...selectedCampaign, mailbox_ids: newIds })
                    fetchMailboxStats(selectedCampaign.campaign_id)
                  } catch {}
                }}
                className="text-sm text-primary-600 hover:text-primary-700"
              >
                {assignedIds.length === mailboxes.length ? 'Deselect All' : 'Select All'}
              </button>
            </div>
          </div>
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={mailboxSearch}
              onChange={e => setMailboxSearch(e.target.value)}
              placeholder="Search mailboxes..."
              className="w-full pl-9 pr-3 py-2 text-sm border rounded-lg bg-white dark:bg-gray-800 dark:border-gray-600 focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
            />
            {mailboxSearch && (
              <button onClick={() => setMailboxSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2">
                <X className="w-4 h-4 text-gray-400 hover:text-gray-600" />
              </button>
            )}
          </div>
          {mailboxStatsLoading ? (
            <div className="text-center py-8 text-gray-500">Loading mailbox stats...</div>
          ) : (
          <div className="border rounded-lg overflow-hidden dark:border-gray-700 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-3 py-2 text-left w-8"></th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => toggleSort('email')}>Email <SortIcon col="email" /></th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => toggleSort('health')}>Health <SortIcon col="health" /></th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => toggleSort('warmup')}>Warmup <SortIcon col="warmup" /></th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => toggleSort('sent')}>Sent <SortIcon col="sent" /></th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => toggleSort('opened')}>Opened <SortIcon col="opened" /></th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => toggleSort('clicked')}>Clicked <SortIcon col="clicked" /></th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => toggleSort('replied')}>Replied <SortIcon col="replied" /></th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => toggleSort('bounced')}>Bounced <SortIcon col="bounced" /></th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => toggleSort('unsub')}>Unsub <SortIcon col="unsub" /></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {sorted.map((m: any) => {
                  const isSelected = assignedIds.includes(m.mailbox_id)
                  const sent = m.campaign_sent || 0
                  const opened = m.campaign_opened || 0
                  const clicked = m.campaign_clicked || 0
                  const replied = m.campaign_replied || 0
                  const bounced = m.campaign_bounced || 0
                  const unsub = m.campaign_unsubscribed || 0
                  return (
                    <tr key={m.mailbox_id} className={`hover:bg-gray-50 dark:hover:bg-gray-700 ${isSelected ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
                      <td className="px-3 py-2">
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
                      <td className="px-3 py-2 text-gray-900 dark:text-gray-100 font-medium">{m.email}</td>
                      <td className="px-3 py-2">
                        {(() => {
                          const h = mailboxHealthMap[m.mailbox_id]
                          const score = h?.health_score ?? '-'
                          const grade = h?.health_grade || ''
                          const numScore = typeof score === 'number' ? score : 0
                          return h ? (
                            <span className={`px-2 py-0.5 text-xs rounded-full ${numScore >= 80 ? 'bg-green-100 text-green-800' : numScore >= 50 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800'}`}>
                              {score} ({grade})
                            </span>
                          ) : (
                            <span className="text-xs text-gray-400">...</span>
                          )
                        })()}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 text-xs rounded-full ${m.warmup_status === 'completed' ? 'bg-green-100 text-green-800' : m.warmup_status === 'active' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'}`}>
                          {m.warmup_status || 'none'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right text-gray-900 dark:text-gray-100 font-medium">{sent}</td>
                      <td className="px-3 py-2 text-right">
                        <span className="text-gray-900 dark:text-gray-100">{opened}</span>
                        {sent > 0 && <span className="text-xs text-gray-400 ml-1">({m.open_rate || 0}%)</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className="text-gray-900 dark:text-gray-100">{clicked}</span>
                        {sent > 0 && <span className="text-xs text-gray-400 ml-1">({m.click_rate || 0}%)</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className="text-green-600">{replied}</span>
                        {sent > 0 && <span className="text-xs text-gray-400 ml-1">({m.reply_rate || 0}%)</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className={bounced > 0 ? 'text-red-600' : 'text-gray-900 dark:text-gray-100'}>{bounced}</span>
                        {sent > 0 && <span className="text-xs text-gray-400 ml-1">({m.bounce_rate || 0}%)</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className={unsub > 0 ? 'text-orange-600' : 'text-gray-900 dark:text-gray-100'}>{unsub}</span>
                      </td>
                    </tr>
                  )
                })}
                {sorted.length === 0 && (
                  <tr><td colSpan={10} className="px-4 py-6 text-center text-gray-500">{mailboxes.length === 0 ? 'No mailboxes available' : 'No mailboxes match your search'}</td></tr>
                )}
              </tbody>
              {totals.sent > 0 && (
                  <tfoot className="bg-gray-50 dark:bg-gray-700 font-medium">
                    <tr>
                      <td className="px-3 py-2" colSpan={4}><span className="text-xs uppercase text-gray-500">Total (assigned)</span></td>
                      <td className="px-3 py-2 text-right">{totals.sent}</td>
                      <td className="px-3 py-2 text-right">{totals.opened} <span className="text-xs text-gray-400">({(totals.opened/totals.sent*100).toFixed(1)}%)</span></td>
                      <td className="px-3 py-2 text-right">{totals.clicked} <span className="text-xs text-gray-400">({(totals.clicked/totals.sent*100).toFixed(1)}%)</span></td>
                      <td className="px-3 py-2 text-right text-green-600">{totals.replied} <span className="text-xs text-gray-400">({(totals.replied/totals.sent*100).toFixed(1)}%)</span></td>
                      <td className="px-3 py-2 text-right text-red-600">{totals.bounced} <span className="text-xs text-gray-400">({(totals.bounced/totals.sent*100).toFixed(1)}%)</span></td>
                      <td className="px-3 py-2 text-right text-orange-600">{totals.unsub}</td>
                    </tr>
                  </tfoot>
              )}
            </table>
          </div>
          )}
        </div>
        )
      })()}

      {/* Leads & Contacts Tab */}
      {/* Top section removed — merged into bottom lead-grouped view */}

      {/* Schedule Tab */}
      {detailTab === 'schedule' && selectedCampaign && (
        <div className="space-y-4">
          {/* Header with Add button */}
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">Schedules</h3>
            <button
              onClick={() => {
                setScheduleModalMode('add')
                setEditingScheduleId(null)
                setScheduleFormData({
                  start_date: new Date().toISOString().split('T')[0],
                  end_date: '',
                  send_window_start: '09:00',
                  send_window_end: '17:00',
                  send_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
                  timezone: selectedCampaign.timezone || 'US/Eastern',
                  label: '',
                  no_end_date: true,
                })
                setScheduleModalOpen(true)
              }}
              className="text-xs bg-primary-600 text-white px-3 py-1.5 rounded hover:bg-primary-700 flex items-center gap-1"
            >
              <span>+</span> Add Schedule
            </button>
          </div>

          {/* Schedule Cards */}
          {schedulesLoading ? (
            <div className="text-sm text-gray-500 py-4 text-center">Loading schedules...</div>
          ) : campaignSchedules.length === 0 ? (
            <div className="bg-white dark:bg-gray-800 border rounded-lg p-6 text-center">
              <p className="text-sm text-gray-500">No schedules configured. Add one to control when emails are sent.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {campaignSchedules.map((sched: any) => {
                const today = new Date().toISOString().split('T')[0]
                const isExpired = sched.end_date && sched.end_date < today
                const isFuture = sched.start_date > today
                const isActive = !isExpired && !isFuture
                const statusLabel = isExpired ? 'Expired' : isFuture ? 'Future' : 'Active'
                const statusColor = isExpired ? 'text-red-600 bg-red-50' : isFuture ? 'text-yellow-600 bg-yellow-50' : 'text-green-600 bg-green-50'
                const sendDays = sched.send_days || []
                const dayDisplay = sendDays.length === 7 ? 'Every day' : sendDays.length === 5 && !sendDays.includes('sat') && !sendDays.includes('sun') ? 'Mon-Fri' : sendDays.map((d: string) => d.charAt(0).toUpperCase() + d.slice(1)).join(', ')
                const tzLabel = TIMEZONE_OPTIONS.find(t => t.value === sched.timezone)?.label || sched.timezone

                return (
                  <div key={sched.schedule_id} className="bg-white dark:bg-gray-800 border rounded-lg p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-sm text-gray-900 dark:text-gray-100">{sched.label || 'Schedule'}</span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => {
                            setScheduleModalMode('edit')
                            setEditingScheduleId(sched.schedule_id)
                            setScheduleFormData({
                              start_date: sched.start_date || '',
                              end_date: sched.end_date || '',
                              send_window_start: sched.send_window_start || '09:00',
                              send_window_end: sched.send_window_end || '17:00',
                              send_days: sched.send_days || ['mon', 'tue', 'wed', 'thu', 'fri'],
                              timezone: sched.timezone || 'US/Eastern',
                              label: sched.label || '',
                              no_end_date: !sched.end_date,
                            })
                            setScheduleModalOpen(true)
                          }}
                          className="text-xs text-primary-600 hover:text-primary-700"
                        >
                          Edit
                        </button>
                        <button
                          onClick={async () => {
                            if (!confirm('Delete this schedule?')) return
                            try {
                              await campaignsApi.deleteSchedule(selectedCampaign.campaign_id, sched.schedule_id)
                              setCampaignSchedules(prev => prev.filter(s => s.schedule_id !== sched.schedule_id))
                            } catch { /* interceptor */ }
                          }}
                          className="text-xs text-red-500 hover:text-red-700"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    <div className="text-xs text-gray-500">
                      {sched.start_date ? new Date(sched.start_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                      {' → '}
                      {sched.end_date ? new Date(sched.end_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'No end date'}
                    </div>
                    <div className="text-xs text-gray-600 dark:text-gray-400">
                      {sched.send_window_start} - {sched.send_window_end} · {dayDisplay} · {tzLabel}
                    </div>
                    <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${statusColor}`}>
                      {statusLabel}
                    </span>
                  </div>
                )
              })}
            </div>
          )}

          {/* Smart Scheduling + Timezone Distribution */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-white dark:bg-gray-800 border rounded-lg p-4 space-y-3">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">Smart Scheduling</h3>
              <div className="bg-blue-50 dark:bg-blue-900/30 rounded-lg p-3">
                <p className="text-sm text-blue-700 dark:text-blue-300">
                  Emails are sent at optimal local times for each contact based on their timezone.
                  Peak windows: 9-11 AM (highest), 2-3:30 PM (second), 7:30-9 AM (third).
                </p>
              </div>
            </div>
            <div className="bg-white dark:bg-gray-800 border rounded-lg p-4 space-y-3">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">Timezone Distribution</h3>
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

          {/* Schedule Add/Edit Modal */}
          {scheduleModalOpen && (
            <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setScheduleModalOpen(false)}>
              <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-5 space-y-4" onClick={e => e.stopPropagation()}>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {scheduleModalMode === 'add' ? 'Add Schedule' : 'Edit Schedule'}
                </h3>

                {/* Label */}
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Label (optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. Morning shift, Weekend promo"
                    value={scheduleFormData.label}
                    onChange={e => setScheduleFormData(f => ({ ...f, label: e.target.value }))}
                    className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                  />
                </div>

                {/* Date Range */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Start Date</label>
                    <input
                      type="date"
                      value={scheduleFormData.start_date}
                      onChange={e => setScheduleFormData(f => ({ ...f, start_date: e.target.value }))}
                      className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">End Date</label>
                    <input
                      type="date"
                      value={scheduleFormData.no_end_date ? '' : scheduleFormData.end_date}
                      disabled={scheduleFormData.no_end_date}
                      onChange={e => setScheduleFormData(f => ({ ...f, end_date: e.target.value }))}
                      className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100 disabled:opacity-50"
                    />
                    <label className="flex items-center gap-1 mt-1 text-xs text-gray-500">
                      <input
                        type="checkbox"
                        checked={scheduleFormData.no_end_date}
                        onChange={e => setScheduleFormData(f => ({ ...f, no_end_date: e.target.checked, end_date: '' }))}
                        className="rounded"
                      />
                      No end date
                    </label>
                  </div>
                </div>

                {/* Time Window */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Start Time</label>
                    <input
                      type="time"
                      value={scheduleFormData.send_window_start}
                      onChange={e => setScheduleFormData(f => ({ ...f, send_window_start: e.target.value }))}
                      className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">End Time</label>
                    <input
                      type="time"
                      value={scheduleFormData.send_window_end}
                      onChange={e => setScheduleFormData(f => ({ ...f, send_window_end: e.target.value }))}
                      className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                    />
                  </div>
                </div>

                {/* Send Days */}
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Send Days</label>
                  <div className="flex gap-1 flex-wrap">
                    {DAY_LABELS.map(day => {
                      const dayKey = day.toLowerCase().slice(0, 3)
                      const isActive = scheduleFormData.send_days.includes(dayKey)
                      return (
                        <button
                          key={day}
                          type="button"
                          onClick={() => {
                            setScheduleFormData(f => ({
                              ...f,
                              send_days: f.send_days.includes(dayKey)
                                ? f.send_days.filter(d => d !== dayKey)
                                : [...f.send_days, dayKey],
                            }))
                          }}
                          className={`px-2.5 py-1 text-xs rounded cursor-pointer hover:opacity-80 ${
                            isActive ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-400'
                          }`}
                        >
                          {day}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Timezone */}
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Timezone</label>
                  <select
                    value={scheduleFormData.timezone}
                    onChange={e => setScheduleFormData(f => ({ ...f, timezone: e.target.value }))}
                    className="w-full px-3 py-1.5 text-sm border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                  >
                    {TIMEZONE_OPTIONS.map(tz => (
                      <option key={tz.value} value={tz.value}>{tz.label}</option>
                    ))}
                  </select>
                </div>

                {/* Actions */}
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    onClick={() => setScheduleModalOpen(false)}
                    className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5"
                  >
                    Cancel
                  </button>
                  <button
                    disabled={scheduleSaving || !scheduleFormData.start_date}
                    onClick={async () => {
                      setScheduleSaving(true)
                      try {
                        const payload = {
                          start_date: scheduleFormData.start_date,
                          end_date: scheduleFormData.no_end_date ? null : (scheduleFormData.end_date || null),
                          send_window_start: scheduleFormData.send_window_start,
                          send_window_end: scheduleFormData.send_window_end,
                          send_days: scheduleFormData.send_days,
                          timezone: scheduleFormData.timezone,
                          label: scheduleFormData.label || null,
                        }
                        if (scheduleModalMode === 'add') {
                          const created = await campaignsApi.addSchedule(selectedCampaign.campaign_id, payload)
                          setCampaignSchedules(prev => [...prev, created])
                        } else if (editingScheduleId) {
                          const updated = await campaignsApi.updateSchedule(selectedCampaign.campaign_id, editingScheduleId, payload)
                          setCampaignSchedules(prev => prev.map(s => s.schedule_id === editingScheduleId ? updated : s))
                        }
                        setScheduleModalOpen(false)
                      } catch { /* interceptor */ }
                      setScheduleSaving(false)
                    }}
                    className="text-sm bg-primary-600 text-white px-4 py-1.5 rounded hover:bg-primary-700 disabled:opacity-50"
                  >
                    {scheduleSaving ? 'Saving...' : scheduleModalMode === 'add' ? 'Add Schedule' : 'Save Changes'}
                  </button>
                </div>
              </div>
            </div>
          )}
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
              onEditStep={(step) => openStepModal(step)}
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
                        <button
                          onClick={async () => {
                            if (!selectedCampaign) return
                            setAiPreviewLoading(true)
                            setAiPreviewResults(null)
                            setShowAIPreviewModal(true)
                            try {
                              const res = await emailPreviewApi.previewPersonalization({
                                campaign_id: selectedCampaign.campaign_id,
                                step_index: step.step_order,
                              })
                              setAiPreviewResults(res.results || [])
                            } catch (err: any) {
                              setAiPreviewResults([])
                              console.error('AI Preview error:', err)
                            } finally {
                              setAiPreviewLoading(false)
                            }
                          }}
                          className="p-1 hover:bg-purple-50 dark:hover:bg-purple-900/20 rounded"
                          title="AI Personalization Preview"
                        >
                          <Sparkles className="w-4 h-4 text-purple-500" />
                        </button>
                      </>
                    )}
                    <button onClick={() => openStepModal(step)} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded">
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
          <button onClick={() => openStepModal(null)} className="w-full py-3 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg text-gray-500 hover:border-primary-500 hover:text-primary-600 flex items-center justify-center gap-2">
            <Plus className="w-4 h-4" /> Add Step
          </button>
        </div>
      )}

      {/* Leads & Contacts — Lead-grouped table with contact expansion */}
      {(detailTab === 'leads_contacts') && (() => {
        // Build contactSchedule lookup for timezone/score data
        const scheduleMap = new Map<number, any>()
        for (const cs of contactSchedule) scheduleMap.set(cs.contact_id, cs)

        // Group contacts by lead_id
        const leadGroups: { key: number | string; lead_id: number | null; cc: any; contacts: any[] }[] = []
        const grouped = new Map<number | string, any[]>()
        for (const cc of contacts) {
          const key = cc.lead_id ?? 'ungrouped'
          if (!grouped.has(key)) grouped.set(key, [])
          grouped.get(key)!.push(cc)
        }
        grouped.forEach((ccs, key) => {
          const first = ccs[0]
          leadGroups.push({ key, lead_id: typeof key === 'number' ? key : null, cc: first, contacts: ccs })
        })
        leadGroups.sort((a, b) => {
          if (a.key === 'ungrouped') return 1
          if (b.key === 'ungrouped') return -1
          return (a.cc.lead_company || '').localeCompare(b.cc.lead_company || '')
        })

        const toggleLead = (key: number | string) => {
          setExpandedLeads(prev => {
            const next = new Set(prev)
            if (next.has(key)) next.delete(key)
            else next.add(key)
            return next
          })
        }

        const statusBadge = (s: string) => {
          const cls = s === 'open' ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300' :
            s === 'hunting' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300' :
            s?.startsWith('closed') ? 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300' :
            'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
          return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>{s}</span>
        }

        const contactStatusBadge = (s: string) => {
          const cls = s === 'active' ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300' :
            s === 'replied' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300' :
            s === 'completed' ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300' :
            s === 'paused' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300' :
            s === 'bounced' ? 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300' :
            'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
          return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>{s}</span>
        }

        return (
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">{contacts.length} enrolled contacts across {leadGroups.length} lead{leadGroups.length !== 1 ? 's' : ''}</span>
              <div className="flex items-center gap-2">
                {removeContactIds.size > 0 && (
                  <button
                    onClick={() => handleRemoveContacts(Array.from(removeContactIds))}
                    className="px-3 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 flex items-center gap-2 text-sm"
                  >
                    <Trash2 className="w-4 h-4" /> Remove Selected ({removeContactIds.size})
                  </button>
                )}
                <button onClick={openEnrollModal} className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 flex items-center gap-2 text-sm">
                  <Users className="w-4 h-4" /> Enroll Contacts
                </button>
              </div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-x-auto">
              {contacts.length === 0 ? (
                <div className="p-8 text-center text-gray-500">No contacts enrolled yet</div>
              ) : (
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 dark:bg-gray-700 sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase w-8"></th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">ID</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">Company / Job Title</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">State</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">Posted</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">Source</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">Type</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">Industry</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">Size</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">Link</th>
                      <th className="px-3 py-2 text-center font-medium text-gray-500 uppercase">Contacts</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {leadGroups.map(group => {
                      const isExpanded = expandedLeads.has(group.key)
                      const f = group.cc as any
                      return (
                        <React.Fragment key={String(group.key)}>
                          {/* Lead row */}
                          <tr
                            className="hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer"
                            onClick={() => toggleLead(group.key)}
                          >
                            <td className="px-3 py-2.5">
                              {isExpanded ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
                            </td>
                            <td className="px-3 py-2.5 text-gray-500">{group.lead_id || '—'}</td>
                            <td className="px-3 py-2.5">
                              {group.lead_id ? (
                                <div>
                                  <a
                                    href={`/dashboard/leads/${group.lead_id}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="font-medium text-gray-900 dark:text-gray-100 hover:text-primary-600 hover:underline"
                                    onClick={e => e.stopPropagation()}
                                  >
                                    {f.lead_company || 'Unknown'}
                                  </a>
                                  {f.lead_title && <p className="text-gray-500 truncate max-w-[200px]">{f.lead_title}</p>}
                                </div>
                              ) : (
                                <span className="text-gray-500 italic">Ungrouped</span>
                              )}
                            </td>
                            <td className="px-3 py-2.5 text-gray-600">{f.lead_state || '—'}</td>
                            <td className="px-3 py-2.5 text-gray-500">{f.lead_posted ? new Date(f.lead_posted).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}</td>
                            <td className="px-3 py-2.5 text-gray-500">{f.lead_source || '—'}</td>
                            <td className="px-3 py-2.5">
                              {f.lead_employment_type ? (
                                <span className={`text-xs px-1.5 py-0.5 rounded ${
                                  f.lead_employment_type === 'Full-time' ? 'bg-green-100 text-green-700' :
                                  f.lead_employment_type === 'Contract' ? 'bg-orange-100 text-orange-700' :
                                  f.lead_employment_type === 'Part-time' ? 'bg-blue-100 text-blue-700' :
                                  f.lead_employment_type === 'Temporary' ? 'bg-yellow-100 text-yellow-700' :
                                  'bg-gray-100 text-gray-700'
                                }`}>{f.lead_employment_type}</span>
                              ) : <span className="text-gray-400">—</span>}
                            </td>
                            <td className="px-3 py-2.5 text-gray-500 max-w-[100px] truncate">{f.lead_industry || '—'}</td>
                            <td className="px-3 py-2.5 text-gray-500">{f.lead_company_size || '—'}</td>
                            <td className="px-3 py-2.5">
                              {f.lead_job_link ? (
                                <a href={f.lead_job_link} target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:underline" onClick={e => e.stopPropagation()}>
                                  <Link2 className="w-3.5 h-3.5" />
                                </a>
                              ) : '—'}
                            </td>
                            <td className="px-3 py-2.5 text-center font-medium">{group.contacts.length}</td>
                            <td className="px-3 py-2.5">{f.lead_status ? statusBadge(f.lead_status) : '—'}</td>
                          </tr>
                          {/* Expanded contacts */}
                          {isExpanded && (
                            <>
                              <tr className="bg-gray-100/80 dark:bg-gray-700/60">
                                <td></td>
                                <td colSpan={11} className="px-0 py-0">
                                  <table className="w-full text-xs">
                                    <thead>
                                      <tr className="text-gray-500 uppercase">
                                        <th className="w-8 px-2 pl-6 py-1.5">
                                          <input
                                            type="checkbox"
                                            checked={group.contacts.every((cc: any) => removeContactIds.has(cc.contact_id))}
                                            onChange={(e) => {
                                              setRemoveContactIds(prev => {
                                                const next = new Set(prev)
                                                for (const cc of group.contacts) {
                                                  if (e.target.checked) next.add(cc.contact_id)
                                                  else next.delete(cc.contact_id)
                                                }
                                                return next
                                              })
                                            }}
                                            className="w-3.5 h-3.5 rounded"
                                          />
                                        </th>
                                        <th className="text-left px-3 py-1.5 font-medium">Contact</th>
                                        <th className="text-left px-3 py-1.5 font-medium">Email</th>
                                        <th className="text-left px-3 py-1.5 font-medium">Timezone</th>
                                        <th className="text-left px-3 py-1.5 font-medium">Best Send</th>
                                        <th className="text-center px-3 py-1.5 font-medium">Score</th>
                                        <th className="text-left px-3 py-1.5 font-medium">Status</th>
                                        <th className="text-center px-3 py-1.5 font-medium">Step</th>
                                        <th className="text-left px-3 py-1.5 font-medium">Next Send</th>
                                        <th className="text-right px-3 py-1.5 font-medium">Actions</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-200/60 dark:divide-gray-600/40">
                                      {group.contacts.map((cc: any) => {
                                        const sched = scheduleMap.get(cc.contact_id)
                                        const tz = (cc as any).contact_timezone || sched?.timezone_label || '—'
                                        const tzLabel = sched?.timezone_label || tz
                                        const bestSend = sched?.recommended_local_time || '—'
                                        const score = sched?.combined_score
                                        return (
                                          <tr key={cc.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 bg-white/50 dark:bg-gray-800/50">
                                            <td className="px-2 pl-6 py-2">
                                              <input
                                                type="checkbox"
                                                checked={removeContactIds.has(cc.contact_id)}
                                                onChange={(e) => {
                                                  setRemoveContactIds(prev => {
                                                    const next = new Set(prev)
                                                    if (e.target.checked) next.add(cc.contact_id)
                                                    else next.delete(cc.contact_id)
                                                    return next
                                                  })
                                                }}
                                                className="w-3.5 h-3.5 rounded"
                                              />
                                            </td>
                                            <td className="px-3 py-2 font-medium text-gray-900 dark:text-gray-100">
                                              {cc.contact_name || `Contact #${cc.contact_id}`}
                                            </td>
                                            <td className="px-3 py-2 text-gray-500 max-w-[160px] truncate">{cc.contact_email || '—'}</td>
                                            <td className="px-3 py-2 text-gray-500">{tzLabel}</td>
                                            <td className="px-3 py-2 text-gray-500">{bestSend}</td>
                                            <td className="px-3 py-2 text-center">
                                              {score != null ? (
                                                <span className={`px-1.5 py-0.5 rounded text-xs ${score >= 0.8 ? 'bg-green-100 text-green-700' : score >= 0.5 ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-600'}`}>
                                                  {(score * 100).toFixed(0)}%
                                                </span>
                                              ) : '—'}
                                            </td>
                                            <td className="px-3 py-2">{contactStatusBadge(cc.status)}</td>
                                            <td className="px-3 py-2 text-center text-gray-600 dark:text-gray-400">Step {cc.current_step}</td>
                                            <td className="px-3 py-2 text-gray-500">{cc.next_send_at ? new Date(cc.next_send_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</td>
                                            <td className="px-3 py-2 text-right flex items-center justify-end gap-1">
                                              <button
                                                onClick={() => selectedCampaign && handleThreadPreview(selectedCampaign.campaign_id, cc.contact_id)}
                                                className="text-xs text-primary-600 hover:underline"
                                              >Thread</button>
                                              <button
                                                onClick={() => handleRemoveContacts([cc.contact_id])}
                                                className="p-1 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                                                title="Remove from campaign"
                                              >
                                                <Trash2 className="w-3.5 h-3.5 text-red-400 hover:text-red-600" />
                                              </button>
                                            </td>
                                          </tr>
                                        )
                                      })}
                                    </tbody>
                                  </table>
                                </td>
                              </tr>
                            </>
                          )}
                        </React.Fragment>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )
      })()}

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
            <div className="relative bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
              <button
                onClick={() => fetchHealthDetail(selectedCampaign.campaign_id, 'analytics')}
                className="w-full flex items-center gap-3 cursor-pointer hover:opacity-80"
              >
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
                <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${healthDetailOpen === 'analytics' ? 'rotate-180' : ''}`} />
              </button>
              {healthDetailOpen === 'analytics' && (
                <div className="mt-3 border-t border-gray-200 dark:border-gray-700 pt-3">
                  {healthDetailLoading ? (
                    <div className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="w-4 h-4 animate-spin" /> Loading breakdown...</div>
                  ) : healthDetail && healthDetail.score != null ? (
                    <div className="space-y-3">
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        {['deliverability', 'engagement', 'volume'].map(key => {
                          const val = healthDetail.components?.[key] ?? 0
                          const weight = key === 'deliverability' ? 40 : key === 'engagement' ? 35 : 25
                          return (
                            <div key={key} className="text-center">
                              <p className="text-xs text-gray-500 capitalize mb-1">{key}</p>
                              <p className={`text-lg font-bold ${val >= 70 ? 'text-green-600' : val >= 40 ? 'text-yellow-600' : 'text-red-600'}`}>{Math.round(val)}</p>
                              <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full mt-1">
                                <div className={`h-full rounded-full ${val >= 70 ? 'bg-green-500' : val >= 40 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${val}%` }} />
                              </div>
                              <p className="text-[10px] text-gray-400 mt-0.5">{Math.round(val * weight / 100)}/{weight} pts</p>
                            </div>
                          )
                        })}
                      </div>
                      {healthDetail.explanation?.length > 0 && (
                        <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5">
                          {healthDetail.explanation.map((line: string, i: number) => <p key={i}>{line}</p>)}
                        </div>
                      )}
                      {healthDetail.recommendations?.length > 0 && (
                        <div className="text-xs space-y-1 border-t pt-2">
                          <p className="font-medium text-gray-700 dark:text-gray-300">Recommendations</p>
                          {healthDetail.recommendations.map((rec: string, i: number) => (
                            <p key={i} className="text-gray-500 dark:text-gray-400 flex gap-1"><span>•</span><span>{rec}</span></p>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-500">Unable to load health details.</p>
                  )}
                </div>
              )}
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
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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

      {/* Step Modal — Rich Two-Panel Editor */}
      {showStepModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowStepModal(false)}>
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-6xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700 shrink-0">
              <h2 className="text-lg font-bold dark:text-gray-100">{editingStep ? 'Edit Step' : 'Add Step'}</h2>
              <button onClick={() => setShowStepModal(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"><X className="w-5 h-5" /></button>
            </div>

            {/* Body */}
            <div className="flex flex-1 overflow-hidden min-h-0">
              {/* Left: Intelligence Panel (email only) */}
              {stepForm.step_type === 'email' && (
                <div className="w-72 shrink-0 bg-gray-50 dark:bg-gray-900/50 border-r border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
                  {/* Tab bar */}
                  <div className="border-b border-gray-200 dark:border-gray-700 px-1 flex flex-wrap">
                    {STEP_INTEL_TABS.map(tab => (
                      <button
                        key={tab.id}
                        onClick={() => setStepIntelTab(tab.id)}
                        className={`flex items-center gap-1 px-2 py-2 text-[10px] font-medium border-b-2 whitespace-nowrap transition-colors ${
                          stepIntelTab === tab.id
                            ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                            : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                        }`}
                      >
                        <tab.icon className="w-3 h-3" />
                        {tab.label}
                      </button>
                    ))}
                  </div>

                  {/* Tab content */}
                  <div className="flex-1 overflow-y-auto">

                    {/* ─── Placeholders Tab ─── */}
                    {stepIntelTab === 'placeholders' && (
                      <div className="p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <Info className="w-4 h-4 text-blue-600" />
                          <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">Placeholders</h4>
                        </div>
                        <p className="text-xs text-gray-500 mb-3">Drag into subject/body, or click to insert at cursor.</p>
                        <div className="space-y-1.5">
                          {STEP_PLACEHOLDERS.map(({ tag, label }) => (
                            <div
                              key={tag}
                              draggable
                              onDragStart={(e) => handlePlaceholderDragStart(e, tag)}
                              onClick={() => handleStepPlaceholderClick(tag)}
                              className="flex items-center gap-2 px-2.5 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md cursor-grab active:cursor-grabbing hover:border-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors group select-none"
                              title={`Drag or click to insert ${tag}`}
                            >
                              <GripVertical className="w-3.5 h-3.5 text-gray-300 group-hover:text-blue-400 shrink-0" />
                              <div className="min-w-0">
                                <div className="text-xs font-mono text-blue-700 dark:text-blue-400 truncate">{tag}</div>
                                <div className="text-[10px] text-gray-500 truncate">{label}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* ─── Scorecard Tab ─── */}
                    {stepIntelTab === 'scorecard' && (
                      <div>
                        {stepScorecardLoading ? (
                          <div className="flex items-center justify-center py-12"><Loader2 className="w-5 h-5 animate-spin text-gray-400" /></div>
                        ) : stepScorecardResult ? (
                          <>
                            <div className="flex justify-center py-4">
                              <StepScoreGauge score={stepScorecardResult.overall_score} size={120} />
                            </div>
                            <div className="text-center mb-4">
                              <span className="text-sm font-bold text-gray-700 dark:text-gray-300">Grade: {stepScorecardResult.overall_grade}</span>
                              <div className={`mt-1 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                                stepScorecardResult.recommendation === 'SEND' ? 'bg-green-100 text-green-800' :
                                stepScorecardResult.recommendation === 'REVIEW' ? 'bg-yellow-100 text-yellow-800' :
                                'bg-red-100 text-red-800'
                              }`}>
                                {stepScorecardResult.recommendation === 'SEND' && <CheckCircle className="w-3 h-3" />}
                                {stepScorecardResult.recommendation === 'REVIEW' && <AlertTriangle className="w-3 h-3" />}
                                {stepScorecardResult.recommendation === 'DO_NOT_SEND' && <X className="w-3 h-3" />}
                                {stepScorecardResult.recommendation_label}
                              </div>
                            </div>
                            <div className="px-3 space-y-1.5 pb-3">
                              {STEP_DIMENSION_ORDER.map(key => {
                                const dim = stepScorecardResult.dimensions[key]
                                if (!dim) return null
                                const isExpanded = stepExpandedDimensions.has(key)
                                const barColor = dim.score >= 70 ? 'bg-green-500' : dim.score >= 40 ? 'bg-yellow-500' : 'bg-red-500'
                                return (
                                  <div key={key} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                                    <button
                                      onClick={() => setStepExpandedDimensions(prev => {
                                        const next = new Set(prev)
                                        if (next.has(key)) next.delete(key); else next.add(key)
                                        return next
                                      })}
                                      className="w-full px-2.5 py-2 flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                                    >
                                      <ChevronDown className={`w-3 h-3 text-gray-400 transition-transform ${isExpanded ? '' : '-rotate-90'}`} />
                                      <span className="text-[11px] text-gray-600 dark:text-gray-400 flex-1 text-left truncate">{STEP_DIMENSION_LABELS[key] || key}</span>
                                      <div className="w-16 h-1.5 rounded-full bg-gray-200 dark:bg-gray-600 overflow-hidden">
                                        <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${dim.score}%` }} />
                                      </div>
                                      <span className="text-[11px] font-medium w-6 text-right" style={{ color: stepScoreColor(dim.score) }}>{dim.score}</span>
                                    </button>
                                    {isExpanded && dim.issues.length > 0 && (
                                      <div className="px-2.5 pb-2 space-y-1 border-t border-gray-100 dark:border-gray-700">
                                        {dim.issues.map((issue: any, i: number) => (
                                          <div key={i} className={`text-[10px] px-2 py-1 rounded mt-1 ${
                                            issue.severity === 'high' ? 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300' :
                                            issue.severity === 'medium' ? 'bg-yellow-50 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300' :
                                            'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                                          }`}>{issue.message}</div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                            <div className="px-3 pb-3">
                              <div className="flex items-center justify-between text-xs text-gray-500 mb-2">
                                <span>{stepScorecardResult.total_issues} issue{stepScorecardResult.total_issues !== 1 ? 's' : ''}</span>
                                {stepScorecardResult.critical_issues > 0 && <span className="text-red-600 font-medium">{stepScorecardResult.critical_issues} critical</span>}
                              </div>
                              {stepScorecardResult.total_issues > 0 && (
                                <button onClick={() => setStepIntelTab('fixes')} className="w-full text-xs py-1.5 text-blue-600 hover:underline flex items-center justify-center gap-1">
                                  <Wrench className="w-3 h-3" /> Go to Fixes tab
                                </button>
                              )}
                              <button onClick={() => { setStepScorecardResult(null); handleStepScorecard() }} className="w-full text-xs py-1.5 text-gray-500 hover:underline flex items-center justify-center gap-1 mt-1">
                                <RefreshCw className="w-3 h-3" /> Re-score
                              </button>
                            </div>
                          </>
                        ) : (
                          <div className="text-center py-8 px-4">
                            <BarChart3 className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                            <p className="text-xs text-gray-500 mb-3">Score your email across 10 quality dimensions.</p>
                            <button onClick={handleStepScorecard} disabled={!stepForm.subject && !stepForm.body_html} className="text-xs py-2 px-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-1 mx-auto">
                              <BarChart3 className="w-3 h-3" /> Score Email
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {/* ─── Fixes Tab ─── */}
                    {stepIntelTab === 'fixes' && (
                      <div>
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                            <Wrench className="w-4 h-4 text-blue-500" /> Fix Suggestions
                          </h3>
                          <p className="text-xs text-gray-500 mt-1">Auto-apply fixes to improve your email score.</p>
                        </div>
                        {stepApplyResult && (
                          <div className="mx-3 mt-3 p-3 rounded-lg bg-gradient-to-r from-red-50 to-green-50 dark:from-red-900/20 dark:to-green-900/20 border border-gray-200 dark:border-gray-700">
                            <div className="flex items-center justify-center gap-3">
                              <div className="text-center">
                                <div className="text-lg font-bold" style={{ color: stepScoreColor(stepApplyResult.before_score) }}>{stepApplyResult.before_score}</div>
                                <div className="text-[10px] text-gray-500">Before</div>
                              </div>
                              <ChevronRight className="w-4 h-4 text-gray-400" />
                              <div className="text-center">
                                <div className="text-lg font-bold" style={{ color: stepScoreColor(stepApplyResult.after_score) }}>{stepApplyResult.after_score}</div>
                                <div className="text-[10px] text-gray-500">After</div>
                              </div>
                              <span className={`text-xs font-medium ${stepApplyResult.delta >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                {stepApplyResult.delta >= 0 ? '+' : ''}{stepApplyResult.delta}
                              </span>
                            </div>
                            <div className="flex items-center justify-center gap-3 mt-2 text-[10px] text-gray-500">
                              <span>Applied: {stepApplyResult.applied_fixes.length}</span>
                              <span>Skipped: {stepApplyResult.skipped_fixes.length}</span>
                            </div>
                          </div>
                        )}
                        <div className="p-3 space-y-2">
                          {!stepFixesResult ? (
                            <button onClick={handleStepGetFixes} disabled={stepFixesLoading || (!stepForm.subject && !stepForm.body_html)} className="w-full text-xs py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-1">
                              {stepFixesLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wrench className="w-3 h-3" />} Get Fix Suggestions
                            </button>
                          ) : stepFixesLoading ? (
                            <div className="flex items-center justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-gray-400" /></div>
                          ) : stepFixesResult.fixes.length === 0 ? (
                            <div className="text-center py-4 text-gray-400">
                              <CheckCircle className="w-8 h-8 mx-auto mb-2 text-green-500" />
                              <p className="text-sm font-medium text-green-600">No fixes needed</p>
                              <p className="text-xs mt-1">This email looks great!</p>
                            </div>
                          ) : (
                            <>
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-xs text-gray-500">{stepFixesResult.fix_count} suggestion{stepFixesResult.fix_count !== 1 ? 's' : ''} ({stepFixesResult.auto_fixable_count} auto-fix)</span>
                                {stepFixesResult.auto_fixable_count > 0 && (
                                  <button onClick={() => {
                                    const autoIds = new Set<string>(stepFixesResult.fixes.filter((f: any) => f.auto_fixable).map((f: any) => f.id))
                                    setStepSelectedFixIds(prev => {
                                      const allSelected = stepFixesResult.fixes.filter((f: any) => f.auto_fixable).every((f: any) => prev.has(f.id))
                                      return allSelected ? new Set() : autoIds
                                    })
                                  }} className="text-[10px] text-blue-600 hover:underline">
                                    {stepFixesResult.fixes.filter((f: any) => f.auto_fixable).every((f: any) => stepSelectedFixIds.has(f.id)) ? 'Deselect All' : 'Select All Auto-Fix'}
                                  </button>
                                )}
                              </div>
                              {stepSelectedFixIds.size > 0 && (
                                <button onClick={handleStepApplySelectedFixes} disabled={stepApplyingFixes} className="w-full text-xs py-2 px-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-1 font-medium mb-2">
                                  {stepApplyingFixes ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
                                  Apply {stepSelectedFixIds.size} Selected Fix{stepSelectedFixIds.size !== 1 ? 'es' : ''}
                                </button>
                              )}
                              {stepFixesResult.fixes.map((fix: any) => {
                                const isSelected = stepSelectedFixIds.has(fix.id)
                                const canToggle = fix.auto_fixable
                                return (
                                  <div key={fix.id} onClick={() => { if (!canToggle) return; setStepSelectedFixIds(prev => { const next = new Set(prev); if (next.has(fix.id)) next.delete(fix.id); else next.add(fix.id); return next }) }} className={`p-2.5 border rounded-lg transition-colors ${canToggle ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50' : 'opacity-70'} ${isSelected ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-200 dark:border-gray-700'}`}>
                                    <div className="flex items-start gap-2">
                                      <input type="checkbox" checked={isSelected} disabled={!canToggle} onChange={() => {}} className="mt-0.5 w-3.5 h-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-40" />
                                      <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-1.5 mb-1">
                                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${fix.severity === 'high' ? 'bg-red-100 text-red-800' : fix.severity === 'medium' ? 'bg-yellow-100 text-yellow-800' : 'bg-blue-100 text-blue-800'}`}>{fix.severity.toUpperCase()}</span>
                                          <span className="text-[10px] text-gray-400">{STEP_DIMENSION_LABELS[fix.dimension] || fix.dimension}</span>
                                          {!canToggle && <span className="text-[10px] text-gray-400 italic">manual</span>}
                                        </div>
                                        <p className="text-xs text-gray-700 dark:text-gray-300">{fix.message}</p>
                                        {fix.original && fix.replacement && fix.auto_fixable && (
                                          <div className="flex items-center gap-1.5 mt-1">
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-700 line-through">{fix.original}</span>
                                            <ChevronRight className="w-2.5 h-2.5 text-gray-400" />
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-50 text-green-700">{fix.replacement}</span>
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                )
                              })}
                              <button onClick={() => { setStepFixesResult(null); setStepApplyResult(null); handleStepGetFixes() }} className="w-full text-xs py-1.5 text-blue-600 hover:underline flex items-center justify-center gap-1 mt-2">
                                <RefreshCw className="w-3 h-3" /> Re-check fixes
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    )}

                    {/* ─── Spam Tab ─── */}
                    {stepIntelTab === 'spam' && (
                      <div>
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                            <AlertTriangle className="w-4 h-4 text-amber-500" /> Spam Free Maker
                          </h3>
                          <p className="text-xs text-gray-500 mt-1">Check for spam trigger words and get fix suggestions.</p>
                        </div>
                        {stepSpamReduceResult && (
                          <div className="mx-3 mt-3 p-3 rounded-lg bg-gradient-to-r from-red-50 to-green-50 dark:from-red-900/20 dark:to-green-900/20 border border-gray-200 dark:border-gray-700">
                            <div className="flex items-center justify-center gap-3">
                              <div className="text-center">
                                <div className={`text-lg font-bold ${stepSpamBadgeColor(stepSpamReduceResult.before_grade).split(' ')[1]}`}>{stepSpamReduceResult.before_score}</div>
                                <div className="text-[10px] text-gray-500">{stepSpamReduceResult.before_grade}</div>
                              </div>
                              <ChevronRight className="w-4 h-4 text-gray-400" />
                              <div className="text-center">
                                <div className={`text-lg font-bold ${stepSpamBadgeColor(stepSpamReduceResult.after_grade).split(' ')[1]}`}>{stepSpamReduceResult.after_score}</div>
                                <div className="text-[10px] text-gray-500">{stepSpamReduceResult.after_grade}</div>
                              </div>
                              <span className="text-xs font-medium text-green-600">-{stepSpamReduceResult.delta}pts</span>
                            </div>
                          </div>
                        )}
                        <div className="p-3 space-y-2">
                          {!stepSpamResult ? (
                            <button onClick={handleStepSpamCheck} disabled={stepSpamLoading || (!stepForm.subject && !stepForm.body_html)} className="w-full text-xs py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 flex items-center justify-center gap-1">
                              {stepSpamLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <AlertTriangle className="w-3 h-3" />} Check Spam Score
                            </button>
                          ) : stepSpamLoading ? (
                            <div className="flex items-center justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-gray-400" /></div>
                          ) : (
                            <>
                              <div className="flex items-center justify-between mb-2">
                                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${stepSpamBadgeColor(stepSpamResult.grade)}`}>{stepSpamResult.grade?.replace('_', ' ')}</span>
                                <span className="text-xs text-gray-500">Score: {stepSpamResult.score}</span>
                              </div>
                              {stepSpamResult.flagged_words?.length === 0 && stepSpamResult.suggestions?.length === 0 ? (
                                <div className="text-center py-4 text-gray-400">
                                  <CheckCircle className="w-8 h-8 mx-auto mb-2 text-green-500" />
                                  <p className="text-sm font-medium text-green-600">No spam words detected</p>
                                  <p className="text-xs mt-1">This email looks clean</p>
                                </div>
                              ) : (
                                <>
                                  {stepSpamResult.suggestions?.length > 1 && (
                                    <button onClick={handleStepApplyAllSpamFixes} className="w-full text-xs py-2 px-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center justify-center gap-1 font-medium">
                                      <Zap className="w-3 h-3" /> Apply All {stepSpamResult.suggestions.length} Fixes
                                    </button>
                                  )}
                                  {stepSpamResult.suggestions?.map((s: any, idx: number) => (
                                    <button key={idx} onClick={() => handleStepSingleSpamFix(s.original, s.replacement)} className="w-full text-left p-2.5 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors group">
                                      <div className="flex items-center gap-2">
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-800 line-through">{s.original}</span>
                                        <ChevronRight className="w-3 h-3 text-gray-400 group-hover:text-blue-500" />
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-800">{s.replacement}</span>
                                      </div>
                                    </button>
                                  ))}
                                  {stepSpamResult.flagged_words?.filter((fw: any) => !stepSpamResult.suggestions?.some((s: any) => s.original === fw.word) && !fw.word?.startsWith('[pattern:')).map((fw: any, idx: number) => (
                                    <div key={`fw-${idx}`} className="p-2.5 border border-gray-200 dark:border-gray-700 rounded-lg opacity-70">
                                      <div className="flex items-center justify-between">
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-800">{fw.word}</span>
                                        <span className="text-[10px] text-gray-400">{fw.severity} | {fw.location} | {fw.points}pts</span>
                                      </div>
                                    </div>
                                  ))}
                                </>
                              )}
                              <button onClick={() => { setStepSpamResult(null); setStepSpamReduceResult(null); handleStepSpamCheck() }} className="w-full text-xs py-2 text-center text-blue-600 hover:underline flex items-center justify-center gap-1">
                                <RefreshCw className="w-3 h-3" /> Re-check spam
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    )}

                    {/* ─── Rendering Tab ─── */}
                    {stepIntelTab === 'rendering' && (
                      <div className="p-4 space-y-3">
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                          <Monitor className="w-4 h-4 text-blue-500" /> Rendering Check
                        </h3>
                        {stepRenderingLoading ? (
                          <div className="flex items-center justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-gray-400" /></div>
                        ) : stepRenderingResult ? (
                          <>
                            <div className="flex items-center gap-3 mb-3">
                              <div className={`text-2xl font-bold ${stepRenderingResult.score >= 80 ? 'text-green-600' : stepRenderingResult.score >= 50 ? 'text-yellow-600' : 'text-red-600'}`}>
                                {stepRenderingResult.score}/100
                              </div>
                              <div className="flex-1 h-2 rounded-full bg-gray-200 dark:bg-gray-600 overflow-hidden">
                                <div className={`h-full rounded-full ${stepRenderingResult.score >= 80 ? 'bg-green-500' : stepRenderingResult.score >= 50 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${stepRenderingResult.score}%` }} />
                              </div>
                            </div>
                            {stepRenderingResult.warnings?.length === 0 ? (
                              <div className="text-center py-4">
                                <CheckCircle className="w-6 h-6 mx-auto mb-1 text-green-500" />
                                <p className="text-xs text-green-600">No rendering issues</p>
                              </div>
                            ) : (
                              <div className="space-y-2">
                                {stepRenderingResult.warnings?.map((w: any, i: number) => (
                                  <div key={i} className={`p-2.5 rounded-lg border text-xs ${w.severity === 'high' ? 'border-red-200 bg-red-50' : w.severity === 'medium' ? 'border-yellow-200 bg-yellow-50' : 'border-blue-200 bg-blue-50'}`}>
                                    <div className="flex items-start gap-2">
                                      <AlertTriangle className={`w-3 h-3 mt-0.5 flex-shrink-0 ${w.severity === 'high' ? 'text-red-500' : w.severity === 'medium' ? 'text-yellow-500' : 'text-blue-500'}`} />
                                      <div>
                                        <p className="text-gray-700">{w.message}</p>
                                        <span className="text-[10px] text-gray-400 mt-0.5 inline-block">{w.client}</span>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                            {stepRenderingResult.stats && (
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-2 border-t border-gray-200 dark:border-gray-700 mt-2">
                                <div className="text-center"><div className="text-xs font-medium">{stepRenderingResult.stats.images || 0}</div><div className="text-[10px] text-gray-400">Images</div></div>
                                <div className="text-center"><div className="text-xs font-medium">{stepRenderingResult.stats.links || 0}</div><div className="text-[10px] text-gray-400">Links</div></div>
                                <div className="text-center"><div className="text-xs font-medium">{stepRenderingResult.stats.html_length || 0}</div><div className="text-[10px] text-gray-400">HTML Size</div></div>
                              </div>
                            )}
                            <button onClick={() => { setStepRenderingResult(null); handleStepRenderingCheck() }} className="w-full text-xs py-1.5 text-blue-600 hover:underline flex items-center justify-center gap-1 mt-2">
                              <RefreshCw className="w-3 h-3" /> Re-check
                            </button>
                          </>
                        ) : (
                          <button onClick={handleStepRenderingCheck} disabled={!stepForm.body_html} className="w-full text-xs py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50">Check Rendering</button>
                        )}
                      </div>
                    )}

                    {/* ─── Humanize Tab ─── */}
                    {stepIntelTab === 'humanize' && (
                      <div className="p-4 space-y-3">
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                          <Brain className="w-4 h-4 text-purple-500" /> AI Detection Shield
                        </h3>
                        <div className="flex gap-2">
                          {(['light', 'medium', 'heavy'] as const).map(level => (
                            <button key={level} onClick={() => setStepHumanizeIntensity(level)} className={`flex-1 text-xs py-1.5 rounded border transition-colors capitalize ${stepHumanizeIntensity === level ? 'bg-purple-100 border-purple-400 text-purple-700' : 'border-gray-200 dark:border-gray-600 text-gray-500 hover:border-gray-300'}`}>{level}</button>
                          ))}
                        </div>
                        <button onClick={handleStepHumanize} disabled={stepHumanizeLoading || !stepForm.body_html} className="w-full text-xs py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 flex items-center justify-center gap-1">
                          {stepHumanizeLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Brain className="w-3 h-3" />} Humanize
                        </button>
                        {stepHumanizeResult && (
                          <>
                            <div className="p-3 rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
                              <p className="text-[10px] text-gray-500 mb-2 uppercase tracking-wide">Burstiness Score</p>
                              <div className="flex items-center gap-3">
                                <div className="text-center">
                                  <div className={`text-sm font-bold ${stepHumanizeResult.burstiness_before < 0.4 ? 'text-red-500' : 'text-green-500'}`}>{stepHumanizeResult.burstiness_before}</div>
                                  <div className="text-[10px] text-gray-400">Before</div>
                                </div>
                                <ChevronRight className="w-3 h-3 text-gray-400" />
                                <div className="text-center">
                                  <div className={`text-sm font-bold ${stepHumanizeResult.burstiness_after < 0.4 ? 'text-red-500' : 'text-green-500'}`}>{stepHumanizeResult.burstiness_after}</div>
                                  <div className="text-[10px] text-gray-400">After</div>
                                </div>
                              </div>
                              <div className="mt-1.5 flex gap-2 text-[10px]">
                                <span className="text-red-400">AI-like: 0.2-0.4</span>
                                <span className="text-green-400">Human: 0.5-0.8</span>
                              </div>
                            </div>
                            {stepHumanizeResult.modifications?.length > 0 && (
                              <div className="space-y-1">
                                <p className="text-[10px] text-gray-500 uppercase tracking-wide">Modifications</p>
                                <div className="flex flex-wrap gap-1">
                                  {stepHumanizeResult.modifications.map((m: string, i: number) => (
                                    <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">{m}</span>
                                  ))}
                                </div>
                              </div>
                            )}
                            <button onClick={handleStepApplyHumanize} className="w-full text-xs py-2 border border-purple-400 text-purple-700 rounded hover:bg-purple-50 dark:hover:bg-purple-900/20">
                              Apply to Email
                            </button>
                          </>
                        )}
                      </div>
                    )}

                    {/* ─── Spintax Tab ─── */}
                    {stepIntelTab === 'spintax' && (
                      <div className="p-4 space-y-3">
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                          <Shuffle className="w-4 h-4 text-orange-500" /> Content Variations
                        </h3>
                        <button onClick={handleStepSpintaxPreview} disabled={stepSpintaxLoading || !stepForm.body_html} className="w-full text-xs py-2 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50 flex items-center justify-center gap-1">
                          {stepSpintaxLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Shuffle className="w-3 h-3" />} Preview Variations
                        </button>
                        {stepSpintaxResult && (
                          <>
                            <div className="flex items-center gap-2">
                              <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-800 font-medium">{stepSpintaxResult.total_variants} unique versions</span>
                              {stepSpintaxResult.errors?.length > 0 && <span className="text-[10px] text-red-500">{stepSpintaxResult.errors.length} errors</span>}
                            </div>
                            {stepSpintaxResult.total_variants <= 1 ? (
                              <div className="text-center py-4 text-gray-400">
                                <p className="text-xs">No spintax patterns found</p>
                                <p className="text-[10px] mt-1">Use {'{option1|option2}'} syntax for variations</p>
                              </div>
                            ) : (
                              <div className="space-y-2">
                                {stepSpintaxResult.variants.map((v: string, i: number) => (
                                  <div key={i} className="p-2.5 border border-gray-200 dark:border-gray-700 rounded-lg">
                                    <div className="text-[10px] text-gray-400 mb-1 font-medium">Variant #{i + 1}</div>
                                    <div className="text-xs text-gray-700 dark:text-gray-300 max-h-24 overflow-y-auto" dangerouslySetInnerHTML={{ __html: v }} />
                                  </div>
                                ))}
                                <button onClick={handleStepSpintaxPreview} className="w-full text-xs py-1.5 text-orange-600 hover:underline flex items-center justify-center gap-1">
                                  <RefreshCw className="w-3 h-3" /> Show More
                                </button>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}

                  </div>
                </div>
              )}

              {/* Right: Form Fields */}
              <div className="flex-1 overflow-y-auto p-6">
                <div className="space-y-4">
                  {/* Step Type */}
                  <div>
                    <label className="block text-sm font-medium mb-1 dark:text-gray-200">Step Type</label>
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
                      {/* Template Selector */}
                      <div>
                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">Template</label>
                        <div className="flex gap-2">
                          <select
                            value={selectedTemplateId || ''}
                            onChange={e => {
                              const id = e.target.value ? Number(e.target.value) : null
                              setSelectedTemplateId(id)
                              if (id) {
                                const tpl = stepTemplates.find((t: any) => t.template_id === id)
                                if (tpl) {
                                  setStepForm(f => ({
                                    ...f,
                                    subject: tpl.subject || '',
                                    body_html: tpl.body_html || '',
                                    body_text: tpl.body_text || '',
                                  }))
                                }
                              }
                            }}
                            className="flex-1 px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
                            disabled={stepTemplatesLoading}
                          >
                            <option value="">{stepTemplatesLoading ? 'Loading templates...' : 'Select a template...'}</option>
                            {stepTemplates.filter((t: any) => t.category === 'outreach').length > 0 && (
                              <optgroup label="Outreach">
                                {stepTemplates.filter((t: any) => t.category === 'outreach').sort((a: any, b: any) => (a.template_id === activeOutreachTemplateId ? -1 : b.template_id === activeOutreachTemplateId ? 1 : 0)).map((t: any) => (
                                  <option key={t.template_id} value={t.template_id}>
                                    {t.template_id === activeOutreachTemplateId ? '\u2605 ' : ''}{t.name}{t.industry ? ` (${t.industry.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())})` : ''}{t.template_id === activeOutreachTemplateId ? ' - Active' : ''}
                                  </option>
                                ))}
                              </optgroup>
                            )}
                            {stepTemplates.filter((t: any) => t.category === 'followup').length > 0 && (
                              <optgroup label="Follow-up">
                                {stepTemplates.filter((t: any) => t.category === 'followup').sort((a: any, b: any) => (a.template_id === activeFollowupTemplateId ? -1 : b.template_id === activeFollowupTemplateId ? 1 : 0)).map((t: any) => (
                                  <option key={t.template_id} value={t.template_id}>
                                    {t.template_id === activeFollowupTemplateId ? '\u2605 ' : ''}{t.name}{t.industry ? ` (${t.industry.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())})` : ''}{t.template_id === activeFollowupTemplateId ? ' - Active' : ''}
                                  </option>
                                ))}
                              </optgroup>
                            )}
                            {stepTemplates.filter((t: any) => t.category !== 'outreach' && t.category !== 'followup').length > 0 && (
                              <optgroup label="Other">
                                {stepTemplates.filter((t: any) => t.category !== 'outreach' && t.category !== 'followup').map((t: any) => (
                                  <option key={t.template_id} value={t.template_id}>{t.name}</option>
                                ))}
                              </optgroup>
                            )}
                          </select>
                        </div>
                        {selectedTemplateId && (() => {
                          const tpl = stepTemplates.find((t: any) => t.template_id === selectedTemplateId)
                          return tpl ? (
                            <div className="mt-1 space-y-1">
                              <p className="text-xs text-gray-500">
                                {tpl.category === 'outreach' && tpl.template_id === activeOutreachTemplateId && <span className="text-green-600 font-medium">Active Outreach</span>}
                                {tpl.category === 'followup' && tpl.template_id === activeFollowupTemplateId && <span className="text-green-600 font-medium">Active Follow-up</span>}
                                {tpl.description && <span className="ml-1">— {tpl.description}</span>}
                              </p>
                              {(tpl.goal || tpl.industry) && (
                                <div className="flex items-center gap-1.5">
                                  {tpl.goal && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-blue-100 text-blue-700">{tpl.goal.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}</span>}
                                  {tpl.industry && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-600">{tpl.industry.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}</span>}
                                </div>
                              )}
                            </div>
                          ) : null
                        })()}
                      </div>

                      {/* Email Headers Display */}
                      <div className="bg-gray-50 dark:bg-gray-900/30 rounded-lg border border-gray-200 dark:border-gray-700 px-4 py-2.5 space-y-1.5">
                        <div className="flex items-center text-xs">
                          <span className="text-gray-400 w-10 shrink-0">To:</span>
                          <span className="text-gray-600 dark:text-gray-400 font-mono text-[11px]">{'{{contact_email}}'}</span>
                        </div>
                        <div className="flex items-center text-xs">
                          <span className="text-gray-400 w-10 shrink-0">CC:</span>
                          <span className="text-gray-400 italic text-[11px]">None</span>
                        </div>
                        <div className="flex items-center text-xs">
                          <span className="text-gray-400 w-10 shrink-0">BCC:</span>
                          <span className="text-gray-400 italic text-[11px]">None</span>
                        </div>
                      </div>

                      {/* Subject */}
                      <div>
                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">Subject</label>
                        <input ref={stepSubjectRef} value={stepForm.subject} onChange={e => setStepForm(f => ({ ...f, subject: e.target.value }))} onDrop={handleDropOnSubject} onDragOver={handleDragOver} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" placeholder="Email subject (supports {spintax|options})" />
                      </div>

                      {/* Formatting Toolbar */}
                      <div className="flex items-center gap-0.5 px-1 py-1 border border-gray-200 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-900/30 flex-wrap">
                        <button type="button" onClick={() => applyStepFormatting('b')} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400" title="Bold"><Bold className="w-3.5 h-3.5" /></button>
                        <button type="button" onClick={() => applyStepFormatting('i')} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400" title="Italic"><Italic className="w-3.5 h-3.5" /></button>
                        <button type="button" onClick={() => applyStepFormatting('u')} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400" title="Underline"><Underline className="w-3.5 h-3.5" /></button>
                        <div className="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />
                        <button type="button" onClick={() => applyStepFormatting('span', 'style="color:#2563eb"')} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400" title="Color (Blue)"><Palette className="w-3.5 h-3.5" /></button>
                        <div className="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />
                        <button type="button" onClick={() => applyStepFormatting('div', 'style="text-align:left"')} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400" title="Align Left"><AlignLeft className="w-3.5 h-3.5" /></button>
                        <button type="button" onClick={() => applyStepFormatting('div', 'style="text-align:center"')} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400" title="Align Center"><AlignCenter className="w-3.5 h-3.5" /></button>
                        <button type="button" onClick={() => applyStepFormatting('div', 'style="text-align:right"')} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400" title="Align Right"><AlignRight className="w-3.5 h-3.5" /></button>
                        <div className="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />
                        <button type="button" onClick={() => applyStepFormatting('li')} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400" title="Bullet List"><List className="w-3.5 h-3.5" /></button>
                        <button type="button" onClick={() => applyStepFormatting('li')} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400" title="Numbered List"><ListOrdered className="w-3.5 h-3.5" /></button>
                      </div>

                      {/* Body Editor / Preview Toggle */}
                      <div>
                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">Body (HTML)</label>
                        {stepShowPreview ? (
                          <div
                            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-3 min-h-[200px] bg-white dark:bg-gray-700 text-sm prose prose-sm max-w-none overflow-y-auto"
                            style={{ maxHeight: '300px' }}
                            dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(stepForm.body_html) }}
                          />
                        ) : (
                          <textarea
                            ref={stepBodyRef}
                            value={stepForm.body_html}
                            onChange={e => setStepForm(f => ({ ...f, body_html: e.target.value }))}
                            onDrop={handleDropOnBody}
                            onDragOver={handleDragOver}
                            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 font-mono text-xs"
                            rows={10}
                            placeholder="<p>Hi {{contact_first_name}},</p>"
                          />
                        )}
                      </div>

                      {/* Attachment info */}
                      <p className="text-[11px] text-gray-400 italic flex items-center gap-1.5">
                        <Info className="w-3 h-3" /> Attachments not supported in cold email (improves deliverability)
                      </p>

                      {/* Reply to thread */}
                      <label className="flex items-center gap-2">
                        <input type="checkbox" checked={stepForm.reply_to_thread} onChange={e => setStepForm(f => ({ ...f, reply_to_thread: e.target.checked }))} />
                        <span className="text-sm dark:text-gray-200">Reply to previous thread</span>
                      </label>
                    </>
                  )}

                  {/* Non-email step types (unchanged logic) */}
                  {stepForm.step_type === 'condition' && (
                    <>
                      <div>
                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">Condition</label>
                        <select value={stepForm.condition_type} onChange={e => setStepForm(f => ({ ...f, condition_type: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600">
                          <option value="">Select condition...</option>
                          <option value="opened">Email Opened</option>
                          <option value="clicked">Link Clicked</option>
                          <option value="replied">Replied</option>
                          <option value="no_action">No Action</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">Window (hours)</label>
                        <input type="number" value={stepForm.condition_window_hours} onChange={e => setStepForm(f => ({ ...f, condition_window_hours: parseInt(e.target.value) || 24 }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                      </div>
                    </>
                  )}
                  {stepForm.step_type === 'sms' && (
                    <div>
                      <label className="block text-sm font-medium mb-1 dark:text-gray-200">SMS Body</label>
                      <textarea value={stepForm.body_text} onChange={e => setStepForm(f => ({ ...f, body_text: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" rows={4} placeholder="Hi {{first_name}}, ..." />
                      <p className="text-xs text-gray-400 mt-1">Max 160 chars recommended. Supports {'{{first_name}}'}, {'{{company}}'} placeholders and {'{'} spintax {'}'}</p>
                    </div>
                  )}
                  {stepForm.step_type === 'call' && (
                    <div>
                      <label className="block text-sm font-medium mb-1 dark:text-gray-200">TwiML URL or Script</label>
                      <input value={stepForm.body_text} onChange={e => setStepForm(f => ({ ...f, body_text: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" placeholder="https://your-domain.com/twiml/script" />
                      <p className="text-xs text-gray-400 mt-1">URL to TwiML instructions for the call, or leave empty for a simple dial</p>
                    </div>
                  )}
                  {stepForm.step_type === 'linkedin' && (
                    <div className="bg-sky-50 dark:bg-sky-900/20 border border-sky-200 dark:border-sky-800 rounded-lg p-3">
                      <p className="text-sm text-sky-700 dark:text-sky-300 flex items-center gap-2">
                        <Linkedin className="w-4 h-4" /> LinkedIn automation requires a browser extension (coming soon)
                      </p>
                      <p className="text-xs text-sky-600 dark:text-sky-400 mt-1">The campaign engine will skip this step and advance to the next one until the extension is configured.</p>
                    </div>
                  )}

                  {/* Delay fields */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-1 dark:text-gray-200">Delay (days)</label>
                      <input type="number" value={stepForm.delay_days} onChange={e => setStepForm(f => ({ ...f, delay_days: parseInt(e.target.value) || 0 }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-1 dark:text-gray-200">Delay (hours)</label>
                      <input type="number" value={stepForm.delay_hours} onChange={e => setStepForm(f => ({ ...f, delay_hours: parseInt(e.target.value) || 0 }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30 shrink-0">
              <div className="flex items-center gap-2">
                {stepForm.step_type === 'email' && (
                  <>
                    <button onClick={handleStepAiRewrite} disabled={stepRewriting || !stepForm.body_html} className="flex items-center gap-1.5 px-3 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors">
                      {stepRewriting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                      {stepRewriting ? 'Rewriting...' : 'AI Rewrite'}
                    </button>
                    <button onClick={() => setStepShowPreview(!stepShowPreview)} disabled={!stepForm.body_html} className="flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 transition-colors">
                      <Eye className="w-3.5 h-3.5" /> {stepShowPreview ? 'Edit' : 'Preview'}
                    </button>
                  </>
                )}
              </div>
              <div className="flex items-center gap-3">
                <button onClick={() => setShowStepModal(false)} className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 dark:text-gray-300">Cancel</button>
                <button onClick={handleAddStep} disabled={saving} className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">
                  {saving ? 'Saving...' : editingStep ? 'Update Step' : 'Add Step'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Enroll Modal — Lead-based contact selection */}
      {showEnrollModal && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowEnrollModal(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-[640px] mx-4 max-h-[85vh] flex flex-col">
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
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-[600px] mx-4 max-h-[80vh] overflow-y-auto">
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
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-[500px] mx-4 max-h-[70vh] overflow-y-auto">
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

      {/* AI Personalization Preview Modal */}
      {showAIPreviewModal && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowAIPreviewModal(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-[900px] mx-4 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-500" />
                AI Personalization Preview
              </h3>
              <button onClick={() => setShowAIPreviewModal(false)} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
            </div>
            {aiPreviewLoading ? (
              <div className="flex flex-col items-center justify-center py-12 gap-3">
                <Loader2 className="w-6 h-6 animate-spin text-purple-500" />
                <p className="text-sm text-gray-500">Generating AI personalized previews...</p>
              </div>
            ) : !aiPreviewResults || aiPreviewResults.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-8">No contacts available for preview. Enroll contacts in this campaign first.</p>
            ) : (
              <div className="space-y-4">
                {aiPreviewResults.map((r: any) => (
                  <div key={r.contact_id} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-2 bg-gray-50 dark:bg-gray-700/50">
                      <span className="font-medium text-sm">{r.contact_name}{r.contact_company ? ` — ${r.contact_company}` : ''}</span>
                      <div className="flex items-center gap-2">
                        {r.ai_used ? (
                          <span className="text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 px-2 py-0.5 rounded-full">{r.tokens_used} tokens</span>
                        ) : (
                          <span className="text-xs bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 px-2 py-0.5 rounded-full">AI skipped</span>
                        )}
                      </div>
                    </div>
                    {r.ai_error && !r.ai_used && (
                      <div className="px-4 py-2 bg-yellow-50 dark:bg-yellow-900/20 border-b border-yellow-200 dark:border-yellow-800">
                        <p className="text-xs text-yellow-700 dark:text-yellow-300">AI error: {r.ai_error}</p>
                      </div>
                    )}
                    <div className="grid grid-cols-2 divide-x divide-gray-200 dark:divide-gray-700">
                      <div className="p-4">
                        <div className="text-xs font-medium text-gray-400 uppercase mb-2">Original</div>
                        <div className="text-xs text-gray-500 mb-1">Subject: <span className="text-gray-800 dark:text-gray-200">{r.original.subject}</span></div>
                        <div className="text-sm text-gray-700 dark:text-gray-300 mt-2 prose prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: r.original.body_html }} />
                      </div>
                      <div className="p-4">
                        <div className="text-xs font-medium text-purple-500 uppercase mb-2">AI Personalized</div>
                        <div className="text-xs text-gray-500 mb-1">Subject: <span className="text-gray-800 dark:text-gray-200">{r.personalized.subject}</span></div>
                        <div className="text-sm text-gray-700 dark:text-gray-300 mt-2 prose prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: r.personalized.body_html }} />
                      </div>
                    </div>
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
