'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { dealsApi } from '@/lib/api'
import type { Deal, DealStage, DealPipelineStage, DealStats, DealActivity, DealContactSearch, DealClientSearch, DealForecast, StaleDeal } from '@/types/api'
import {
  Plus, X, DollarSign, TrendingUp, Award, BarChart3, GripVertical,
  Trash2, Bot, Mail, MailOpen, Reply, AlertTriangle,
  Clock, MessageSquare, ArrowRight, Search, User, Building2, Target,
} from 'lucide-react'

const formatCurrency = (v: number) => {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}K`
  return `$${v.toFixed(0)}`
}

const activityIcon = (type: string) => {
  switch (type) {
    case 'email_sent': return <Mail className="w-3.5 h-3.5 text-blue-500" />
    case 'email_received': return <Reply className="w-3.5 h-3.5 text-green-500" />
    case 'email_opened': return <MailOpen className="w-3.5 h-3.5 text-purple-500" />
    case 'email_bounced': return <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
    case 'stage_change': return <ArrowRight className="w-3.5 h-3.5 text-orange-500" />
    case 'auto_created': return <Bot className="w-3.5 h-3.5 text-indigo-500" />
    default: return <MessageSquare className="w-3.5 h-3.5 text-gray-400" />
  }
}

export default function DealsPage() {
  const [pipeline, setPipeline] = useState<DealPipelineStage[]>([])
  const [stats, setStats] = useState<DealStats | null>(null)
  const [forecast, setForecast] = useState<DealForecast | null>(null)
  const [staleDealIds, setStaleDealIds] = useState<Set<number>>(new Set())
  const [staleCount, setStaleCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showDetailDrawer, setShowDetailDrawer] = useState(false)
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null)
  const [stages, setStages] = useState<DealStage[]>([])
  const [saving, setSaving] = useState(false)
  const [dealForm, setDealForm] = useState({
    name: '', stage_id: 0, value: 0, probability: 50, notes: '',
    contact_id: null as number | null, client_id: null as number | null,
  })
  const [dragDeal, setDragDeal] = useState<number | null>(null)

  // Contact/Client search state
  const [contactSearch, setContactSearch] = useState('')
  const [contactResults, setContactResults] = useState<DealContactSearch[]>([])
  const [selectedContact, setSelectedContact] = useState<DealContactSearch | null>(null)
  const [showContactDropdown, setShowContactDropdown] = useState(false)
  const [clientSearch, setClientSearch] = useState('')
  const [clientResults, setClientResults] = useState<DealClientSearch[]>([])
  const [selectedClient, setSelectedClient] = useState<DealClientSearch | null>(null)
  const [showClientDropdown, setShowClientDropdown] = useState(false)
  const contactSearchTimeout = useRef<NodeJS.Timeout | null>(null)
  const clientSearchTimeout = useRef<NodeJS.Timeout | null>(null)

  // Activity note
  const [newNote, setNewNote] = useState('')
  const [addingNote, setAddingNote] = useState(false)

  const fetchPipeline = useCallback(async () => {
    setLoading(true)
    try {
      const [pipelineData, statsData, stagesData, forecastData, staleData] = await Promise.all([
        dealsApi.pipeline(),
        dealsApi.stats(),
        dealsApi.listStages(),
        dealsApi.forecast().catch(() => null),
        dealsApi.stale().catch(() => []),
      ])
      setPipeline(pipelineData || [])
      setStats(statsData || null)
      setStages(stagesData || [])
      setForecast(forecastData)
      const staleIds = new Set<number>((staleData || []).map((s: StaleDeal) => s.deal_id))
      setStaleDealIds(staleIds)
      setStaleCount(staleIds.size)
      if (stagesData?.length && !dealForm.stage_id) {
        setDealForm(f => ({ ...f, stage_id: stagesData[0].stage_id }))
      }
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { fetchPipeline() }, [fetchPipeline])

  // Contact search with debounce
  useEffect(() => {
    if (contactSearchTimeout.current) clearTimeout(contactSearchTimeout.current)
    if (!contactSearch || contactSearch.length < 2) {
      setContactResults([])
      return
    }
    contactSearchTimeout.current = setTimeout(async () => {
      try {
        const results = await dealsApi.searchContacts(contactSearch)
        setContactResults(results || [])
      } catch { setContactResults([]) }
    }, 300)
    return () => { if (contactSearchTimeout.current) clearTimeout(contactSearchTimeout.current) }
  }, [contactSearch])

  // Client search with debounce
  useEffect(() => {
    if (clientSearchTimeout.current) clearTimeout(clientSearchTimeout.current)
    if (!clientSearch || clientSearch.length < 2) {
      setClientResults([])
      return
    }
    clientSearchTimeout.current = setTimeout(async () => {
      try {
        const results = await dealsApi.searchClients(clientSearch)
        setClientResults(results || [])
      } catch { setClientResults([]) }
    }, 300)
    return () => { if (clientSearchTimeout.current) clearTimeout(clientSearchTimeout.current) }
  }, [clientSearch])

  const selectContact = (c: DealContactSearch) => {
    setSelectedContact(c)
    setDealForm(f => ({ ...f, contact_id: c.contact_id }))
    setContactSearch(c.name)
    setShowContactDropdown(false)
    // Auto-fill company if contact has one
    if (c.company && !selectedClient) {
      setClientSearch(c.company)
      // Try to find matching client
      dealsApi.searchClients(c.company).then(clients => {
        if (clients?.length) {
          setSelectedClient(clients[0])
          setDealForm(f => ({ ...f, client_id: clients[0].client_id }))
          setClientSearch(clients[0].name)
        }
      }).catch(() => {})
    }
  }

  const selectClient = (c: DealClientSearch) => {
    setSelectedClient(c)
    setDealForm(f => ({ ...f, client_id: c.client_id }))
    setClientSearch(c.name)
    setShowClientDropdown(false)
  }

  const handleCreate = async () => {
    if (!dealForm.name || !dealForm.stage_id) return
    setSaving(true)
    try {
      await dealsApi.create(dealForm)
      setShowCreateModal(false)
      setDealForm({ name: '', stage_id: stages[0]?.stage_id || 0, value: 0, probability: 50, notes: '', contact_id: null, client_id: null })
      setSelectedContact(null)
      setSelectedClient(null)
      setContactSearch('')
      setClientSearch('')
      await fetchPipeline()
    } catch { /* ignore */ }
    setSaving(false)
  }

  const openDeal = async (deal: Deal) => {
    try {
      const full = await dealsApi.get(deal.deal_id)
      setSelectedDeal(full)
      setShowDetailDrawer(true)
    } catch {
      setSelectedDeal(deal)
      setShowDetailDrawer(true)
    }
  }

  const handleUpdateDeal = async (dealId: number, data: Record<string, unknown>) => {
    try {
      await dealsApi.update(dealId, data)
      await fetchPipeline()
      if (selectedDeal?.deal_id === dealId) {
        const updated = await dealsApi.get(dealId)
        setSelectedDeal(updated)
      }
    } catch { /* ignore */ }
  }

  const handleDeleteDeal = async (dealId: number) => {
    try {
      await dealsApi.delete(dealId)
      setShowDetailDrawer(false)
      setSelectedDeal(null)
      await fetchPipeline()
    } catch { /* ignore */ }
  }

  const handleAddNote = async () => {
    if (!selectedDeal || !newNote.trim()) return
    setAddingNote(true)
    try {
      await dealsApi.addActivity(selectedDeal.deal_id, {
        activity_type: 'note',
        description: newNote.trim(),
      })
      setNewNote('')
      const updated = await dealsApi.get(selectedDeal.deal_id)
      setSelectedDeal(updated)
    } catch { /* ignore */ }
    setAddingNote(false)
  }

  const handleDragStart = (dealId: number) => setDragDeal(dealId)
  const handleDragOver = (e: React.DragEvent) => e.preventDefault()
  const handleDrop = async (stageId: number) => {
    if (!dragDeal) return
    setDragDeal(null)
    await handleUpdateDeal(dragDeal, { stage_id: stageId })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading deals...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Deals</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">CRM Pipeline</p>
        </div>
        <button onClick={() => setShowCreateModal(true)} className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700">
          <Plus className="w-4 h-4" /> New Deal
        </button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-center gap-2 text-gray-500 text-sm mb-1">
              <DollarSign className="w-4 h-4" /> Pipeline Value
            </div>
            <p className="text-2xl font-bold">{formatCurrency(stats.total_pipeline_value)}</p>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-center gap-2 text-gray-500 text-sm mb-1">
              <Target className="w-4 h-4" /> Weighted Forecast
            </div>
            <p className="text-2xl font-bold text-primary-600">{forecast ? formatCurrency(forecast.weighted_value) : '$0'}</p>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-center gap-2 text-gray-500 text-sm mb-1">
              <BarChart3 className="w-4 h-4" /> Total Deals
            </div>
            <p className="text-2xl font-bold">{stats.total_deals}</p>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-center gap-2 text-gray-500 text-sm mb-1">
              <Award className="w-4 h-4" /> Win Rate
            </div>
            <p className="text-2xl font-bold">{stats.win_rate}%</p>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-center gap-2 text-gray-500 text-sm mb-1">
              <TrendingUp className="w-4 h-4" /> Avg Deal Size
            </div>
            <p className="text-2xl font-bold">{formatCurrency(stats.avg_deal_size)}</p>
            {staleCount > 0 && (
              <p className="text-xs text-orange-500 mt-1 flex items-center gap-1">
                <Clock className="w-3 h-3" /> {staleCount} stale deal{staleCount > 1 ? 's' : ''}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Kanban Board */}
      <div className="flex gap-4 overflow-x-auto pb-4">
        {pipeline.map(stage => (
          <div key={stage.stage_id} className="flex-shrink-0 w-72"
            onDragOver={handleDragOver}
            onDrop={() => handleDrop(stage.stage_id)}>
            {/* Stage Header */}
            <div className="flex items-center gap-2 mb-3 px-1">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: stage.color || '#6B7280' }} />
              <h3 className="font-medium text-sm text-gray-900 dark:text-gray-100">{stage.name}</h3>
              <span className="text-xs text-gray-400 ml-auto">{stage.count}</span>
              <span className="text-xs text-gray-400">{formatCurrency(stage.total_value)}</span>
            </div>
            {/* Cards */}
            <div className="space-y-2 min-h-[100px] bg-gray-50 dark:bg-gray-900/30 rounded-lg p-2">
              {stage.deals.map(deal => {
                const isStale = staleDealIds.has(deal.deal_id)
                return (
                  <div key={deal.deal_id}
                    draggable
                    onDragStart={() => handleDragStart(deal.deal_id)}
                    onClick={() => openDeal(deal)}
                    className={`bg-white dark:bg-gray-800 rounded-lg border p-3 cursor-pointer hover:shadow-md transition-shadow ${
                      dragDeal === deal.deal_id ? 'opacity-50' : ''
                    } ${isStale ? 'border-orange-300 dark:border-orange-600' : 'border-gray-200 dark:border-gray-700'}`}>
                    <div className="flex items-start gap-2">
                      <GripVertical className="w-4 h-4 text-gray-300 mt-0.5 flex-shrink-0 cursor-grab" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <p className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">{deal.name}</p>
                          {deal.is_auto_created && (
                            <span className="flex-shrink-0 px-1.5 py-0.5 text-[10px] font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300 rounded-full">
                              Auto
                            </span>
                          )}
                        </div>
                        {deal.client_name && <p className="text-xs text-gray-500 truncate">{deal.client_name}</p>}
                        <div className="flex items-center justify-between mt-2">
                          <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{formatCurrency(deal.value)}</span>
                          <span className="text-xs text-gray-400">{deal.probability}%</span>
                        </div>
                        {deal.contact_name && (
                          <p className="text-xs text-gray-400 mt-1 truncate flex items-center gap-1">
                            <User className="w-3 h-3" /> {deal.contact_name}
                          </p>
                        )}
                        {isStale && (
                          <p className="text-[10px] text-orange-500 mt-1 flex items-center gap-1">
                            <Clock className="w-3 h-3" /> Stale — no recent activity
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
              {stage.deals.length === 0 && (
                <div className="text-center py-4 text-xs text-gray-400">
                  Drop deals here
                </div>
              )}
            </div>
          </div>
        ))}
        {pipeline.length === 0 && (
          <div className="flex-1 text-center py-12 text-gray-500">
            <DollarSign className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p className="font-medium">No deal stages found</p>
            <p className="text-sm mt-1">Stages are created automatically on first startup</p>
          </div>
        )}
      </div>

      {/* ─── Create Modal ───────────────────────────────────────── */}
      {showCreateModal && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowCreateModal(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-[500px] max-w-[90vw] max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold dark:text-gray-100">New Deal</h2>
              <button onClick={() => setShowCreateModal(false)}><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Deal Name *</label>
                <input value={dealForm.name} onChange={e => setDealForm(f => ({ ...f, name: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" placeholder="e.g., Acme Corp — Q2 Campaign" />
              </div>

              {/* Contact Picker */}
              <div className="relative">
                <label className="block text-sm font-medium mb-1">
                  <User className="w-3.5 h-3.5 inline mr-1" /> Contact
                </label>
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
                  <input
                    value={contactSearch}
                    onChange={e => { setContactSearch(e.target.value); setShowContactDropdown(true); setSelectedContact(null); setDealForm(f => ({ ...f, contact_id: null })) }}
                    onFocus={() => setShowContactDropdown(true)}
                    className="w-full pl-9 pr-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
                    placeholder="Search by name, email, or company..."
                  />
                  {selectedContact && (
                    <button onClick={() => { setSelectedContact(null); setContactSearch(''); setDealForm(f => ({ ...f, contact_id: null })) }}
                      className="absolute right-2 top-2 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
                  )}
                </div>
                {showContactDropdown && contactResults.length > 0 && (
                  <div className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                    {contactResults.map(c => (
                      <button key={c.contact_id} onClick={() => selectContact(c)}
                        className="w-full text-left px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-600 flex flex-col text-sm">
                        <span className="font-medium">{c.name}</span>
                        <span className="text-xs text-gray-500">{c.email}{c.company ? ` — ${c.company}` : ''}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Client Picker */}
              <div className="relative">
                <label className="block text-sm font-medium mb-1">
                  <Building2 className="w-3.5 h-3.5 inline mr-1" /> Company
                </label>
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
                  <input
                    value={clientSearch}
                    onChange={e => { setClientSearch(e.target.value); setShowClientDropdown(true); setSelectedClient(null); setDealForm(f => ({ ...f, client_id: null })) }}
                    onFocus={() => setShowClientDropdown(true)}
                    className="w-full pl-9 pr-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm"
                    placeholder="Search companies..."
                  />
                  {selectedClient && (
                    <button onClick={() => { setSelectedClient(null); setClientSearch(''); setDealForm(f => ({ ...f, client_id: null })) }}
                      className="absolute right-2 top-2 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
                  )}
                </div>
                {showClientDropdown && clientResults.length > 0 && (
                  <div className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                    {clientResults.map(c => (
                      <button key={c.client_id} onClick={() => selectClient(c)}
                        className="w-full text-left px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-600 text-sm font-medium">
                        {c.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Stage</label>
                <select value={dealForm.stage_id} onChange={e => setDealForm(f => ({ ...f, stage_id: parseInt(e.target.value) }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600">
                  {stages.map(s => <option key={s.stage_id} value={s.stage_id}>{s.name}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Value ($)</label>
                  <input type="number" value={dealForm.value} onChange={e => setDealForm(f => ({ ...f, value: parseFloat(e.target.value) || 0 }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Probability (%)</label>
                  <input type="number" min={0} max={100} value={dealForm.probability} onChange={e => setDealForm(f => ({ ...f, probability: parseInt(e.target.value) || 0 }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Notes</label>
                <textarea value={dealForm.notes} onChange={e => setDealForm(f => ({ ...f, notes: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" rows={3} />
              </div>
              <div className="flex gap-3 pt-2">
                <button onClick={() => setShowCreateModal(false)} className="flex-1 px-4 py-2 border rounded-lg">Cancel</button>
                <button onClick={handleCreate} disabled={!dealForm.name || saving} className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">
                  {saving ? 'Creating...' : 'Create Deal'}
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ─── Detail Drawer ──────────────────────────────────────── */}
      {showDetailDrawer && selectedDeal && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowDetailDrawer(false)} />
          <div className="fixed right-0 top-0 h-full w-[420px] max-w-[90vw] bg-white dark:bg-gray-800 z-50 shadow-xl overflow-y-auto">
            <div className="p-6 space-y-6">
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">{selectedDeal.name}</h2>
                    {selectedDeal.is_auto_created && (
                      <span className="px-2 py-0.5 text-xs font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300 rounded-full flex items-center gap-1">
                        <Bot className="w-3 h-3" /> Auto
                      </span>
                    )}
                  </div>
                  {selectedDeal.client_name && <p className="text-sm text-gray-500">{selectedDeal.client_name}</p>}
                </div>
                <button onClick={() => setShowDetailDrawer(false)}><X className="w-5 h-5" /></button>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-xs text-gray-400 uppercase">Value</span>
                  <p className="text-lg font-bold">{formatCurrency(selectedDeal.value)}</p>
                </div>
                <div>
                  <span className="text-xs text-gray-400 uppercase">Probability</span>
                  <p className="text-lg font-bold">{selectedDeal.probability}%</p>
                </div>
              </div>

              <div>
                <span className="text-xs text-gray-400 uppercase">Stage</span>
                <select value={selectedDeal.stage_id} onChange={e => handleUpdateDeal(selectedDeal.deal_id, { stage_id: parseInt(e.target.value) })} className="w-full mt-1 px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm">
                  {stages.map(s => <option key={s.stage_id} value={s.stage_id}>{s.name}</option>)}
                </select>
              </div>

              {selectedDeal.contact_name && (
                <div>
                  <span className="text-xs text-gray-400 uppercase">Contact</span>
                  <p className="text-sm flex items-center gap-1"><User className="w-3.5 h-3.5 text-gray-400" /> {selectedDeal.contact_name}</p>
                  {selectedDeal.contact_email && <p className="text-xs text-gray-500 ml-5">{selectedDeal.contact_email}</p>}
                </div>
              )}

              {selectedDeal.expected_close_date && (
                <div>
                  <span className="text-xs text-gray-400 uppercase">Expected Close</span>
                  <p className="text-sm">{new Date(selectedDeal.expected_close_date).toLocaleDateString()}</p>
                </div>
              )}

              {selectedDeal.notes && (
                <div>
                  <span className="text-xs text-gray-400 uppercase">Notes</span>
                  <p className="text-sm whitespace-pre-wrap text-gray-700 dark:text-gray-300">{selectedDeal.notes}</p>
                </div>
              )}

              {/* ─── Activity Timeline ─────────────────────────────── */}
              <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Activity Timeline</h3>

                {/* Add Note */}
                <div className="flex gap-2 mb-4">
                  <input
                    value={newNote}
                    onChange={e => setNewNote(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAddNote() } }}
                    placeholder="Add a note..."
                    className="flex-1 px-3 py-1.5 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                  />
                  <button onClick={handleAddNote} disabled={!newNote.trim() || addingNote}
                    className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">
                    {addingNote ? '...' : 'Add'}
                  </button>
                </div>

                {/* Activities */}
                <div className="space-y-3 max-h-64 overflow-y-auto">
                  {(selectedDeal.activities || []).map((a: DealActivity) => (
                    <div key={a.activity_id} className="flex gap-2 items-start">
                      <div className="mt-0.5">{activityIcon(a.activity_type)}</div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-gray-700 dark:text-gray-300">{a.description || a.activity_type}</p>
                        {a.created_at && (
                          <p className="text-[10px] text-gray-400 mt-0.5">
                            {new Date(a.created_at).toLocaleString()}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                  {(!selectedDeal.activities || selectedDeal.activities.length === 0) && (
                    <p className="text-xs text-gray-400 text-center py-2">No activities yet</p>
                  )}
                </div>
              </div>

              <div className="flex gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                <button onClick={() => handleDeleteDeal(selectedDeal.deal_id)} className="flex items-center gap-2 px-4 py-2 text-red-600 border border-red-200 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-sm">
                  <Trash2 className="w-4 h-4" /> Delete
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
