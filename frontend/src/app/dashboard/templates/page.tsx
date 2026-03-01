'use client'

import { useEffect, useState } from 'react'
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
} from 'lucide-react'

interface EmailTemplate {
  template_id: number
  name: string
  subject: string
  body_html: string
  body_text: string | null
  status: 'active' | 'inactive'
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
}

const emptyForm: TemplateForm = {
  name: '',
  subject: '',
  body_html: '',
  body_text: '',
  description: '',
  status: 'inactive',
}

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<EmailTemplate[]>([])
  const [activeTemplateId, setActiveTemplateId] = useState<number | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<number | null>(null)
  const [showPreview, setShowPreview] = useState<any>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<TemplateForm>(emptyForm)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const fetchTemplates = async () => {
    try {
      setLoading(true)
      setError('')
      const data = await templatesApi.list(showArchived ? { show_archived: true } : {})
      setTemplates(data.items || [])
      setActiveTemplateId(data.active_template_id)
    } catch (err: any) {
      if (err.code !== 'ERR_CANCELED') {
        setError(err.response?.data?.detail || 'Failed to load templates')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTemplates()
  }, [showArchived])

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
      if (editingId) {
        await templatesApi.update(editingId, form)
      } else {
        await templatesApi.create(form)
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

  const activeTemplate = templates.find((t) => t.template_id === activeTemplateId)

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
            Manage email templates for outreach campaigns. Only one template can be active at a time.
          </p>
        </div>
        <button
          onClick={handleCreate}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create Template
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')}>
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Active Template Card */}
      {activeTemplate && (
        <div className="border-2 border-green-400 bg-green-50 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="w-5 h-5 text-green-600" />
            <h3 className="font-semibold text-green-800">Active Template</h3>
          </div>
          <p className="text-green-900 font-medium">{activeTemplate.name}</p>
          <p className="text-green-700 text-sm mt-1">Subject: {activeTemplate.subject}</p>
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
                <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
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

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg w-full max-w-3xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-6 border-b">
              <h2 className="text-lg font-semibold">
                {editingId ? 'Edit Template' : 'Create Template'}
              </h2>
              <button onClick={() => setShowModal(false)}>
                <X className="w-5 h-5 text-gray-400 hover:text-gray-600" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm">
                  {error}
                </div>
              )}

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
                <label className="block text-sm font-medium text-gray-700 mb-1">Subject Line *</label>
                <input
                  type="text"
                  value={form.subject}
                  onChange={(e) => setForm({ ...form, subject: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
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
                  value={form.body_html}
                  onChange={(e) => setForm({ ...form, body_html: e.target.value })}
                  rows={12}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="<p>Hi {{contact_first_name}},</p>..."
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Plain Text Body</label>
                <textarea
                  value={form.body_text}
                  onChange={(e) => setForm({ ...form, body_text: e.target.value })}
                  rows={6}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="Hi {{contact_first_name}},..."
                />
              </div>

              {/* Placeholder reference */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Info className="w-4 h-4 text-blue-600" />
                  <h4 className="text-sm font-medium text-blue-800">Available Placeholders</h4>
                </div>
                <div className="flex items-center gap-4 mb-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm font-medium text-gray-700">Show Archived</span>
          </label>
      </div>

      <div className="grid grid-cols-2 gap-1 text-xs text-blue-700">
                  <div><code>{'{{contact_first_name}}'}</code> — Recipient first name</div>
                  <div><code>{'{{sender_first_name}}'}</code> — Sender first name</div>
                  <div><code>{'{{job_title}}'}</code> — Job title from lead</div>
                  <div><code>{'{{job_location}}'}</code> — Job location</div>
                  <div><code>{'{{company_name}}'}</code> — Company name</div>
                  <div><code>{'{{signature}}'}</code> — Mailbox email signature</div>
                  <div><code>{'{{logo_url}}'}</code> — Exzelon logo URL</div>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 p-6 border-t bg-gray-50">
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
