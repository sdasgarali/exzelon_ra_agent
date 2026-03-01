'use client'

import { useState, useEffect } from 'react'
import { tenantsApi } from '@/lib/api'
import { useAuthStore } from '@/lib/store'

interface Tenant {
  tenant_id: number
  name: string
  slug: string
  is_active: boolean
  max_users: number
  max_mailboxes: number
  plan: string
  created_at: string
  updated_at: string
  is_archived: boolean
  user_count: number
  lead_count: number
  mailbox_count: number
  contact_count: number
}

interface TenantForm {
  name: string
  slug: string
  plan: string
  max_users: number
  max_mailboxes: number
  is_active: boolean
}

const PLAN_OPTIONS = [
  { value: 'free', label: 'Free', color: 'bg-gray-100 text-gray-800' },
  { value: 'standard', label: 'Standard', color: 'bg-blue-100 text-blue-800' },
  { value: 'premium', label: 'Premium', color: 'bg-purple-100 text-purple-800' },
]

const EMPTY_FORM: TenantForm = {
  name: '',
  slug: '',
  plan: 'free',
  max_users: 5,
  max_mailboxes: 10,
  is_active: true,
}

type SortField = 'tenant_id' | 'name' | 'slug' | 'plan' | 'created_at'
type SortOrder = 'asc' | 'desc'

