'use client'

import React, { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { leadsApi, pipelinesApi, lobApi, api, getApiError } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { useLobStore } from '@/lib/lob-store'
import { ContactsWizard } from '@/components/contacts-wizard'
import { SizeFilter, NumericFilter, SizeFilterValue, EMPTY_SIZE_FILTER, sizeFilterParams, salaryFilterParams, sizeFilterActive } from '@/components/size-filter'
import { ExcelTextFilter, TextCondition, textConditionParams, textConditionActive } from '@/components/excel-text-filter'
import { useNeedsTenantSelection, SelectTenantBanner } from '@/components/tenant-guard'

interface Lead {
  lead_id: number
  client_name: string
  job_title: string
  state: string
  posting_date: string
  job_link: string
  source: string
  employment_type: string | null
  lead_status: string
  campaign_status?: string | null
  campaign_id?: number | null
  mailing_status?: string | null
  contact_email: string
  salary_min: number
  salary_max: number
  contact_count: number  // Number of contacts linked to this lead
  industry: string | null
  company_size: string | null
  employer_website: string | null
  run_id: number | null
  data_type: string
  is_archived: boolean
  downloaded_at: string | null
  lob_id: number | null
  metadata: Record<string, any> | null
  created_at: string
  updated_at: string
}

interface ColumnConfig {
  label_overrides: Record<string, string>
  hidden_columns: string[]
  metadata_columns: { key: string; label: string; type: string }[]
  filters: string[]
}

interface LeadFilterOptions {
  industries: string[]
  industry_categories?: Record<string, string[]>
  company_sizes: string[]
  data_types: string[]
  exclusion_keywords: { it_keywords: string[]; staffing_keywords: string[] }
  job_titles: string[]
  job_title_categories?: Record<string, string[]>
  employment_types?: string[]
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
  { value: 'campaign_draft', label: 'Campaign-Draft', color: 'bg-cyan-100 text-cyan-800' },
  { value: 'campaign_active', label: 'Campaign-Active', color: 'bg-emerald-100 text-emerald-800' },
  { value: 'campaign_paused', label: 'Campaign-Paused', color: 'bg-amber-200 text-amber-900' },
  { value: 'campaign_completed', label: 'Campaign-Completed', color: 'bg-sky-100 text-sky-800' },
]

// Pipeline statuses that can be set via the dropdown (excludes campaign-derived statuses)
const PIPELINE_STATUS_OPTIONS = STATUS_OPTIONS.filter(s => !s.value.startsWith('campaign_'))

// Badge colors for the derived "Mailing-Status" column (server sends the label directly).
const MAILING_STATUS_COLORS: Record<string, string> = {
  'Campaign-Draft': 'bg-cyan-100 text-cyan-800',
  'Campaign-Active': 'bg-emerald-100 text-emerald-800',
  'Campaign-Paused': 'bg-amber-200 text-amber-900',
  'Campaign-Closed': 'bg-sky-100 text-sky-800',
  'Mailed-Offline': 'bg-green-100 text-green-800',
  'Not-Mailed': 'bg-gray-100 text-gray-600',
}

const SOURCE_OPTIONS = ['jsearch', 'indeed', 'linkedin', 'glassdoor', 'mock', 'import']

const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
]

type SortField = 'lead_id' | 'client_name' | 'job_title' | 'state' | 'posting_date' | 'created_at' | 'source' | 'employment_type' | 'lead_status' | 'contact_count' | 'industry' | 'company_size' | 'run_id' | 'downloaded_at'
type SortOrder = 'asc' | 'desc'

const EMPLOYMENT_TYPE_OPTIONS = ['Full-time', 'Contract', 'Part-time', 'Temporary', 'Internship']

