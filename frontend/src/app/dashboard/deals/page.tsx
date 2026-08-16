'use client'

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { dealsApi } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { ClaimTag, AgeBadge, OwnerChip } from '@/components/deal-badges'
import type { Deal, DealStage, DealStats, DealActivity, DealContactSearch, DealClientSearch, DealForecast, StaleDeal } from '@/types/api'
import {
  Plus, X, DollarSign, Award, BarChart3, GripVertical,
  Trash2, Bot, Mail, MailOpen, Reply, AlertTriangle,
  MessageSquare, ArrowRight, Search, User, Building2, Target,
  LayoutGrid, List as ListIcon, Hand, UserPlus, RotateCcw,
} from 'lucide-react'

const formatCurrency = (v: number) => {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}K`
  return `$${v.toFixed(0)}`
}

const NUMERIC_OPS = [
  { value: '', label: 'Any' },
  { value: 'eq', label: '=' },
  { value: 'ne', label: '≠' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '≤' },
  { value: 'gt', label: '>' },
  { value: 'gte', label: '≥' },
  { value: 'between', label: 'between' },
]

const activityIcon = (type: string) => {
  switch (type) {
    case 'email_sent': return <Mail className="w-3.5 h-3.5 text-blue-500" />
    case 'email_received': return <Reply className="w-3.5 h-3.5 text-green-500" />
    case 'email_opened': return <MailOpen className="w-3.5 h-3.5 text-purple-500" />
    case 'email_bounced': return <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
    case 'stage_change': return <ArrowRight className="w-3.5 h-3.5 text-orange-500" />
    case 'auto_created': return <Bot className="w-3.5 h-3.5 text-indigo-500" />
    case 'claimed': return <Hand className="w-3.5 h-3.5 text-green-600" />
    case 'unclaimed': return <RotateCcw className="w-3.5 h-3.5 text-gray-400" />
    case 'assigned': return <UserPlus className="w-3.5 h-3.5 text-blue-600" />
    default: return <MessageSquare className="w-3.5 h-3.5 text-gray-400" />
  }
}

interface RepOption { user_id: number; label: string }

export default function DealsPage() {
  const { user } = useAuthStore()
  const effectiveRole = user?.base_role || user?.role || ''
  const isRep = ['bdm', 'recruiter'].includes(effectiveRole)
  const isAdmin = ['admin', 'super_admin'].includes(effectiveRole)

  const [tab, setTab] = useState<'board' | 'list'>('board')
  const [deals, setDeals] = useState<Deal[]>([])
  const [stages, setStages] = useState<DealStage[]>([])
  const [stats, setStats] = useState<DealStats | null>(null)
  const [forecast, setForecast] = useState<DealForecast | null>(null)
  const [staleDealIds, setStaleDealIds] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showDetailDrawer, setShowDetailDrawer] = useState(false)
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null)
  const [saving, setSaving] = useState(false)
  const [actioning, setActioning] = useState<number | null>(null)
  const [dealForm, setDealForm] = useState({
    name: '', stage_id: 0, value: 0, probability: 50, notes: '',
    contact_id: null as number | null, client_id: null as number | null,
  })
  const [dragDeal, setDragDeal] = useState<number | null>(null)

  // Filters
  const [fStage, setFStage] = useState('')
  const [fValueOp, setFValueOp] = useState('')
  const [fValueVal, setFValueVal] = useState('')
  const [fValueVal2, setFValueVal2] = useState('')
  const [fProbOp, setFProbOp] = useState('')
  const [fProbVal, setFProbVal] = useState('')
  const [fProbVal2, setFProbVal2] = useState('')
  const [fCreatedFrom, setFCreatedFrom] = useState('')
  const [fCreatedTo, setFCreatedTo] = useState('')
  const [fClaimedBy, setFClaimedBy] = useState('')
  const [fSearch, setFSearch] = useState('')

  // Reps for the assign dropdown (admins only)
  const [reps, setReps] = useState<RepOption[]>([])

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

  const [newNote, setNewNote] = useState('')
  const [addingNote, setAddingNote] = useState(false)

  const buildParams = useCallback(() => {
    const p: Record<string, unknown> = { page_size: 200 }
    if (fStage) p.stage_id = Number(fStage)
    if (fValueOp && fValueVal) { p.value_op = fValueOp; p.value_val = Number(fValueVal); if (fValueOp === 'between' && fValueVal2) p.value_val2 = Number(fValueVal2) }
    if (fProbOp && fProbVal) { p.probability_op = fProbOp; p.probability_val = Number(fProbVal); if (fProbOp === 'between' && fProbVal2) p.probability_val2 = Number(fProbVal2) }
    if (fCreatedFrom) p.created_from = fCreatedFrom
    if (fCreatedTo) p.created_to = fCreatedTo
    if (fClaimedBy) p.claimed_by = fClaimedBy
    if (fSearch.trim()) p.search = fSearch.trim()
    return p
  }, [fStage, fValueOp, fValueVal, fValueVal2, fProbOp, fProbVal, fProbVal2, fCreatedFrom, fCreatedTo, fClaimedBy, fSearch])

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [listData, stagesData, statsData, forecastData, staleData] = await Promise.all([
        dealsApi.list(buildParams()),
        dealsApi.listStages(),
        dealsApi.stats().catch(() => null),
        dealsApi.forecast().catch(() => null),
        dealsApi.stale().catch(() => []),
      ])
      setDeals(listData?.items || [])
      setStages(stagesData || [])
      setStats(statsData || null)
      setForecast(forecastData)
      setStaleDealIds(new Set<number>((staleData || []).map((s: StaleDeal) => s.deal_id)))
      if (stagesData?.length && !dealForm.stage_id) setDealForm(f => ({ ...f, stage_id: stagesData[0].stage_id }))
    } catch { /* ignore */ }
    setLoading(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildParams])

  useEffect(() => { fetchAll() }, [fetchAll])

  // Load assignable reps: admins → any rep; recruiters → BDMs (workflow hand-off).
  const canAssign = isAdmin || effectiveRole === 'recruiter'
  useEffect(() => {
    if (!canAssign) return
    dealsApi.assignees()
      .then((arr) => setReps(Array.isArray(arr) ? arr.map((u: { user_id: number; label: string }) => ({ user_id: u.user_id, label: u.label })) : []))
      .catch(() => setReps([]))
  }, [canAssign])

  // Distinct claimers present in the loaded deals (for the Claimed By filter)
  const claimerOptions = useMemo(() => {
    const seen = new Map<number, string>()
    deals.forEach(d => { if (d.claimed_by?.id) seen.set(d.claimed_by.id, d.claimed_by.name || `User ${d.claimed_by.id}`) })
    return Array.from(seen.entries()).map(([id, name]) => ({ id, name }))
  }, [deals])

  const boardStages = useMemo(() => {
    return stages.map(s => {
      const stageDeals = deals.filter(d => d.stage_id === s.stage_id)
      return { ...s, deals: stageDeals, count: stageDeals.length, total_value: stageDeals.reduce((a, d) => a + (d.value || 0), 0) }
    })
  }, [stages, deals])

  const hasActiveFilters = !!(fStage || fValueOp || fProbOp || fCreatedFrom || fCreatedTo || fClaimedBy || fSearch)
  const clearFilters = () => {
    setFStage(''); setFValueOp(''); setFValueVal(''); setFValueVal2(''); setFProbOp(''); setFProbVal(''); setFProbVal2('')
    setFCreatedFrom(''); setFCreatedTo(''); setFClaimedBy(''); setFSearch('')
  }

  // Contact/client search debounce
  useEffect(() => {
    if (contactSearchTimeout.current) clearTimeout(contactSearchTimeout.current)
    if (!contactSearch || contactSearch.length < 2) { setContactResults([]); return }
    contactSearchTimeout.current = setTimeout(async () => {
      try { setContactResults(await dealsApi.searchContacts(contactSearch) || []) } catch { setContactResults([]) }
    }, 300)
    return () => { if (contactSearchTimeout.current) clearTimeout(contactSearchTimeout.current) }
  }, [contactSearch])
  useEffect(() => {
    if (clientSearchTimeout.current) clearTimeout(clientSearchTimeout.current)
    if (!clientSearch || clientSearch.length < 2) { setClientResults([]); return }
    clientSearchTimeout.current = setTimeout(async () => {
      try { setClientResults(await dealsApi.searchClients(clientSearch) || []) } catch { setClientResults([]) }
    }, 300)
    return () => { if (clientSearchTimeout.current) clearTimeout(clientSearchTimeout.current) }
  }, [clientSearch])

  const selectContact = (c: DealContactSearch) => {
    setSelectedContact(c)
    setDealForm(f => ({ ...f, contact_id: c.contact_id }))
    setContactSearch(c.name); setShowContactDropdown(false)
    if (c.company && !selectedClient) {
      setClientSearch(c.company)
      dealsApi.searchClients(c.company).then(clients => {
        if (clients?.length) { setSelectedClient(clients[0]); setDealForm(f => ({ ...f, client_id: clients[0].client_id })); setClientSearch(clients[0].name) }
      }).catch(() => {})
    }
  }
  const selectClient = (c: DealClientSearch) => { setSelectedClient(c); setDealForm(f => ({ ...f, client_id: c.client_id })); setClientSearch(c.name); setShowClientDropdown(false) }

  const handleCreate = async () => {
    if (!dealForm.name || !dealForm.stage_id) return
    setSaving(true)
    try {
      await dealsApi.create(dealForm)
      setShowCreateModal(false)
      setDealForm({ name: '', stage_id: stages[0]?.stage_id || 0, value: 0, probability: 50, notes: '', contact_id: null, client_id: null })
      setSelectedContact(null); setSelectedClient(null); setContactSearch(''); setClientSearch('')
      await fetchAll()
    } catch { /* ignore */ }
    setSaving(false)
  }

  const openDeal = async (deal: Deal) => {
    try { setSelectedDeal(await dealsApi.get(deal.deal_id)); setShowDetailDrawer(true) }
    catch { setSelectedDeal(deal); setShowDetailDrawer(true) }
  }

  const refreshSelected = async (dealId: number) => {
    if (selectedDeal?.deal_id === dealId) {
      try { setSelectedDeal(await dealsApi.get(dealId)) } catch { /* ignore */ }
    }
  }

  const handleUpdateDeal = async (dealId: number, data: Record<string, unknown>) => {
    try { await dealsApi.update(dealId, data); await fetchAll(); await refreshSelected(dealId) } catch { /* ignore */ }
  }
  const handleDeleteDeal = async (dealId: number) => {
    try { await dealsApi.delete(dealId); setShowDetailDrawer(false); setSelectedDeal(null); await fetchAll() } catch { /* ignore */ }
  }

  const doClaim = async (dealId: number) => { setActioning(dealId); try { await dealsApi.claim(dealId); await fetchAll(); await refreshSelected(dealId) } catch { /* ignore */ } setActioning(null) }
  const doUnclaim = async (dealId: number) => { setActioning(dealId); try { await dealsApi.unclaim(dealId); await fetchAll(); await refreshSelected(dealId) } catch { /* ignore */ } setActioning(null) }
  const doAssign = async (dealId: number, userId: number | null) => { setActioning(dealId); try { await dealsApi.assign(dealId, userId); await fetchAll(); await refreshSelected(dealId) } catch { /* ignore */ } setActioning(null) }

  const handleAddNote = async () => {
    if (!selectedDeal || !newNote.trim()) return
    setAddingNote(true)
    try {
      await dealsApi.addActivity(selectedDeal.deal_id, { activity_type: 'note', description: newNote.trim() })
      setNewNote('')
      setSelectedDeal(await dealsApi.get(selectedDeal.deal_id))
    } catch { /* ignore */ }
    setAddingNote(false)
  }

  const handleDragStart = (dealId: number) => setDragDeal(dealId)
  const handleDragOver = (e: React.DragEvent) => e.preventDefault()
  const handleDrop = async (stageId: number) => { if (!dragDeal) return; setDragDeal(null); await handleUpdateDeal(dragDeal, { stage_id: stageId }) }

  const canClaim = (d: Deal) => isRep && d.is_unclaimed
  const canUnclaim = (d: Deal) => !d.is_unclaimed && (isAdmin || d.claimed_by?.id === user?.user_id)

  // Inline claim/assign controls reused on cards + rows + drawer
  const ClaimControls = ({ d, compact = false }: { d: Deal; compact?: boolean }) => (
    <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
      {canClaim(d) && (
        <button onClick={() => doClaim(d.deal_id)} disabled={actioning === d.deal_id}
          className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50">
          <Hand className="w-3 h-3" /> Claim
        </button>
      )}
      {canUnclaim(d) && !compact && (
        <button onClick={() => doUnclaim(d.deal_id)} disabled={actioning === d.deal_id}
          className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50">
          <RotateCcw className="w-3 h-3" /> Release
        </button>
      )}
      {canAssign && reps.length > 0 && (
        <select
          value={d.owner?.id ?? ''}
          onChange={e => doAssign(d.deal_id, e.target.value ? Number(e.target.value) : null)}
          disabled={actioning === d.deal_id}
          title={effectiveRole === 'recruiter' ? 'Hand off to a BDM' : 'Assign owner'}
          className="text-[11px] px-1.5 py-0.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700"
        >
          <option value="">{effectiveRole === 'recruiter' ? 'Hand to BDM…' : 'Assign…'}</option>
          {reps.map(r => <option key={r.user_id} value={r.user_id}>{r.label}</option>)}
        </select>
      )}
    </div>
  )

  if (loading && deals.length === 0) {
    return <div className="flex items-center justify-center h-64"><div className="text-gray-500">Loading deals...</div></div>
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Deals</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">CRM Pipeline &amp; claim queue</p>
        </div>
        <button onClick={() => setShowCreateModal(true)} className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700">
          <Plus className="w-4 h-4" /> New Deal
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard icon={<DollarSign className="w-4 h-4" />} label="Pipeline Value" value={formatCurrency(stats.total_pipeline_value)} />
          <StatCard icon={<Target className="w-4 h-4" />} label="Weighted Forecast" value={forecast ? formatCurrency(forecast.weighted_value) : '$0'} accent />
          <StatCard icon={<BarChart3 className="w-4 h-4" />} label="Total Deals" value={String(stats.total_deals)} />
          <StatCard icon={<Award className="w-4 h-4" />} label="Win Rate" value={`${stats.win_rate}%`} />
        </div>
      )}

      {/* Tabs + filter bar */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between border-b border-gray-200 dark:border-gray-700 px-3">
          <nav className="flex gap-1">
            {([['board', 'Board View', <LayoutGrid key="b" className="w-4 h-4" />], ['list', 'List View', <ListIcon key="l" className="w-4 h-4" />]] as const).map(([key, label, icon]) => (
              <button key={key} onClick={() => setTab(key)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
                  tab === key ? 'border-primary-600 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-200'
                }`}>
                {icon} {label}
              </button>
            ))}
          </nav>
        </div>

        {/* Filters */}
        <div className="p-3 flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[180px]">
            <label className="block text-[11px] text-gray-400 mb-0.5">Search</label>
            <div className="relative">
              <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-gray-400" />
              <input value={fSearch} onChange={e => setFSearch(e.target.value)} placeholder="Deal name…"
                className="w-full pl-8 pr-3 py-1.5 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
            </div>
          </div>
          <FilterSelect label="Status" value={fStage} onChange={setFStage}
            options={[{ value: '', label: 'All stages' }, ...stages.map(s => ({ value: String(s.stage_id), label: s.name }))]} />
          <NumericFilter label="Value" op={fValueOp} setOp={setFValueOp} v={fValueVal} setV={setFValueVal} v2={fValueVal2} setV2={setFValueVal2} />
          <NumericFilter label="Probability" op={fProbOp} setOp={setFProbOp} v={fProbVal} setV={setFProbVal} v2={fProbVal2} setV2={setFProbVal2} />
          <div>
            <label className="block text-[11px] text-gray-400 mb-0.5">Created from</label>
            <input type="date" value={fCreatedFrom} onChange={e => setFCreatedFrom(e.target.value)} className="px-2 py-1.5 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
          </div>
          <div>
            <label className="block text-[11px] text-gray-400 mb-0.5">to</label>
            <input type="date" value={fCreatedTo} onChange={e => setFCreatedTo(e.target.value)} className="px-2 py-1.5 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
          </div>
          <FilterSelect label="Claimed By" value={fClaimedBy} onChange={setFClaimedBy}
            options={[{ value: '', label: 'Anyone' }, { value: 'unclaimed', label: 'Unclaimed' }, { value: 'me', label: 'Me' }, ...claimerOptions.map(c => ({ value: String(c.id), label: c.name }))]} />
          {hasActiveFilters && (
            <button onClick={clearFilters} className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-200">Clear</button>
          )}
        </div>
      </div>

      {/* ─── Board View ─────────────────────────────────────────── */}
      {tab === 'board' && (
        <div className="flex gap-4 overflow-x-auto pb-4">
          {boardStages.map(stage => (
            <div key={stage.stage_id} className="flex-shrink-0 w-72" onDragOver={handleDragOver} onDrop={() => handleDrop(stage.stage_id)}>
              <div className="flex items-center gap-2 mb-3 px-1">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: stage.color || '#6B7280' }} />
                <h3 className="font-medium text-sm text-gray-900 dark:text-gray-100">{stage.name}</h3>
                <span className="text-xs text-gray-400 ml-auto">{stage.count}</span>
                <span className="text-xs text-gray-400">{formatCurrency(stage.total_value)}</span>
              </div>
              <div className="space-y-2 min-h-[100px] bg-gray-50 dark:bg-gray-900/30 rounded-lg p-2">
                {stage.deals.map(deal => (
                  <div key={deal.deal_id} draggable onDragStart={() => handleDragStart(deal.deal_id)} onClick={() => openDeal(deal)}
                    className={`bg-white dark:bg-gray-800 rounded-lg border p-3 cursor-pointer hover:shadow-md transition-shadow ${
                      dragDeal === deal.deal_id ? 'opacity-50' : ''} ${staleDealIds.has(deal.deal_id) ? 'border-orange-300 dark:border-orange-600' : 'border-gray-200 dark:border-gray-700'}`}>
                    <div className="flex items-start gap-2">
                      <GripVertical className="w-4 h-4 text-gray-300 mt-0.5 flex-shrink-0 cursor-grab" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <ClaimTag claimedBy={deal.claimed_by} owner={deal.owner} />
                          <AgeBadge days={deal.age_days} />
                          {deal.is_auto_created && <span className="px-1.5 py-0.5 text-[10px] font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300 rounded-full">Auto</span>}
                        </div>
                        <p className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate mt-1.5">{deal.name}</p>
                        {deal.client_name && <p className="text-xs text-gray-500 truncate">{deal.client_name}</p>}
                        <div className="flex items-center justify-between mt-2">
                          <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{formatCurrency(deal.value)}</span>
                          <span className="text-xs text-gray-400">{deal.probability}%</span>
                        </div>
                        <div className="mt-2"><ClaimControls d={deal} compact /></div>
                      </div>
                    </div>
                  </div>
                ))}
                {stage.deals.length === 0 && <div className="text-center py-4 text-xs text-gray-400">No deals</div>}
              </div>
            </div>
          ))}
          {boardStages.length === 0 && (
            <div className="flex-1 text-center py-12 text-gray-500">
              <DollarSign className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p className="font-medium">No deal stages found</p>
            </div>
          )}
        </div>
      )}

      {/* ─── List View ──────────────────────────────────────────── */}
      {tab === 'list' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900">
                <tr>
                  {['Claim', 'Age', 'Deal', 'Stage', 'Value', 'Prob.', 'Owner', 'Created', 'Actions'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
                {deals.map(d => (
                  <tr key={d.deal_id} onClick={() => openDeal(d)} className="hover:bg-gray-50 dark:hover:bg-gray-700/40 cursor-pointer">
                    <td className="px-3 py-2"><ClaimTag claimedBy={d.claimed_by} owner={d.owner} /></td>
                    <td className="px-3 py-2"><AgeBadge days={d.age_days} /></td>
                    <td className="px-3 py-2 font-medium text-gray-900 dark:text-gray-100 max-w-[220px] truncate">
                      {d.name}
                      {d.client_name && <span className="block text-xs text-gray-400 truncate">{d.client_name}</span>}
                    </td>
                    <td className="px-3 py-2"><span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: d.stage_color || '#6b7280' }} />{d.stage_name}</span></td>
                    <td className="px-3 py-2 font-semibold">{formatCurrency(d.value)}</td>
                    <td className="px-3 py-2 text-gray-500">{d.probability}%</td>
                    <td className="px-3 py-2">{d.owner ? <OwnerChip owner={d.owner} /> : <span className="text-gray-300">—</span>}</td>
                    <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{new Date(d.created_at).toLocaleDateString()}</td>
                    <td className="px-3 py-2"><ClaimControls d={d} /></td>
                  </tr>
                ))}
                {deals.length === 0 && (
                  <tr><td colSpan={9} className="px-3 py-10 text-center text-gray-400">No deals match these filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ─── Create Modal ───────────────────────────────────────── */}
      {showCreateModal && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowCreateModal(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-[500px] mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold dark:text-gray-100">New Deal</h2>
              <button onClick={() => setShowCreateModal(false)}><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Deal Name *</label>
                <input value={dealForm.name} onChange={e => setDealForm(f => ({ ...f, name: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" placeholder="e.g., Acme Corp — Q2 Campaign" />
              </div>
              <div className="relative">
                <label className="block text-sm font-medium mb-1"><User className="w-3.5 h-3.5 inline mr-1" /> Contact</label>
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
                  <input value={contactSearch} onChange={e => { setContactSearch(e.target.value); setShowContactDropdown(true); setSelectedContact(null); setDealForm(f => ({ ...f, contact_id: null })) }} onFocus={() => setShowContactDropdown(true)} className="w-full pl-9 pr-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" placeholder="Search by name, email, or company..." />
                  {selectedContact && <button onClick={() => { setSelectedContact(null); setContactSearch(''); setDealForm(f => ({ ...f, contact_id: null })) }} className="absolute right-2 top-2 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>}
                </div>
                {showContactDropdown && contactResults.length > 0 && (
                  <div className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                    {contactResults.map(c => (
                      <button key={c.contact_id} onClick={() => selectContact(c)} className="w-full text-left px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-600 flex flex-col text-sm">
                        <span className="font-medium">{c.name}</span>
                        <span className="text-xs text-gray-500">{c.email}{c.company ? ` — ${c.company}` : ''}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="relative">
                <label className="block text-sm font-medium mb-1"><Building2 className="w-3.5 h-3.5 inline mr-1" /> Company</label>
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
                  <input value={clientSearch} onChange={e => { setClientSearch(e.target.value); setShowClientDropdown(true); setSelectedClient(null); setDealForm(f => ({ ...f, client_id: null })) }} onFocus={() => setShowClientDropdown(true)} className="w-full pl-9 pr-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 text-sm" placeholder="Search companies..." />
                  {selectedClient && <button onClick={() => { setSelectedClient(null); setClientSearch(''); setDealForm(f => ({ ...f, client_id: null })) }} className="absolute right-2 top-2 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>}
                </div>
                {showClientDropdown && clientResults.length > 0 && (
                  <div className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                    {clientResults.map(c => <button key={c.client_id} onClick={() => selectClient(c)} className="w-full text-left px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-600 text-sm font-medium">{c.name}</button>)}
                  </div>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Stage</label>
                <select value={dealForm.stage_id} onChange={e => setDealForm(f => ({ ...f, stage_id: parseInt(e.target.value) }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600">
                  {stages.map(s => <option key={s.stage_id} value={s.stage_id}>{s.name}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div><label className="block text-sm font-medium mb-1">Value ($)</label><input type="number" value={dealForm.value} onChange={e => setDealForm(f => ({ ...f, value: parseFloat(e.target.value) || 0 }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" /></div>
                <div><label className="block text-sm font-medium mb-1">Probability (%)</label><input type="number" min={0} max={100} value={dealForm.probability} onChange={e => setDealForm(f => ({ ...f, probability: parseInt(e.target.value) || 0 }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" /></div>
              </div>
              <div><label className="block text-sm font-medium mb-1">Notes</label><textarea value={dealForm.notes} onChange={e => setDealForm(f => ({ ...f, notes: e.target.value }))} className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600" rows={3} /></div>
              <div className="flex gap-3 pt-2">
                <button onClick={() => setShowCreateModal(false)} className="flex-1 px-4 py-2 border rounded-lg">Cancel</button>
                <button onClick={handleCreate} disabled={!dealForm.name || saving} className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">{saving ? 'Creating...' : 'Create Deal'}</button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ─── Detail Drawer ──────────────────────────────────────── */}
      {showDetailDrawer && selectedDeal && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setShowDetailDrawer(false)} />
          <div className="fixed right-0 top-0 h-full w-[440px] max-w-[90vw] bg-white dark:bg-gray-800 z-50 shadow-xl overflow-y-auto">
            <div className="p-6 space-y-6">
              <div className="flex justify-between items-start">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <ClaimTag claimedBy={selectedDeal.claimed_by} owner={selectedDeal.owner} size="md" />
                    <AgeBadge days={selectedDeal.age_days} size="md" />
                    {selectedDeal.is_auto_created && <span className="px-2 py-0.5 text-xs font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300 rounded-full flex items-center gap-1"><Bot className="w-3 h-3" /> Auto</span>}
                  </div>
                  <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mt-2 truncate">{selectedDeal.name}</h2>
                  {selectedDeal.client_name && <p className="text-sm text-gray-500">{selectedDeal.client_name}</p>}
                </div>
                <button onClick={() => setShowDetailDrawer(false)}><X className="w-5 h-5" /></button>
              </div>

              {/* Claim / Assign actions */}
              <div className="flex items-center gap-2 flex-wrap"><ClaimControls d={selectedDeal} /></div>

              <div className="grid grid-cols-2 gap-4">
                <Field label="Value" value={formatCurrency(selectedDeal.value)} />
                <Field label="Probability" value={`${selectedDeal.probability}%`} />
                <Field label="Claimed By" value={selectedDeal.claimed_by?.name || 'Unclaimed'} />
                <Field label="Assigned Owner" value={selectedDeal.owner?.name || 'Unassigned'} />
                <Field label="Age" value={`${selectedDeal.age_days ?? 0} days`} />
                <Field label="Created" value={new Date(selectedDeal.created_at).toLocaleDateString()} />
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
              {selectedDeal.notes && (
                <div><span className="text-xs text-gray-400 uppercase">Notes</span><p className="text-sm whitespace-pre-wrap text-gray-700 dark:text-gray-300">{selectedDeal.notes}</p></div>
              )}

              {/* Activity Timeline */}
              <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Activity Timeline</h3>
                <div className="flex gap-2 mb-4">
                  <input value={newNote} onChange={e => setNewNote(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAddNote() } }} placeholder="Add a note..." className="flex-1 px-3 py-1.5 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600" />
                  <button onClick={handleAddNote} disabled={!newNote.trim() || addingNote} className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">{addingNote ? '...' : 'Add'}</button>
                </div>
                <div className="space-y-3 max-h-64 overflow-y-auto">
                  {(selectedDeal.activities || []).map((a: DealActivity) => (
                    <div key={a.activity_id} className="flex gap-2 items-start">
                      <div className="mt-0.5">{activityIcon(a.activity_type)}</div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-gray-700 dark:text-gray-300">{a.description || a.activity_type}</p>
                        {a.created_at && <p className="text-[10px] text-gray-400 mt-0.5">{new Date(a.created_at).toLocaleString()}</p>}
                      </div>
                    </div>
                  ))}
                  {(!selectedDeal.activities || selectedDeal.activities.length === 0) && <p className="text-xs text-gray-400 text-center py-2">No activities yet</p>}
                </div>
              </div>

              <div className="flex gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                <button onClick={() => handleDeleteDeal(selectedDeal.deal_id)} className="flex items-center gap-2 px-4 py-2 text-red-600 border border-red-200 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-sm"><Trash2 className="w-4 h-4" /> Delete</button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ─── Small presentational helpers ──────────────────────────────────

function StatCard({ icon, label, value, accent }: { icon: React.ReactNode; label: string; value: string; accent?: boolean }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className="flex items-center gap-2 text-gray-500 text-sm mb-1">{icon} {label}</div>
      <p className={`text-2xl font-bold ${accent ? 'text-primary-600' : ''}`}>{value}</p>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div><span className="text-xs text-gray-400 uppercase">{label}</span><p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{value}</p></div>
  )
}

function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <div>
      <label className="block text-[11px] text-gray-400 mb-0.5">{label}</label>
      <select value={value} onChange={e => onChange(e.target.value)} className="px-2 py-1.5 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600">
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
}

function NumericFilter({ label, op, setOp, v, setV, v2, setV2 }: { label: string; op: string; setOp: (s: string) => void; v: string; setV: (s: string) => void; v2: string; setV2: (s: string) => void }) {
  return (
    <div>
      <label className="block text-[11px] text-gray-400 mb-0.5">{label}</label>
      <div className="flex items-center gap-1">
        <select value={op} onChange={e => setOp(e.target.value)} className="px-1.5 py-1.5 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600">
          {NUMERIC_OPS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {op && <input type="number" value={v} onChange={e => setV(e.target.value)} placeholder="0" className="w-20 px-2 py-1.5 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600" />}
        {op === 'between' && <input type="number" value={v2} onChange={e => setV2(e.target.value)} placeholder="max" className="w-20 px-2 py-1.5 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600" />}
      </div>
    </div>
  )
}
