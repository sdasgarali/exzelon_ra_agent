'use client'

import { useEffect, useState, useCallback } from 'react'
import { lobApi, getApiError } from '@/lib/api'
import { useLobStore, type LOB, type LOBTypeInfo } from '@/lib/lob-store'
import {
  Plus,
  Pencil,
  Trash2,
  Star,
  Briefcase,
  HeartPulse,
  Code,
  Brain,
  Megaphone,
  Settings,
  Layers,
  X,
  Check,
  Pause,
  Play,
} from 'lucide-react'

const LOB_ICONS: Record<string, React.ElementType> = {
  briefcase: Briefcase,
  'heart-pulse': HeartPulse,
  code: Code,
  brain: Brain,
  megaphone: Megaphone,
  settings: Settings,
}

function getLobIcon(iconName: string | null): React.ElementType {
  return iconName ? LOB_ICONS[iconName] || Layers : Layers
}

export default function LobPage() {
  const { lobs, setLobs, lobTypes, setLobTypes } = useLobStore()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editLob, setEditLob] = useState<LOB | null>(null)
  const [saving, setSaving] = useState(false)

  // Form state
  const [formName, setFormName] = useState('')
  const [formType, setFormType] = useState('staffing')
  const [formDesc, setFormDesc] = useState('')
  const [formColor, setFormColor] = useState('#1A3C6E')
  const [formIcon, setFormIcon] = useState('briefcase')
  const [formAdapterSettings, setFormAdapterSettings] = useState<Record<string, any>>({})

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [lobData, typeData] = await Promise.all([
        lobApi.list(),
        lobApi.listTypes(),
      ])
      setLobs(lobData)
      setLobTypes(typeData)
    } catch (err) {
      setError(getApiError(err, 'Failed to load LOBs'))
    } finally {
      setLoading(false)
    }
  }, [setLobs, setLobTypes])

  useEffect(() => {
    loadData()
  }, [loadData])

  function openCreateForm() {
    setFormName('')
    setFormType('staffing')
    setFormDesc('')
    setFormColor('#1A3C6E')
    setFormIcon('briefcase')
    setFormAdapterSettings({})
    setEditLob(null)
    setShowCreate(true)
  }

  function openEditForm(lob: LOB) {
    setFormName(lob.name)
    setFormType(lob.lob_type)
    setFormDesc(lob.description || '')
    setFormColor(lob.color || '#6366F1')
    setFormIcon(lob.icon || 'briefcase')
    setFormAdapterSettings(lob.lead_source_config || {})
    setEditLob(lob)
    setShowCreate(true)
  }

  async function handleSave() {
    if (!formName.trim()) return
    setSaving(true)
    setError('')
    try {
      const payload: Record<string, any> = {
        name: formName.trim(),
        lob_type: formType,
        description: formDesc.trim() || null,
        color: formColor,
        icon: formIcon,
      }
      // Include adapter settings if any fields are set
      if (Object.keys(formAdapterSettings).length > 0) {
        payload.lead_source_config = formAdapterSettings
      }
      if (editLob) {
        await lobApi.update(editLob.lob_id, payload)
      } else {
        await lobApi.create(payload)
      }
      await loadData()
      setShowCreate(false)
    } catch (err) {
      setError(getApiError(err, 'Failed to save LOB'))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(lob: LOB) {
    if (!confirm(`Delete "${lob.name}"? This will archive the LOB.`)) return
    try {
      await lobApi.delete(lob.lob_id)
      await loadData()
    } catch (err) {
      setError(getApiError(err, 'Failed to delete LOB'))
    }
  }

  async function handleSetDefault(lobId: number) {
    try {
      await lobApi.setDefault(lobId)
      await loadData()
    } catch (err) {
      setError(getApiError(err, 'Failed to set default LOB'))
    }
  }

  async function handleToggleStatus(lob: LOB) {
    const newStatus = lob.status === 'active' ? 'paused' : 'active'
    try {
      await lobApi.update(lob.lob_id, { status: newStatus })
      await loadData()
    } catch (err) {
      setError(getApiError(err, 'Failed to update LOB status'))
    }
  }

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">Lines of Business</h1>
        <div className="animate-pulse space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-20 bg-gray-100 dark:bg-gray-700 rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Lines of Business</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Manage your business lines — each LOB has its own lead sources, ICP, business rules, and AI prompts.
          </p>
        </div>
        <button
          onClick={openCreateForm}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          <Plus className="w-4 h-4" /> New LOB
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* LOB Cards */}
      <div className="space-y-3">
        {lobs.map(lob => {
          const Icon = getLobIcon(lob.icon)
          const typeInfo = lobTypes.find(t => t.lob_type === lob.lob_type)
          return (
            <div
              key={lob.lob_id}
              className={`bg-white dark:bg-gray-800 border rounded-lg p-4 ${
                lob.status === 'paused'
                  ? 'border-gray-200 dark:border-gray-700 opacity-60'
                  : 'border-gray-200 dark:border-gray-700'
              }`}
            >
              <div className="flex items-center gap-4">
                {/* Color dot + Icon */}
                <div
                  className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                  style={{ backgroundColor: `${lob.color}15` }}
                >
                  <Icon className="w-5 h-5" style={{ color: lob.color || '#6366F1' }} />
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{lob.name}</h3>
                    {lob.is_default && (
                      <span className="px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 text-[10px] font-medium rounded">
                        Default
                      </span>
                    )}
                    {lob.status === 'paused' && (
                      <span className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-500 text-[10px] font-medium rounded">
                        Paused
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {typeInfo?.label || lob.lob_type} {lob.description ? ` — ${lob.description}` : ''}
                  </p>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 flex-shrink-0">
                  {!lob.is_default && (
                    <button
                      onClick={() => handleSetDefault(lob.lob_id)}
                      className="p-2 text-gray-400 hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-900/20 rounded-lg transition-colors"
                      title="Set as default"
                    >
                      <Star className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={() => handleToggleStatus(lob)}
                    className="p-2 text-gray-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                    title={lob.status === 'active' ? 'Pause' : 'Activate'}
                  >
                    {lob.status === 'active' ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                  </button>
                  <button
                    onClick={() => openEditForm(lob)}
                    className="p-2 text-gray-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                    title="Edit"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  {!lob.is_default && (
                    <button
                      onClick={() => handleDelete(lob)}
                      className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          )
        })}

        {lobs.length === 0 && (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            <Layers className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p className="text-sm">No lines of business configured yet.</p>
            <button
              onClick={openCreateForm}
              className="mt-3 text-blue-600 hover:text-blue-700 text-sm font-medium"
            >
              Create your first LOB
            </button>
          </div>
        )}
      </div>

      {/* Create/Edit Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-lg p-6 mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                {editLob ? 'Edit LOB' : 'Create New LOB'}
              </h2>
              <button onClick={() => setShowCreate(false)} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded">
                <X className="w-5 h-5 text-gray-400" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={e => setFormName(e.target.value)}
                  placeholder="e.g., Revenue Cycle Management"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              {!editLob && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Type</label>
                  <select
                    value={formType}
                    onChange={e => {
                      setFormType(e.target.value)
                      const typeInfo = lobTypes.find(t => t.lob_type === e.target.value)
                      if (typeInfo) {
                        setFormColor(typeInfo.default_color)
                        setFormIcon(typeInfo.default_icon)
                      }
                    }}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                  >
                    {lobTypes.map(t => (
                      <option key={t.lob_type} value={t.lob_type}>{t.label}</option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
                <textarea
                  value={formDesc}
                  onChange={e => setFormDesc(e.target.value)}
                  placeholder="Brief description of this LOB..."
                  rows={2}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* Adapter Settings */}
              {formType !== 'staffing' && (
                <div className="border border-gray-200 dark:border-gray-600 rounded-lg p-4 bg-gray-50 dark:bg-gray-700/50">
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Adapter Settings</label>

                  {formType === 'rcm' && (
                    <div className="space-y-3">
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">NPI Taxonomy</label>
                        <select
                          value={formAdapterSettings.npi_taxonomy || ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, npi_taxonomy: e.target.value || undefined }))}
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        >
                          <option value="">All Taxonomies</option>
                          <option value="207R00000X">Internal Medicine</option>
                          <option value="208600000X">Surgery</option>
                          <option value="207Q00000X">Family Medicine</option>
                          <option value="2084P0800X">Psychiatry</option>
                          <option value="207V00000X">Obstetrics & Gynecology</option>
                          <option value="208000000X">Pediatrics</option>
                          <option value="207X00000X">Orthopedic Surgery</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">State Filter</label>
                        <input
                          type="text"
                          value={formAdapterSettings.state_filter || ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, state_filter: e.target.value || undefined }))}
                          placeholder="e.g., TX, CA, NY"
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">City Filter</label>
                        <input
                          type="text"
                          value={formAdapterSettings.city_filter || ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, city_filter: e.target.value || undefined }))}
                          placeholder="e.g., Houston, Dallas"
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Google Places Query</label>
                        <input
                          type="text"
                          value={formAdapterSettings.google_places_query || ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, google_places_query: e.target.value || undefined }))}
                          placeholder="e.g., medical billing company"
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        />
                      </div>
                    </div>
                  )}

                  {formType === 'software_dev' && (
                    <div className="space-y-3">
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Crunchbase Categories (comma-separated)</label>
                        <input
                          type="text"
                          value={formAdapterSettings.crunchbase_categories || ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, crunchbase_categories: e.target.value || undefined }))}
                          placeholder="e.g., SaaS, Enterprise Software, FinTech"
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Funding Stage</label>
                        <select
                          value={formAdapterSettings.funding_stage || ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, funding_stage: e.target.value || undefined }))}
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        >
                          <option value="">Any Stage</option>
                          <option value="seed">Seed</option>
                          <option value="series_a">Series A</option>
                          <option value="series_b">Series B</option>
                          <option value="series_c">Series C+</option>
                          <option value="ipo">IPO / Public</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">GitHub Language</label>
                        <input
                          type="text"
                          value={formAdapterSettings.github_language || ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, github_language: e.target.value || undefined }))}
                          placeholder="e.g., Python, TypeScript"
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Min Repos</label>
                        <input
                          type="number"
                          value={formAdapterSettings.min_repos ?? ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, min_repos: e.target.value ? parseInt(e.target.value) : undefined }))}
                          placeholder="e.g., 5"
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        />
                      </div>
                    </div>
                  )}

                  {formType === 'ai_services' && (
                    <div className="space-y-3">
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Crunchbase Categories (comma-separated)</label>
                        <input
                          type="text"
                          value={formAdapterSettings.crunchbase_categories || ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, crunchbase_categories: e.target.value || undefined }))}
                          placeholder="e.g., Artificial Intelligence, Machine Learning"
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">GitHub Query</label>
                        <input
                          type="text"
                          value={formAdapterSettings.github_query || ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, github_query: e.target.value || undefined }))}
                          placeholder="e.g., topic:llm topic:ai-agent"
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Min Repos</label>
                        <input
                          type="number"
                          value={formAdapterSettings.min_repos ?? ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, min_repos: e.target.value ? parseInt(e.target.value) : undefined }))}
                          placeholder="e.g., 3"
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        />
                      </div>
                    </div>
                  )}

                  {formType === 'digital_marketing' && (
                    <div className="space-y-3">
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Domains to Audit (one per line)</label>
                        <textarea
                          value={formAdapterSettings.domains || ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, domains: e.target.value || undefined }))}
                          placeholder="example.com&#10;another-site.com"
                          rows={3}
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm font-mono"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                          Max Performance Score: {formAdapterSettings.max_performance_score ?? 1}
                        </label>
                        <input
                          type="range"
                          min="0"
                          max="1"
                          step="0.05"
                          value={formAdapterSettings.max_performance_score ?? 1}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, max_performance_score: parseFloat(e.target.value) }))}
                          className="w-full"
                        />
                        <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
                          <span>0 (worst)</span>
                          <span>1 (best)</span>
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">BuiltWith Technology Search</label>
                        <input
                          type="text"
                          value={formAdapterSettings.builtwith_tech || ''}
                          onChange={e => setFormAdapterSettings(p => ({ ...p, builtwith_tech: e.target.value || undefined }))}
                          placeholder="e.g., WordPress, Shopify, React"
                          className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                        />
                      </div>
                    </div>
                  )}

                  {formType === 'custom' && (
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Configuration JSON</label>
                      <textarea
                        value={typeof formAdapterSettings === 'object' && Object.keys(formAdapterSettings).length > 0
                          ? JSON.stringify(formAdapterSettings, null, 2)
                          : ''}
                        onChange={e => {
                          try {
                            const parsed = e.target.value ? JSON.parse(e.target.value) : {}
                            setFormAdapterSettings(parsed)
                          } catch {
                            // Allow typing — only update on valid JSON
                          }
                        }}
                        placeholder='{"key": "value"}'
                        rows={5}
                        className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm font-mono"
                      />
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Color</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={formColor}
                      onChange={e => setFormColor(e.target.value)}
                      className="w-8 h-8 rounded cursor-pointer border border-gray-300"
                    />
                    <input
                      type="text"
                      value={formColor}
                      onChange={e => setFormColor(e.target.value)}
                      className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white font-mono"
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !formName.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm font-medium"
              >
                <Check className="w-4 h-4" />
                {saving ? 'Saving...' : editLob ? 'Update' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
