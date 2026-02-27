'use client'

import { useState, useEffect, useCallback } from 'react'
import { pipelinesApi, dashboardApi, leadsApi } from '@/lib/api'

interface PipelineRun {
  run_id: number
  pipeline_name: string
  status: string
  started_at: string
  ended_at: string | null
  records_processed: number
  records_success: number
  records_failed: number
  error_message: string | null
  triggered_by: string
  duration_seconds: number | null
  adapters_used: string[] | null
}

interface PipelineStats {
  leads_sourced: number
  contacts_enriched: number
  emails_validated: number
  emails_sent: number
}

interface SelectorLead {
  lead_id: number
  client_name: string
  job_title: string
  state: string
  lead_status: string
  contact_count: number
}

export default function PipelinesPage() {
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [stats, setStats] = useState<PipelineStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Simple boolean states for each pipeline button - always start as false
  const [leadSourcingRunning, setLeadSourcingRunning] = useState(false)
  const [contactEnrichmentRunning, setContactEnrichmentRunning] = useState(false)
  const [emailValidationRunning, setEmailValidationRunning] = useState(false)
  const [outreachRunning, setOutreachRunning] = useState(false)

  // Lead selector popup state
  const [showLeadSelector, setShowLeadSelector] = useState(false)
  const [selectorPipeline, setSelectorPipeline] = useState<'contact-enrichment' | 'outreach'>('contact-enrichment')
  const [selectorLeads, setSelectorLeads] = useState<SelectorLead[]>([])
  const [selectorLoading, setSelectorLoading] = useState(false)
  const [selectorSearch, setSelectorSearch] = useState('')
  const [selectorStatus, setSelectorStatus] = useState('')
  const [selectorPage, setSelectorPage] = useState(1)
  const [selectorTotal, setSelectorTotal] = useState(0)
  const [selectorSelected, setSelectorSelected] = useState<Set<number>>(new Set())

  const SELECTOR_PAGE_SIZE = 20

  // Fetch data function
  const fetchData = async () => {
    try {
      const [runsData, kpis] = await Promise.all([
        pipelinesApi.runs({ limit: 50 }),
        dashboardApi.kpis()
      ])
      setRuns(runsData || [])
      setStats({
        leads_sourced: kpis.total_leads || 0,
        contacts_enriched: kpis.total_contacts || 0,
        emails_validated: kpis.total_valid_emails || 0,
        emails_sent: kpis.emails_sent || 0,
      })
      return runsData || []
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch pipeline data')
      return []
    }
  }

  // Initial load
  useEffect(() => {
    const init = async () => {
      setLoading(true)
      await fetchData()
      setLoading(false)
    }
    init()
  }, [])

  // Fetch leads for selector
  const fetchSelectorLeads = useCallback(async (search: string, status: string, page: number) => {
    setSelectorLoading(true)
    try {
      const params: Record<string, any> = {
        page,
        page_size: SELECTOR_PAGE_SIZE,
        sort_by: 'created_at',
        sort_order: 'desc',
      }
      if (search) params.search = search
      if (status) params.status = status

      const response = await leadsApi.list(params)
      setSelectorLeads(response.items || [])
      setSelectorTotal(response.total || 0)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch leads')
    } finally {
      setSelectorLoading(false)
    }
  }, [])

  // Debounced search for selector
  const [debouncedSelectorSearch, setDebouncedSelectorSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSelectorSearch(selectorSearch), 300)
    return () => clearTimeout(timer)
  }, [selectorSearch])

  useEffect(() => {
    if (showLeadSelector) {
      fetchSelectorLeads(debouncedSelectorSearch, selectorStatus, selectorPage)
    }
  }, [showLeadSelector, debouncedSelectorSearch, selectorStatus, selectorPage, fetchSelectorLeads])

  // Open lead selector for a pipeline
  const openLeadSelector = (pipeline: 'contact-enrichment' | 'outreach') => {
    setSelectorPipeline(pipeline)
    setSelectorSelected(new Set())
    setSelectorSearch('')
    setSelectorStatus('')
    setSelectorPage(1)
    setShowLeadSelector(true)
  }

  // Toggle lead selection
  const toggleSelectorLead = (id: number) => {
    setSelectorSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Toggle select all on current page
  const toggleSelectorSelectAll = () => {
    const pageIds = selectorLeads.map(l => l.lead_id)
    const allSelected = pageIds.every(id => selectorSelected.has(id))
    setSelectorSelected(prev => {
      const next = new Set(prev)
      if (allSelected) {
        pageIds.forEach(id => next.delete(id))
      } else {
        pageIds.forEach(id => next.add(id))
      }
      return next
    })
  }

  // Run pipeline with selected leads
  const handleRunWithSelectedLeads = async (runAll: boolean) => {
    const leadIds = runAll ? undefined : Array.from(selectorSelected)
    setShowLeadSelector(false)

    if (selectorPipeline === 'contact-enrichment') {
      setContactEnrichmentRunning(true)
      setError('')
      setSuccess('')
      try {
        await pipelinesApi.runContactEnrichment(leadIds)
        setSuccess(leadIds
          ? `Contact enrichment started for ${leadIds.length} selected leads!`
          : 'Contact enrichment pipeline started for all leads!')
        startPolling('contact-enrichment')
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to start contact enrichment')
        setContactEnrichmentRunning(false)
      }
    } else if (selectorPipeline === 'outreach') {
      setOutreachRunning(true)
      setError('')
      setSuccess('')
      try {
        await pipelinesApi.runOutreach('send', true, leadIds)
        setSuccess(leadIds
          ? `Outreach started for ${leadIds.length} selected leads!`
          : 'Outreach pipeline started!')
        startPolling('outreach')
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to start outreach')
        setOutreachRunning(false)
      }
    }
  }

  // Polling helper
  const startPolling = (pipelineType: string) => {
    let attempts = 0
    const maxAttempts = 60

    const poll = async () => {
      attempts++
      const runsData = await fetchData()

      const stillRunning = runsData.some((r: PipelineRun) =>
        r.status && r.status.toLowerCase() === 'running'
      )

      if (!stillRunning || attempts >= maxAttempts) {
        if (pipelineType === 'lead-sourcing') setLeadSourcingRunning(false)
        if (pipelineType === 'contact-enrichment') setContactEnrichmentRunning(false)
        if (pipelineType === 'email-validation') setEmailValidationRunning(false)
        if (pipelineType === 'outreach') setOutreachRunning(false)

        const latestRun = runsData[0]
        if (latestRun && latestRun.status === 'completed') {
          setSuccess(`Pipeline completed! Processed: ${latestRun.records_processed}, Success: ${latestRun.records_success}, Failed: ${latestRun.records_failed}`)
        }
        return
      }

      setTimeout(poll, 3000)
    }

    setTimeout(poll, 2000)
  }

  // Run pipeline with polling (original - for lead-sourcing and email-validation)
  const runPipeline = async (pipelineType: string) => {
    // Set running state
    if (pipelineType === 'lead-sourcing') setLeadSourcingRunning(true)
    if (pipelineType === 'contact-enrichment') setContactEnrichmentRunning(true)
    if (pipelineType === 'email-validation') setEmailValidationRunning(true)
    if (pipelineType === 'outreach') setOutreachRunning(true)

    setError('')
    setSuccess('')

    try {
      // Start the pipeline
      switch (pipelineType) {
        case 'lead-sourcing':
          await pipelinesApi.runLeadSourcing(['indeed', 'linkedin', 'glassdoor'])
          setSuccess('Lead sourcing pipeline started!')
          break
        case 'contact-enrichment':
          await pipelinesApi.runContactEnrichment()
          setSuccess('Contact enrichment pipeline started!')
          break
        case 'email-validation':
          await pipelinesApi.runEmailValidation()
          setSuccess('Email validation pipeline started!')
          break
        case 'outreach':
          await pipelinesApi.runOutreach('mailmerge', true)
          setSuccess('Outreach pipeline started!')
          break
      }

      startPolling(pipelineType)

    } catch (err: any) {
      setError(err.response?.data?.detail || `Failed to start ${pipelineType} pipeline`)
      // Reset running state on error
      if (pipelineType === 'lead-sourcing') setLeadSourcingRunning(false)
      if (pipelineType === 'contact-enrichment') setContactEnrichmentRunning(false)
      if (pipelineType === 'email-validation') setEmailValidationRunning(false)
      if (pipelineType === 'outreach') setOutreachRunning(false)
    }
  }

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      running: 'bg-blue-100 text-blue-800 animate-pulse',
      completed: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800',
      pending: 'bg-yellow-100 text-yellow-800',
    }
    return colors[status?.toLowerCase()] || 'bg-gray-100 text-gray-800'
  }

  const getLeadStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      new: 'bg-slate-100 text-slate-800',
      enriched: 'bg-purple-100 text-purple-800',
      validated: 'bg-teal-100 text-teal-800',
      open: 'bg-green-100 text-green-800',
      hunting: 'bg-yellow-100 text-yellow-800',
      sent: 'bg-indigo-100 text-indigo-800',
      skipped: 'bg-orange-100 text-orange-800',
    }
    return colors[status?.toLowerCase()] || 'bg-gray-100 text-gray-800'
  }

  const getPipelineBadge = (name: string) => {
    const colors: Record<string, string> = {
      'lead_sourcing': 'bg-indigo-100 text-indigo-800',
      'contact_enrichment': 'bg-purple-100 text-purple-800',
      'email_validation': 'bg-cyan-100 text-cyan-800',
      'outreach': 'bg-orange-100 text-orange-800',
    }
    return colors[name?.toLowerCase()] || 'bg-gray-100 text-gray-800'
  }

  const formatPipelineName = (name: string) => {
    return name?.replace(/_/g, ' ').replace(/-/g, ' ').split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
  }

  const selectorTotalPages = Math.ceil(selectorTotal / SELECTOR_PAGE_SIZE) || 1
  const pageLeadIds = selectorLeads.map(l => l.lead_id)
  const allPageSelected = pageLeadIds.length > 0 && pageLeadIds.every(id => selectorSelected.has(id))

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading pipeline data...</div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Pipeline Management</h1>
          <p className="text-gray-500 mt-1">Run and monitor data pipelines</p>
        </div>
        <button
          onClick={() => fetchData()}
          className="btn-secondary"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg mb-4 flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError('')} className="font-bold">&times;</button>
        </div>
      )}

      {success && (
        <div className="bg-green-50 text-green-600 px-4 py-2 rounded-lg mb-4 flex justify-between items-center">
          <span>{success}</span>
          <button onClick={() => setSuccess('')} className="font-bold">&times;</button>
        </div>
      )}

      {/* Complete Workflow Visualization */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-6 mb-6">
        <h3 className="font-semibold text-blue-800 mb-4">Complete Data Pipeline Workflow</h3>
        <div className="flex items-center justify-between text-sm">
          <div className="flex flex-col items-center">
            <div className="w-12 h-12 bg-indigo-500 rounded-full flex items-center justify-center text-white font-bold mb-2">1</div>
            <span className="px-3 py-1 bg-indigo-100 text-indigo-800 rounded font-medium">Lead Sourcing</span>
            <span className="text-xs text-gray-500 mt-1">{stats?.leads_sourced || 0} leads</span>
          </div>
          <div className="flex-1 h-1 bg-indigo-200 mx-2"></div>
          <div className="flex flex-col items-center">
            <div className="w-12 h-12 bg-purple-500 rounded-full flex items-center justify-center text-white font-bold mb-2">2</div>
            <span className="px-3 py-1 bg-purple-100 text-purple-800 rounded font-medium">Contact Enrichment</span>
            <span className="text-xs text-gray-500 mt-1">{stats?.contacts_enriched || 0} contacts</span>
          </div>
          <div className="flex-1 h-1 bg-purple-200 mx-2"></div>
          <div className="flex flex-col items-center">
            <div className="w-12 h-12 bg-cyan-500 rounded-full flex items-center justify-center text-white font-bold mb-2">3</div>
            <span className="px-3 py-1 bg-cyan-100 text-cyan-800 rounded font-medium">Email Validation</span>
            <span className="text-xs text-gray-500 mt-1">{stats?.emails_validated || 0} valid</span>
          </div>
          <div className="flex-1 h-1 bg-cyan-200 mx-2"></div>
          <div className="flex flex-col items-center">
            <div className="w-12 h-12 bg-orange-500 rounded-full flex items-center justify-center text-white font-bold mb-2">4</div>
            <span className="px-3 py-1 bg-orange-100 text-orange-800 rounded font-medium">Outreach</span>
            <span className="text-xs text-gray-500 mt-1">{stats?.emails_sent || 0} sent</span>
          </div>
        </div>
      </div>

      {/* Pipeline Control Cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {/* Lead Sourcing */}
        <div className="card p-4 border-t-4 border-indigo-500">
          <h4 className="font-semibold text-gray-800 mb-2">Lead Sourcing</h4>
          <p className="text-sm text-gray-500 mb-4">Scrape job postings from Indeed, LinkedIn, Glassdoor</p>
          <button
            onClick={() => runPipeline('lead-sourcing')}
            disabled={leadSourcingRunning}
            className={`btn-primary w-full text-sm ${leadSourcingRunning ? 'opacity-75 animate-pulse' : ''}`}
          >
            {leadSourcingRunning ? 'Running...' : 'Run Pipeline'}
          </button>
        </div>

        {/* Contact Enrichment */}
        <div className="card p-4 border-t-4 border-purple-500">
          <h4 className="font-semibold text-gray-800 mb-2">Contact Enrichment</h4>
          <p className="text-sm text-gray-500 mb-4">Find decision-maker contacts for sourced leads</p>
          <button
            onClick={() => openLeadSelector('contact-enrichment')}
            disabled={contactEnrichmentRunning}
            className={`btn-primary w-full text-sm ${contactEnrichmentRunning ? 'opacity-75 animate-pulse' : ''}`}
          >
            {contactEnrichmentRunning ? 'Running...' : 'Run Pipeline'}
          </button>
        </div>

        {/* Email Validation */}
        <div className="card p-4 border-t-4 border-cyan-500">
          <h4 className="font-semibold text-gray-800 mb-2">Email Validation</h4>
          <p className="text-sm text-gray-500 mb-4">Validate email addresses using ZeroBounce/MillionVerifier</p>
          <button
            onClick={() => runPipeline('email-validation')}
            disabled={emailValidationRunning}
            className={`btn-primary w-full text-sm ${emailValidationRunning ? 'opacity-75 animate-pulse' : ''}`}
          >
            {emailValidationRunning ? 'Running...' : 'Run Pipeline'}
          </button>
        </div>

        {/* Outreach */}
        <div className="card p-4 border-t-4 border-orange-500">
          <h4 className="font-semibold text-gray-800 mb-2">Outreach</h4>
          <p className="text-sm text-gray-500 mb-4">Send emails or export for mail merge</p>
          <button
            onClick={() => openLeadSelector('outreach')}
            disabled={outreachRunning}
            className={`btn-primary w-full text-sm ${outreachRunning ? 'opacity-75 animate-pulse' : ''}`}
          >
            {outreachRunning ? 'Running...' : 'Run Pipeline'}
          </button>
        </div>
      </div>

      {/* Business Rules Info */}
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
        <h4 className="font-semibold text-yellow-800 mb-2">Business Rules Applied</h4>
        <div className="grid grid-cols-4 gap-4 text-sm text-yellow-700">
          <div>
            <span className="font-medium">Bounce Rate Target:</span>
            <span className="ml-1">&lt; 2%</span>
          </div>
          <div>
            <span className="font-medium">Cooldown Period:</span>
            <span className="ml-1">10 days</span>
          </div>
          <div>
            <span className="font-medium">Max per Company/Job:</span>
            <span className="ml-1">4 contacts</span>
          </div>
          <div>
            <span className="font-medium">Daily Send Limit:</span>
            <span className="ml-1">30 emails</span>
          </div>
        </div>
      </div>

      {/* Pipeline Run History */}
      <div className="card overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="font-semibold text-gray-800">Pipeline Run History</h3>
        </div>
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Run ID
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Pipeline
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Started
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Duration
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Adapter
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Records
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Success/Failed
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Triggered By
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {runs.map((run) => (
              <tr key={run.run_id} className="hover:bg-gray-50">
                <td className="px-6 py-4 text-sm text-gray-900 font-mono">
                  #{run.run_id}
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 text-xs rounded-full ${getPipelineBadge(run.pipeline_name)}`}>
                    {formatPipelineName(run.pipeline_name)}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 text-xs rounded-full ${getStatusBadge(run.status)}`}>
                    {run.status}
                  </span>
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {run.duration_seconds != null ? (
                    run.duration_seconds < 60
                      ? `${run.duration_seconds}s`
                      : `${Math.floor(run.duration_seconds / 60)}m ${Math.round(run.duration_seconds % 60)}s`
                  ) : '-'}
                </td>
                <td className="px-6 py-4 text-sm">
                  {run.adapters_used && run.adapters_used.length > 0 ? (
                    <div className="flex gap-1 flex-wrap">
                      {run.adapters_used.map((a: string) => (
                        <span key={a} className={`text-xs px-2 py-0.5 rounded-full ${
                          a === 'apollo' ? 'bg-orange-100 text-orange-700' :
                          a === 'seamless' ? 'bg-cyan-100 text-cyan-700' :
                          a === 'mock' ? 'bg-gray-100 text-gray-600' :
                          'bg-purple-100 text-purple-700'
                        }`}>
                          {a}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </td>
                <td className="px-6 py-4 text-sm text-gray-900">
                  {run.records_processed || 0}
                </td>
                <td className="px-6 py-4 text-sm">
                  <span className="text-green-600">{run.records_success || 0}</span>
                  {' / '}
                  <span className="text-red-600">{run.records_failed || 0}</span>
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {run.triggered_by || 'system'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {runs.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            No pipeline runs yet. Start a pipeline above to see run history.
          </div>
        )}
      </div>

      {/* Lead Selector Modal */}
      {showLeadSelector && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full mx-4 max-h-[85vh] flex flex-col">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-semibold text-gray-800">
                {selectorPipeline === 'contact-enrichment' ? 'Select Leads for Contact Enrichment' : 'Select Leads for Outreach'}
              </h3>
              <p className="text-sm text-gray-500 mt-1">
                Choose specific leads or run for all. {selectorTotal} total leads available.
              </p>
            </div>

            {/* Search & Filters */}
            <div className="px-6 py-3 border-b bg-gray-50 flex gap-3">
              <input
                type="text"
                placeholder="Search company or job title..."
                value={selectorSearch}
                onChange={(e) => { setSelectorSearch(e.target.value); setSelectorPage(1) }}
                className="input flex-1"
              />
              <select
                value={selectorStatus}
                onChange={(e) => { setSelectorStatus(e.target.value); setSelectorPage(1) }}
                className="input w-40"
              >
                <option value="">All Statuses</option>
                <option value="new">New</option>
                <option value="enriched">Enriched</option>
                <option value="validated">Validated</option>
                <option value="open">Open</option>
                <option value="sent">Sent</option>
              </select>
            </div>

            {/* Selection Info */}
            {selectorSelected.size > 0 && (
              <div className="px-6 py-2 bg-blue-50 border-b flex items-center justify-between">
                <span className="text-sm text-blue-800 font-medium">{selectorSelected.size} lead(s) selected</span>
                <button
                  onClick={() => setSelectorSelected(new Set())}
                  className="text-sm text-blue-600 hover:text-blue-800"
                >
                  Clear selection
                </button>
              </div>
            )}

            {/* Lead List */}
            <div className="overflow-y-auto flex-1">
              {selectorLoading ? (
                <div className="text-center py-8 text-gray-500">Loading leads...</div>
              ) : selectorLeads.length === 0 ? (
                <div className="text-center py-8 text-gray-500">No leads found.</div>
              ) : (
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-4 py-2 w-10">
                        <input
                          type="checkbox"
                          checked={allPageSelected}
                          onChange={toggleSelectorSelectAll}
                          className="w-4 h-4"
                        />
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Company / Job</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Contacts</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {selectorLeads.map((lead) => (
                      <tr
                        key={lead.lead_id}
                        className={`cursor-pointer ${selectorSelected.has(lead.lead_id) ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                        onClick={() => toggleSelectorLead(lead.lead_id)}
                      >
                        <td className="px-4 py-2">
                          <input
                            type="checkbox"
                            checked={selectorSelected.has(lead.lead_id)}
                            onChange={() => toggleSelectorLead(lead.lead_id)}
                            onClick={(e) => e.stopPropagation()}
                            className="w-4 h-4"
                          />
                        </td>
                        <td className="px-4 py-2 text-xs font-mono text-gray-500">#{lead.lead_id}</td>
                        <td className="px-4 py-2">
                          <div className="text-sm font-medium text-gray-800">{lead.client_name}</div>
                          <div className="text-xs text-gray-500">{lead.job_title}</div>
                        </td>
                        <td className="px-4 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${getLeadStatusBadge(lead.lead_status)}`}>
                            {lead.lead_status}
                          </span>
                        </td>
                        <td className="px-4 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            lead.contact_count > 0 ? 'bg-purple-100 text-purple-800' : 'bg-gray-100 text-gray-500'
                          }`}>
                            {lead.contact_count || 0}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Pagination */}
            <div className="px-6 py-2 border-t bg-gray-50 flex items-center justify-between text-sm">
              <span className="text-gray-500">
                Page {selectorPage} of {selectorTotalPages} ({selectorTotal} leads)
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setSelectorPage(p => Math.max(1, p - 1))}
                  disabled={selectorPage === 1}
                  className="px-3 py-1 border rounded disabled:opacity-50 hover:bg-gray-100"
                >
                  Previous
                </button>
                <button
                  onClick={() => setSelectorPage(p => Math.min(selectorTotalPages, p + 1))}
                  disabled={selectorPage >= selectorTotalPages}
                  className="px-3 py-1 border rounded disabled:opacity-50 hover:bg-gray-100"
                >
                  Next
                </button>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-between items-center">
              <button
                onClick={() => setShowLeadSelector(false)}
                className="btn-secondary"
              >
                Cancel
              </button>
              <div className="flex gap-3">
                <button
                  onClick={() => handleRunWithSelectedLeads(true)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 text-sm font-medium"
                >
                  Run for All Leads
                </button>
                <button
                  onClick={() => handleRunWithSelectedLeads(false)}
                  disabled={selectorSelected.size === 0}
                  className={`px-4 py-2 rounded-lg text-white text-sm font-medium disabled:opacity-50 ${
                    selectorPipeline === 'contact-enrichment'
                      ? 'bg-purple-600 hover:bg-purple-700'
                      : 'bg-orange-600 hover:bg-orange-700'
                  }`}
                >
                  Run for Selected ({selectorSelected.size})
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