export default function TenantsPage() {
  const { user } = useAuthStore()

  const [tenants, setTenants] = useState<Tenant[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Pagination
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)

  // Sorting
  const [sortBy, setSortBy] = useState<SortField>('name')
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc')

  // Filters
  const [search, setSearch] = useState('')
  const [filterPlan, setFilterPlan] = useState('')
  const [showArchived, setShowArchived] = useState(false)

  // Modals
  const [showFormModal, setShowFormModal] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [editingTenant, setEditingTenant] = useState<Tenant | null>(null)
  const [deletingTenant, setDeletingTenant] = useState<Tenant | null>(null)
  const [formData, setFormData] = useState<TenantForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Debounced search
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    if (user?.role === 'super_admin') {
      fetchTenants()
    }
  }, [page, pageSize, debouncedSearch, filterPlan, sortBy, sortOrder, showArchived, user?.role])

  const fetchTenants = async () => {
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
      if (filterPlan) params.plan = filterPlan
      if (showArchived) params.show_archived = true

      const response = await tenantsApi.list(params)
      const tenantList = Array.isArray(response) ? response : (response?.items || [])
      setTenants(tenantList)
      setTotal(response?.total || tenantList.length)
    } catch (err: any) {
      if (err.code !== 'ERR_CANCELED') {
        setError(err.response?.data?.detail || 'Failed to fetch tenants')
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

  const openCreateModal = () => {
    setEditingTenant(null)
    setFormData(EMPTY_FORM)
    setShowFormModal(true)
  }

  const openEditModal = (tenant: Tenant) => {
    setEditingTenant(tenant)
    setFormData({
      name: tenant.name,
      slug: tenant.slug,
      plan: tenant.plan,
      max_users: tenant.max_users,
      max_mailboxes: tenant.max_mailboxes,
      is_active: tenant.is_active,
    })
    setShowFormModal(true)
  }

  const openDeleteModal = (tenant: Tenant) => {
    setDeletingTenant(tenant)
    setShowDeleteModal(true)
  }

  const handleSave = async () => {
    if (!formData.name.trim()) {
      setError('Tenant name is required')
      return
    }
    if (!formData.slug.trim()) {
      setError('Tenant slug is required')
      return
    }

    try {
      setSaving(true)
      setError('')
      if (editingTenant) {
        await tenantsApi.update(editingTenant.tenant_id, formData)
        setSuccess(`Tenant "${formData.name}" updated successfully`)
      } else {
        await tenantsApi.create(formData)
        setSuccess(`Tenant "${formData.name}" created successfully`)
      }
      setShowFormModal(false)
      setFormData(EMPTY_FORM)
      setEditingTenant(null)
      fetchTenants()
      setTimeout(() => setSuccess(''), 4000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save tenant')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deletingTenant) return
    try {
      setDeleting(true)
      setError('')
      await tenantsApi.delete(deletingTenant.tenant_id)
      setSuccess(`Tenant "${deletingTenant.name}" archived successfully`)
      setShowDeleteModal(false)
      setDeletingTenant(null)
      fetchTenants()
      setTimeout(() => setSuccess(''), 4000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to archive tenant')
    } finally {
      setDeleting(false)
    }
  }

  const clearFilters = () => {
    setSearch('')
    setFilterPlan('')
    setShowArchived(false)
    setPage(1)
  }

  const getPlanBadge = (plan: string) => {
    const opt = PLAN_OPTIONS.find(p => p.value === plan)
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

  const generateSlug = (name: string) => {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortBy !== field) return <span className="text-gray-300 ml-1">&#8645;</span>
    return sortOrder === 'asc' ? <span className="ml-1">&#8593;</span> : <span className="ml-1">&#8595;</span>
  }

  const totalPages = Math.ceil(total / pageSize) || 1
  const activeFiltersCount = [filterPlan, search].filter(Boolean).length + (showArchived ? 1 : 0)

  // Access control: super_admin only
  if (user?.role !== 'super_admin') {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="text-red-400 mb-4">
            <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-gray-800 mb-2">Access Denied</h2>
          <p className="text-gray-500">You must be a Super Admin to access tenant management.</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Tenants</h1>
          <p className="text-gray-500 text-sm mt-1">
            {total} tenant(s) across the platform
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={openCreateModal}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 flex items-center gap-2 text-sm font-medium"
          >
            <span>+</span>
            Create Tenant
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
              placeholder="Search by tenant name or slug..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="input w-full"
            />
          </div>

          <select
            value={filterPlan}
            onChange={(e) => { setFilterPlan(e.target.value); setPage(1); }}
            className="input w-40"
          >
            <option value="">All Plans</option>
            {PLAN_OPTIONS.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
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

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th
                  onClick={() => handleSort('tenant_id')}
                  className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  ID <SortIcon field="tenant_id" />
                </th>
                <th
                  onClick={() => handleSort('name')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Name <SortIcon field="name" />
                </th>
                <th
                  onClick={() => handleSort('slug')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Slug <SortIcon field="slug" />
                </th>
                <th
                  onClick={() => handleSort('plan')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Plan <SortIcon field="plan" />
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Users
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Leads
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Mailboxes
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Contacts
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th
                  onClick={() => handleSort('created_at')}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                >
                  Created <SortIcon field="created_at" />
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={11} className="px-4 py-8 text-center text-gray-500">
                    Loading tenants...
                  </td>
                </tr>
              ) : tenants.length === 0 ? (
                <tr>
                  <td colSpan={11} className="px-4 py-8 text-center">
                    <div className="flex flex-col items-center justify-center py-4">
                      <div className="text-gray-300 mb-4">
                        <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                        </svg>
                      </div>
                      <h3 className="text-lg font-medium text-gray-900 mb-1">No tenants found</h3>
                      <p className="text-sm text-gray-500">
                        {activeFiltersCount > 0
                          ? 'Try adjusting your filters.'
                          : 'Click "Create Tenant" to add the first tenant.'}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                tenants.map((tenant) => (
                  <tr
                    key={tenant.tenant_id}
                    className={`${tenant.is_archived ? 'opacity-60 bg-gray-50' : ''} hover:bg-gray-50`}
                  >
                    <td className="px-3 py-3">
                      <span className="text-xs px-2 py-1 rounded bg-blue-50 text-blue-700 font-mono">
                        #{tenant.tenant_id}
                      </span>
                      {tenant.is_archived && (
                        <span className="ml-1 text-xs px-1.5 py-0.5 rounded bg-gray-200 text-gray-600 font-medium">Archived</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium text-gray-900">{tenant.name}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-gray-500 font-mono">{tenant.slug}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 text-xs rounded-full capitalize ${getPlanBadge(tenant.plan)}`}>
                        {tenant.plan}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      <span className="font-medium">{tenant.user_count}</span>
                      <span className="text-gray-400"> / {tenant.max_users}</span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {tenant.lead_count.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      <span className="font-medium">{tenant.mailbox_count}</span>
                      <span className="text-gray-400"> / {tenant.max_mailboxes}</span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {tenant.contact_count.toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 text-xs rounded-full ${tenant.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                        {tenant.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {formatDate(tenant.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => openEditModal(tenant)}
                          className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                          title="Edit tenant"
                        >
                          Edit
                        </button>
                        {!tenant.is_archived && (
                          <button
                            onClick={() => openDeleteModal(tenant)}
                            className="text-red-600 hover:text-red-800 text-sm font-medium"
                            title="Archive tenant"
                          >
                            Archive
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

        {/* Pagination */}
        <div className="bg-gray-50 px-6 py-3 flex items-center justify-between border-t">
          <div className="flex items-center gap-4">
            <div className="text-sm text-gray-500">
              Showing {tenants.length > 0 ? ((page - 1) * pageSize) + 1 : 0} to {Math.min(page * pageSize, total)} of {total} results
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

      {/* Create/Edit Modal */}
      {showFormModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-semibold text-gray-800">
                {editingTenant ? 'Edit Tenant' : 'Create Tenant'}
              </h3>
            </div>
            <div className="px-6 py-4 space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => {
                    const name = e.target.value
                    setFormData(prev => ({
                      ...prev,
                      name,
                      ...(!editingTenant ? { slug: generateSlug(name) } : {}),
                    }))
                  }}
                  placeholder="Acme Corporation"
                  className="input w-full"
                />
              </div>

              {/* Slug */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Slug <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={formData.slug}
                  onChange={(e) => setFormData(prev => ({ ...prev, slug: e.target.value }))}
                  placeholder="acme-corporation"
                  className="input w-full font-mono"
                />
                <p className="text-xs text-gray-400 mt-1">URL-friendly identifier. Auto-generated from name.</p>
              </div>

              {/* Plan */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Plan</label>
                <select
                  value={formData.plan}
                  onChange={(e) => setFormData(prev => ({ ...prev, plan: e.target.value }))}
                  className="input w-full"
                >
                  {PLAN_OPTIONS.map(p => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>

              {/* Max Users & Max Mailboxes */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Max Users</label>
                  <input
                    type="number"
                    min={1}
                    value={formData.max_users}
                    onChange={(e) => setFormData(prev => ({ ...prev, max_users: parseInt(e.target.value) || 1 }))}
                    className="input w-full"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Max Mailboxes</label>
                  <input
                    type="number"
                    min={1}
                    value={formData.max_mailboxes}
                    onChange={(e) => setFormData(prev => ({ ...prev, max_mailboxes: parseInt(e.target.value) || 1 }))}
                    className="input w-full"
                  />
                </div>
              </div>

              {/* Active Toggle */}
              <div>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => setFormData(prev => ({ ...prev, is_active: e.target.checked }))}
                    className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm font-medium text-gray-700">Tenant is active</span>
                </label>
              </div>
            </div>
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-end gap-3">
              <button
                onClick={() => { setShowFormModal(false); setEditingTenant(null); setFormData(EMPTY_FORM); }}
                disabled={saving}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? 'Saving...' : (editingTenant ? 'Update Tenant' : 'Create Tenant')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Archive Confirmation Modal */}
      {showDeleteModal && deletingTenant && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-semibold text-amber-600">Confirm Archive</h3>
            </div>
            <div className="px-6 py-4">
              <p className="text-gray-700 mb-3">
                Are you sure you want to archive tenant <strong>&quot;{deletingTenant.name}&quot;</strong>?
              </p>
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-700">
                <p className="font-medium mb-1">This tenant and all associated data will be soft-deleted.</p>
                <ul className="list-disc ml-4 space-y-1">
                  <li>Users under this tenant will lose access</li>
                  <li>All pipelines for this tenant will be paused</li>
                  <li>Use the &quot;Show Archived&quot; toggle to view archived tenants</li>
                </ul>
              </div>
            </div>
            <div className="px-6 py-4 border-t bg-gray-50 flex justify-end gap-3">
              <button
                onClick={() => { setShowDeleteModal(false); setDeletingTenant(null); }}
                disabled={deleting}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
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
