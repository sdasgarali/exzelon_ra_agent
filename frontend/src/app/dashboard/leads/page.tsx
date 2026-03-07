'use client'

import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { leadsApi, pipelinesApi, api } from '@/lib/api'

interface Lead {
  lead_id: number
  client_name: string
  job_title: string
  state: string
  posting_date: string
  job_link: string
  source: string
  lead_status: string
  contact_email: string
  salary_min: number
  salary_max: number
  contact_count: number  // Number of contacts linked to this lead
  industry: string | null
  company_size: string | null
  is_archived: boolean
  created_at: string
  updated_at: string
}

interface LeadFilterOptions {
  industries: string[]
  company_sizes: string[]
}

interface Contact {
  contact_id: number
  lead_id: number
  first_name: string
  last_name: string
  email: string
  title: string
  validation_status: string
}

const STATUS_OPTIONS = [
  { value: 'new', label: 'New', color: 'bg-slate-100 text-slate-800' },
  { value: 'enriched', label: 'Enriched', color: 'bg-purple-100 text-purple-800' },
  { value: 'validated', label: 'Validated', color: 'bg-teal-100 text-teal-800' },
  { value: 'open', label: 'Open', color: 'bg-green-100 text-green-800' },
  { value: 'hunting', label: 'Hunting', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'sent', label: 'Sent', color: 'bg-indigo-100 text-indigo-800' },
  { value: 'skipped', label: 'Skipped', color: 'bg-orange-100 text-orange-800' },
  { value: 'closed_hired', label: 'Closed-Hired', color: 'bg-blue-100 text-blue-800' },
  { value: 'closed_not_hired', label: 'Closed-Not-Hired', color: 'bg-gray-100 text-gray-800' },
  { value: 'closed_test', label: 'Closed-Test', color: 'bg-amber-100 text-amber-800' },
]

const SOURCE_OPTIONS = ['jsearch', 'apollo', 'indeed', 'linkedin', 'glassdoor', 'mock', 'import']

const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
]

