'use client'

import { useState, useEffect } from 'react'
import { clientsApi, api } from '@/lib/api'

interface Client {
  client_id: number
  client_name: string
  status: string
  industry: string
  company_size: string
  location_state: string
  client_category: string
  service_count: number
  is_archived: boolean
  created_at: string
  updated_at: string
}

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active', color: 'bg-green-100 text-green-800' },
  { value: 'inactive', label: 'Inactive', color: 'bg-red-100 text-red-800' },
]

const CATEGORY_OPTIONS = [
  { value: 'regular', label: 'Regular', color: 'bg-green-100 text-green-800' },
  { value: 'occasional', label: 'Occasional', color: 'bg-blue-100 text-blue-800' },
  { value: 'prospect', label: 'Prospect', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'dormant', label: 'Dormant', color: 'bg-gray-100 text-gray-800' },
]

type SortField = 'client_id' | 'client_name' | 'status' | 'client_category' | 'industry' | 'created_at'
type SortOrder = 'asc' | 'desc'

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Pagination
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)

  // Sorting
  const [sortBy, setSortBy] = useState<SortField>('client_name')
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc')

  // Filters
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [showArchived, setShowArchived] = useState(false)

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  // Modals
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [togglingStatus, setTogglingStatus] = useState<number | null>(null)

  // Debounced search
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    fetchClients()
  }, [page, pageSize, debouncedSearch, filterStatus, filterCategory, sortBy, sortOrder, showArchived])

  const fetchClients = async () => {
    try {
      setLoading(true)
      setError('')
      const params: Record<string, any> = {
        skip: (page - 1) * pageSize,
        limit: pageSize,
        sort_by: sortBy,
        sort_order: sortOrder,
      }
      if (debouncedSearch) params.search = debouncedSearch
      if (filterStatus) params.status = filterStatus
      if (filterCategory) params.category = filterCategory
      if (showArchived) params.show_archived = true

      const response = await clientsApi.list(params)
      const clientList = Array.isArray(response) ? response : (response?.items || [])
      setClients(clientList)
      setTotal(response?.total || clientList.length)
    } catch (err: any) {
      if (err.code !== 'ERR_CANCELED') {
        setError(err.response?.data?.detail || 'Failed to fetch clients')
      }
    } finally {
      setLoading(false)
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

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === clients.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(clients.map(c => c.client_id)))
    }
  }

  const handleBulkDelete = async () => {
    try {
      setDeleting(true)
      await clientsApi.bulkDelete(Array.from(selectedIds))
      setSuccess(`Successfully archived ${selectedIds.size} client(s)`)
      setSelectedIds(new Set())
      setShowDeleteModal(false)
      fetchClients()
      setTimeout(() => setSuccess(''), 4000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to archive clients')
    } finally {
      setDeleting(false)
    }
  }

  const handleExport = async () => {
    try {
      setExporting(true)
      const params: Record<string, any> = {}
      if (filterStatus) params.status = filterStatus
      if (filterCategory) params.category = filterCategory
      if (debouncedSearch) params.search = debouncedSearch
      if (showArchived) params.show_archived = true

      const blob = await clientsApi.exportCsv(params)

      const url = window.URL.createObjectURL(new Blob([blob]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `clients_export_${new Date().toISOString().slice(0, 10)}.csv`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)

      setSuccess('Export completed successfully')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to export clients')
    } finally {
      setExporting(false)
    }
  }

  const handleToggleStatus = async (client: Client) => {
    const newStatus = client.status === 'active' ? 'inactive' : 'active'
    try {
      setTogglingStatus(client.client_id)
      await clientsApi.update(client.client_id, { status: newStatus })
      setClients(prev => prev.map(c =>
        c.client_id === client.client_id ? { ...c, status: newStatus } : c
      ))
      setSuccess(`${client.client_name} set to ${newStatus}`)
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update status')
    } finally {
      setTogglingStatus(null)
    }
  }

  const clearFilters = () => {
    setSearch('')
    setFilterStatus('')
    setFilterCategory('')
    setShowArchived(false)
    setPage(1)
  }

  const getStatusBadge = (status: string) => {
    const opt = STATUS_OPTIONS.find(s => s.value === status)
    return opt?.color || 'bg-gray-100 text-gray-800'
  }

  const getCategoryBadge = (category: string) => {
    const opt = CATEGORY_OPTIONS.find(c => c.value === category)
    return opt?.color || 'bg-gray-100 text-gray-800'
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-'
    try {
      const d = new Date(dateString)
      return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    } catch {
      return dateString
    }
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortBy !== field) return <span className="text-gray-300 ml-1">&#8645;</span>
    return sortOrder === 'asc' ? <span className="ml-1">&#8593;</span> : <span className="ml-1">&#8595;</span>
  }

  const totalPages = Math.ceil(total / pageSize) || 1
  const activeFiltersCount = [filterStatus, filterCategory, search].filter(Boolean).length + (showArchived ? 1 : 0)

  return (
    <div>
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Clients</h1>
          <p className="text-gray-500 text-sm mt-1">
            {total} companies tracked across all pipelines
          </p>
        </div>
        <div className="flex gap-2">
          {selectedIds.size > 0 && (
            <button
              onClick={() => setShowDeleteModal(true)}
              className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 flex items-center gap-2 text-sm font-medium"
            >
              Archive Selected ({selectedIds.size})
            </button>
          )}
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
          <div className="flex-1 min-w-64">
            <input
              type="text"
              placeholder="Search by ID (#42), company name, industry, or location..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="input w-full"
            />
          </div>

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
            value={filterCategory}
            onChange={(e) => { setFilterCategory(e.target.value); setPage(1); }}
            className="input w-40"
          >
            <option value="">All Categories</option>
            {CATEGORY_OPTIONS.map(c => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => { setShowArchived(e.target.checked); setPage(1); }}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm font-medium text-gray-700 whitespace-nowrap">Show Archived</span>
          </label>

          {activeFiltersCount > 0 && (
            <button onClick={clearFilters} className="text-sm text-gray-500 hover:text-gray-700">
              Clear all
            </button>
          )}
        </div>
      </div>

      {/* Selection Info Bar */}
      {selectedIds.size > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 mb-4 flex items-center justify-between">
          <span className="text-sm text-blue-800 font-medium">{selectedIds.size} client(s) selected</span>
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
                    checked={clients.length > 0 && selectedIds.size === clients.length}
                    onChange={toggleSelectAll}
                    className="w-4 h-4"
                  />
                </th>
                <th
                  onClick={() => handleSort('client_id')}
                  className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  ID <SortIcon field="client_id" />
                </th>
                <th
                  onClick={() => handleSort('client_name')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Client Name <SortIcon field="client_name" />
                </th>
                <th
                  onClick={() => handleSort('industry')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Industry <SortIcon field="industry" />
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Size
                </th>
                <th
                  onClick={() => handleSort('status')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Status <SortIcon field="status" />
                </th>
                <th
                  onClick={() => handleSort('client_category')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Category <SortIcon field="client_category" />
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Services
                </th>
                <th
                  onClick={() => handleSort('created_at')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Created <SortIcon field="created_at" />
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                    Loading clients...
                  </td>
                </tr>
              ) : clients.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center">
                    <div className="flex flex-col items-center justify-center py-4">
                      <div className="text-gray-300 mb-4">
                        <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                        </svg>
                      </div>
                      <h3 className="text-lg font-medium text-gray-900 mb-1">No clients found</h3>
                      <p className="text-sm text-gray-500">
                        {activeFiltersCount > 0
                          ? 'Try adjusting your filters.'
                          : 'Clients will appear here after running the lead sourcing pipeline.'}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                clients.map((client) => (
                  <tr
                    key={client.client_id}
                    className={`${client.is_archived ? "opacity-60 bg-gray-50" : ""} ${selectedIds.has(client.client_id) ? "bg-blue-50 hover:bg-blue-100" : "hover:bg-gray-50"}`}
                  >
                    <td className="px-3 py-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(client.client_id)}
                        onChange={() => toggleSelect(client.client_id)}
                        className="w-4 h-4"
                      />
                    </td>
                    <td className="px-3 py-3">
                      <span className="text-xs px-2 py-1 rounded bg-blue-50 text-blue-700 font-mono">
                        #{client.client_id}
                      </span>
                      {client.is_archived && (
                        <span className="ml-1 text-xs px-1.5 py-0.5 rounded bg-gray-200 text-gray-600 font-medium">Archived</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium text-gray-900">{client.client_name}</div>
                      <div className="text-sm text-gray-500">{client.location_state || '-'}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {client.industry || '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {client.company_size || '-'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleToggleStatus(client)}
                        disabled={togglingStatus === client.client_id}
                        className={`px-2 py-1 text-xs rounded-full cursor-pointer hover:opacity-80 transition-opacity disabled:opacity-50 ${getStatusBadge(client.status)}`}
                        title={`Click to set ${client.status === 'active' ? 'Inactive' : 'Active'}`}
                      >
                        {togglingStatus === client.client_id ? '...' : client.status}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 text-xs rounded-full ${getCategoryBadge(client.client_category)}`}>
                        {client.client_category}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {client.service_count || 0}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {formatDate(client.created_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="bg-gray-50 px-6 py-3 flex items-center justify-between border-t">
          <div className="flex items-center gap-4">
            <div className="text-sm text-gray-500">
              Showing {clients.length > 0 ? ((page - 1) * pageSize) + 1 : 0} to {Math.min(page * pageSize, total)} of {total} results
            </div>
            <select
              value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
              className="text-sm border rounded px-2 py-1"
            >
              <option value="10">10 / page</option>
              <option value="25">25 / page</option>
              <option value="50">50 / page</option>
              <option value="100">100 / page</option>
            </select>
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
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={page * pageSize >= total}
              className="px-3 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100"
            >
              Next
            </button>
            <button
              onClick={() => setPage(totalPages)}
              disabled={page * pageSize >= total}
              className="px-2 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100"
              title="Last page"
            >
              &raquo;
            </button>
          </div>
        </div>
      </div>

      {/* Archive Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-semibold text-amber-600">Confirm Archive</h3>
            </div>
            <div className="px-6 py-4">
              <p className="text-gray-700 mb-3">
                Are you sure you want to archive <strong>{selectedIds.size}</strong> client(s)?
              </p>
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-700">
                <p className="font-medium mb-1">Archived clients will be hidden by default but can be restored.</p>
                <ul className="list-disc ml-4 space-y-1">
                  <li>Use the &quot;Show Archived&quot; toggle to view archived clients</li>
                  <li>Archived clients are excluded from active pipeline processing</li>
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
    </div>
  )
}
