'use client'

import { useEffect, useState, useRef, useCallback, DragEvent } from 'react'
import DOMPurify from 'dompurify'
import { templatesApi, emailPreviewApi, deliverabilityApi } from '@/lib/api'
import type { RenderingCheckResult, HumanizeResult, SpintaxPreviewResult } from '@/types/api'
import {
  Plus,
  Edit,
  Trash2,
  Eye,
  CheckCircle,
  X,
  FileEdit,
  Info,
  Zap,
  GripVertical,
  AlertTriangle,
  Monitor,
  Brain,
  Shuffle,
  Shield,
  Loader2,
  RefreshCw,
  Sparkles,
  ChevronRight,
} from 'lucide-react'

type TemplateCategory = 'outreach' | 'followup'

interface EmailTemplate {
  template_id: number
  name: string
  subject: string
  body_html: string
  body_text: string | null
  status: 'active' | 'inactive'
  category: TemplateCategory
  is_default: boolean
  description: string | null
  created_at: string
  updated_at: string
}

interface TemplateForm {
  name: string
  subject: string
  body_html: string
  body_text: string
  description: string
  status: 'active' | 'inactive'
  category: TemplateCategory
}

const emptyForm: TemplateForm = {
  name: '',
  subject: '',
  body_html: '',
  body_text: '',
  description: '',
  status: 'inactive',
  category: 'outreach',
}

const PLACEHOLDERS = [
  { tag: '{{contact_first_name}}', label: 'Recipient first name' },
  { tag: '{{sender_first_name}}', label: 'Sender first name' },
  { tag: '{{job_title}}', label: 'Job title from lead' },
  { tag: '{{job_location}}', label: 'Job location' },
  { tag: '{{company_name}}', label: 'Company name' },
  { tag: '{{signature}}', label: 'Mailbox email signature' },
  { tag: '{{logo_url}}', label: 'Company logo URL' },
  { tag: '{{unsubscribe_link}}', label: 'Unsubscribe link' },
]

// ─── Helpers ───────────────────────────────────────────────────────

interface SpamSuggestion {
  original: string
  replacement: string
}

interface DeliverabilityData {
  overall_score: number
  dns: { score: number; weight: number; spf: any; dkim: any; dmarc: any }
  spam: { score: number; raw_score: number; weight: number; grade: string; flagged_words: any[] }
  blacklist: { score: number; weight: number; is_clean: boolean; ip: string; total_checked: number; total_listed: number; results: any[] }
  reputation: { score: number; weight: number; domain: string; bounce_rate: number; is_blacklisted: boolean }
}

function spamBadgeColor(grade: string) {
  switch (grade) {
    case 'clean': return 'bg-green-100 text-green-800'
    case 'low_risk': return 'bg-yellow-100 text-yellow-800'
    case 'medium_risk': return 'bg-orange-100 text-orange-800'
    case 'high_risk': return 'bg-red-100 text-red-800'
    case 'spam': return 'bg-red-200 text-red-900'
    default: return 'bg-gray-100 text-gray-700'
  }
}

function scoreColor(score: number): string {
  if (score >= 80) return '#22c55e'
  if (score >= 60) return '#eab308'
  if (score >= 40) return '#f97316'
  return '#ef4444'
}

