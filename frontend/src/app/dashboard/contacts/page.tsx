'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { contactsApi, api } from '@/lib/api'
import { useAuthStore } from '@/lib/store'

interface Contact {
  contact_id: number
  lead_id: number | null
  lead_ids: number[]
  client_name: string
  first_name: string
  last_name: string
  title: string
  email: string
  phone: string
  linkedin_url: string | null
  location_state: string
  timezone: string | null
  priority_level: string
  validation_status: string
  source: string
  outreach_status: string
  unsubscribed_at: string | null
  is_test: boolean
}

const TIMEZONE_LABELS: Record<string, string> = {
  'America/New_York': 'ET',
  'America/Chicago': 'CT',
  'America/Denver': 'MT',
  'America/Los_Angeles': 'PT',
  'America/Anchorage': 'AKT',
  'Pacific/Honolulu': 'HT',
  'America/Phoenix': 'MT',
  'America/Boise': 'MT',
  'America/Detroit': 'ET',
  'America/Indiana/Indianapolis': 'ET',
}

function formatTimezone(tz: string | null): string {
  if (!tz) return '-'
  return TIMEZONE_LABELS[tz] || tz.split('/').pop()?.replace(/_/g, ' ') || tz
}

const EMPTY_FORM = {
  first_name: '', last_name: '', email: '', client_name: '',
  title: '', phone: '', linkedin_url: '', location_state: '', source: 'manual',
  priority_level: '', is_test: false as boolean,
}