export default function LeadsPage() {
  const router = useRouter()
  const isSuperAdmin = useAuthStore((s) => s.isSuperAdmin())
  const isAdmin = useAuthStore((s) => s.isAdmin())
  const { needsTenantSelection, runDisabledTitle } = useNeedsTenantSelection()
  const activeLobId = useLobStore((s) => s.activeLobId)
  const getActiveLob = useLobStore((s) => s.getActiveLob)
  const [columnConfig, setColumnConfig] = useState<ColumnConfig | null>(null)
  const [expandedRowId, setExpandedRowId] = useState<number | null>(null)
  const [leads, setLeads] = useState<Lead[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [updating, setUpdating] = useState<number | null>(null)
  const [pageSize, setPageSize] = useState(200)

  // Filters
  const [showFilters, setShowFilters] = useState(false)
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [filterState, setFilterState] = useState<string[]>([])
  const [filterFromDate, setFilterFromDate] = useState('')
  const [filterToDate, setFilterToDate] = useState('')
  const [filterIndustry, setFilterIndustry] = useState<string[]>([])
  const [sizeFilter, setSizeFilter] = useState<SizeFilterValue>(EMPTY_SIZE_FILTER)
  const [salaryFilter, setSalaryFilter] = useState<SizeFilterValue>(EMPTY_SIZE_FILTER)
  const [filterDataType, setFilterDataType] = useState('')
  const [filterEmploymentType, setFilterEmploymentType] = useState<string[]>([])
  const [filterExcludeKeywords, setFilterExcludeKeywords] = useState<string[]>([])
  const [filterTitle, setFilterTitle] = useState<string[]>([])
  // Excel-style Text Filter conditions (Contains / Begins With / Custom / …)
  const [filterIndustryText, setFilterIndustryText] = useState<TextCondition | null>(null)
  const [filterTitleText, setFilterTitleText] = useState<TextCondition | null>(null)
  const [filterCompanyText, setFilterCompanyText] = useState<TextCondition | null>(null)
  const [filterEmploymentText, setFilterEmploymentText] = useState<TextCondition | null>(null)
  const [filterExtractedFrom, setFilterExtractedFrom] = useState('')
  const [filterExtractedTo, setFilterExtractedTo] = useState('')
  const [filterDownloaded, setFilterDownloaded] = useState('')

  // Export modal
  const [showExportModal, setShowExportModal] = useState(false)

  // Filter options from backend
  const [leadFilterOptions, setLeadFilterOptions] = useState<LeadFilterOptions>({ industries: [], company_sizes: [], data_types: [], exclusion_keywords: { it_keywords: [], staffing_keywords: [] }, job_titles: [] })

  // Sorting
  const [sortBy, setSortBy] = useState<SortField>('created_at')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')

  // Import
  const [importing, setImporting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Contacts modal
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null)

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
  const [showBulkUpdateModal, setShowBulkUpdateModal] = useState(false)
  const [bulkUpdating, setBulkUpdating] = useState(false)
  const [bulkUpdateForm, setBulkUpdateForm] = useState({ data_type: '' })

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

  // Campaign eligibility check
  const [eligibleLeadIds, setEligibleLeadIds] = useState<number[]>([])
  const [checkingEligibility, setCheckingEligibility] = useState(false)

  // Status cards stats
  const [leadStats, setLeadStats] = useState<{ total: number; by_status: Record<string, number>; by_campaign_status: Record<string, number> } | null>(null)
  const [totalContactAssociations, setTotalContactAssociations] = useState(0)

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

  // Debounced campaign eligibility check when selection changes
  useEffect(() => {
    if (selectedIds.size === 0) {
      setEligibleLeadIds([])
      return
    }
    setCheckingEligibility(true)
    const timer = setTimeout(async () => {
      try {
        const result = await leadsApi.campaignEligible(Array.from(selectedIds))
        setEligibleLeadIds(result.eligible_lead_ids || [])
      } catch {
        setEligibleLeadIds([])
      } finally {
        setCheckingEligibility(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [selectedIds])

  // Load filter options on mount
  useEffect(() => {
    leadsApi.filterOptions().then(setLeadFilterOptions).catch(() => {})
  }, [])

  // Fetch column config when active LOB changes
  useEffect(() => {
    const lob = getActiveLob()
    if (lob && lob.lob_type !== 'staffing') {
      lobApi.getColumnConfig(lob.lob_type).then(setColumnConfig).catch(() => setColumnConfig(null))
    } else {
      setColumnConfig(null)
    }
  }, [activeLobId])

  // Fetch lead stats for status cards — refetch when leads change (covers mutations) or archive toggle
  useEffect(() => {
    leadsApi.stats({ show_archived: showArchived || undefined }).then(setLeadStats).catch(() => {})
  }, [leads, showArchived])

  // Debounce search
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  // Clear selections when filters change (not on page/sort changes)
  useEffect(() => {
    setSelectedIds(new Set())
  }, [debouncedSearch, filterStatus, filterSource, filterState, filterFromDate, filterToDate, filterExtractedFrom, filterExtractedTo, filterDownloaded, filterIndustry, sizeFilter, salaryFilter, filterDataType, filterEmploymentType, filterExcludeKeywords, filterTitle, filterIndustryText, filterTitleText, filterCompanyText, filterEmploymentText, pageSize, showArchived])

  useEffect(() => {
    fetchLeads()
  }, [page, pageSize, debouncedSearch, filterStatus, filterSource, filterState, filterFromDate, filterToDate, filterExtractedFrom, filterExtractedTo, filterDownloaded, filterIndustry, sizeFilter, salaryFilter, filterDataType, filterEmploymentType, filterExcludeKeywords, filterTitle, filterIndustryText, filterTitleText, filterCompanyText, filterEmploymentText, sortBy, sortOrder, showArchived, activeLobId])

  // Build the active filter set shared by the leads list AND the CSV export, so
  // an export always matches exactly what the user is viewing (WYSIWYG). Excludes
  // pagination/sort — callers add those as needed.
  const buildLeadFilterParams = (): Record<string, any> => {
    const params: Record<string, any> = {}
    if (debouncedSearch) params.search = debouncedSearch
    if (filterStatus) params.status = filterStatus
    if (filterSource) params.source = filterSource
    if (filterState.length) params.state = filterState
    if (filterFromDate) params.from_date = filterFromDate
    if (filterToDate) params.to_date = filterToDate
    if (filterIndustry.length) params.industry = filterIndustry
    Object.assign(params, sizeFilterParams(sizeFilter))
    Object.assign(params, salaryFilterParams(salaryFilter))
    if (filterDataType) params.data_type = filterDataType
    if (filterEmploymentType.length) params.employment_type = filterEmploymentType
    if (filterExcludeKeywords.length) params.exclude_keywords = filterExcludeKeywords
    if (filterTitle.length) params.title = filterTitle
    // Excel-style Text Filter conditions
    Object.assign(params, textConditionParams('industry', filterIndustryText))
    Object.assign(params, textConditionParams('title', filterTitleText))
    Object.assign(params, textConditionParams('company', filterCompanyText))
    Object.assign(params, textConditionParams('employment_type', filterEmploymentText))
    if (filterExtractedFrom) params.extracted_from = filterExtractedFrom
    if (filterExtractedTo) params.extracted_to = filterExtractedTo
    if (filterDownloaded) params.downloaded = filterDownloaded
    if (showArchived) params.show_archived = true
    // Filter by active LOB if one is selected
    const activeLob = getActiveLob()
    if (activeLob && activeLob.lob_type !== 'staffing') {
      params.lob_id = activeLob.lob_id
    }
    return params
  }

  const fetchLeads = async () => {
    try {
      setLoading(true)
      setError('')
      setExpandedRowId(null)
      const params: Record<string, any> = {
        page,
        page_size: pageSize,
        sort_by: sortBy,
        sort_order: sortOrder,
        ...buildLeadFilterParams(),
      }

      const response = await leadsApi.list(params)
      setLeads(response.items || [])
      setTotal(response.total || 0)
      setTotalContactAssociations(response.total_contact_associations || 0)
    } catch (err: any) {
      if (err.code !== 'ERR_CANCELED') {
        setError(getApiError(err, 'Failed to fetch leads'))
      }
    } finally {
      setLoading(false)
    }
  }

  const updateLeadStatus = async (leadId: number, newStatus: string, force = false) => {
    try {
      setUpdating(leadId)
      await leadsApi.update(leadId, { lead_status: newStatus }, force)
      setLeads(leads.map(lead =>
        lead.lead_id === leadId ? { ...lead, lead_status: newStatus } : lead
      ))
      setSuccess(force ? 'Status overridden successfully' : 'Status updated successfully')
      setTimeout(() => setSuccess(''), 2000)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      const isTransitionBlock =
        err?.response?.status === 400 &&
        typeof detail === 'string' &&
        detail.includes('Cannot transition')
      // Admins/super-admins may override a blocked transition after confirming.
      if (isTransitionBlock && isAdmin && !force) {
        if (window.confirm(`${detail}\n\nStill want to continue? (Admin override)`)) {
          await updateLeadStatus(leadId, newStatus, true)
        }
        return
      }
      setError(getApiError(err, 'Failed to update status'))
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
    setFilterState([])
    setFilterFromDate('')
    setFilterToDate('')
    setFilterIndustry([])
    setSizeFilter(EMPTY_SIZE_FILTER)
    setSalaryFilter(EMPTY_SIZE_FILTER)
    setFilterDataType('')
    setFilterEmploymentType([])
    setFilterExcludeKeywords([])
    setFilterTitle([])
    setFilterIndustryText(null)
    setFilterTitleText(null)
    setFilterCompanyText(null)
    setFilterEmploymentText(null)
    setFilterDownloaded('')
    setShowArchived(false)
    setPage(1)
  }

  const handleExport = async (mode: 'all' | 'selected') => {
    try {
      setExporting(true)
      setShowExportModal(false)
      // POST with a JSON body (not GET query params): a "selected" export of many
      // leads would otherwise put hundreds of lead_ids in the URL and exceed the
      // proxy's request-line limit, failing the request.
      // "All" exports the exact filtered view the user sees (WYSIWYG); "selected"
      // exports the checked rows. Sent as a JSON body so large selections don't
      // overflow the URL length limit.
      const body: Record<string, unknown> =
        mode === 'selected'
          ? { lead_ids: Array.from(selectedIds) }
          : buildLeadFilterParams()

      const response = await api.post('/leads/export/csv', body, {
        responseType: 'blob'
      })

      // Guard against a silent "blank" download: the CSV always contains a header
      // row, so a header-only payload means zero leads matched. Tell the user
      // instead of downloading an empty-looking file.
      const csvText = await (response.data as Blob).text()
      const dataRows = csvText.split('\n').filter(line => line.trim() !== '').length - 1
      if (dataRows <= 0) {
        setError(mode === 'selected'
          ? 'No matching leads to export for the current selection.'
          : 'No leads matched your current filters — nothing to export. (Tip: check the Archived toggle and active filters.)')
        return
      }

      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `leads_export_${new Date().toISOString().slice(0, 10)}.csv`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)

      setSuccess(`Export completed — ${dataRows} row${dataRows === 1 ? '' : 's'} (${mode === 'selected' ? selectedIds.size + ' selected leads' : 'all filtered leads'})`)
      setTimeout(() => setSuccess(''), 3000)
      fetchLeads() // Refresh to show updated downloaded_at
    } catch (err: any) {
      setError(getApiError(err, 'Failed to export leads'))
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
      setError(getApiError(err, 'Failed to import leads'))
    } finally {
      setImporting(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const fetchContactsForLead = (lead: Lead) => {
    setSelectedLead(lead)
  }

  const closeContactsModal = () => {
    setSelectedLead(null)
  }

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const allCurrentPageSelected = leads.length > 0 && leads.every(l => selectedIds.has(l.lead_id))

  const toggleSelectAll = () => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (allCurrentPageSelected) {
        // Deselect only current page leads
        leads.forEach(l => next.delete(l.lead_id))
      } else {
        // Add current page leads to existing selections
        leads.forEach(l => next.add(l.lead_id))
      }
      return next
    })
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
      setError(getApiError(err, 'Failed to delete leads'))
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
      setError(getApiError(err, 'Failed to restore leads'))
      setTimeout(() => setError(''), 4000)
    }
  }

  const handleBulkUpdate = async () => {
    const updates: Record<string, any> = {}
    if (bulkUpdateForm.data_type !== '') updates.data_type = bulkUpdateForm.data_type
    if (Object.keys(updates).length === 0) return
    setBulkUpdating(true)
    try {
      await leadsApi.bulkUpdate(Array.from(selectedIds), updates)
      setSuccess(`Updated ${selectedIds.size} lead(s)`)
      setShowBulkUpdateModal(false)
      setBulkUpdateForm({ data_type: '' })
      setSelectedIds(new Set())
      fetchLeads()
      setTimeout(() => setSuccess(''), 4000)
    } catch (err: any) {
      setError(getApiError(err, 'Bulk update failed'))
      setTimeout(() => setError(''), 4000)
    } finally {
      setBulkUpdating(false)
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
      setError(getApiError(err, 'Failed to update status'))
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
      setError(getApiError(err, 'Failed to run outreach'))
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
      setError(getApiError(err, 'Failed to load enrichment preview'))
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
      setError(getApiError(err, 'Failed to start enrichment'))
    } finally {
      setEnriching(false)
    }
  }

  const getStatusBadge = (status: string) => {
    const statusOption = STATUS_OPTIONS.find(s => s.value === status)
    return statusOption?.color || 'bg-gray-100 text-gray-800'
  }

  const getDisplayStatus = (lead: Lead): string =>
    lead.campaign_status ? `campaign_${lead.campaign_status}` : lead.lead_status

  const getDisplayStatusLabel = (lead: Lead): string => {
    const displayStatus = getDisplayStatus(lead)
    const opt = STATUS_OPTIONS.find(s => s.value === displayStatus)
    return opt?.label || displayStatus
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

  const formatSalary = (min: number | null, max: number | null) => {
    const fmt = (n: number) => n >= 1000 ? `$${Math.round(n / 1000)}k` : `$${n}`
    const lo = min && min > 0 ? min : null
    const hi = max && max > 0 ? max : null
    if (lo && hi) return lo === hi ? fmt(lo) : `${fmt(lo)} - ${fmt(hi)}`
    if (lo) return `${fmt(lo)}+`
    if (hi) return `Up to ${fmt(hi)}`
    return '-'
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

  // Multi-select dropdown component
  const MultiSelectDropdown = ({ label, options, selected, onChange, labelMap }: {
    label: string
    options: string[]
    selected: string[]
    onChange: (vals: string[]) => void
    labelMap?: Record<string, string>
  }) => {
    const [open, setOpen] = useState(false)
    const ref = useRef<HTMLDivElement>(null)

    useEffect(() => {
      const handleClickOutside = (e: MouseEvent) => {
        if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
      }
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [])

    const toggle = (val: string) => {
      onChange(selected.includes(val) ? selected.filter(v => v !== val) : [...selected, val])
      setPage(1)
    }

    return (
      <div ref={ref} className="relative">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className={`input w-full text-left flex items-center justify-between ${selected.length > 0 ? 'border-blue-400 bg-blue-50' : ''}`}
        >
          <span className="truncate text-sm">
            {selected.length === 0 ? `All ${label}` : `${label} (${selected.length})`}
          </span>
          <span className="text-gray-400 ml-1">{open ? '\u25B2' : '\u25BC'}</span>
        </button>
        {open && (
          <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
            <div className="flex gap-2 px-3 py-2 border-b bg-gray-50 sticky top-0">
              <button type="button" onClick={() => { onChange([...options]); setPage(1) }} className="text-xs text-blue-600 hover:underline">Select All</button>
              <button type="button" onClick={() => { onChange([]); setPage(1) }} className="text-xs text-gray-500 hover:underline">Clear</button>
            </div>
            {options.map(opt => (
              <label key={opt} className="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-50 cursor-pointer text-sm">
                <input
                  type="checkbox"
                  checked={selected.includes(opt)}
                  onChange={() => toggle(opt)}
                  className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600"
                />
                {labelMap?.[opt] || opt}
              </label>
            ))}
            {options.length === 0 && <div className="px-3 py-2 text-xs text-gray-400">No options available</div>}
          </div>
        )}
      </div>
    )
  }

  // Searchable multi-select with optional grouped categories and per-category "All" checkbox
  const SearchableMultiSelect = ({ label, options, selected, onChange, grouped }: {
    label: string
    options: string[] | { category: string; items: string[] }[]
    selected: string[]
    onChange: (vals: string[]) => void
    grouped?: boolean
  }) => {
    const [open, setOpen] = useState(false)
    const [searchText, setSearchText] = useState('')
    const ref = useRef<HTMLDivElement>(null)

    useEffect(() => {
      const handleClickOutside = (e: MouseEvent) => {
        if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
      }
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [])

    const allItems: string[] = grouped
      ? (options as { category: string; items: string[] }[]).flatMap(g => g.items)
      : (options as string[])

    const filterBySearch = (items: string[]) =>
      searchText ? items.filter(i => i.toLowerCase().includes(searchText.toLowerCase())) : items

    const toggle = (val: string) => {
      onChange(selected.includes(val) ? selected.filter(v => v !== val) : [...selected, val])
      setPage(1)
    }

    const toggleCategory = (categoryItems: string[]) => {
      const allSelected = categoryItems.every(i => selected.includes(i))
      if (allSelected) {
        onChange(selected.filter(v => !categoryItems.includes(v)))
      } else {
        const merged = Array.from(new Set([...selected, ...categoryItems]))
        onChange(merged)
      }
      setPage(1)
    }

    return (
      <div ref={ref} className="relative">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className={`input w-full text-left flex items-center justify-between ${selected.length > 0 ? 'border-blue-400 bg-blue-50' : ''}`}
        >
          <span className="truncate text-sm">
            {selected.length === 0 ? `All ${label}` : `${label} (${selected.length})`}
          </span>
          <span className="text-gray-400 ml-1">{open ? '\u25B2' : '\u25BC'}</span>
        </button>
        {open && (
          <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-72 overflow-y-auto min-w-0 sm:min-w-[220px]">
            <div className="flex gap-2 px-3 py-2 border-b bg-gray-50 sticky top-0 z-10">
              <button type="button" onClick={() => { onChange([...allItems]); setPage(1) }} className="text-xs text-blue-600 hover:underline">Select All</button>
              <button type="button" onClick={() => { onChange([]); setPage(1) }} className="text-xs text-gray-500 hover:underline">Clear</button>
            </div>
            <div className="px-3 py-2 border-b sticky top-[37px] bg-white z-10">
              <input
                type="text"
                placeholder="Search..."
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                className="w-full text-sm border border-gray-200 rounded px-2 py-1 focus:outline-none focus:border-blue-400"
              />
            </div>
            {grouped ? (
              (options as { category: string; items: string[] }[]).map(group => {
                const filtered = filterBySearch(group.items)
                if (filtered.length === 0) return null
                const allCatSelected = group.items.length > 0 && group.items.every(i => selected.includes(i))
                const someCatSelected = group.items.some(i => selected.includes(i))
                return (
                  <div key={group.category}>
                    <label className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 border-b cursor-pointer">
                      <input
                        type="checkbox"
                        checked={allCatSelected}
                        ref={(el) => { if (el) el.indeterminate = someCatSelected && !allCatSelected }}
                        onChange={() => toggleCategory(group.items)}
                        className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600"
                      />
                      <span className="text-xs font-semibold text-gray-600 uppercase">{group.category}</span>
                      <span className="text-xs text-gray-400 ml-auto">{group.items.filter(i => selected.includes(i)).length}/{group.items.length}</span>
                    </label>
                    {filtered.map(opt => (
                      <label key={opt} className="flex items-center gap-2 px-3 py-1.5 pl-7 hover:bg-gray-50 cursor-pointer text-sm">
                        <input
                          type="checkbox"
                          checked={selected.includes(opt)}
                          onChange={() => toggle(opt)}
                          className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600"
                        />
                        {opt}
                      </label>
                    ))}
                  </div>
                )
              })
            ) : (
              filterBySearch(allItems).map(opt => (
                <label key={opt} className="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-50 cursor-pointer text-sm">
                  <input
                    type="checkbox"
                    checked={selected.includes(opt)}
                    onChange={() => toggle(opt)}
                    className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600"
                  />
                  {opt}
                </label>
              ))
            )}
            {allItems.length === 0 && <div className="px-3 py-2 text-xs text-gray-400">No options available</div>}
            {allItems.length > 0 && filterBySearch(allItems).length === 0 && <div className="px-3 py-2 text-xs text-gray-400">No matches for &ldquo;{searchText}&rdquo;</div>}
          </div>
        )}
      </div>
    )
  }

  const activeFiltersCount = [filterStatus, filterSource, filterFromDate, filterToDate, filterExtractedFrom, filterExtractedTo, filterDownloaded, filterDataType, search].filter(Boolean).length
    + (filterState.length > 0 ? 1 : 0) + (filterIndustry.length > 0 ? 1 : 0) + (filterEmploymentType.length > 0 ? 1 : 0) + (sizeFilterActive(sizeFilter) ? 1 : 0) + (sizeFilterActive(salaryFilter) ? 1 : 0) + (filterExcludeKeywords.length > 0 ? 1 : 0) + (filterTitle.length > 0 ? 1 : 0) + (showArchived ? 1 : 0)
    + [filterIndustryText, filterTitleText, filterCompanyText, filterEmploymentText].filter(textConditionActive).length

  // Helper: get column label with LOB overrides
  const colLabel = (field: string, defaultLabel: string): string => {
    if (columnConfig?.label_overrides?.[field]) return columnConfig.label_overrides[field]
    return defaultLabel
  }

  // Helper: check if a column is hidden by LOB config
  const isHidden = (field: string): boolean => {
    return columnConfig?.hidden_columns?.includes(field) ?? false
  }

  // Helper: render a metadata value by type
  const renderMetaValue = (value: any, type: string) => {
    if (value === null || value === undefined) return <span className="text-gray-400">-</span>
    switch (type) {
      case 'number':
        return <span className="text-sm text-gray-700">{typeof value === 'number' ? value.toLocaleString() : value}</span>
      case 'currency':
        return <span className="text-sm text-gray-700 font-medium">
          {typeof value === 'number' ? (value >= 1_000_000 ? `$${(value / 1_000_000).toFixed(1)}M` : `$${(value / 1000).toFixed(0)}K`) : `$${value}`}
        </span>
      case 'badge':
        return <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">{value}</span>
      case 'tags': {
        const items = Array.isArray(value) ? value : String(value).split(',').map((s: string) => s.trim())
        return <div className="flex flex-wrap gap-1">{items.slice(0, 3).map((t: string, i: number) => (
          <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-700">{t}</span>
        ))}{items.length > 3 && <span className="text-[10px] text-gray-400">+{items.length - 3}</span>}</div>
      }
      case 'score': {
        const score = typeof value === 'number' ? value : parseFloat(value)
        const pct = Math.round((isNaN(score) ? 0 : score) * 100)
        const color = pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-yellow-500' : 'bg-red-500'
        return <div className="flex items-center gap-2">
          <div className="w-16 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
          </div>
          <span className="text-xs text-gray-600">{pct}</span>
        </div>
      }
      case 'phone':
        return <a href={`tel:${value}`} className="text-sm text-blue-600 hover:underline">{value}</a>
      default:
        return <span className="text-sm text-gray-700">{String(value)}</span>
    }
  }

  // Compute total visible column count for colSpan
  // 19 = base columns incl. Mailing-Status + Campaign-ID
  const baseColCount = 19
    - (isHidden('salary_min') ? 0 : 0) // salary is not a separate column currently
    - (isHidden('employment_type') ? 1 : 0)
    + (columnConfig?.metadata_columns?.length ?? 0)

  return (
    <div>
      <SelectTenantBanner action="enrich leads or send outreach" />
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Leads</h1>
          <p className="text-gray-500 text-sm mt-1">
            {total.toLocaleString()} job postings sourced from LinkedIn, Indeed, Glassdoor, and more
            {totalContactAssociations > 0 && (
              <> — {totalContactAssociations.toLocaleString()} contacts are associated with these leads</>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {selectedIds.size > 0 && (
            <>
              {showArchived ? (
                <button
                  onClick={handleBulkUnarchive}
                  className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 flex items-center gap-2 text-sm font-medium"
                >
                  Restore Selected ({selectedIds.size})
                </button>
              ) : (
                <>
                  <button
                    onClick={handleOpenEnrichPreview}
                    disabled={needsTenantSelection}
                    title={runDisabledTitle}
                    className="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 flex items-center gap-2 text-sm font-medium disabled:opacity-60 disabled:cursor-not-allowed"
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
                        setError(getApiError(err, 'Failed to load preview'))
                      } finally {
                        setLoadingPreview(false)
                      }
                    }}
                    disabled={needsTenantSelection || Array.from(selectedIds).filter(id => (contactCountCache[id] || 0) > 0).length === 0}
                    className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 flex items-center gap-2 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                    title={needsTenantSelection ? runDisabledTitle : (Array.from(selectedIds).filter(id => (contactCountCache[id] || 0) > 0).length === 0 ? 'No selected leads have contacts' : '')}
                  >
                    Send Outreach ({Array.from(selectedIds).filter(id => (contactCountCache[id] || 0) > 0).length})
                  </button>
                  <button
                    onClick={() => setShowStatusModal(true)}
                    className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 flex items-center gap-2 text-sm font-medium"
                  >
                    Update Status ({selectedIds.size})
                  </button>
                  <button
                    onClick={() => setShowDeleteModal(true)}
                    className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 flex items-center gap-2 text-sm font-medium"
                  >
                    Archive Selected ({selectedIds.size})
                  </button>
                  {isSuperAdmin && (
                    <button
                      onClick={() => setShowBulkUpdateModal(true)}
                      className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 flex items-center gap-2 text-sm font-medium"
                    >
                      Bulk Update ({selectedIds.size})
                    </button>
                  )}
                  <button
                    onClick={() => {
                      const ids = eligibleLeadIds.join(',')
                      router.push(`/dashboard/campaigns?create_from_leads=${ids}`)
                    }}
                    disabled={eligibleLeadIds.length === 0 || checkingEligibility}
                    className="bg-emerald-600 text-white px-4 py-2 rounded-lg hover:bg-emerald-700 flex items-center gap-2 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                    title={eligibleLeadIds.length === 0 ? 'No selected leads are eligible (need contacts + not in active campaign)' : ''}
                  >
                    {checkingEligibility ? (
                      <><span className="animate-spin">&#8635;</span> Checking...</>
                    ) : (
                      <>Create Campaign ({eligibleLeadIds.length})</>
                    )}
                  </button>
                </>
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
          <div className="relative">
            <button
              onClick={() => setShowExportModal(true)}
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
            {showExportModal && (
              <>
              <div className="fixed inset-0 z-40" onClick={() => setShowExportModal(false)} />
              <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 w-56">
                <div className="p-2">
                  <div className="text-xs font-medium text-gray-500 px-3 py-1.5">Export Options</div>
                  <button
                    onClick={() => handleExport('all')}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 rounded flex items-center gap-2"
                  >
                    <span>&#128196;</span> All Leads {total > 0 && <span className="text-gray-400 text-xs">({total})</span>}
                  </button>
                  <button
                    onClick={() => handleExport('selected')}
                    disabled={selectedIds.size === 0}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 rounded flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <span>&#9745;</span> Selected Only {selectedIds.size > 0 && <span className="text-gray-400 text-xs">({selectedIds.size})</span>}
                  </button>
                </div>
                <div className="border-t px-2 py-1.5">
                  <button
                    onClick={() => setShowExportModal(false)}
                    className="w-full text-center text-xs text-gray-500 hover:text-gray-700 py-1"
                  >
                    Cancel
                  </button>
                </div>
              </div>
              </>
            )}
          </div>
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

      {/* Status Cards */}
      {leadStats && leadStats.total > 0 && (
        <div className="flex flex-wrap gap-3 mb-4">
          {/* Total card */}
          <button
            onClick={() => { setFilterStatus(''); setPage(1) }}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
              !filterStatus ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            <span className="text-lg font-bold">{leadStats.total}</span>
            <span>Total</span>
          </button>

          {/* Pipeline status cards — only show those with count > 0 */}
          {PIPELINE_STATUS_OPTIONS.map(opt => {
            const count = leadStats.by_status[opt.value] || 0
            if (count === 0) return null
            return (
              <button
                key={opt.value}
                onClick={() => { setFilterStatus(filterStatus === opt.value ? '' : opt.value); setPage(1) }}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                  filterStatus === opt.value ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
                }`}
              >
                <span className={`inline-block w-2.5 h-2.5 rounded-full ${opt.color.split(' ')[0]}`} />
                <span>{opt.label}</span>
                <span className="font-bold">{count}</span>
                <span className="text-gray-400 font-normal">/ {leadStats.total}</span>
              </button>
            )
          })}

          {/* Campaign status cards — only show those with count > 0 */}
          {leadStats.by_campaign_status && Object.keys(leadStats.by_campaign_status).length > 0 && (
            <>
              <div className="w-px bg-gray-200 self-stretch mx-1" />
              {STATUS_OPTIONS.filter(s => s.value.startsWith('campaign_')).map(opt => {
                const campKey = opt.value.replace('campaign_', '')
                const count = leadStats.by_campaign_status[campKey] || 0
                if (count === 0) return null
                return (
                  <button
                    key={opt.value}
                    onClick={() => { setFilterStatus(filterStatus === opt.value ? '' : opt.value); setPage(1) }}
                    className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                      filterStatus === opt.value ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    <span className={`inline-block w-2.5 h-2.5 rounded-full ${opt.color.split(' ')[0]}`} />
                    <span>{opt.label}</span>
                    <span className="font-bold">{count}</span>
                    <span className="text-gray-400 font-normal">/ {leadStats.total}</span>
                  </button>
                )
              })}
            </>
          )}
        </div>
      )}

      {/* Search and Filter Bar */}
      <div className="card p-4 mb-4">
        <div className="flex flex-wrap gap-4 items-center">
          {/* Search */}
          <div className="flex-1 min-w-64">
            <input
              type="text"
              placeholder="Search by ID (#42), Run ID (R5), company, job title, or state..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="input w-full"
            />
          </div>

          {/* Quick Filters */}
          <select
            value={filterStatus}
            onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
            className="input w-full sm:w-40"
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
            Advance Filters {activeFiltersCount > 0 && `(${activeFiltersCount})`}
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
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
            <div>
              <label className="label text-sm">State</label>
              <MultiSelectDropdown
                label="States"
                options={US_STATES}
                selected={filterState}
                onChange={setFilterState}
              />
            </div>
            <div>
              <label className="label text-sm">Industry</label>
              <ExcelTextFilter
                label="Industries"
                grouped={!!leadFilterOptions.industry_categories && Object.keys(leadFilterOptions.industry_categories).length > 0}
                options={leadFilterOptions.industry_categories && Object.keys(leadFilterOptions.industry_categories).length > 0
                  ? Object.entries(leadFilterOptions.industry_categories).map(([category, items]) => ({ category, items }))
                  : leadFilterOptions.industries}
                selected={filterIndustry}
                onChange={setFilterIndustry}
                textCondition={filterIndustryText}
                onTextConditionChange={setFilterIndustryText}
                onAfterChange={() => setPage(1)}
              />
            </div>
            <div className="col-span-2">
              <label className="label text-sm">Company Size (employees)</label>
              <SizeFilter value={sizeFilter} onChange={(v) => { setSizeFilter(v); setPage(1); }} />
            </div>
            <div className="col-span-2">
              <label className="label text-sm">Salary ($)</label>
              <NumericFilter
                label="Salary"
                placeholder="amount"
                anyLabel="Any salary"
                value={salaryFilter}
                onChange={(v) => { setSalaryFilter(v); setPage(1); }}
              />
            </div>
            <div>
              <label className="label text-sm">Data Type</label>
              <select
                value={filterDataType}
                onChange={(e) => { setFilterDataType(e.target.value); setPage(1); }}
                className="input w-full"
              >
                <option value="">All</option>
                <option value="prod">Production</option>
                <option value="test">Test</option>
              </select>
            </div>
            <div>
              <label className="label text-sm">Position Type</label>
              <ExcelTextFilter
                label="Position Types"
                options={leadFilterOptions.employment_types && leadFilterOptions.employment_types.length > 0
                  ? leadFilterOptions.employment_types
                  : EMPLOYMENT_TYPE_OPTIONS}
                selected={filterEmploymentType}
                onChange={setFilterEmploymentType}
                textCondition={filterEmploymentText}
                onTextConditionChange={setFilterEmploymentText}
                onAfterChange={() => setPage(1)}
              />
            </div>
            <div>
              <label className="label text-sm">Company Name</label>
              <ExcelTextFilter
                label="Company"
                selected={[]}
                onChange={() => {}}
                textCondition={filterCompanyText}
                onTextConditionChange={setFilterCompanyText}
                onAfterChange={() => setPage(1)}
              />
            </div>
            <div>
              <label className="label text-sm">Exclusion Keywords</label>
              <SearchableMultiSelect
                label="Exclusions"
                grouped
                options={[
                  { category: 'IT / Tech', items: leadFilterOptions.exclusion_keywords.it_keywords },
                  { category: 'Staffing / Agency', items: leadFilterOptions.exclusion_keywords.staffing_keywords },
                ]}
                selected={filterExcludeKeywords}
                onChange={setFilterExcludeKeywords}
              />
            </div>
            <div>
              <label className="label text-sm">Job Title</label>
              <ExcelTextFilter
                label="Titles"
                grouped={!!leadFilterOptions.job_title_categories && Object.keys(leadFilterOptions.job_title_categories).length > 0}
                options={leadFilterOptions.job_title_categories && Object.keys(leadFilterOptions.job_title_categories).length > 0
                  ? Object.entries(leadFilterOptions.job_title_categories).sort(([a], [b]) => a.localeCompare(b)).map(([category, items]) => ({ category, items: items.sort() }))
                  : leadFilterOptions.job_titles}
                selected={filterTitle}
                onChange={setFilterTitle}
                textCondition={filterTitleText}
                onTextConditionChange={setFilterTitleText}
                onAfterChange={() => setPage(1)}
              />
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
              <label className="label text-sm">Extracted From</label>
              <input
                type="date"
                value={filterExtractedFrom}
                onChange={(e) => { setFilterExtractedFrom(e.target.value); setPage(1); }}
                className="input w-full"
              />
            </div>
            <div>
              <label className="label text-sm">Extracted To</label>
              <input
                type="date"
                value={filterExtractedTo}
                onChange={(e) => { setFilterExtractedTo(e.target.value); setPage(1); }}
                className="input w-full"
              />
            </div>
            <div>
              <label className="label text-sm">Downloaded</label>
              <select
                value={filterDownloaded}
                onChange={(e) => { setFilterDownloaded(e.target.value); setPage(1); }}
                className="input w-full"
              >
                <option value="">All</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
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
                <option value="200">200 per page</option>
                <option value="500">All</option>
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

      {/* Pagination (top) */}
      <div className="bg-white px-6 py-3 flex items-center justify-between border rounded-lg mb-2">
        <div className="text-sm text-gray-500">
          Showing {leads.length > 0 ? ((page - 1) * pageSize) + 1 : 0} to {Math.min(page * pageSize, total)} of {total} results
        </div>
        <div className="flex gap-2 items-center">
          <button onClick={() => setPage(1)} disabled={page === 1} className="px-2 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100" title="First page">&laquo;</button>
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100">Previous</button>
          <span className="px-3 py-1 text-sm text-gray-600">Page {page} of {Math.ceil(total / pageSize) || 1}</span>
          <button onClick={() => setPage(p => p + 1)} disabled={page * pageSize >= total} className="px-3 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100">Next</button>
          <button onClick={() => setPage(Math.ceil(total / pageSize))} disabled={page * pageSize >= total} className="px-2 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100" title="Last page">&raquo;</button>
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={allCurrentPageSelected}
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
                  onClick={() => handleSort('run_id')}
                  className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Run <SortIcon field="run_id" />
                </th>
                <th
                  onClick={() => handleSort('client_name')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  {colLabel('client_name', 'Company')} / {colLabel('job_title', 'Job Title')} <SortIcon field="client_name" />
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Salary
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
                  {colLabel('posting_date', 'Posted')} <SortIcon field="posting_date" />
                </th>
                <th
                  onClick={() => handleSort('created_at')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Extracted <SortIcon field="created_at" />
                </th>
                <th
                  onClick={() => handleSort('downloaded_at')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Downloaded <SortIcon field="downloaded_at" />
                </th>
                <th
                  onClick={() => handleSort('source')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Source <SortIcon field="source" />
                </th>
                {!isHidden('employment_type') && (
                  <th
                    onClick={() => handleSort('employment_type')}
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                  >
                    Type <SortIcon field="employment_type" />
                  </th>
                )}
                <th
                  onClick={() => handleSort('industry')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Industry <SortIcon field="industry" />
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Website
                </th>
                <th
                  onClick={() => handleSort('company_size')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Size <SortIcon field="company_size" />
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  {colLabel('job_link', 'Link')}
                </th>
                {/* LOB metadata columns */}
                {columnConfig?.metadata_columns?.map(mc => (
                  <th key={mc.key} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    {mc.label}
                  </th>
                ))}
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
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Mailing-Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Campaign-ID
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={baseColCount} className="px-4 py-8 text-center text-gray-500">
                    Loading leads...
                  </td>
                </tr>
              ) : leads.length === 0 ? (
                <tr>
                  <td colSpan={baseColCount} className="px-4 py-8 text-center text-gray-500">
                    No leads found. {activeFiltersCount > 0 ? 'Try adjusting your filters.' : 'Run the Lead Sourcing pipeline to fetch jobs.'}
                  </td>
                </tr>
              ) : (
                leads.map((lead) => (
                  <React.Fragment key={lead.lead_id}>
                  <tr
                    className={`${lead.is_archived ? "opacity-60 bg-gray-50" : ""} ${selectedIds.has(lead.lead_id) ? "bg-blue-50 hover:bg-blue-100" : "hover:bg-gray-50"} ${lead.metadata && columnConfig ? 'cursor-pointer' : ''}`}
                    onClick={() => {
                      if (lead.metadata && columnConfig) {
                        setExpandedRowId(expandedRowId === lead.lead_id ? null : lead.lead_id)
                      }
                    }}
                  >
                    <td className="px-3 py-3" onClick={e => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(lead.lead_id)}
                        onChange={() => toggleSelect(lead.lead_id)}
                        className="w-4 h-4"
                      />
                    </td>
                    <td className="px-3 py-3" onClick={e => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        <Link href={`/dashboard/leads/${lead.lead_id}`} className="text-xs px-2 py-1 rounded bg-blue-50 text-blue-700 font-mono hover:bg-blue-100">
                          #{lead.lead_id}
                        </Link>
                        {lead.data_type === 'test' && <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-medium">TEST</span>}
                        {lead.is_archived && <span className="text-xs px-1.5 py-0.5 rounded bg-gray-200 text-gray-600 font-medium">Archived</span>}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-xs text-gray-500 font-mono">
                      {lead.run_id ? `R${lead.run_id}` : '-'}
                    </td>
                    <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                      <Link href={`/dashboard/leads/${lead.lead_id}`} className="text-sm font-medium text-blue-700 hover:text-blue-900 hover:underline">
                        {lead.client_name}
                      </Link>
                      <div className="text-sm text-gray-500">{lead.job_title}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700 whitespace-nowrap">
                      {formatSalary(lead.salary_min, lead.salary_max)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {lead.state || '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {formatDate(lead.posting_date)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {lead.downloaded_at ? (
                        <span className="text-xs px-2 py-1 rounded bg-green-50 text-green-700" title={new Date(lead.downloaded_at).toLocaleString()}>
                          {new Date(lead.downloaded_at).toLocaleDateString()}
                        </span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-1 rounded bg-gray-100 text-gray-700">
                        {lead.source}
                      </span>
                    </td>
                    {!isHidden('employment_type') && (
                      <td className="px-4 py-3">
                        {lead.employment_type ? (
                          <span className={`text-xs px-2 py-1 rounded ${
                            lead.employment_type === 'Full-time' ? 'bg-green-100 text-green-700' :
                            lead.employment_type === 'Contract' ? 'bg-orange-100 text-orange-700' :
                            lead.employment_type === 'Part-time' ? 'bg-blue-100 text-blue-700' :
                            lead.employment_type === 'Temporary' ? 'bg-yellow-100 text-yellow-700' :
                            'bg-gray-100 text-gray-700'
                          }`}>
                            {lead.employment_type}
                          </span>
                        ) : (
                          <span className="text-gray-400 text-sm">-</span>
                        )}
                      </td>
                    )}
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {lead.industry || '-'}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {lead.employer_website ? (
                        <a
                          href={/^https?:\/\//i.test(lead.employer_website) ? lead.employer_website : `https://${lead.employer_website}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800 hover:underline"
                          title={lead.employer_website}
                          onClick={e => e.stopPropagation()}
                        >
                          {truncateUrl(lead.employer_website.replace(/^https?:\/\//i, ''), 25)}
                        </a>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
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
                          onClick={e => e.stopPropagation()}
                        >
                          {truncateUrl(lead.job_link, 25)}
                        </a>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    {/* LOB metadata column values */}
                    {columnConfig?.metadata_columns?.map(mc => (
                      <td key={mc.key} className="px-4 py-3">
                        {renderMetaValue(lead.metadata?.[mc.key], mc.type)}
                      </td>
                    ))}
                    <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
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
                    <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                      {lead.campaign_status ? (
                        <span
                          title="Status set by campaign"
                          className={`text-xs px-2 py-1 rounded-full inline-block ${getStatusBadge(getDisplayStatus(lead))}`}
                        >
                          {getDisplayStatusLabel(lead)}
                        </span>
                      ) : (
                        <select
                          value={lead.lead_status}
                          onChange={(e) => updateLeadStatus(lead.lead_id, e.target.value)}
                          disabled={updating === lead.lead_id}
                          className={`text-xs px-2 py-1 rounded-full border-0 cursor-pointer ${getStatusBadge(lead.lead_status)} ${updating === lead.lead_id ? 'opacity-50' : ''}`}
                        >
                          {PIPELINE_STATUS_OPTIONS.map((status) => (
                            <option key={status.value} value={status.value}>
                              {status.label}
                            </option>
                          ))}
                        </select>
                      )}
                    </td>
                    {/* Mailing-Status (derived from campaign enrollment + download flag) */}
                    <td className="px-4 py-3">
                      {lead.mailing_status ? (
                        <span
                          className={`text-xs px-2 py-1 rounded-full inline-block ${MAILING_STATUS_COLORS[lead.mailing_status] || 'bg-gray-100 text-gray-600'}`}
                        >
                          {lead.mailing_status}
                        </span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    {/* Campaign-ID */}
                    <td className="px-4 py-3 text-sm">
                      {lead.campaign_id ? (
                        <a
                          href={`/dashboard/campaigns?campaign_id=${lead.campaign_id}`}
                          className="text-blue-600 hover:text-blue-800 hover:underline"
                          onClick={e => e.stopPropagation()}
                        >
                          #{lead.campaign_id}
                        </a>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                  </tr>
                  {/* Expandable metadata detail row */}
                  {expandedRowId === lead.lead_id && lead.metadata && (
                    <tr className="bg-gray-50">
                      <td colSpan={baseColCount} className="px-6 py-4">
                        <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Metadata Details</div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                          {Object.entries(lead.metadata).map(([key, value]) => (
                            <div key={key} className="bg-white rounded-lg border border-gray-200 px-3 py-2">
                              <div className="text-[10px] font-medium text-gray-400 uppercase">{key.replace(/_/g, ' ')}</div>
                              <div className="text-sm text-gray-800 mt-0.5 break-words">
                                {value === null || value === undefined
                                  ? '-'
                                  : Array.isArray(value)
                                    ? value.join(', ')
                                    : typeof value === 'object'
                                      ? JSON.stringify(value)
                                      : String(value)}
                              </div>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                  </React.Fragment>
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

      {/* Bulk Update Modal */}
      {showBulkUpdateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-bold mb-1">Bulk Update {selectedIds.size} Lead{selectedIds.size > 1 ? 's' : ''}</h2>
            <p className="text-sm text-gray-500 mb-4">Only filled fields will be updated.</p>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data Type</label>
                <select value={bulkUpdateForm.data_type} onChange={e => setBulkUpdateForm(f => ({ ...f, data_type: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm">
                  <option value="">— No change —</option>
                  <option value="test">Test</option>
                  <option value="prod">Prod</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => { setShowBulkUpdateModal(false); setBulkUpdateForm({ data_type: '' }) }} className="px-4 py-2 text-sm border rounded-lg hover:bg-gray-50">Cancel</button>
              <button onClick={handleBulkUpdate} disabled={bulkUpdating || bulkUpdateForm.data_type === ''} className="px-4 py-2 text-sm text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                {bulkUpdating ? 'Updating...' : 'Update'}
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
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
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
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
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
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 mb-4">
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

      {/* Contacts Wizard */}
      {selectedLead && (
        <ContactsWizard
          lead={selectedLead}
          onClose={closeContactsModal}
          onContactAdded={() => fetchLeads()}
        />
      )}
    </div>
  )
}