function ScoreGauge({ score, size = 120 }: { score: number; size?: number }) {
  const radius = (size - 16) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference
  const color = scoreColor(score)

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

type IntelligenceTab = 'placeholders' | 'spam' | 'rendering' | 'humanize' | 'spintax' | 'score'

// ─── Main Component ────────────────────────────────────────────────

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<EmailTemplate[]>([])
  const [activeOutreachId, setActiveOutreachId] = useState<number | null>(null)
  const [activeFollowupId, setActiveFollowupId] = useState<number | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<number | null>(null)
  const [showPreview, setShowPreview] = useState<any>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<TemplateForm>(emptyForm)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [dragOverField, setDragOverField] = useState<string | null>(null)

  // Template library filters
  const [industryFilter, setIndustryFilter] = useState('')
  const [goalFilter, setGoalFilter] = useState('')
  const [seedingLibrary, setSeedingLibrary] = useState(false)

  // Refs for drop targets
  const subjectRef = useRef<HTMLInputElement>(null)
  const bodyHtmlRef = useRef<HTMLTextAreaElement>(null)
  const bodyTextRef = useRef<HTMLTextAreaElement>(null)

  // ─── Intelligence panel state ────────────────────────────────
  const [activeTab, setActiveTab] = useState<IntelligenceTab>('placeholders')

  // Spam tab
  const [spamResult, setSpamResult] = useState<{ score: number; grade: string; flagged_words: any[]; suggestions: SpamSuggestion[] } | null>(null)
  const [loadingSpam, setLoadingSpam] = useState(false)
  const [spamReduceResult, setSpamReduceResult] = useState<{ before_score: number; after_score: number; before_grade: string; after_grade: string; delta: number } | null>(null)

  // Rendering tab
  const [renderingResult, setRenderingResult] = useState<RenderingCheckResult | null>(null)
  const [loadingRendering, setLoadingRendering] = useState(false)

  // Humanize tab
  const [humanizeResult, setHumanizeResult] = useState<HumanizeResult | null>(null)
  const [loadingHumanize, setLoadingHumanize] = useState(false)
  const [humanizeIntensity, setHumanizeIntensity] = useState<string>('medium')

  // Spintax tab
  const [spintaxResult, setSpintaxResult] = useState<SpintaxPreviewResult | null>(null)
  const [loadingSpintax, setLoadingSpintax] = useState(false)

  // Deliverability score tab
  const [deliverabilityData, setDeliverabilityData] = useState<DeliverabilityData | null>(null)
  const [loadingDeliverability, setLoadingDeliverability] = useState(false)

  // AI Rewrite + inline preview
  const [rewriting, setRewriting] = useState(false)
  const [showInlinePreview, setShowInlinePreview] = useState(false)

  // ─── Intelligence handlers ──────────────────────────────────

  const resetIntelligenceState = useCallback(() => {
    setSpamResult(null)
    setSpamReduceResult(null)
    setRenderingResult(null)
    setHumanizeResult(null)
    setSpintaxResult(null)
    setDeliverabilityData(null)
    setShowInlinePreview(false)
  }, [])

  const handleSpamCheck = useCallback(async () => {
    if (!form.subject && !form.body_html) return
    setLoadingSpam(true)
    try {
      const data = await emailPreviewApi.spamCheck({ subject: form.subject, body_html: form.body_html })
      setSpamResult(data)
    } catch (err) { console.error(err) }
    finally { setLoadingSpam(false) }
  }, [form.subject, form.body_html])

  const handleApplyAllSpamFixes = useCallback(async () => {
    if (!spamResult?.suggestions || spamResult.suggestions.length === 0) return
    try {
      const data = await deliverabilityApi.spamReduce({
        subject: form.subject,
        body_html: form.body_html,
        replacements: spamResult.suggestions.map(s => ({ original: s.original, replacement: s.replacement })),
      })
      setSpamReduceResult({ before_score: data.before_score, after_score: data.after_score, before_grade: data.before_grade, after_grade: data.after_grade, delta: data.delta })
      setForm(prev => ({ ...prev, subject: data.new_subject, body_html: data.new_body_html }))
      setSpamResult(prev => prev ? { ...prev, suggestions: [] } : null)
    } catch (err) { console.error(err) }
  }, [form.subject, form.body_html, spamResult])

  const handleSingleSpamFix = useCallback(async (original: string, replacement: string) => {
    try {
      const data = await deliverabilityApi.spamReduce({
        subject: form.subject,
        body_html: form.body_html,
        replacements: [{ original, replacement }],
      })
      setForm(prev => ({ ...prev, subject: data.new_subject, body_html: data.new_body_html }))
      setSpamResult(prev => {
        if (!prev) return null
        return { ...prev, suggestions: prev.suggestions.filter(s => s.original !== original) }
      })
    } catch (err) { console.error(err) }
  }, [form.subject, form.body_html])

  const handleRenderingCheck = useCallback(async () => {
    if (!form.body_html) return
    setLoadingRendering(true)
    try {
      const data = await deliverabilityApi.renderingCheck({ body_html: form.body_html })
      setRenderingResult(data)
    } catch (err) { console.error(err) }
    finally { setLoadingRendering(false) }
  }, [form.body_html])

  const handleHumanize = useCallback(async () => {
    if (!form.body_html) return
    setLoadingHumanize(true)
    try {
      const data = await deliverabilityApi.humanize({
        subject: form.subject,
        body_html: form.body_html,
        body_text: form.body_text || '',
        intensity: humanizeIntensity,
      })
      setHumanizeResult(data)
    } catch (err) { console.error(err) }
    finally { setLoadingHumanize(false) }
  }, [form.subject, form.body_html, form.body_text, humanizeIntensity])

  const handleApplyHumanize = useCallback(() => {
    if (!humanizeResult) return
    setForm(prev => ({
      ...prev,
      subject: humanizeResult.subject,
      body_html: humanizeResult.body_html,
      body_text: humanizeResult.body_text || prev.body_text,
    }))
    resetIntelligenceState()
  }, [humanizeResult, resetIntelligenceState])

  const handleSpintaxPreview = useCallback(async () => {
    if (!form.body_html) return
    setLoadingSpintax(true)
    try {
      const data = await deliverabilityApi.spintaxPreview({ text: form.body_html, count: 5 })
      setSpintaxResult(data)
    } catch (err) { console.error(err) }
    finally { setLoadingSpintax(false) }
  }, [form.body_html])

  const handleDeliverabilityScore = useCallback(async () => {
    if (!form.subject && !form.body_html) return
    setLoadingDeliverability(true)
    try {
      const data = await emailPreviewApi.deliverabilityScore({
        mailbox_id: 0,
        subject: form.subject,
        body_html: form.body_html,
      })
      setDeliverabilityData(data)
    } catch (err) { console.error(err) }
    finally { setLoadingDeliverability(false) }
  }, [form.subject, form.body_html])

  const handleAiRewrite = useCallback(async () => {
    if (!form.body_html) return
    setRewriting(true)
    try {
      const data = await deliverabilityApi.humanize({
        subject: form.subject,
        body_html: form.body_html,
        body_text: form.body_text || '',
        intensity: 'heavy',
      })
      setForm(prev => ({
        ...prev,
        subject: data.subject,
        body_html: data.body_html,
        body_text: data.body_text || prev.body_text,
      }))
      resetIntelligenceState()
    } catch (err) { console.error(err) }
    finally { setRewriting(false) }
  }, [form.subject, form.body_html, form.body_text, resetIntelligenceState])

  // Auto-load tab data when tab changes
  useEffect(() => {
    if (!showModal || (!form.body_html && !form.subject)) return
    if (activeTab === 'rendering' && !renderingResult && !loadingRendering) handleRenderingCheck()
    if (activeTab === 'score' && !deliverabilityData && !loadingDeliverability) handleDeliverabilityScore()
  }, [activeTab, showModal]) // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Original handlers ──────────────────────────────────────

  const fetchTemplates = async () => {
    try {
      setLoading(true)
      setError('')
      const params: Record<string, any> = showArchived ? { show_archived: true } : {}
      if (industryFilter) params.industry = industryFilter
      if (goalFilter) params.goal = goalFilter
      const data = await templatesApi.list(params)
      setTemplates(data.items || [])
      setActiveOutreachId(data.active_outreach_template_id ?? data.active_template_id ?? null)
      setActiveFollowupId(data.active_followup_template_id ?? null)
    } catch (err: any) {
      if (err.code !== 'ERR_CANCELED') {
        setError(err.response?.data?.detail || 'Failed to load templates')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleSeedLibrary = async () => {
    setSeedingLibrary(true)
    try {
      await templatesApi.seedLibrary()
      fetchTemplates()
    } catch { /* ignore */ }
    setSeedingLibrary(false)
  }

  useEffect(() => {
    fetchTemplates()
  }, [showArchived, industryFilter, goalFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleCreate = () => {
    setEditingId(null)
    setForm(emptyForm)
    setShowModal(true)
    setError('')
    setActiveTab('placeholders')
    resetIntelligenceState()
  }

  const handleEdit = (template: EmailTemplate) => {
    setEditingId(template.template_id)
    setForm({
      name: template.name,
      subject: template.subject,
      body_html: template.body_html,
      body_text: template.body_text || '',
      description: template.description || '',
      status: template.status,
      category: template.category || 'outreach',
    })
    setShowModal(true)
    setError('')
    setActiveTab('placeholders')
    resetIntelligenceState()
  }

  const handleSave = async () => {
    if (!form.name || !form.subject || !form.body_html) {
      setError('Name, subject, and HTML body are required')
      return
    }
    setSaving(true)
    setError('')
    try {
      const { status: _status, ...payload } = form
      if (editingId) {
        await templatesApi.update(editingId, payload)
      } else {
        await templatesApi.create(payload)
      }
      setShowModal(false)
      fetchTemplates()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save template')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await templatesApi.delete(id)
      setShowDeleteConfirm(null)
      fetchTemplates()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to archive template')
      setShowDeleteConfirm(null)
    }
  }

  const handleActivate = async (id: number) => {
    try {
      await templatesApi.activate(id)
      fetchTemplates()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to activate template')
    }
  }

  const handlePreview = async (id: number) => {
    try {
      const data = await templatesApi.preview(id)
      setShowPreview(data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to preview template')
    }
  }

  // --- Drag & Drop helpers ---
  const handleDragStart = (e: DragEvent, tag: string) => {
    e.dataTransfer.setData('text/plain', tag)
    e.dataTransfer.effectAllowed = 'copy'
  }

  const insertAtCursor = (
    ref: React.RefObject<HTMLInputElement | HTMLTextAreaElement | null>,
    fieldKey: keyof TemplateForm,
    tag: string,
  ) => {
    const el = ref.current
    if (!el) {
      setForm((prev) => ({ ...prev, [fieldKey]: prev[fieldKey] + tag }))
      return
    }
    const start = el.selectionStart ?? el.value.length
    const end = el.selectionEnd ?? start
    const before = el.value.slice(0, start)
    const after = el.value.slice(end)
    const newVal = before + tag + after
    setForm((prev) => ({ ...prev, [fieldKey]: newVal }))
    // Restore cursor after React re-render
    requestAnimationFrame(() => {
      el.focus()
      const pos = start + tag.length
      el.setSelectionRange(pos, pos)
    })
  }

  const handleDropOnField = (
    e: DragEvent,
    ref: React.RefObject<HTMLInputElement | HTMLTextAreaElement | null>,
    fieldKey: keyof TemplateForm,
  ) => {
    e.preventDefault()
    setDragOverField(null)
    const tag = e.dataTransfer.getData('text/plain')
    if (!tag) return
    insertAtCursor(ref, fieldKey, tag)
  }

  const handleDragOverField = (e: DragEvent, fieldName: string) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
    setDragOverField(fieldName)
  }

  const handleClickPlaceholder = (tag: string) => {
    // Insert into the body_html field by default (most common target)
    insertAtCursor(bodyHtmlRef, 'body_html', tag)
  }

  const activeOutreach = templates.find((t) => t.template_id === activeOutreachId)
  const activeFollowup = templates.find((t) => t.template_id === activeFollowupId)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading templates...</div>
      </div>
    )
  }

  // ─── Intelligence tab definitions ──────────────────────────

  const INTEL_TABS: { id: IntelligenceTab; label: string; icon: typeof Info }[] = [
    { id: 'placeholders', label: 'Vars', icon: Info },
    { id: 'spam', label: 'Spam', icon: AlertTriangle },
    { id: 'rendering', label: 'Render', icon: Monitor },
    { id: 'humanize', label: 'Human', icon: Brain },
    { id: 'spintax', label: 'Spintax', icon: Shuffle },
    { id: 'score', label: 'Score', icon: Shield },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Email Templates</h1>
          <p className="text-gray-500 mt-1">
            Manage email templates for outreach campaigns. One template can be active per category.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm font-medium text-gray-700">Show Archived</span>
          </label>
          <button
            onClick={handleCreate}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Create Template
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={industryFilter}
          onChange={(e) => setIndustryFilter(e.target.value)}
          className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg bg-white focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="">All Industries</option>
          <option value="saas">SaaS</option>
          <option value="recruiting">Recruiting</option>
          <option value="healthcare">Healthcare</option>
          <option value="ecommerce">E-Commerce</option>
          <option value="finance">Finance</option>
          <option value="general">General</option>
        </select>
        <select
          value={goalFilter}
          onChange={(e) => setGoalFilter(e.target.value)}
          className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg bg-white focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="">All Goals</option>
          <option value="cold_outreach">Cold Outreach</option>
          <option value="follow_up">Follow-up</option>
          <option value="re_engagement">Re-engagement</option>
          <option value="event_invite">Event Invite</option>
          <option value="demo_request">Demo Request</option>
        </select>
        <button
          onClick={handleSeedLibrary}
          disabled={seedingLibrary}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-purple-50 text-purple-700 border border-purple-200 rounded-lg hover:bg-purple-100 transition-colors disabled:opacity-50"
        >
          <Zap className="w-3.5 h-3.5" />
          {seedingLibrary ? 'Seeding...' : 'Seed System Templates'}
        </button>
      </div>

      {/* Error banner */}
      {error && !showModal && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')}>
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Active Template Cards — side by side */}
      {(activeOutreach || activeFollowup) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {activeOutreach && (
            <div className="border-2 border-green-400 bg-green-50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle className="w-5 h-5 text-green-600" />
                <h3 className="font-semibold text-green-800">Active Outreach Template</h3>
              </div>
              <p className="text-green-900 font-medium">{activeOutreach.name}</p>
              <p className="text-green-700 text-sm mt-1">Subject: {activeOutreach.subject}</p>
            </div>
          )}
          {activeFollowup && (
            <div className="border-2 border-blue-400 bg-blue-50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle className="w-5 h-5 text-blue-600" />
                <h3 className="font-semibold text-blue-800">Active Follow-up Template</h3>
              </div>
              <p className="text-blue-900 font-medium">{activeFollowup.name}</p>
              <p className="text-blue-700 text-sm mt-1">Subject: {activeFollowup.subject}</p>
            </div>
          )}
        </div>
      )}

      {/* Templates Table */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Category
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Subject
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Created
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {templates.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                  No templates yet. Create your first template to get started.
                </td>
              </tr>
            ) : (
              templates.map((template) => (
                <tr key={template.template_id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <FileEdit className="w-4 h-4 text-gray-400" />
                      <div>
                        <div className="text-sm font-medium text-gray-900">{template.name}</div>
                        {template.is_default && (
                          <span className="text-xs text-blue-600">Default</span>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        template.category === 'followup'
                          ? 'bg-orange-100 text-orange-800'
                          : 'bg-purple-100 text-purple-800'
                      }`}
                    >
                      {template.category === 'followup' ? 'Follow-up' : 'Outreach'}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-900 max-w-xs truncate">{template.subject}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        template.status === 'active'
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {template.status === 'active' ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(template.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => handlePreview(template.template_id)}
                        className="p-1.5 text-gray-400 hover:text-blue-600 transition-colors"
                        title="Preview"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      {template.status !== 'active' && (
                        <button
                          onClick={() => handleActivate(template.template_id)}
                          className="p-1.5 text-gray-400 hover:text-green-600 transition-colors"
                          title="Activate"
                        >
                          <Zap className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        onClick={() => handleEdit(template)}
                        className="p-1.5 text-gray-400 hover:text-yellow-600 transition-colors"
                        title="Edit"
                      >
                        <Edit className="w-4 h-4" />
                      </button>
                      {!template.is_default && (
                        <button
                          onClick={() => setShowDeleteConfirm(template.template_id)}
                          className="p-1.5 text-gray-400 hover:text-red-600 transition-colors"
                          title="Archive"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Create/Edit Modal — Two-column layout with intelligence panel */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col">
            {/* Modal header */}
            <div className="flex items-center justify-between p-6 border-b shrink-0">
              <h2 className="text-lg font-semibold">
                {editingId ? 'Edit Template' : 'Create Template'}
              </h2>
              <button onClick={() => setShowModal(false)}>
                <X className="w-5 h-5 text-gray-400 hover:text-gray-600" />
              </button>
            </div>

            {/* Modal body — two columns */}
            <div className="flex flex-1 overflow-hidden">
              {/* Left: Intelligence panel with tabs */}
              <div className="w-72 shrink-0 bg-gray-50 border-r border-gray-200 flex flex-col overflow-hidden">
                {/* Tab bar */}
                <div className="border-b border-gray-200 px-1 flex flex-wrap">
                  {INTEL_TABS.map(tab => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`flex items-center gap-1 px-2 py-2 text-[10px] font-medium border-b-2 whitespace-nowrap transition-colors ${
                        activeTab === tab.id
                          ? 'border-blue-500 text-blue-600'
                          : 'border-transparent text-gray-500 hover:text-gray-700'
                      }`}
                    >
                      <tab.icon className="w-3 h-3" />
                      {tab.label}
                    </button>
                  ))}
                </div>

                {/* Tab content */}
                <div className="flex-1 overflow-y-auto">

                  {/* ─── Tab 1: Placeholders ─── */}
                  {activeTab === 'placeholders' && (
                    <div className="p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <Info className="w-4 h-4 text-blue-600" />
                        <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Placeholders</h4>
                      </div>
                      <p className="text-xs text-gray-500 mb-3">Drag into any field or click to insert into HTML body.</p>
                      <div className="space-y-1.5">
                        {PLACEHOLDERS.map(({ tag, label }) => (
                          <div
                            key={tag}
                            draggable
                            onDragStart={(e) => handleDragStart(e, tag)}
                            onClick={() => handleClickPlaceholder(tag)}
                            className="flex items-center gap-2 px-2.5 py-2 bg-white border border-gray-200 rounded-md cursor-grab active:cursor-grabbing hover:border-blue-400 hover:bg-blue-50 transition-colors group select-none"
                            title={`Drag or click to insert ${tag}`}
                          >
                            <GripVertical className="w-3.5 h-3.5 text-gray-300 group-hover:text-blue-400 shrink-0" />
                            <div className="min-w-0">
                              <div className="text-xs font-mono text-blue-700 truncate">{tag}</div>
                              <div className="text-[10px] text-gray-500 truncate">{label}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* ─── Tab 2: Spam Check ─── */}
                  {activeTab === 'spam' && (
                    <div>
                      <div className="p-4 border-b border-gray-200">
                        <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4 text-amber-500" />
                          Spam Free Maker
                        </h3>
                        <p className="text-xs text-gray-500 mt-1">
                          Check for spam trigger words and get fix suggestions.
                        </p>
                      </div>

                      {/* Before/After score comparison */}
                      {spamReduceResult && (
                        <div className="mx-3 mt-3 p-3 rounded-lg bg-gradient-to-r from-red-50 to-green-50 border border-gray-200">
                          <div className="flex items-center justify-center gap-3">
                            <div className="text-center">
                              <div className={`text-lg font-bold ${spamBadgeColor(spamReduceResult.before_grade).split(' ')[1]}`}>{spamReduceResult.before_score}</div>
                              <div className="text-[10px] text-gray-500">{spamReduceResult.before_grade}</div>
                            </div>
                            <ChevronRight className="w-4 h-4 text-gray-400" />
                            <div className="text-center">
                              <div className={`text-lg font-bold ${spamBadgeColor(spamReduceResult.after_grade).split(' ')[1]}`}>{spamReduceResult.after_score}</div>
                              <div className="text-[10px] text-gray-500">{spamReduceResult.after_grade}</div>
                            </div>
                            <span className="text-xs font-medium text-green-600">-{spamReduceResult.delta}pts</span>
                          </div>
                        </div>
                      )}

                      <div className="p-3 space-y-2">
                        {!spamResult ? (
                          <button
                            onClick={handleSpamCheck}
                            disabled={loadingSpam || (!form.subject && !form.body_html)}
                            className="w-full text-xs py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 flex items-center justify-center gap-1"
                          >
                            {loadingSpam ? <Loader2 className="w-3 h-3 animate-spin" /> : <AlertTriangle className="w-3 h-3" />}
                            Check Spam Score
                          </button>
                        ) : loadingSpam ? (
                          <div className="flex items-center justify-center py-8">
                            <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
                          </div>
                        ) : (
                          <>
                            {/* Grade badge */}
                            <div className="flex items-center justify-between mb-2">
                              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${spamBadgeColor(spamResult.grade)}`}>
                                {spamResult.grade?.replace('_', ' ')}
                              </span>
                              <span className="text-xs text-gray-500">Score: {spamResult.score}</span>
                            </div>

                            {spamResult.flagged_words?.length === 0 && spamResult.suggestions?.length === 0 ? (
                              <div className="text-center py-4 text-gray-400">
                                <CheckCircle className="w-8 h-8 mx-auto mb-2 text-green-500" />
                                <p className="text-sm font-medium text-green-600">No spam words detected</p>
                                <p className="text-xs mt-1">This template looks clean</p>
                              </div>
                            ) : (
                              <>
                                {/* Apply All button */}
                                {spamResult.suggestions?.length > 1 && (
                                  <button
                                    onClick={handleApplyAllSpamFixes}
                                    className="w-full text-xs py-2 px-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center justify-center gap-1 font-medium"
                                  >
                                    <Zap className="w-3 h-3" /> Apply All {spamResult.suggestions.length} Fixes
                                  </button>
                                )}
                                {spamResult.suggestions?.map((s, idx) => (
                                  <button
                                    key={idx}
                                    onClick={() => handleSingleSpamFix(s.original, s.replacement)}
                                    className="w-full text-left p-2.5 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors group"
                                  >
                                    <div className="flex items-center gap-2">
                                      <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-800 line-through">
                                        {s.original}
                                      </span>
                                      <ChevronRight className="w-3 h-3 text-gray-400 group-hover:text-blue-500" />
                                      <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-800">
                                        {s.replacement}
                                      </span>
                                    </div>
                                  </button>
                                ))}
                                {/* Flagged words without suggestions */}
                                {spamResult.flagged_words?.filter(fw =>
                                  !spamResult.suggestions?.some(s => s.original === fw.word) && !fw.word?.startsWith('[pattern:')
                                ).map((fw, idx) => (
                                  <div key={`fw-${idx}`} className="p-2.5 border border-gray-200 rounded-lg opacity-70">
                                    <div className="flex items-center justify-between">
                                      <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-800">
                                        {fw.word}
                                      </span>
                                      <span className="text-[10px] text-gray-400">
                                        {fw.severity} | {fw.location} | {fw.points}pts
                                      </span>
                                    </div>
                                  </div>
                                ))}
                              </>
                            )}
                            <button
                              onClick={() => { setSpamResult(null); setSpamReduceResult(null); handleSpamCheck() }}
                              className="w-full text-xs py-2 text-center text-blue-600 hover:underline flex items-center justify-center gap-1"
                            >
                              <RefreshCw className="w-3 h-3" /> Re-check spam
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  )}

                  {/* ─── Tab 3: Rendering ─── */}
                  {activeTab === 'rendering' && (
                    <div className="p-4 space-y-3">
                      <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                        <Monitor className="w-4 h-4 text-blue-500" />
                        Rendering Check
                      </h3>
                      {loadingRendering ? (
                        <div className="flex items-center justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-gray-400" /></div>
                      ) : renderingResult ? (
                        <>
                          <div className="flex items-center gap-3 mb-3">
                            <div className={`text-2xl font-bold ${renderingResult.score >= 80 ? 'text-green-600' : renderingResult.score >= 50 ? 'text-yellow-600' : 'text-red-600'}`}>
                              {renderingResult.score}/100
                            </div>
                            <div className="flex-1 h-2 rounded-full bg-gray-200 overflow-hidden">
                              <div className={`h-full rounded-full ${renderingResult.score >= 80 ? 'bg-green-500' : renderingResult.score >= 50 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${renderingResult.score}%` }} />
                            </div>
                          </div>
                          {renderingResult.warnings?.length === 0 ? (
                            <div className="text-center py-4">
                              <CheckCircle className="w-6 h-6 mx-auto mb-1 text-green-500" />
                              <p className="text-xs text-green-600">No rendering issues</p>
                            </div>
                          ) : (
                            <div className="space-y-2">
                              {renderingResult.warnings?.map((w, i) => (
                                <div key={i} className={`p-2.5 rounded-lg border text-xs ${
                                  w.severity === 'high' ? 'border-red-200 bg-red-50' :
                                  w.severity === 'medium' ? 'border-yellow-200 bg-yellow-50' :
                                  'border-blue-200 bg-blue-50'
                                }`}>
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
                          {renderingResult.stats && (
                            <div className="grid grid-cols-3 gap-2 pt-2 border-t border-gray-200 mt-2">
                              <div className="text-center"><div className="text-xs font-medium">{renderingResult.stats.images || 0}</div><div className="text-[10px] text-gray-400">Images</div></div>
                              <div className="text-center"><div className="text-xs font-medium">{renderingResult.stats.links || 0}</div><div className="text-[10px] text-gray-400">Links</div></div>
                              <div className="text-center"><div className="text-xs font-medium">{renderingResult.stats.html_length || 0}</div><div className="text-[10px] text-gray-400">HTML Size</div></div>
                            </div>
                          )}
                          <button
                            onClick={() => { setRenderingResult(null); handleRenderingCheck() }}
                            className="w-full text-xs py-1.5 text-blue-600 hover:underline flex items-center justify-center gap-1 mt-2"
                          >
                            <RefreshCw className="w-3 h-3" /> Re-check
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={handleRenderingCheck}
                          disabled={!form.body_html}
                          className="w-full text-xs py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                        >
                          Check Rendering
                        </button>
                      )}
                    </div>
                  )}

                  {/* ─── Tab 4: Humanize ─── */}
                  {activeTab === 'humanize' && (
                    <div className="p-4 space-y-3">
                      <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                        <Brain className="w-4 h-4 text-purple-500" />
                        AI Detection Shield
                      </h3>
                      {/* Intensity selector */}
                      <div className="flex gap-2">
                        {(['light', 'medium', 'heavy'] as const).map(level => (
                          <button
                            key={level}
                            onClick={() => setHumanizeIntensity(level)}
                            className={`flex-1 text-xs py-1.5 rounded border transition-colors capitalize ${
                              humanizeIntensity === level
                                ? 'bg-purple-100 border-purple-400 text-purple-700'
                                : 'border-gray-200 text-gray-500 hover:border-gray-300'
                            }`}
                          >
                            {level}
                          </button>
                        ))}
                      </div>
                      <button
                        onClick={handleHumanize}
                        disabled={loadingHumanize || !form.body_html}
                        className="w-full text-xs py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 flex items-center justify-center gap-1"
                      >
                        {loadingHumanize ? <Loader2 className="w-3 h-3 animate-spin" /> : <Brain className="w-3 h-3" />}
                        Humanize
                      </button>

                      {humanizeResult && (
                        <>
                          {/* Burstiness comparison */}
                          <div className="p-3 rounded-lg bg-white border border-gray-200">
                            <p className="text-[10px] text-gray-500 mb-2 uppercase tracking-wide">Burstiness Score</p>
                            <div className="flex items-center gap-3">
                              <div className="text-center">
                                <div className={`text-sm font-bold ${humanizeResult.burstiness_before < 0.4 ? 'text-red-500' : 'text-green-500'}`}>{humanizeResult.burstiness_before}</div>
                                <div className="text-[10px] text-gray-400">Before</div>
                              </div>
                              <ChevronRight className="w-3 h-3 text-gray-400" />
                              <div className="text-center">
                                <div className={`text-sm font-bold ${humanizeResult.burstiness_after < 0.4 ? 'text-red-500' : 'text-green-500'}`}>{humanizeResult.burstiness_after}</div>
                                <div className="text-[10px] text-gray-400">After</div>
                              </div>
                            </div>
                            <div className="mt-1.5 flex gap-2 text-[10px]">
                              <span className="text-red-400">AI-like: 0.2-0.4</span>
                              <span className="text-green-400">Human: 0.5-0.8</span>
                            </div>
                          </div>
                          {/* Modifications */}
                          {humanizeResult.modifications?.length > 0 && (
                            <div className="space-y-1">
                              <p className="text-[10px] text-gray-500 uppercase tracking-wide">Modifications</p>
                              <div className="flex flex-wrap gap-1">
                                {humanizeResult.modifications.map((m, i) => (
                                  <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">{m}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          <button onClick={handleApplyHumanize} className="w-full text-xs py-2 border border-purple-400 text-purple-700 rounded hover:bg-purple-50">
                            Apply to Template
                          </button>
                        </>
                      )}
                    </div>
                  )}

                  {/* ─── Tab 5: Spintax ─── */}
                  {activeTab === 'spintax' && (
                    <div className="p-4 space-y-3">
                      <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                        <Shuffle className="w-4 h-4 text-orange-500" />
                        Content Variations
                      </h3>
                      <button
                        onClick={handleSpintaxPreview}
                        disabled={loadingSpintax || !form.body_html}
                        className="w-full text-xs py-2 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50 flex items-center justify-center gap-1"
                      >
                        {loadingSpintax ? <Loader2 className="w-3 h-3 animate-spin" /> : <Shuffle className="w-3 h-3" />}
                        Preview Variations
                      </button>
                      {spintaxResult && (
                        <>
                          <div className="flex items-center gap-2">
                            <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-800 font-medium">
                              {spintaxResult.total_variants} unique versions
                            </span>
                            {spintaxResult.errors?.length > 0 && (
                              <span className="text-[10px] text-red-500">{spintaxResult.errors.length} errors</span>
                            )}
                          </div>
                          {spintaxResult.total_variants <= 1 ? (
                            <div className="text-center py-4 text-gray-400">
                              <p className="text-xs">No spintax patterns found</p>
                              <p className="text-[10px] mt-1">Use {'{option1|option2}'} syntax for variations</p>
                            </div>
                          ) : (
                            <div className="space-y-2">
                              {spintaxResult.variants.map((v, i) => (
                                <div key={i} className="p-2.5 border border-gray-200 rounded-lg">
                                  <div className="text-[10px] text-gray-400 mb-1 font-medium">Variant #{i + 1}</div>
                                  <div className="text-xs text-gray-700 max-h-24 overflow-y-auto" dangerouslySetInnerHTML={{ __html: v }} />
                                </div>
                              ))}
                              <button
                                onClick={handleSpintaxPreview}
                                className="w-full text-xs py-1.5 text-orange-600 hover:underline flex items-center justify-center gap-1"
                              >
                                <RefreshCw className="w-3 h-3" /> Show More
                              </button>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}

                  {/* ─── Tab 6: Deliverability Score ─── */}
                  {activeTab === 'score' && (
                    <div>
                      {loadingDeliverability ? (
                        <div className="flex items-center justify-center py-12"><Loader2 className="w-5 h-5 animate-spin text-gray-400" /></div>
                      ) : deliverabilityData ? (
                        <>
                          <div className="flex justify-center py-4">
                            <ScoreGauge score={deliverabilityData.overall_score} size={120} />
                          </div>
                          <p className="text-center text-xs text-gray-500 mb-4">Overall Score</p>
                          <div className="px-4 space-y-3 pb-4">
                            {/* DNS */}
                            <div className="border border-gray-200 rounded-lg p-3">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-xs font-medium text-gray-700">DNS ({deliverabilityData.dns.weight}%)</span>
                                <span className="text-xs font-bold" style={{ color: scoreColor(deliverabilityData.dns.score) }}>{deliverabilityData.dns.score}/100</span>
                              </div>
                              <div className="space-y-1.5">
                                {['spf', 'dkim', 'dmarc'].map(type => {
                                  const dnsData = deliverabilityData.dns[type as keyof typeof deliverabilityData.dns] as any
                                  const valid = dnsData?.valid
                                  return (
                                    <div key={type} className="flex items-center justify-between text-xs">
                                      <span className="uppercase text-gray-500">{type}</span>
                                      <span className={valid ? 'text-green-600' : 'text-red-600'}>{valid ? 'Pass' : 'Fail'}</span>
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                            {/* Spam */}
                            <div className="border border-gray-200 rounded-lg p-3">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-xs font-medium text-gray-700">Spam Filter ({deliverabilityData.spam.weight}%)</span>
                                <span className="text-xs font-bold" style={{ color: scoreColor(deliverabilityData.spam.score) }}>{deliverabilityData.spam.score}/100</span>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className={`text-xs px-2 py-0.5 rounded-full ${spamBadgeColor(deliverabilityData.spam.grade)}`}>{deliverabilityData.spam.grade}</span>
                                <span className="text-xs text-gray-500">Raw: {deliverabilityData.spam.raw_score}</span>
                              </div>
                            </div>
                            {/* Blacklist */}
                            <div className="border border-gray-200 rounded-lg p-3">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-xs font-medium text-gray-700">Blacklist ({deliverabilityData.blacklist.weight}%)</span>
                                <span className="text-xs font-bold" style={{ color: scoreColor(deliverabilityData.blacklist.score) }}>{deliverabilityData.blacklist.score}/100</span>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className={`text-xs px-2 py-0.5 rounded-full ${deliverabilityData.blacklist.is_clean ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                                  {deliverabilityData.blacklist.is_clean ? 'Clean' : 'Listed'}
                                </span>
                                {deliverabilityData.blacklist.ip && <span className="text-xs text-gray-500">IP: {deliverabilityData.blacklist.ip}</span>}
                              </div>
                              <p className="text-[10px] text-gray-400 mt-1">{deliverabilityData.blacklist.total_checked} checked, {deliverabilityData.blacklist.total_listed} listed</p>
                            </div>
                            {/* Reputation */}
                            <div className="border border-gray-200 rounded-lg p-3">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-xs font-medium text-gray-700">Reputation ({deliverabilityData.reputation.weight}%)</span>
                                <span className="text-xs font-bold" style={{ color: scoreColor(deliverabilityData.reputation.score) }}>{deliverabilityData.reputation.score}/100</span>
                              </div>
                              {deliverabilityData.reputation.domain && <p className="text-xs text-gray-500">Domain: {deliverabilityData.reputation.domain}</p>}
                              <p className="text-xs text-gray-500">Bounce rate: {deliverabilityData.reputation.bounce_rate}%</p>
                            </div>
                          </div>
                          <div className="px-4 pb-3">
                            <button
                              onClick={() => { setDeliverabilityData(null); handleDeliverabilityScore() }}
                              className="w-full text-xs py-1.5 text-blue-600 hover:underline flex items-center justify-center gap-1"
                            >
                              <RefreshCw className="w-3 h-3" /> Re-check
                            </button>
                          </div>
                        </>
                      ) : (
                        <div className="text-center py-8">
                          <button
                            onClick={handleDeliverabilityScore}
                            disabled={!form.subject && !form.body_html}
                            className="text-xs py-2 px-4 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                          >
                            Run Deliverability Score
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Right: Form fields */}
              <div className="flex-1 p-6 overflow-y-auto space-y-4">
                {error && (
                  <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm">
                    {error}
                  </div>
                )}

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Template Name *</label>
                    <input
                      type="text"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      placeholder="e.g., Free Candidate Preview"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Category *</label>
                    <select
                      value={form.category}
                      onChange={(e) => setForm({ ...form, category: e.target.value as TemplateCategory })}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    >
                      <option value="outreach">Outreach</option>
                      <option value="followup">Follow-up</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Subject Line *</label>
                  <input
                    ref={subjectRef}
                    type="text"
                    value={form.subject}
                    onChange={(e) => setForm({ ...form, subject: e.target.value })}
                    onDrop={(e) => handleDropOnField(e, subjectRef, 'subject')}
                    onDragOver={(e) => handleDragOverField(e, 'subject')}
                    onDragLeave={() => setDragOverField(null)}
                    className={`w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors ${
                      dragOverField === 'subject'
                        ? 'border-blue-400 bg-blue-50 ring-2 ring-blue-200'
                        : 'border-gray-300'
                    }`}
                    placeholder="e.g., Free candidate preview for {{job_title}} position"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                  <input
                    type="text"
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="Brief description of when to use this template"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">HTML Body *</label>
                  {showInlinePreview ? (
                    <div
                      className="w-full border border-gray-300 rounded-lg px-4 py-3 min-h-[200px] bg-white text-sm prose prose-sm max-w-none overflow-y-auto"
                      style={{ maxHeight: '300px' }}
                      dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(form.body_html) }}
                    />
                  ) : (
                    <textarea
                      ref={bodyHtmlRef}
                      value={form.body_html}
                      onChange={(e) => setForm({ ...form, body_html: e.target.value })}
                      onDrop={(e) => handleDropOnField(e, bodyHtmlRef, 'body_html')}
                      onDragOver={(e) => handleDragOverField(e, 'body_html')}
                      onDragLeave={() => setDragOverField(null)}
                      rows={12}
                      className={`w-full border rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors ${
                        dragOverField === 'body_html'
                          ? 'border-blue-400 bg-blue-50 ring-2 ring-blue-200'
                          : 'border-gray-300'
                      }`}
                      placeholder="<p>Hi {{contact_first_name}},</p>..."
                    />
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Plain Text Body</label>
                  <textarea
                    ref={bodyTextRef}
                    value={form.body_text}
                    onChange={(e) => setForm({ ...form, body_text: e.target.value })}
                    onDrop={(e) => handleDropOnField(e, bodyTextRef, 'body_text')}
                    onDragOver={(e) => handleDragOverField(e, 'body_text')}
                    onDragLeave={() => setDragOverField(null)}
                    rows={6}
                    className={`w-full border rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors ${
                      dragOverField === 'body_text'
                        ? 'border-blue-400 bg-blue-50 ring-2 ring-blue-200'
                        : 'border-gray-300'
                    }`}
                    placeholder="Hi {{contact_first_name}},..."
                  />
                </div>
              </div>
            </div>

            {/* Modal footer */}
            <div className="flex items-center justify-between p-6 border-t bg-gray-50 shrink-0">
              <div className="flex items-center gap-2">
                <button
                  onClick={handleAiRewrite}
                  disabled={rewriting || !form.body_html}
                  className="flex items-center gap-1.5 px-3 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors"
                >
                  {rewriting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                  {rewriting ? 'Rewriting...' : 'AI Rewrite'}
                </button>
                <button
                  onClick={() => setShowInlinePreview(!showInlinePreview)}
                  disabled={!form.body_html}
                  className="flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100 disabled:opacity-50 transition-colors"
                >
                  <Eye className="w-3.5 h-3.5" />
                  {showInlinePreview ? 'Edit' : 'Preview'}
                </button>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-100"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? 'Saving...' : editingId ? 'Update Template' : 'Create Template'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm !== null && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold mb-2">Archive Template</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to archive this template? It can be restored later.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowDeleteConfirm(null)}
                className="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-100"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(showDeleteConfirm)}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {showPreview && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg w-full max-w-3xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-6 border-b">
              <div>
                <h2 className="text-lg font-semibold">Template Preview</h2>
                <p className="text-sm text-gray-500">{showPreview.name}</p>
              </div>
              <button onClick={() => setShowPreview(null)}>
                <X className="w-5 h-5 text-gray-400 hover:text-gray-600" />
              </button>
            </div>
            <div className="p-6">
              <div className="mb-4">
                <label className="block text-xs font-medium text-gray-500 mb-1">SUBJECT</label>
                <p className="text-sm font-medium text-gray-900">{showPreview.subject}</p>
              </div>
              <div className="mb-4">
                <label className="block text-xs font-medium text-gray-500 mb-1">HTML PREVIEW</label>
                <div
                  className="border border-gray-200 rounded-lg p-4 text-sm"
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(showPreview.body_html) }}
                />
              </div>
              {showPreview.body_text && (
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">PLAIN TEXT</label>
                  <pre className="border border-gray-200 rounded-lg p-4 text-sm whitespace-pre-wrap font-mono bg-gray-50">
                    {showPreview.body_text}
                  </pre>
                </div>
              )}
            </div>
            <div className="flex justify-end p-6 border-t bg-gray-50">
              <button
                onClick={() => setShowPreview(null)}
                className="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-100"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