type SortField = 'lead_id' | 'client_name' | 'job_title' | 'state' | 'posting_date' | 'created_at' | 'source' | 'lead_status' | 'contact_count' | 'industry' | 'company_size'
type SortOrder = 'asc' | 'desc'

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [updating, setUpdating] = useState<number | null>(null)
  const [pageSize, setPageSize] = useState(25)

  // Filters
  const [showFilters, setShowFilters] = useState(false)
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [filterState, setFilterState] = useState('')
  const [filterFromDate, setFilterFromDate] = useState('')
  const [filterToDate, setFilterToDate] = useState('')
  const [filterIndustry, setFilterIndustry] = useState('')
  const [filterCompanySize, setFilterCompanySize] = useState('')

  // Filter options from backend
  const [leadFilterOptions, setLeadFilterOptions] = useState<LeadFilterOptions>({ industries: [], company_sizes: [] })

  // Sorting
  const [sortBy, setSortBy] = useState<SortField>('created_at')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')

  // Import
  const [importing, setImporting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Contacts modal
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null)
  const [leadContacts, setLeadContacts] = useState<Contact[]>([])
  const [loadingContacts, setLoadingContacts] = useState(false)

  // Show archived toggle
  const [showArchived, setShowArchived] = useState(false)

  // Bulk status update
  const [showStatusModal, setShowStatusModal] = useState(false)
  const [bulkStatusValue, setBulkStatusValue] = useState('')
  const [updatingBulkStatus, setUpdatingBulkStatus] = useState(false)

  // Bulk delete (archive)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Bulk outreach
  const [showOutreachModal, setShowOutreachModal] = useState(false)
  const [sendingOutreach, setSendingOutreach] = useState(false)
  const [outreachDryRun, setOutreachDryRun] = useState(true)
  const [outreachResults, setOutreachResults] = useState<any>(null)
  const [showResultsModal, setShowResultsModal] = useState(false)
  const [outreachPreview, setOutreachPreview] = useState<any>(null)
  const [loadingPreview, setLoadingPreview] = useState(false)

  // Bulk contact enrichment
  const [showEnrichModal, setShowEnrichModal] = useState(false)
  const [enriching, setEnriching] = useState(false)
  const [enrichPreview, setEnrichPreview] = useState<any>(null)
  const [loadingEnrichPreview, setLoadingEnrichPreview] = useState(false)
  const [showEnrichResultsModal, setShowEnrichResultsModal] = useState(false)
  const [enrichResultMsg, setEnrichResultMsg] = useState('')
  const [enrichRunId, setEnrichRunId] = useState<number | null>(null)
  const [enrichLeadResults, setEnrichLeadResults] = useState<any[] | null>(null)
  const [enrichRunStatus, setEnrichRunStatus] = useState<string>('pending')
  const [enrichRunDuration, setEnrichRunDuration] = useState<number | null>(null)
  const [enrichAdaptersUsed, setEnrichAdaptersUsed] = useState<string[] | null>(null)

  // Cache contact counts across pages so selection works when navigating
  const [contactCountCache, setContactCountCache] = useState<Record<number, number>>({})

  // Update cache whenever leads change (user browses pages)
  useEffect(() => {
    if (leads.length > 0) {
      setContactCountCache(prev => {
        const next = { ...prev }
        leads.forEach(l => { next[l.lead_id] = l.contact_count })
        return next
      })
    }
  }, [leads])

  // Load filter options on mount
  useEffect(() => {
    leadsApi.filterOptions().then(setLeadFilterOptions).catch(() => {})
  }, [])

  // Debounce search
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    fetchLeads()
  }, [page, pageSize, debouncedSearch, filterStatus, filterSource, filterState, filterFromDate, filterToDate, filterIndustry, filterCompanySize, sortBy, sortOrder, showArchived])

  const fetchLeads = async () => {
    try {
      setLoading(true)
      setError('')
      const params: Record<string, any> = {
        page,
        page_size: pageSize,
        sort_by: sortBy,
        sort_order: sortOrder,
      }
      if (debouncedSearch) params.search = debouncedSearch
      if (filterStatus) params.status = filterStatus
      if (filterSource) params.source = filterSource
      if (filterState) params.state = filterState
      if (filterFromDate) params.from_date = filterFromDate
      if (filterToDate) params.to_date = filterToDate
      if (filterIndustry) params.industry = filterIndustry
      if (filterCompanySize) params.company_size = filterCompanySize
      if (showArchived) params.show_archived = true

      const response = await leadsApi.list(params)
      setLeads(response.items || [])
      setTotal(response.total || 0)
    } catch (err: any) {
      if (err.code !== 'ERR_CANCELED') {
        setError(err.response?.data?.detail || 'Failed to fetch leads')
      }
    } finally {
      setLoading(false)
    }
  }

  const updateLeadStatus = async (leadId: number, newStatus: string) => {
    try {
      setUpdating(leadId)
      await leadsApi.update(leadId, { lead_status: newStatus })
      setLeads(leads.map(lead =>
        lead.lead_id === leadId ? { ...lead, lead_status: newStatus } : lead
      ))
      setSuccess('Status updated successfully')
      setTimeout(() => setSuccess(''), 2000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update status')
    } finally {
      setUpdating(null)
    }
  }

  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      setSortOrder('asc')
    }
    setPage(1)
  }

  const clearFilters = () => {
    setSearch('')
    setFilterStatus('')
    setFilterSource('')
    setFilterState('')
    setFilterFromDate('')
    setFilterToDate('')
    setFilterIndustry('')
    setFilterCompanySize('')
    setShowArchived(false)
    setPage(1)
  }

  const handleExport = async () => {
    try {
      setExporting(true)
      const params = new URLSearchParams()
      if (filterStatus) params.append('status', filterStatus)
      if (filterSource) params.append('source', filterSource)
      if (filterState) params.append('state', filterState)
      if (filterFromDate) params.append('from_date', filterFromDate)
      if (filterToDate) params.append('to_date', filterToDate)
      if (debouncedSearch) params.append('search', debouncedSearch)

      const response = await api.get(`/leads/export/csv?${params.toString()}`, {
        responseType: 'blob'
      })

      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `leads_export_${new Date().toISOString().slice(0, 10)}.csv`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)

      setSuccess('Export completed successfully')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to export leads')
    } finally {
      setExporting(false)
    }
  }

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    try {
      setImporting(true)
      const formData = new FormData()
      formData.append('file', file)

      const response = await api.post('/leads/import/csv', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })

      const result = response.data
      setSuccess(`Import complete: ${result.imported} leads imported, ${result.skipped} skipped`)
      if (result.errors?.length > 0) {
        setError(`Errors: ${result.errors.join(', ')}`)
      }
      fetchLeads()
      setTimeout(() => setSuccess(''), 5000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to import leads')
    } finally {
      setImporting(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const fetchContactsForLead = async (lead: Lead) => {
    try {
      setSelectedLead(lead)
      setLoadingContacts(true)
      const response = await api.get(`/contacts?lead_id=${lead.lead_id}`)
      setLeadContacts(response.data.items || [])
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch contacts')
    } finally {
      setLoadingContacts(false)
    }
  }

  const closeContactsModal = () => {
    setSelectedLead(null)
    setLeadContacts([])
  }

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === leads.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(leads.map(l => l.lead_id)))
    }
  }

  const handleBulkDelete = async () => {
    try {
      setDeleting(true)
      await api.delete('/leads/bulk', { data: { lead_ids: Array.from(selectedIds) } })
      setSuccess(`Successfully deleted ${selectedIds.size} lead(s) and their linked contacts`)
      setSelectedIds(new Set())
      setShowDeleteModal(false)
      fetchLeads()
      setTimeout(() => setSuccess(''), 4000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete leads')
    } finally {
      setDeleting(false)
    }
  }



  const handleBulkUnarchive = async () => {
    try {
      const result = await leadsApi.bulkUnarchive(Array.from(selectedIds))
      setSuccess(result.message || 'Leads restored successfully')
      setSelectedIds(new Set())
      fetchLeads()
      setTimeout(() => setSuccess(''), 4000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to restore leads')
      setTimeout(() => setError(''), 4000)
    }
  }

  const handleBulkStatusUpdate = async () => {
    if (!bulkStatusValue) return
    try {
      setUpdatingBulkStatus(true)
      const result = await leadsApi.bulkUpdateStatus(Array.from(selectedIds), bulkStatusValue)
      setSuccess(result.message || 'Status updated successfully')
      setShowStatusModal(false)
      setBulkStatusValue('')
      setSelectedIds(new Set())
      fetchLeads()
      setTimeout(() => setSuccess(''), 4000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update status')
    } finally {
      setUpdatingBulkStatus(false)
    }
  }

  const handleBulkOutreach = async () => {
    try {
      setSendingOutreach(true)
      const ids = Array.from(selectedIds).filter(id => (contactCountCache[id] || 0) > 0)
      if (ids.length === 0) {
        setError('None of the selected leads have contacts. Run Contact Enrichment first.')
        setShowOutreachModal(false)
        setSendingOutreach(false)
        return
      }
      let data: any

      if (ids.length === 1) {
        const result = await leadsApi.runOutreach(ids[0], outreachDryRun)
        data = {
          total_leads: 1,
          results: [{
            lead_id: ids[0],
            sent: result.sent || 0,
            skipped: result.skipped || 0,
            errors: result.errors || 0,
            error: result.error,
            message: result.message
          }],
          summary: {
            total_sent: result.sent || 0,
            total_skipped: result.skipped || 0,
            total_errors: result.errors || 0
          },
          dry_run: outreachDryRun
        }
      } else {
        data = await leadsApi.bulkOutreach(ids, outreachDryRun)
      }

      setOutreachResults(data)
      setShowOutreachModal(false)
      setOutreachPreview(null)
      setShowResultsModal(true)

      if (!outreachDryRun) {
        fetchLeads()
        setSelectedIds(new Set())
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to run outreach')
    } finally {
      setSendingOutreach(false)
    }
  }

  const handleOpenEnrichPreview = async () => {
    setShowEnrichModal(true)
    setLoadingEnrichPreview(true)
    setEnrichPreview(null)
    try {
      const ids = Array.from(selectedIds)
      const preview = await leadsApi.bulkEnrichPreview(ids)
      setEnrichPreview(preview)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load enrichment preview')
      setShowEnrichModal(false)
    } finally {
      setLoadingEnrichPreview(false)
    }
  }

  const handleBulkEnrich = async () => {
    try {
      setEnriching(true)
      const ids = Array.from(selectedIds)
      const data = await leadsApi.bulkEnrich(ids)
      setShowEnrichModal(false)
      setEnrichPreview(null)
      setEnrichResultMsg(data.message || `Enrichment started for ${data.lead_count} lead(s)`)
      setEnrichRunId(data.run_id || null)
      setEnrichLeadResults(null)
      setEnrichRunStatus('running')
      setShowEnrichResultsModal(true)

      // Poll for results if we have a run_id
      if (data.run_id) {
        const pollInterval = setInterval(async () => {
          try {
            const runDetail = await pipelinesApi.getRunDetail(data.run_id)
            if (runDetail.status === 'completed' || runDetail.status === 'failed') {
              clearInterval(pollInterval)
              setEnrichRunStatus(runDetail.status)
              setEnrichLeadResults(runDetail.lead_results || [])
              setEnrichRunDuration(runDetail.duration_seconds || null)
              setEnrichAdaptersUsed(runDetail.adapters_used || null)
              fetchLeads()
              setSelectedIds(new Set())
            }
          } catch {
            clearInterval(pollInterval)
            setEnrichRunStatus('failed')
          }
        }, 3000)
        // Safety timeout - stop polling after 5 minutes
        setTimeout(() => clearInterval(pollInterval), 300000)
      } else {
        // Fallback: no run_id (old backend), show completion after delay
        setEnrichRunStatus('completed')
        setTimeout(() => {
          fetchLeads()
          setSelectedIds(new Set())
        }, 3000)
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start enrichment')
    } finally {
      setEnriching(false)
    }
  }

  const getStatusBadge = (status: string) => {
    const statusOption = STATUS_OPTIONS.find(s => s.value === status)
    return statusOption?.color || 'bg-gray-100 text-gray-800'
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-'
    try {
      const date = new Date(dateString)
      return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    } catch {
      return dateString
    }
  }

  const truncateUrl = (url: string | null, maxLength: number = 30) => {
    if (!url) return '-'
    if (url.length <= maxLength) return url
    return url.substring(0, maxLength) + '...'
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortBy !== field) return <span className="text-gray-300 ml-1">&#8645;</span>
    return sortOrder === 'asc' ? <span className="ml-1">&#8593;</span> : <span className="ml-1">&#8595;</span>
  }

  const activeFiltersCount = [filterStatus, filterSource, filterState, filterFromDate, filterToDate, filterIndustry, filterCompanySize, search].filter(Boolean).length + (showArchived ? 1 : 0)

  return (
    <div>
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Leads</h1>
          <p className="text-gray-500 text-sm mt-1">
            {total} job postings sourced from LinkedIn, Indeed, Glassdoor, and more
          </p>
        </div>
        <div className="flex gap-2">
          {selectedIds.size > 0 && (
            <>
              <button
                onClick={handleOpenEnrichPreview}
                className="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 flex items-center gap-2 text-sm font-medium"
              >
                Contact Enrich ({selectedIds.size})
              </button>
              <button
                onClick={async () => {
                  setOutreachDryRun(true)
                  setShowOutreachModal(true)
                  setLoadingPreview(true)
                  try {
                    const eligibleIds = Array.from(selectedIds).filter(id => (contactCountCache[id] || 0) > 0)
                    if (eligibleIds.length > 0) {
                      const preview = await leadsApi.previewOutreach(eligibleIds)
                      setOutreachPreview(preview)
                    }
                  } catch (err: any) {
                    setError(err.response?.data?.detail || 'Failed to load preview')
                  } finally {
                    setLoadingPreview(false)
                  }
                }}
                disabled={Array.from(selectedIds).filter(id => (contactCountCache[id] || 0) > 0).length === 0}
                className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 flex items-center gap-2 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                title={Array.from(selectedIds).filter(id => (contactCountCache[id] || 0) > 0).length === 0 ? 'No selected leads have contacts' : ''}
              >
                Send Outreach ({Array.from(selectedIds).filter(id => (contactCountCache[id] || 0) > 0).length})
              </button>
              <button
                onClick={() => setShowStatusModal(true)}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 flex items-center gap-2 text-sm font-medium"
              >
                Update Status ({selectedIds.size})
              </button>
              {showArchived ? (
                <button
                  onClick={handleBulkUnarchive}
                  className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 flex items-center gap-2 text-sm font-medium"
                >
                  Restore Selected ({selectedIds.size})
                </button>
              ) : (
                <button
                  onClick={() => setShowDeleteModal(true)}
                  className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 flex items-center gap-2 text-sm font-medium"
                >
                  Archive Selected ({selectedIds.size})
                </button>
              )}
            </>
          )}
          {/* Import Button */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleImport}
            accept=".csv"
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className="btn-secondary flex items-center gap-2"
          >
            {importing ? (
              <>
                <span className="animate-spin">&#8635;</span>
                Importing...
              </>
            ) : (
              <>
                <span>&#8593;</span>
                Import CSV
              </>
            )}
          </button>

          {/* Export Button */}
          <button
            onClick={handleExport}
            disabled={exporting}
            className="btn-secondary flex items-center gap-2"
          >
            {exporting ? (
              <>
                <span className="animate-spin">&#8635;</span>
                Exporting...
              </>
            ) : (
              <>
                <span>&#8595;</span>
                Export CSV
              </>
            )}
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg mb-4 flex justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="font-bold">x</button>
        </div>
      )}
      {success && (
        <div className="bg-green-50 text-green-600 px-4 py-2 rounded-lg mb-4">
          {success}
        </div>
      )}

      {/* Search and Filter Bar */}
      <div className="card p-4 mb-4">
        <div className="flex flex-wrap gap-4 items-center">
          {/* Search */}
          <div className="flex-1 min-w-64">
            <input
              type="text"
              placeholder="Search by ID (#42), company, job title, or state..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="input w-full"
            />
          </div>

          {/* Quick Filters */}
          <select
            value={filterStatus}
            onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
            className="input w-40"
          >
            <option value="">All Statuses</option>
            {STATUS_OPTIONS.map(s => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>

          <select
            value={filterSource}
            onChange={(e) => { setFilterSource(e.target.value); setPage(1); }}
            className="input w-36"
          >
            <option value="">All Sources</option>
            {SOURCE_OPTIONS.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          {/* Show Archived Toggle */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => { setShowArchived(e.target.checked); setPage(1); }}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm font-medium text-gray-700 whitespace-nowrap">Show Archived</span>
          </label>

          {/* Toggle More Filters */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`btn-secondary text-sm ${activeFiltersCount > 0 ? 'bg-blue-50 border-blue-300' : ''}`}
          >
            Filters {activeFiltersCount > 0 && `(${activeFiltersCount})`}
          </button>

          {activeFiltersCount > 0 && (
            <button onClick={clearFilters} className="text-sm text-gray-500 hover:text-gray-700">
              Clear all
            </button>
          )}
        </div>

        {/* Expanded Filters */}
        {showFilters && (
          <div className="mt-4 pt-4 border-t">
            <div className="grid grid-cols-3 md:grid-cols-6 gap-4">
            <div>
              <label className="label text-sm">State</label>
              <select
                value={filterState}
                onChange={(e) => { setFilterState(e.target.value); setPage(1); }}
                className="input w-full"
              >
                <option value="">All States</option>
                {US_STATES.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label text-sm">Industry</label>
              <select
                value={filterIndustry}
                onChange={(e) => { setFilterIndustry(e.target.value); setPage(1); }}
                className="input w-full"
              >
                <option value="">All Industries</option>
                {leadFilterOptions.industries.map(i => (
                  <option key={i} value={i}>{i}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label text-sm">Company Size</label>
              <select
                value={filterCompanySize}
                onChange={(e) => { setFilterCompanySize(e.target.value); setPage(1); }}
                className="input w-full"
              >
                <option value="">All Sizes</option>
                {leadFilterOptions.company_sizes.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label text-sm">Posted From</label>
              <input
                type="date"
                value={filterFromDate}
                onChange={(e) => { setFilterFromDate(e.target.value); setPage(1); }}
                className="input w-full"
              />
            </div>
            <div>
              <label className="label text-sm">Posted To</label>
              <input
                type="date"
                value={filterToDate}
                onChange={(e) => { setFilterToDate(e.target.value); setPage(1); }}
                className="input w-full"
              />
            </div>
            <div>
              <label className="label text-sm">Page Size</label>
              <select
                value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                className="input w-full"
              >
                <option value="10">10 per page</option>
                <option value="25">25 per page</option>
                <option value="50">50 per page</option>
                <option value="100">100 per page</option>
              </select>
            </div>
            </div>
          </div>
        )}
      </div>

      {/* Selection Info Bar */}
      {selectedIds.size > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 mb-4 flex items-center justify-between">
          <span className="text-sm text-blue-800 font-medium">{selectedIds.size} lead(s) selected</span>
          <button onClick={() => setSelectedIds(new Set())} className="text-sm text-blue-600 hover:text-blue-800">Clear selection</button>
        </div>
      )}

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={leads.length > 0 && selectedIds.size === leads.length}
                    onChange={toggleSelectAll}
                    className="w-4 h-4"
                  />
                </th>
                <th
                  onClick={() => handleSort('lead_id')}
                  className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  ID <SortIcon field="lead_id" />
                </th>
                <th
                  onClick={() => handleSort('client_name')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Company / Job Title <SortIcon field="client_name" />
                </th>
                <th
                  onClick={() => handleSort('state')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  State <SortIcon field="state" />
                </th>
                <th
                  onClick={() => handleSort('posting_date')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Posted <SortIcon field="posting_date" />
                </th>
                <th
                  onClick={() => handleSort('source')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Source <SortIcon field="source" />
                </th>
                <th
                  onClick={() => handleSort('industry')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Industry <SortIcon field="industry" />
                </th>
                <th
                  onClick={() => handleSort('company_size')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Size <SortIcon field="company_size" />
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Link
                </th>
                <th
                  onClick={() => handleSort('contact_count')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Contacts <SortIcon field="contact_count" />
                </th>
                <th
                  onClick={() => handleSort('lead_status')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Status <SortIcon field="lead_status" />
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={11} className="px-4 py-8 text-center text-gray-500">
                    Loading leads...
                  </td>
                </tr>
              ) : leads.length === 0 ? (
                <tr>
                  <td colSpan={11} className="px-4 py-8 text-center text-gray-500">
                    No leads found. {activeFiltersCount > 0 ? 'Try adjusting your filters.' : 'Run the Lead Sourcing pipeline to fetch jobs.'}
                  </td>
                </tr>
              ) : (
                leads.map((lead) => (
                  <tr key={lead.lead_id} className={`${lead.is_archived ? "opacity-60 bg-gray-50" : ""} ${selectedIds.has(lead.lead_id) ? "bg-blue-50 hover:bg-blue-100" : "hover:bg-gray-50"}`}>
                    <td className="px-3 py-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(lead.lead_id)}
                        onChange={() => toggleSelect(lead.lead_id)}
                        className="w-4 h-4"
                      />
                    </td>
                    <td className="px-3 py-3">
                      <Link href={`/dashboard/leads/${lead.lead_id}`} className="text-xs px-2 py-1 rounded bg-blue-50 text-blue-700 font-mono hover:bg-blue-100">
                        #{lead.lead_id}
                      </Link>
                      {lead.is_archived && <span className="ml-1 text-xs px-1.5 py-0.5 rounded bg-gray-200 text-gray-600 font-medium">Archived</span>}
                    </td>
                    <td className="px-4 py-3">
                      <Link href={`/dashboard/leads/${lead.lead_id}`} className="text-sm font-medium text-blue-700 hover:text-blue-900 hover:underline">
                        {lead.client_name}
                      </Link>
                      <div className="text-sm text-gray-500">{lead.job_title}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {lead.state || '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {formatDate(lead.posting_date)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-1 rounded bg-gray-100 text-gray-700">
                        {lead.source}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {lead.industry || '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {lead.company_size || '-'}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {lead.job_link ? (
                        <a
                          href={lead.job_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800 hover:underline"
                          title={lead.job_link}
                        >
                          {truncateUrl(lead.job_link, 25)}
                        </a>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => fetchContactsForLead(lead)}
                        className={`text-xs px-2 py-1 rounded-full ${
                          lead.contact_count > 0
                            ? 'bg-purple-100 text-purple-800 hover:bg-purple-200'
                            : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        {lead.contact_count || 0} contacts
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={lead.lead_status}
                        onChange={(e) => updateLeadStatus(lead.lead_id, e.target.value)}
                        disabled={updating === lead.lead_id}
                        className={`text-xs px-2 py-1 rounded-full border-0 cursor-pointer ${getStatusBadge(lead.lead_status)} ${updating === lead.lead_id ? 'opacity-50' : ''}`}
                      >
                        {STATUS_OPTIONS.map((status) => (
                          <option key={status.value} value={status.value}>
                            {status.label}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="bg-gray-50 px-6 py-3 flex items-center justify-between border-t">
          <div className="text-sm text-gray-500">
            Showing {leads.length > 0 ? ((page - 1) * pageSize) + 1 : 0} to {Math.min(page * pageSize, total)} of {total} results
          </div>
          <div className="flex gap-2 items-center">
            <button
              onClick={() => setPage(1)}
              disabled={page === 1}
              className="px-2 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100"
              title="First page"
            >
              &laquo;
            </button>
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100"
            >
              Previous
            </button>
            <span className="px-3 py-1 text-sm text-gray-600">
              Page {page} of {Math.ceil(total / pageSize) || 1}
            </span>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={page * pageSize >= total}
              className="px-3 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100"
            >
              Next
            </button>
            <button
              onClick={() => setPage(Math.ceil(total / pageSize))}
              disabled={page * pageSize >= total}
              className="px-2 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100"
              title="Last page"
            >
              &raquo;
            </button>
          </div>
        </div>
      </div>

      {/* Import Help */}
      <div className="mt-4 p-4 bg-gray-50 rounded-lg">
        <h4 className="text-sm font-medium text-gray-700 mb-2">Import CSV Format:</h4>
        <p className="text-xs text-gray-500 mb-2">
          Required columns: <span className="font-mono bg-gray-200 px-1">Company Name</span>, <span className="font-mono bg-gray-200 px-1">Job Title</span>
        </p>
        <p className="text-xs text-gray-500">
          Optional: <span className="font-mono bg-gray-200 px-1">State</span>, <span className="font-mono bg-gray-200 px-1">Posting Date</span> (YYYY-MM-DD), <span className="font-mono bg-gray-200 px-1">Job Link</span>, <span className="font-mono bg-gray-200 px-1">Source</span>, <span className="font-mono bg-gray-200 px-1">Status</span> (open/hunting/closed_hired/closed_not_hired), <span className="font-mono bg-gray-200 px-1">Salary Min</span>, <span className="font-mono bg-gray-200 px-1">Salary Max</span>
        </p>
      </div>

      {/* Bulk Status Update Modal */}
      {showStatusModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-semibold text-blue-600">Update Status for {selectedIds.size} Lead(s)</h3>
            </div>
            <div className="px-6 py-4">
              <p className="text-gray-700 mb-3">Select the new status for all selected leads:</p>
              <select
                value={bulkStatusValue}
                onChange={(e) => setBulkStatusValue(e.target.value)}
                className="input w-full"
              >
                <option value="">-- Select Status --</option>
                {STATUS_OPTIONS.map(s => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-end gap-3">
              <button
                onClick={() => { setShowStatusModal(false); setBulkStatusValue(''); }}
                disabled={updatingBulkStatus}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleBulkStatusUpdate}
                disabled={updatingBulkStatus || !bulkStatusValue}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {updatingBulkStatus ? 'Updating...' : 'Update Status'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Archive Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-semibold text-amber-600">Confirm Archive</h3>
            </div>
            <div className="px-6 py-4">
              <p className="text-gray-700 mb-3">
                Are you sure you want to archive <strong>{selectedIds.size}</strong> lead(s)?
              </p>
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-700">
                <p className="font-medium mb-1">Archived leads will be hidden by default but can be restored.</p>
                <ul className="list-disc ml-4 space-y-1">
                  <li>Contacts linked to this lead remain active for other leads</li>
                  <li>Use the "Show Archived" toggle to view archived leads</li>
                  <li>Archived leads are excluded from pipelines</li>
                </ul>
              </div>
            </div>
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-end gap-3">
              <button
                onClick={() => setShowDeleteModal(false)}
                disabled={deleting}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleBulkDelete}
                disabled={deleting}
                className="bg-amber-600 text-white px-4 py-2 rounded-lg hover:bg-amber-700 disabled:opacity-50"
              >
                {deleting ? 'Archiving...' : 'Archive'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Outreach Confirmation Modal */}
      {showOutreachModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[85vh] flex flex-col">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-semibold text-indigo-700">Confirm Outreach</h3>
              <p className="text-sm text-gray-500 mt-1">
                {outreachPreview
                  ? (() => {
                      const totalEligible = outreachPreview.assignments?.reduce((sum: number, a: any) => sum + (a.eligible_count || 0), 0) || 0
                      return totalEligible > 0
                        ? totalEligible + ' eligible contact(s) across ' + outreachPreview.assignments?.length + ' lead(s)'
                        : outreachPreview.assignments?.length + ' lead(s) - no eligible contacts'
                    })()
                  : 'Loading preview...'}
              </p>
            </div>
            <div className="px-6 py-4 overflow-y-auto flex-1">
              {loadingPreview ? (
                <div className="text-center py-8 text-gray-500">Loading outreach preview...</div>
              ) : outreachPreview ? (
                <>
                  {/* Available Senders Banner */}
                  <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3 mb-4">
                    <p className="text-xs font-medium text-indigo-700 mb-1">
                      Cold Ready Senders ({outreachPreview.available_mailboxes?.length || 0})
                    </p>
                    {outreachPreview.available_mailboxes?.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {outreachPreview.available_mailboxes.map((mb: any) => (
                          <span key={mb.mailbox_id} className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800">
                            {mb.display_name || mb.email} ({mb.sent_today}/{mb.daily_limit})
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-red-600">No Cold Ready mailboxes available. Set mailbox warmup status to Cold Ready first.</p>
                    )}
                  </div>

                  {/* Lead-by-Lead Breakdown */}
                  <div className="space-y-3 mb-4">
                    {outreachPreview.assignments?.map((a: any) => (
                      <div key={a.lead_id} className="border rounded-lg overflow-hidden">
                        <div className="px-3 py-2 bg-gray-50 flex justify-between items-center">
                          <div>
                            <span className="text-sm font-medium text-gray-800">
                              #{a.lead_id} {a.client_name}
                            </span>
                            <span className="text-xs text-gray-500 ml-2">{a.job_title}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            {a.sender ? (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700" title="Assigned sender">
                                {a.sender.display_name || a.sender.email}
                              </span>
                            ) : (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                                {a.eligible_count === 0 ? 'All skipped' : 'No sender'}
                              </span>
                            )}
                          </div>
                        </div>
                        {a.error ? (
                          <div className="px-3 py-2 text-xs text-red-600">{a.error}</div>
                        ) : a.contacts?.length > 0 ? (
                          <div className="divide-y">
                            {a.contacts.map((c: any) => (
                              <div key={c.contact_id} className="px-3 py-1.5 flex justify-between items-center text-xs">
                                <div>
                                  <span className="text-gray-800">{c.name}</span>
                                  <span className="text-gray-400 ml-2">{c.email}</span>
                                </div>
                                {c.eligible ? (
                                  <span className="px-2 py-0.5 rounded-full bg-green-100 text-green-700">Eligible</span>
                                ) : (
                                  <span className="px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700" title={c.skip_reason || ''}>
                                    {c.skip_reason && c.skip_reason.includes('Cooldown') ? 'Cooldown' : c.skip_reason && c.skip_reason.includes('not validated') ? 'Not Validated' : c.skip_reason || 'Skipped'}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="px-3 py-2 text-xs text-gray-500">No contacts linked</div>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Dry Run Toggle */}
                  <label className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer ${!outreachDryRun ? 'bg-yellow-50 border-yellow-300' : 'bg-gray-50 border-gray-200'}`}>
                    <input
                      type="checkbox"
                      checked={outreachDryRun}
                      onChange={(e) => setOutreachDryRun(e.target.checked)}
                      className="w-4 h-4"
                    />
                    <div>
                      <span className="text-sm font-medium text-gray-700">Dry Run Mode</span>
                      <p className="text-xs text-gray-500">
                        {outreachDryRun ? 'Simulate only - no emails will be sent' : 'LIVE MODE - Emails will actually be sent!'}
                      </p>
                    </div>
                  </label>
                </>
              ) : (
                <div className="text-center py-8 text-red-500">Failed to load preview</div>
              )}
            </div>
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-end gap-3">
              <button
                onClick={() => { setShowOutreachModal(false); setOutreachPreview(null) }}
                disabled={sendingOutreach}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleBulkOutreach}
                disabled={sendingOutreach || loadingPreview || !outreachPreview?.available_mailboxes?.length}
                className={`px-4 py-2 rounded-lg text-white disabled:opacity-50 ${outreachDryRun ? 'bg-indigo-600 hover:bg-indigo-700' : 'bg-orange-600 hover:bg-orange-700'}`}
              >
                {sendingOutreach ? 'Processing...' : outreachDryRun ? 'Run Dry Test' : 'Send Emails'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Outreach Results Modal */}
      {showResultsModal && outreachResults && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
            <div className="px-6 py-4 border-b flex justify-between items-center">
              <div className="flex items-center gap-3">
                <h3 className="text-lg font-semibold text-gray-900">Outreach Results</h3>
                {outreachResults.dry_run && (
                  <span className="text-xs px-2 py-1 rounded-full bg-yellow-100 text-yellow-800 font-medium">Dry Run</span>
                )}
              </div>
              <button
                onClick={() => { setShowResultsModal(false); setOutreachResults(null) }}
                className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
              >
                &times;
              </button>
            </div>
            <div className="px-6 py-4 overflow-y-auto flex-1">
              {/* Summary Cards */}
              <div className="grid grid-cols-3 gap-3 mb-4">
                <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-center">
                  <div className="text-2xl font-bold text-green-700">{outreachResults.summary?.total_sent || 0}</div>
                  <div className="text-xs text-green-600">Sent</div>
                </div>
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-center">
                  <div className="text-2xl font-bold text-yellow-700">{outreachResults.summary?.total_skipped || 0}</div>
                  <div className="text-xs text-yellow-600">Skipped</div>
                </div>
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-center">
                  <div className="text-2xl font-bold text-red-700">{outreachResults.summary?.total_errors || 0}</div>
                  <div className="text-xs text-red-600">Errors</div>
                </div>
              </div>
              {/* Per-lead breakdown */}
              <h4 className="text-sm font-medium text-gray-700 mb-2">Per-Lead Breakdown ({outreachResults.total_leads} leads)</h4>
              <div className="space-y-2">
                {outreachResults.results?.map((r: any, i: number) => (
                  <div key={i} className="p-3 border rounded-lg bg-gray-50">
                    <div className="flex justify-between items-center">
                      <span className="text-sm font-medium text-gray-800">Lead #{r.lead_id}</span>
                      <div className="flex gap-2 text-xs">
                        {r.sent > 0 && <span className="px-2 py-0.5 rounded bg-green-100 text-green-700">{r.sent} sent</span>}
                        {r.skipped > 0 && <span className="px-2 py-0.5 rounded bg-yellow-100 text-yellow-700">{r.skipped} skipped</span>}
                        {r.errors > 0 && <span className="px-2 py-0.5 rounded bg-red-100 text-red-700">{r.errors} errors</span>}
                        {r.sent === 0 && r.skipped === 0 && r.errors === 0 && !r.error && (
                          <span className="px-2 py-0.5 rounded bg-gray-100 text-gray-600">No contacts</span>
                        )}
                      </div>
                    </div>
                    {r.error && <p className="text-xs text-red-600 mt-1">{r.error}</p>}
                    {r.message && <p className="text-xs text-gray-500 mt-1">{r.message}</p>}
                  </div>
                ))}
              </div>
            </div>
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-end">
              <button
                onClick={() => { setShowResultsModal(false); setOutreachResults(null) }}
                className="btn-secondary"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Enrichment Preview Modal */}
      {showEnrichModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[85vh] flex flex-col">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-semibold text-purple-700">Contact Enrichment Preview</h3>
              <p className="text-sm text-gray-500 mt-1">
                {enrichPreview
                  ? `${enrichPreview.summary?.will_enrich || 0} lead(s) will be enriched, ${enrichPreview.summary?.will_skip || 0} skipped`
                  : 'Loading preview...'}
              </p>
            </div>
            <div className="px-6 py-4 overflow-y-auto flex-1">
              {loadingEnrichPreview ? (
                <div className="text-center py-8 text-gray-500">Loading enrichment preview...</div>
              ) : enrichPreview ? (
                <>
                  {/* Summary Cards */}
                  <div className="grid grid-cols-4 gap-3 mb-4">
                    <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 text-center">
                      <div className="text-2xl font-bold text-purple-700">{enrichPreview.summary?.will_enrich || 0}</div>
                      <div className="text-xs text-purple-600">Will Enrich</div>
                    </div>
                    <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-center">
                      <div className="text-2xl font-bold text-green-700">{enrichPreview.summary?.contacts_from_cache || 0}</div>
                      <div className="text-xs text-green-600">From Cache</div>
                    </div>
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-center">
                      <div className="text-2xl font-bold text-yellow-700">{enrichPreview.summary?.leads_needing_api || 0}</div>
                      <div className="text-xs text-yellow-600">Need API Calls</div>
                    </div>
                    <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-center">
                      <div className="text-2xl font-bold text-indigo-700">{enrichPreview.summary?.auto_enrich_siblings || 0}</div>
                      <div className="text-xs text-indigo-600">Auto-Enrich Siblings</div>
                    </div>
                  </div>

                  {/* Per-Lead Breakdown */}
                  <div className="space-y-2 mb-4">
                    {enrichPreview.previews?.map((p: any) => (
                      <div key={p.lead_id} className="p-3 border rounded-lg bg-gray-50 flex justify-between items-center">
                        <div>
                          <span className="text-sm font-medium text-gray-800">
                            #{p.lead_id} {p.client_name}
                          </span>
                          <span className="text-xs text-gray-500 ml-2">{p.job_title}</span>
                          <div className="flex gap-2 mt-1">
                            <span className="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-600">
                              {p.current_contacts} existing
                            </span>
                            {p.reusable_count > 0 && (
                              <span className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700">
                                +{p.reusable_count} from cache
                              </span>
                            )}
                            {p.api_needed > 0 && (
                              <span className="text-xs px-2 py-0.5 rounded bg-yellow-100 text-yellow-700">
                                {p.api_needed} via API
                              </span>
                            )}
                          </div>
                        </div>
                        <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                          p.status === 'enrich' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-500'
                        }`}>
                          {p.status === 'enrich' ? 'Enrich' : 'Skip'}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* Auto-Enrich Siblings */}
                  {enrichPreview.auto_enrich_previews?.length > 0 && (
                    <div className="mb-4">
                      <h4 className="text-sm font-medium text-indigo-700 mb-2">
                        Auto-Enrich Siblings ({enrichPreview.auto_enrich_previews.length} additional leads)
                      </h4>
                      <p className="text-xs text-gray-500 mb-2">
                        These leads are at the same company and will be auto-enriched from cache — no extra API calls.
                      </p>
                      <div className="space-y-2">
                        {enrichPreview.auto_enrich_previews.map((s: any) => (
                          <div key={s.lead_id} className="p-3 border border-indigo-200 rounded-lg bg-indigo-50 flex justify-between items-center">
                            <div>
                              <span className="text-sm font-medium text-gray-800">
                                #{s.lead_id} {s.client_name}
                              </span>
                              <span className="text-xs text-gray-500 ml-2">{s.job_title}</span>
                              <div className="flex gap-2 mt-1">
                                <span className="text-xs px-2 py-0.5 rounded bg-indigo-100 text-indigo-700">
                                  +{s.reusable_count} from cache
                                </span>
                              </div>
                            </div>
                            <span className="text-xs px-2 py-1 rounded-full font-medium bg-indigo-100 text-indigo-700">
                              Auto
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-8 text-red-500">Failed to load preview</div>
              )}
            </div>
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-end gap-3">
              <button
                onClick={() => { setShowEnrichModal(false); setEnrichPreview(null) }}
                disabled={enriching}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleBulkEnrich}
                disabled={enriching || loadingEnrichPreview || !enrichPreview?.summary?.will_enrich}
                className="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 disabled:opacity-50"
              >
                {enriching ? 'Processing...' : `Enrich ${enrichPreview?.summary?.will_enrich || 0} Lead(s)`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Enrichment Results Modal */}
      {showEnrichResultsModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[85vh] flex flex-col">
            <div className="px-6 py-4 border-b flex justify-between items-center">
              <div>
                <h3 className="text-lg font-semibold text-purple-700">
                  {enrichRunStatus === 'running' ? 'Enrichment Running...' : enrichRunStatus === 'completed' ? 'Enrichment Complete' : enrichRunStatus === 'failed' ? 'Enrichment Failed' : 'Enrichment Started'}
                </h3>
                <p className="text-sm text-gray-500 mt-1">{enrichResultMsg}</p>
                {(enrichRunDuration != null || enrichAdaptersUsed) && (
                  <div className="flex gap-3 mt-2">
                    {enrichRunDuration != null && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                        {enrichRunDuration < 60
                          ? `${enrichRunDuration}s`
                          : `${Math.floor(enrichRunDuration / 60)}m ${Math.round(enrichRunDuration % 60)}s`}
                      </span>
                    )}
                    {enrichAdaptersUsed && enrichAdaptersUsed.map((a: string) => (
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
                )}
              </div>
              <button
                onClick={() => { setShowEnrichResultsModal(false); setEnrichLeadResults(null); setEnrichRunId(null) }}
                className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
              >
                &times;
              </button>
            </div>
            <div className="px-6 py-4 overflow-y-auto flex-1">
              {/* Spinner while running */}
              {enrichRunStatus === 'running' && !enrichLeadResults && (
                <div className="text-center py-8">
                  <div className="w-12 h-12 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin mx-auto mb-4"></div>
                  <p className="text-gray-600">Processing leads... Results will appear here automatically.</p>
                </div>
              )}

              {/* Summary Cards */}
              {enrichLeadResults && enrichLeadResults.length > 0 && (
                <>
                  <div className="grid grid-cols-5 gap-3 mb-4">
                    <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-center">
                      <div className="text-2xl font-bold text-green-700">
                        {enrichLeadResults.filter((r: any) => r.status === 'enriched').length}
                      </div>
                      <div className="text-xs text-green-600">Enriched</div>
                    </div>
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-center">
                      <div className="text-2xl font-bold text-blue-700">
                        {enrichLeadResults.filter((r: any) => r.status === 'cache_only').length}
                      </div>
                      <div className="text-xs text-blue-600">From Cache</div>
                    </div>
                    <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-center">
                      <div className="text-2xl font-bold text-indigo-700">
                        {enrichLeadResults.filter((r: any) => r.status === 'auto_enriched').length}
                      </div>
                      <div className="text-xs text-indigo-600">Auto-Enriched</div>
                    </div>
                    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-center">
                      <div className="text-2xl font-bold text-gray-700">
                        {enrichLeadResults.filter((r: any) => r.status === 'skipped').length}
                      </div>
                      <div className="text-xs text-gray-600">Skipped</div>
                    </div>
                    <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-center">
                      <div className="text-2xl font-bold text-red-700">
                        {enrichLeadResults.filter((r: any) => r.status === 'error').length}
                      </div>
                      <div className="text-xs text-red-600">Errors</div>
                    </div>
                  </div>

                  {/* Per-Lead Rows */}
                  <h4 className="text-sm font-medium text-gray-700 mb-2">Per-Lead Breakdown ({enrichLeadResults.length} leads)</h4>
                  <div className="space-y-2">
                    {enrichLeadResults.map((r: any, i: number) => (
                      <div key={i} className="p-3 border rounded-lg bg-gray-50 flex justify-between items-center">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono text-gray-500">#{r.lead_id}</span>
                            <span className="text-sm font-medium text-gray-800 truncate">{r.client_name}</span>
                          </div>
                          <div className="flex gap-2 mt-1 flex-wrap">
                            {r.contacts_found > 0 && (
                              <span className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700">+{r.contacts_found} found</span>
                            )}
                            {r.contacts_reused > 0 && (
                              <span className="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700">{r.contacts_reused} reused</span>
                            )}
                            {r.adapter_used && (
                              <span className="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-600">via {r.adapter_used}</span>
                            )}
                          </div>
                          {r.reason && (
                            <p className="text-xs text-gray-500 mt-1">{r.reason}</p>
                          )}
                        </div>
                        <span className={`text-xs px-2 py-1 rounded-full font-medium whitespace-nowrap ml-2 ${
                          r.status === 'enriched' ? 'bg-green-100 text-green-700' :
                          r.status === 'cache_only' ? 'bg-blue-100 text-blue-700' :
                          r.status === 'auto_enriched' ? 'bg-indigo-100 text-indigo-700' :
                          r.status === 'skipped' ? 'bg-gray-100 text-gray-600' :
                          r.status === 'error' ? 'bg-red-100 text-red-700' :
                          'bg-gray-100 text-gray-600'
                        }`}>
                          {r.status === 'enriched' ? 'Enriched' :
                           r.status === 'cache_only' ? 'Cached' :
                           r.status === 'auto_enriched' ? 'Auto' :
                           r.status === 'skipped' ? 'Skipped' :
                           r.status === 'error' ? 'Error' : r.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {/* No results yet and not running */}
              {!enrichLeadResults && enrichRunStatus !== 'running' && (
                <div className="text-center py-8">
                  <div className="w-16 h-16 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <span className="text-2xl text-purple-600">&#10003;</span>
                  </div>
                  <p className="text-gray-700 mb-2">{enrichResultMsg}</p>
                  <p className="text-sm text-gray-500">Running in background. Leads will update automatically.</p>
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-end">
              <button
                onClick={() => { setShowEnrichResultsModal(false); setEnrichLeadResults(null); setEnrichRunId(null); setEnrichRunDuration(null); setEnrichAdaptersUsed(null) }}
                className="btn-secondary"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Contacts Modal */}
      {selectedLead && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b flex justify-between items-center">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  Contacts for {selectedLead.client_name}
                </h3>
                <p className="text-sm text-gray-500">{selectedLead.job_title}</p>
              </div>
              <button
                onClick={closeContactsModal}
                className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
              >
                &times;
              </button>
            </div>

            {/* Modal Body */}
            <div className="px-6 py-4 overflow-y-auto flex-1">
              {loadingContacts ? (
                <div className="text-center py-8 text-gray-500">
                  Loading contacts...
                </div>
              ) : leadContacts.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <p className="mb-2">No contacts found for this lead.</p>
                  <p className="text-sm">Run the Contact Enrichment pipeline to discover contacts.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {leadContacts.map((contact) => (
                    <div
                      key={contact.contact_id}
                      className="p-4 border rounded-lg hover:bg-gray-50"
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="font-medium text-gray-900">
                            {contact.first_name} {contact.last_name}
                          </div>
                          <div className="text-sm text-gray-500">
                            {contact.title || 'No title'}
                          </div>
                          <a
                            href={`mailto:${contact.email}`}
                            className="text-sm text-blue-600 hover:underline"
                          >
                            {contact.email}
                          </a>
                        </div>
                        <div>
                          <span
                            className={`text-xs px-2 py-1 rounded-full ${
                              contact.validation_status === 'valid'
                                ? 'bg-green-100 text-green-800'
                                : contact.validation_status === 'invalid'
                                ? 'bg-red-100 text-red-800'
                                : 'bg-gray-100 text-gray-600'
                            }`}
                          >
                            {contact.validation_status || 'Not validated'}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-between items-center">
              <span className="text-sm text-gray-500">
                {leadContacts.length} contact{leadContacts.length !== 1 ? 's' : ''} linked to this lead
              </span>
              <button
                onClick={closeContactsModal}
                className="btn-secondary"
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
