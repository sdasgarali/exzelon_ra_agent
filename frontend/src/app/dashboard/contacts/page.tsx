'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { contactsApi, api } from '@/lib/api'

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
  location_state: string
  priority_level: string
  validation_status: string
  source: string
  outreach_status: string
  unsubscribed_at: string | null
}

const EMPTY_FORM = {
  first_name: '', last_name: '', email: '', client_name: '',
  title: '', phone: '', location_state: '', source: 'manual',
  priority_level: '',
}

export default function ContactsPage() {
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
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortBy, setSortBy] = useState('')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  // Multi-select & delete
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Create contact modal
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createForm, setCreateForm] = useState({ ...EMPTY_FORM })
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    fetchContacts()
  }, [page, pageSize, debouncedSearch, filterPriority, filterValidation, filterSource, filterOutreachStatus, showArchived, sortBy, sortOrder])

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
              <div className="grid grid-cols-2 gap-4">
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
              <div className="grid grid-cols-2 gap-4">
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

      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Contacts</h1>
          <p className="text-gray-500 text-sm mt-1">
            {total} contacts total
          </p>
        </div>
        <div className="flex gap-3">
          {selectedIds.size > 0 && (
            <button
              onClick={() => setShowDeleteModal(true)}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium">
              Archive Selected ({selectedIds.size})
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
          <select value={filterPriority} onChange={(e) => { setFilterPriority(e.target.value); setPage(1); }} className="input w-44">
            <option value="">All Priorities</option>
            <option value="p1_job_poster">P1 - Job Poster</option>
            <option value="p2_hr_ta_recruiter">P2 - HR/Recruiter</option>
            <option value="p3_hr_manager">P3 - HR Manager</option>
            <option value="p4_ops_leader">P4 - Ops Leader</option>
            <option value="p5_functional_manager">P5 - Func. Mgr</option>
          </select>
          <select value={filterValidation} onChange={(e) => { setFilterValidation(e.target.value); setPage(1); }} className="input w-40">
            <option value="">All Validation</option>
            <option value="valid">Valid</option>
            <option value="invalid">Invalid</option>
            <option value="pending">Pending</option>
            <option value="unknown">Unknown</option>
          </select>
          <select value={filterSource} onChange={(e) => { setFilterSource(e.target.value); setPage(1); }} className="input w-44">
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
          <select value={filterOutreachStatus} onChange={(e) => { setFilterOutreachStatus(e.target.value); setPage(1); }} className="input w-40">
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="unsubscribed">Unsubscribed</option>
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
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {loading ? (
                <tr><td colSpan={11} className="px-4 py-8 text-center text-gray-500">Loading contacts...</td></tr>
              ) : contacts.length === 0 ? (
                <tr><td colSpan={11} className="px-4 py-8 text-center text-gray-500">No contacts found. Run Contact Enrichment pipeline to discover contacts.</td></tr>
              ) : (
                contacts.map((contact) => (
                  <tr key={contact.contact_id} className={"hover:bg-gray-50" + (selectedIds.has(contact.contact_id) ? ' bg-blue-50' : '')}>
                    <td className="px-4 py-3">
                      <input type="checkbox" checked={selectedIds.has(contact.contact_id)} onChange={() => toggleSelect(contact.contact_id)} className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium text-gray-900">{contact.first_name} {contact.last_name}</div>
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
    </div>
  )
}
