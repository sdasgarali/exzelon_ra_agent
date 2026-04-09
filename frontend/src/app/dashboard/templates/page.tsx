'use client'

import { useEffect, useState, useRef, DragEvent } from 'react'
import DOMPurify from 'dompurify'
import { templatesApi } from '@/lib/api'
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

      {/* Create/Edit Modal — Two-column layout with placeholder panel */}
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
              {/* Left: Placeholder panel */}
              <div className="w-56 shrink-0 bg-gray-50 border-r border-gray-200 p-4 overflow-y-auto">
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
            <div className="flex items-center justify-end gap-3 p-6 border-t bg-gray-50 shrink-0">
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