export default function ContactsPage() {
  const isSuperAdmin = useAuthStore((s) => s.isSuperAdmin())
  const [contacts, setContacts] = useState<Contact[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [pageSize, setPageSize] = useState(25)
  const [showArchived, setShowArchived] = useState(false)
  const [search, setSearch] = useState('')
  const [filterPriority, setFilterPriority] = useState('')
  const [filterValidation, setFilterValidation] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [filterOutreachStatus, setFilterOutreachStatus] = useState('')
  const [filterDataType, setFilterDataType] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortBy, setSortBy] = useState('')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  // Multi-select & delete
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showBulkUpdateModal, setShowBulkUpdateModal] = useState(false)
  const [bulkUpdating, setBulkUpdating] = useState(false)
  const [bulkUpdateForm, setBulkUpdateForm] = useState({ data_type: '', first_name: '', last_name: '', client_name: '', email: '', phone: '', timezone: '', lead_id: '', outreach_status: '', validation_status: '', priority_level: '' })

  // Create contact modal
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createForm, setCreateForm] = useState({ ...EMPTY_FORM })
  const [creating, setCreating] = useState(false)

  // Edit contact modal
  const [showEditModal, setShowEditModal] = useState(false)
  const [editingContactId, setEditingContactId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState({ ...EMPTY_FORM })
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    fetchContacts()
  }, [page, pageSize, debouncedSearch, filterPriority, filterValidation, filterSource, filterOutreachStatus, filterDataType, showArchived, sortBy, sortOrder])

  const fetchContacts = async () => {
    try {
      setLoading(true)
      setError('')
      const params: Record<string, any> = { page, page_size: pageSize }
      if (debouncedSearch) params.search = debouncedSearch
      if (filterPriority) params.priority_level = filterPriority
      if (filterValidation) params.validation_status = filterValidation
      if (filterSource) params.source = filterSource
      if (filterOutreachStatus) params.outreach_status = filterOutreachStatus
      if (filterDataType) params.data_type = filterDataType
      if (showArchived) params.show_archived = true
      if (sortBy) { params.sort_by = sortBy; params.sort_order = sortOrder }
      const response = await contactsApi.list(params)
      const contactList = Array.isArray(response) ? response : (response?.items || [])
      setContacts(contactList)
      setTotal(response?.total || contactList.length)
    } catch (err: any) {
      if (err.code !== 'ERR_CANCELED') {
        setError(err.response?.data?.detail || 'Failed to fetch contacts')
      }
    } finally {
      setLoading(false)
    }
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
    if (selectedIds.size === contacts.length && contacts.length > 0) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(contacts.map(c => c.contact_id)))
    }
  }

  const isAllSelected = contacts.length > 0 && selectedIds.size === contacts.length

  const handleDeleteSelected = async () => {
    try {
      setDeleting(true)
      setError('')
      const response = await api.delete('/contacts/bulk', { data: { contact_ids: Array.from(selectedIds) } })
      const count = response.data?.deleted_count || selectedIds.size
      setSuccess(`${count} contact(s) archived successfully.`)
      setSelectedIds(new Set())
      setShowDeleteModal(false)
      fetchContacts()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to archive contacts')
      setShowDeleteModal(false)
    } finally {
      setDeleting(false)
    }
  }

  const handleBulkUpdate = async () => {
    const updates: Record<string, any> = {}
    for (const [k, v] of Object.entries(bulkUpdateForm)) {
      if (v !== '') {
        updates[k] = k === 'lead_id' ? parseInt(v) : v
      }
    }
    if (Object.keys(updates).length === 0) return
    setBulkUpdating(true)
    try {
      await contactsApi.bulkUpdate(Array.from(selectedIds), updates)
      setSuccess(`Updated ${selectedIds.size} contact(s)`)
      setShowBulkUpdateModal(false)
      setBulkUpdateForm({ data_type: '', first_name: '', last_name: '', client_name: '', email: '', phone: '', timezone: '', lead_id: '', outreach_status: '', validation_status: '', priority_level: '' })
      setSelectedIds(new Set())
      fetchContacts()
      setTimeout(() => setSuccess(''), 4000)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Bulk update failed')
      setTimeout(() => setError(''), 4000)
    } finally {
      setBulkUpdating(false)
    }
  }

  const handleCreateContact = async () => {
    if (!createForm.first_name || !createForm.last_name || !createForm.email || !createForm.client_name) return
    try {
      setCreating(true)
      setError('')
      await contactsApi.create(createForm)
      setSuccess('Contact created successfully!')
      setShowCreateModal(false)
      setCreateForm({ ...EMPTY_FORM })
      fetchContacts()
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create contact')
    } finally {
      setCreating(false)
    }
  }

  const handleEditContact = async () => {
    if (!editingContactId || !editForm.first_name || !editForm.last_name || !editForm.email) return
    try {
      setEditing(true)
      setError('')
      await contactsApi.update(editingContactId, editForm)
      setSuccess('Contact updated successfully!')
      setShowEditModal(false)
      setEditingContactId(null)
      setEditForm({ ...EMPTY_FORM })
      fetchContacts()
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update contact')
    } finally {
      setEditing(false)
    }
  }

  const handleDeleteSingle = async (contactId: number) => {
    if (!confirm('Archive this contact?')) return
    try {
      setError('')
      await contactsApi.delete(contactId)
      setSuccess('Contact archived successfully!')
      fetchContacts()
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to archive contact')
    }
  }

  const handleRestoreSelected = async () => {
    try {
      setDeleting(true)
      setError('')
      const response = await contactsApi.bulkRestore(Array.from(selectedIds))
      const count = response?.restored_count || selectedIds.size
      setSuccess(`${count} contact(s) restored successfully.`)
      setSelectedIds(new Set())
      fetchContacts()
      setTimeout(() => setSuccess(''), 4000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to restore contacts')
    } finally {
      setDeleting(false)
    }
  }

  // Reset test data
  const [resettingTestData, setResettingTestData] = useState(false)

  const handleResetTestData = async () => {
    if (!confirm('Reset all outreach data for test contacts? This deletes their outreach events, campaign enrollments, and suppression entries.')) return
    try {
      setResettingTestData(true)
      setError('')
      const res = await api.post('/contacts/reset-test-data')
      const d = res.data
      setSuccess(`Reset ${d.reset_count} test contact(s): ${d.events_deleted} events, ${d.enrollments_deleted} enrollments, ${d.suppressions_removed} suppressions removed.`)
      fetchContacts()
      setTimeout(() => setSuccess(''), 6000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to reset test data')
    } finally {
      setResettingTestData(false)
    }
  }

  const getValidationBadge = (status: string) => {
    const colors: Record<string, string> = {
      valid: 'bg-green-100 text-green-800',
      invalid: 'bg-red-100 text-red-800',
      unknown: 'bg-gray-100 text-gray-800',
      pending: 'bg-yellow-100 text-yellow-800',
    }
    return colors[status] || 'bg-gray-100 text-gray-800'
  }

  const getPriorityBadge = (priority: string) => {
    if (!priority) return 'bg-gray-100 text-gray-800'
    const level = priority.split('_')[0]
    const colors: Record<string, string> = {
      p1: 'bg-red-100 text-red-800',
      p2: 'bg-orange-100 text-orange-800',
      p3: 'bg-yellow-100 text-yellow-800',
      p4: 'bg-blue-100 text-blue-800',
      p5: 'bg-gray-100 text-gray-800',
    }
    return colors[level] || 'bg-gray-100 text-gray-800'
  }

  const getPriorityLabel = (priority: string) => {
    if (!priority) return '-'
    const labels: Record<string, string> = {
      p1_job_poster: 'P1 - Job Poster',
      p2_hr_ta_recruiter: 'P2 - HR/Recruiter',
      p3_hr_manager: 'P3 - HR Manager',
      p4_ops_leader: 'P4 - Ops Leader',
      p5_functional_manager: 'P5 - Func. Mgr',
    }
    return labels[priority] || priority.split('_')[0].toUpperCase()
  }

  const getOutreachStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      active: 'bg-green-100 text-green-800',
      inactive: 'bg-gray-100 text-gray-800',
      unsubscribed: 'bg-red-100 text-red-800',
    }
    return colors[status] || 'bg-green-100 text-green-800'
  }

  const getOutreachStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      active: 'Active',
      inactive: 'Inactive',
      unsubscribed: 'Unsubscribed',
    }
    return labels[status] || 'Active'
  }

  const handleSort = (column: string) => {
    if (sortBy === column) {
      if (sortOrder === 'asc') {
        setSortOrder('desc')
      } else {
        // Third click: clear sort
        setSortBy('')
        setSortOrder('desc')
      }
    } else {
      setSortBy(column)
      setSortOrder('asc')
    }
    setPage(1)
  }

  const getSortIcon = (column: string) => {
    if (sortBy !== column) return ' \u2195'
    return sortOrder === 'asc' ? ' \u2191' : ' \u2193'
  }

  const totalPages = Math.ceil(total / pageSize) || 1

  return (
    <div>
      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-md w-full mx-4">
            <div className="flex items-center mb-4">
              <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center mr-3">
                <span className="text-red-600 text-xl">&#9888;</span>
              </div>
              <h3 className="text-lg font-semibold text-gray-800">Confirm Deletion</h3>
            </div>
            <p className="text-gray-600 mb-2">
              You are about to archive <strong>{selectedIds.size}</strong> contact(s).
            </p>
            <div className="bg-red-50 border border-red-200 rounded p-3 mb-4">
              <p className="text-sm text-red-800 font-medium mb-1">This action cannot be undone.</p>
              <p className="text-sm text-red-700">The following related data will also be removed:</p>
              <ul className="text-sm text-red-700 mt-1 ml-4 list-disc">
                <li>Outreach events linked to these contacts</li>
                <li>Email validation results for these contacts</li>
              </ul>
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowDeleteModal(false)} disabled={deleting} className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50">Cancel</button>
              <button onClick={handleDeleteSelected} disabled={deleting} className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50">
                {deleting ? 'Archiving...' : 'Archive'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Contact Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold text-gray-800">Create Contact</h3>
              <button onClick={() => setShowCreateModal(false)} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">First Name *</label>
                  <input value={createForm.first_name} onChange={e => setCreateForm(f => ({ ...f, first_name: e.target.value }))} className="input w-full" placeholder="John" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Last Name *</label>
                  <input value={createForm.last_name} onChange={e => setCreateForm(f => ({ ...f, last_name: e.target.value }))} className="input w-full" placeholder="Doe" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
                <input type="email" value={createForm.email} onChange={e => setCreateForm(f => ({ ...f, email: e.target.value }))} className="input w-full" placeholder="john.doe@company.com" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Company / Client Name *</label>
                <input value={createForm.client_name} onChange={e => setCreateForm(f => ({ ...f, client_name: e.target.value }))} className="input w-full" placeholder="Acme Corp" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Job Title</label>
                <input value={createForm.title} onChange={e => setCreateForm(f => ({ ...f, title: e.target.value }))} className="input w-full" placeholder="HR Manager" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
                  <input value={createForm.phone} onChange={e => setCreateForm(f => ({ ...f, phone: e.target.value }))} className="input w-full" placeholder="+1 555-0123" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">State</label>
                  <input value={createForm.location_state} onChange={e => setCreateForm(f => ({ ...f, location_state: e.target.value }))} className="input w-full" placeholder="CA" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">LinkedIn Profile</label>
                <input value={createForm.linkedin_url} onChange={e => setCreateForm(f => ({ ...f, linkedin_url: e.target.value }))} className="input w-full" placeholder="https://linkedin.com/in/johndoe" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Priority Level</label>
                <select value={createForm.priority_level} onChange={e => setCreateForm(f => ({ ...f, priority_level: e.target.value }))} className="input w-full">
                  <option value="">-- Select --</option>
                  <option value="p1_job_poster">P1 - Job Poster</option>
                  <option value="p2_hr_ta_recruiter">P2 - HR/Recruiter</option>
                  <option value="p3_hr_manager">P3 - HR Manager</option>
                  <option value="p4_ops_leader">P4 - Ops Leader</option>
                  <option value="p5_functional_manager">P5 - Functional Manager</option>
                </select>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={createForm.is_test}
                  onChange={e => setCreateForm(f => ({ ...f, is_test: e.target.checked }))}
                  className="w-4 h-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                />
                <span className="text-sm font-medium text-gray-700">Test Contact</span>
                <span className="text-xs text-gray-400">(bypasses cooldown &amp; fatigue checks)</span>
              </label>
              <div className="flex gap-3 pt-2">
                <button onClick={() => setShowCreateModal(false)} className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50">Cancel</button>
                <button
                  onClick={handleCreateContact}
                  disabled={!createForm.first_name || !createForm.last_name || !createForm.email || !createForm.client_name || creating}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
                  {creating ? 'Creating...' : 'Create Contact'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit Contact Modal */}
      {showEditModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold text-gray-800">Edit Contact</h3>
              <button onClick={() => { setShowEditModal(false); setEditingContactId(null) }} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">First Name *</label>
                  <input value={editForm.first_name} onChange={e => setEditForm(f => ({ ...f, first_name: e.target.value }))} className="input w-full" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Last Name *</label>
                  <input value={editForm.last_name} onChange={e => setEditForm(f => ({ ...f, last_name: e.target.value }))} className="input w-full" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
                <input type="email" value={editForm.email} onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))} className="input w-full" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Company / Client Name</label>
                <input value={editForm.client_name} onChange={e => setEditForm(f => ({ ...f, client_name: e.target.value }))} className="input w-full" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Job Title</label>
                <input value={editForm.title} onChange={e => setEditForm(f => ({ ...f, title: e.target.value }))} className="input w-full" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
                  <input value={editForm.phone} onChange={e => setEditForm(f => ({ ...f, phone: e.target.value }))} className="input w-full" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">State</label>
                  <input value={editForm.location_state} onChange={e => setEditForm(f => ({ ...f, location_state: e.target.value }))} className="input w-full" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">LinkedIn Profile</label>
                <input value={editForm.linkedin_url} onChange={e => setEditForm(f => ({ ...f, linkedin_url: e.target.value }))} className="input w-full" placeholder="https://linkedin.com/in/johndoe" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Priority Level</label>
                <select value={editForm.priority_level} onChange={e => setEditForm(f => ({ ...f, priority_level: e.target.value }))} className="input w-full">
                  <option value="">-- Select --</option>
                  <option value="p1_job_poster">P1 - Job Poster</option>
                  <option value="p2_hr_ta_recruiter">P2 - HR/Recruiter</option>
                  <option value="p3_hr_manager">P3 - HR Manager</option>
                  <option value="p4_ops_leader">P4 - Ops Leader</option>
                  <option value="p5_functional_manager">P5 - Functional Manager</option>
                </select>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={editForm.is_test}
                  onChange={e => setEditForm(f => ({ ...f, is_test: e.target.checked }))}
                  className="w-4 h-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                />
                <span className="text-sm font-medium text-gray-700">Test Contact</span>
                <span className="text-xs text-gray-400">(bypasses cooldown &amp; fatigue checks)</span>
              </label>
              <div className="flex gap-3 pt-2">
                <button onClick={() => { setShowEditModal(false); setEditingContactId(null) }} className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50">Cancel</button>
                <button
                  onClick={handleEditContact}
                  disabled={!editForm.first_name || !editForm.last_name || !editForm.email || editing}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
                  {editing ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Contacts</h1>
          <p className="text-gray-500 text-sm mt-1">
            {total} contacts total
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          {selectedIds.size > 0 && (
            <>
              {showArchived ? (
                <button
                  onClick={handleRestoreSelected}
                  disabled={deleting}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium disabled:opacity-50">
                  {deleting ? 'Restoring...' : `Restore Selected (${selectedIds.size})`}
                </button>
              ) : (
                <>
                  <button
                    onClick={() => setShowDeleteModal(true)}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium">
                    Archive Selected ({selectedIds.size})
                  </button>
                  {isSuperAdmin && (
                    <button
                      onClick={() => setShowBulkUpdateModal(true)}
                      className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-medium">
                      Bulk Update ({selectedIds.size})
                    </button>
                  )}
                </>
              )}
            </>
          )}
          {isSuperAdmin && (
            <button
              onClick={handleResetTestData}
              disabled={resettingTestData}
              className="px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 font-medium disabled:opacity-50"
            >
              {resettingTestData ? 'Resetting...' : 'Reset Test Data'}
            </button>
          )}
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">
            + Create Contact
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg mb-4 flex justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="font-bold">x</button>
        </div>
      )}

      {success && (
        <div className="bg-green-50 text-green-600 px-4 py-2 rounded-lg mb-4 flex justify-between">
          <span>{success}</span>
          <button onClick={() => setSuccess('')} className="font-bold">x</button>
        </div>
      )}

      {/* Search and Filters */}
      <div className="card p-4 mb-4">
        <div className="flex flex-wrap gap-4 items-center">
          <div className="flex-1 min-w-64">
            <input type="text" placeholder="Search name, email, or company..." value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} className="input w-full" />
          </div>
          <select value={filterPriority} onChange={(e) => { setFilterPriority(e.target.value); setPage(1); }} className="input w-full sm:w-44">
            <option value="">All Priorities</option>
            <option value="p1_job_poster">P1 - Job Poster</option>
            <option value="p2_hr_ta_recruiter">P2 - HR/Recruiter</option>
            <option value="p3_hr_manager">P3 - HR Manager</option>
            <option value="p4_ops_leader">P4 - Ops Leader</option>
            <option value="p5_functional_manager">P5 - Func. Mgr</option>
          </select>
          <select value={filterValidation} onChange={(e) => { setFilterValidation(e.target.value); setPage(1); }} className="input w-full sm:w-40">
            <option value="">All Validation</option>
            <option value="valid">Valid</option>
            <option value="invalid">Invalid</option>
            <option value="pending">Pending</option>
            <option value="unknown">Unknown</option>
          </select>
          <select value={filterSource} onChange={(e) => { setFilterSource(e.target.value); setPage(1); }} className="input w-full sm:w-44">
            <option value="">All Sources</option>
            <option value="mock">Mock</option>
            <option value="apollo">Apollo</option>
            <option value="seamless">Seamless</option>
            <option value="hunter_contact">Hunter.io</option>
            <option value="snovio">Snov.io</option>
            <option value="rocketreach">RocketReach</option>
            <option value="pdl">People Data Labs</option>
            <option value="proxycurl">Proxycurl</option>
          </select>
          <select value={filterOutreachStatus} onChange={(e) => { setFilterOutreachStatus(e.target.value); setPage(1); }} className="input w-full sm:w-40">
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="unsubscribed">Unsubscribed</option>
          </select>
          <select value={filterDataType} onChange={(e) => { setFilterDataType(e.target.value); setPage(1); }} className="input w-full sm:w-40">
            <option value="">All Data Types</option>
            <option value="enriched">Enriched</option>
            <option value="test">Test</option>
          </select>
          <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }} className="input w-36">
            <option value="10">10 per page</option>
            <option value="25">25 per page</option>
            <option value="50">50 per page</option>
            <option value="100">100 per page</option>
          </select>
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
      </div>

      {/* Selection Bar */}
      {selectedIds.size > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 mb-4 flex items-center justify-between">
          <span className="text-sm text-blue-800 font-medium">{selectedIds.size} contact(s) selected</span>
          <button onClick={() => setSelectedIds(new Set())} className="text-sm text-blue-600 hover:text-blue-800">Clear Selection</button>
        </div>
      )}

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 w-10">
                  <input type="checkbox" checked={isAllSelected} onChange={toggleSelectAll} className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                </th>
                {[
                  { key: 'name', label: 'Name' },
                  { key: 'company', label: 'Company' },
                  { key: 'email', label: 'Email' },
                  { key: 'phone', label: 'Phone' },
                  { key: 'linkedin_url', label: 'LinkedIn' },
                  { key: 'timezone', label: 'Timezone' },
                  { key: 'priority', label: 'Priority' },
                  { key: 'validation', label: 'Validation' },
                  { key: 'lead_id', label: 'Lead ID' },
                  { key: 'source', label: 'Source' },
                  { key: 'status', label: 'Status' },
                  { key: 'unsubscribed_at', label: 'Unsub Date' },
                ].map(col => (
                  <th key={col.key} onClick={() => handleSort(col.key)} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700 hover:bg-gray-100 select-none whitespace-nowrap">
                    {col.label}{getSortIcon(col.key)}
                  </th>
                ))}
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {loading ? (
                <tr><td colSpan={14} className="px-4 py-8 text-center text-gray-500">Loading contacts...</td></tr>
              ) : contacts.length === 0 ? (
                <tr><td colSpan={14} className="px-4 py-8 text-center text-gray-500">No contacts found. Run Contact Enrichment pipeline to discover contacts.</td></tr>
              ) : (
                contacts.map((contact) => (
                  <tr key={contact.contact_id} className={"hover:bg-gray-50" + (selectedIds.has(contact.contact_id) ? ' bg-blue-50' : '')}>
                    <td className="px-4 py-3">
                      <input type="checkbox" checked={selectedIds.has(contact.contact_id)} onChange={() => toggleSelect(contact.contact_id)} className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium text-gray-900">
                        {contact.first_name} {contact.last_name}
                        {contact.is_test && <span className="ml-1.5 px-1.5 py-0.5 text-[10px] font-semibold rounded-full bg-teal-100 text-teal-700">TEST</span>}
                      </div>
                      <div className="text-sm text-gray-500">{contact.title || '-'}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{contact.client_name || '-'}</td>
                    <td className="px-4 py-3 text-sm">
                      {contact.email ? (
                        <a href={'mailto:' + contact.email} className="text-blue-600 hover:underline">{contact.email}</a>
                      ) : '-'}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {contact.phone ? (
                        <a href={'tel:' + contact.phone} className="text-blue-600 hover:underline">{contact.phone}</a>
                      ) : '-'}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {contact.linkedin_url ? (
                        <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Profile</a>
                      ) : '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500" title={contact.timezone || ''}>
                      {formatTimezone(contact.timezone)}
                    </td>
                    <td className="px-4 py-3">
                      {contact.priority_level ? (
                        <span className={'px-2 py-1 text-xs rounded-full ' + getPriorityBadge(contact.priority_level)}>
                          {getPriorityLabel(contact.priority_level)}
                        </span>
                      ) : '-'}
                    </td>
                    <td className="px-4 py-3">
                      <span className={'px-2 py-1 text-xs rounded-full ' + getValidationBadge(contact.validation_status || 'unknown')}>
                        {contact.validation_status || 'pending'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {(contact.lead_ids && contact.lead_ids.length > 0) ? (
                        <div className="flex flex-wrap gap-1">
                          {contact.lead_ids.map((lid) => (
                            <Link key={lid} href={`/dashboard/leads/${lid}`} className="text-xs px-2 py-1 rounded bg-purple-50 text-purple-700 font-mono hover:bg-purple-100 cursor-pointer">
                              #{lid}
                            </Link>
                          ))}
                        </div>
                      ) : contact.lead_id ? (
                        <Link href={`/dashboard/leads/${contact.lead_id}`} className="text-xs px-2 py-1 rounded bg-purple-50 text-purple-700 font-mono hover:bg-purple-100 cursor-pointer">
                          #{contact.lead_id}
                        </Link>
                      ) : <span className="text-gray-400">-</span>}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{contact.source || '-'}</td>
                    <td className="px-4 py-3">
                      <span className={'px-2 py-1 text-xs rounded-full ' + getOutreachStatusBadge(contact.outreach_status || 'active')}>
                        {getOutreachStatusLabel(contact.outreach_status || 'active')}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {contact.unsubscribed_at ? new Date(contact.unsubscribed_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => {
                            setEditingContactId(contact.contact_id)
                            setEditForm({
                              first_name: contact.first_name || '',
                              last_name: contact.last_name || '',
                              email: contact.email || '',
                              client_name: contact.client_name || '',
                              title: contact.title || '',
                              phone: contact.phone || '',
                              linkedin_url: contact.linkedin_url || '',
                              location_state: contact.location_state || '',
                              source: contact.source || 'manual',
                              priority_level: contact.priority_level || '',
                              is_test: contact.is_test || false,
                            })
                            setShowEditModal(true)
                          }}
                          className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDeleteSingle(contact.contact_id)}
                          className="text-xs text-red-500 hover:text-red-700 font-medium"
                        >
                          Delete
                        </button>
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
          <div className="text-sm text-gray-500">
            Showing {contacts.length > 0 ? ((page - 1) * pageSize) + 1 : 0} to {Math.min(page * pageSize, total)} of {total} contacts
          </div>
          <div className="flex gap-2 items-center">
            <button onClick={() => setPage(1)} disabled={page === 1} className="px-2 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100">&laquo;</button>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100">Previous</button>
            <span className="px-3 py-1 text-sm text-gray-600">Page {page} of {totalPages}</span>
            <button onClick={() => setPage(p => p + 1)} disabled={page * pageSize >= total} className="px-3 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100">Next</button>
            <button onClick={() => setPage(totalPages)} disabled={page * pageSize >= total} className="px-2 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-100">&raquo;</button>
          </div>
        </div>
      </div>

      {/* Bulk Update Modal */}
      {showBulkUpdateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 p-6 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-bold mb-1">Bulk Update {selectedIds.size} Contact{selectedIds.size > 1 ? 's' : ''}</h2>
            <p className="text-sm text-gray-500 mb-4">Only filled fields will be updated.</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data Type</label>
                <select value={bulkUpdateForm.data_type} onChange={e => setBulkUpdateForm(f => ({ ...f, data_type: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm">
                  <option value="">— No change —</option>
                  <option value="enriched">Enriched</option>
                  <option value="test">Test</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
                <input type="text" value={bulkUpdateForm.first_name} onChange={e => setBulkUpdateForm(f => ({ ...f, first_name: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Leave blank to skip" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                <input type="text" value={bulkUpdateForm.last_name} onChange={e => setBulkUpdateForm(f => ({ ...f, last_name: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Leave blank to skip" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Client Name</label>
                <input type="text" value={bulkUpdateForm.client_name} onChange={e => setBulkUpdateForm(f => ({ ...f, client_name: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Leave blank to skip" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input type="text" value={bulkUpdateForm.email} onChange={e => setBulkUpdateForm(f => ({ ...f, email: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Leave blank to skip" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
                <input type="text" value={bulkUpdateForm.phone} onChange={e => setBulkUpdateForm(f => ({ ...f, phone: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Leave blank to skip" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Timezone</label>
                <input type="text" value={bulkUpdateForm.timezone} onChange={e => setBulkUpdateForm(f => ({ ...f, timezone: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Leave blank to skip" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Lead ID</label>
                <input type="number" value={bulkUpdateForm.lead_id} onChange={e => setBulkUpdateForm(f => ({ ...f, lead_id: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Leave blank to skip" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Outreach Status</label>
                <select value={bulkUpdateForm.outreach_status} onChange={e => setBulkUpdateForm(f => ({ ...f, outreach_status: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm">
                  <option value="">— No change —</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="unsubscribed">Unsubscribed</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Validation Status</label>
                <select value={bulkUpdateForm.validation_status} onChange={e => setBulkUpdateForm(f => ({ ...f, validation_status: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm">
                  <option value="">— No change —</option>
                  <option value="valid">Valid</option>
                  <option value="invalid">Invalid</option>
                  <option value="unknown">Unknown</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">Priority Level</label>
                <select value={bulkUpdateForm.priority_level} onChange={e => setBulkUpdateForm(f => ({ ...f, priority_level: e.target.value }))} className="w-full border rounded-lg px-3 py-2 text-sm">
                  <option value="">— No change —</option>
                  <option value="P1">P1 - Job Poster</option>
                  <option value="P2">P2 - Direct Report</option>
                  <option value="P3">P3 - Department Head</option>
                  <option value="P4">P4 - HR/Recruiting</option>
                  <option value="P5">P5 - Functional Manager</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => { setShowBulkUpdateModal(false); setBulkUpdateForm({ data_type: '', first_name: '', last_name: '', client_name: '', email: '', phone: '', timezone: '', lead_id: '', outreach_status: '', validation_status: '', priority_level: '' }) }} className="px-4 py-2 text-sm border rounded-lg hover:bg-gray-50">Cancel</button>
              <button onClick={handleBulkUpdate} disabled={bulkUpdating || Object.values(bulkUpdateForm).every(v => v === '')} className="px-4 py-2 text-sm text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                {bulkUpdating ? 'Updating...' : 'Update'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
