'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { companyExclusionsApi, getApiError } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import {
  Building2, Search, Plus, Trash2, CheckSquare, Square,
  ChevronLeft, ChevronRight, X, Upload, Filter, ToggleLeft, ToggleRight,
  ArrowLeft, AlertCircle, Check, Edit2, Save,
} from 'lucide-react'

interface CompanyExclusion {
  exclusion_id: number
  tenant_id: number
  lob_id: number | null
  company_name: string
  company_name_normalized: string
  category: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

const PAGE_SIZE = 50

export default function ExcludedCompaniesPage() {
  const router = useRouter()
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin'

  const [exclusions, setExclusions] = useState<CompanyExclusion[]>([])
  const [loading, setLoading] = useState(true)
  const [totalCount, setTotalCount] = useState(0)
  const [activeCount, setActiveCount] = useState(0)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [categories, setCategories] = useState<string[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [allSelected, setAllSelected] = useState(false)

  // Add/Edit state
  const [showAddModal, setShowAddModal] = useState(false)
  const [showBulkModal, setShowBulkModal] = useState(false)
  const [newCompanyName, setNewCompanyName] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editCategory, setEditCategory] = useState('')

  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)

  // Bulk import
  const [bulkText, setBulkText] = useState('')
  const [bulkCategory, setBulkCategory] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const xlsxInputRef = useRef<HTMLInputElement>(null)

  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    if (user && !isAdmin) {
      router.replace('/dashboard')
    }
  }, [user, isAdmin, router])

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      const params: Record<string, any> = {
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
      }
      if (search) params.search = search
      if (categoryFilter) params.category = categoryFilter

      const [items, countData, cats] = await Promise.all([
        companyExclusionsApi.list(params),
        companyExclusionsApi.count(search ? { search } : categoryFilter ? { category: categoryFilter } : {}),
        companyExclusionsApi.categories(),
      ])
      setExclusions(items)
      setTotalCount(countData.total)
      setActiveCount(countData.active)
      setCategories(cats)
      setSelectedIds(new Set())
      setAllSelected(false)
    } catch (err) {
      setError(getApiError(err, 'Failed to load exclusions'))
    } finally {
      setLoading(false)
    }
  }, [page, search, categoryFilter])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleSearchChange = (val: string) => {
    setSearchInput(val)
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current)
    searchTimeoutRef.current = setTimeout(() => {
      setSearch(val)
      setPage(0)
    }, 300)
  }

  const clearMessages = () => { setError(''); setSuccess('') }

  // Toggle select all on current page
  const handleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(new Set())
      setAllSelected(false)
    } else {
      setSelectedIds(new Set(exclusions.map(e => e.exclusion_id)))
      setAllSelected(true)
    }
  }

  const handleSelectOne = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Toggle active/inactive for one row
  const handleToggleActive = async (item: CompanyExclusion) => {
    clearMessages()
    try {
      await companyExclusionsApi.update(item.exclusion_id, { is_active: !item.is_active })
      setExclusions(prev =>
        prev.map(e => e.exclusion_id === item.exclusion_id ? { ...e, is_active: !e.is_active } : e)
      )
    } catch (err) {
      setError(getApiError(err, 'Failed to toggle'))
    }
  }

  // Toggle ALL active (select all / unselect all)
  const handleToggleAllActive = async (active: boolean) => {
    clearMessages()
    setSaving(true)
    try {
      const payload: any = { is_active: active }
      if (categoryFilter) payload.category = categoryFilter
      const result = await companyExclusionsApi.toggleAll(payload)
      setSuccess(`${result.updated} exclusions ${active ? 'activated' : 'deactivated'}`)
      await fetchData()
    } catch (err) {
      setError(getApiError(err, 'Failed to toggle all'))
    } finally {
      setSaving(false)
    }
  }

  // Add single company
  const handleAddCompany = async () => {
    if (!newCompanyName.trim()) return
    clearMessages()
    setSaving(true)
    try {
      await companyExclusionsApi.create({
        company_name: newCompanyName.trim(),
        category: newCategory.trim() || undefined,
      })
      setSuccess(`Added "${newCompanyName.trim()}" to exclusion list`)
      setNewCompanyName('')
      setNewCategory('')
      setShowAddModal(false)
      await fetchData()
    } catch (err) {
      setError(getApiError(err, 'Failed to add company'))
    } finally {
      setSaving(false)
    }
  }

  // Bulk import
  const handleBulkImport = async () => {
    const lines = bulkText.split('\n').map(l => l.trim()).filter(Boolean)
    if (lines.length === 0) return
    clearMessages()
    setSaving(true)
    try {
      const companies = lines.map(name => ({
        company_name: name,
        category: bulkCategory.trim() || undefined,
      }))
      const result = await companyExclusionsApi.bulkCreate(companies)
      setSuccess(`Imported: ${result.created} added, ${result.skipped} duplicates skipped`)
      setBulkText('')
      setBulkCategory('')
      setShowBulkModal(false)
      await fetchData()
    } catch (err) {
      setError(getApiError(err, 'Failed to import'))
    } finally {
      setSaving(false)
    }
  }

  // Edit inline
  const handleStartEdit = (item: CompanyExclusion) => {
    setEditingId(item.exclusion_id)
    setEditName(item.company_name)
    setEditCategory(item.category || '')
  }

  const handleSaveEdit = async () => {
    if (editingId === null) return
    clearMessages()
    setSaving(true)
    try {
      await companyExclusionsApi.update(editingId, {
        company_name: editName.trim(),
        category: editCategory.trim() || undefined,
      })
      setEditingId(null)
      setSuccess('Updated successfully')
      await fetchData()
    } catch (err) {
      setError(getApiError(err, 'Failed to update'))
    } finally {
      setSaving(false)
    }
  }

  // Delete single
  const handleDelete = async (item: CompanyExclusion) => {
    if (!confirm(`Remove "${item.company_name}" from exclusion list?`)) return
    clearMessages()
    try {
      await companyExclusionsApi.delete(item.exclusion_id)
      setSuccess(`Removed "${item.company_name}"`)
      await fetchData()
    } catch (err) {
      setError(getApiError(err, 'Failed to delete'))
    }
  }

  // Bulk delete selected
  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return
    if (!confirm(`Remove ${selectedIds.size} selected companies from exclusion list?`)) return
    clearMessages()
    setSaving(true)
    try {
      const result = await companyExclusionsApi.bulkDelete(Array.from(selectedIds))
      setSuccess(`Removed ${result.deleted} exclusions`)
      setSelectedIds(new Set())
      await fetchData()
    } catch (err) {
      setError(getApiError(err, 'Failed to delete'))
    } finally {
      setSaving(false)
    }
  }

  // CSV file import
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result as string
      if (!text) return
      // Parse CSV: expect first column to be company name
      const lines = text.split('\n').slice(1) // skip header
        .map(line => {
          const cols = line.split(',')
          return cols[0]?.replace(/"/g, '').trim()
        })
        .filter(Boolean)
      setBulkText(lines.join('\n'))
      setShowBulkModal(true)
    }
    reader.readAsText(file)
    // Reset input so same file can be re-selected
    e.target.value = ''
  }

  // Excel (.xlsx) file upload
  const handleXlsxUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    clearMessages()
    setSaving(true)
    try {
      const result = await companyExclusionsApi.uploadXlsx(file)
      setSuccess(`Excel import: ${result.created} added, ${result.skipped} duplicates skipped from "${result.filename}"`)
      await fetchData()
    } catch (err) {
      setError(getApiError(err, 'Failed to import Excel file'))
    } finally {
      setSaving(false)
      e.target.value = ''
    }
  }

  const totalPages = Math.ceil(totalCount / PAGE_SIZE)

  if (!isAdmin) return null

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push('/dashboard/settings')}
            className="p-2 hover:bg-zinc-800 rounded-lg transition"
          >
            <ArrowLeft className="w-5 h-5 text-zinc-400" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Building2 className="w-6 h-6 text-red-400" />
              Excluded Companies
            </h1>
            <p className="text-sm text-zinc-400 mt-1">
              Leads from these companies will be skipped during sourcing. Manage the blocklist for Staffing LOBs.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="bg-zinc-800 px-3 py-1.5 rounded-lg text-zinc-300">
            {totalCount} total
          </span>
          <span className="bg-green-900/50 px-3 py-1.5 rounded-lg text-green-300">
            {activeCount} active
          </span>
          <span className="bg-zinc-700/50 px-3 py-1.5 rounded-lg text-zinc-400">
            {totalCount - activeCount} bypassed
          </span>
        </div>
      </div>

      {/* Messages */}
      {error && (
        <div className="bg-red-900/50 border border-red-700 text-red-200 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
          <button onClick={() => setError('')} className="ml-auto"><X className="w-4 h-4" /></button>
        </div>
      )}
      {success && (
        <div className="bg-green-900/50 border border-green-700 text-green-200 px-4 py-3 rounded-lg flex items-center gap-2">
          <Check className="w-4 h-4 shrink-0" />
          {success}
          <button onClick={() => setSuccess('')} className="ml-auto"><X className="w-4 h-4" /></button>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            placeholder="Search companies..."
            value={searchInput}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="w-full pl-9 pr-8 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {searchInput && (
            <button
              onClick={() => { setSearchInput(''); setSearch(''); setPage(0) }}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              <X className="w-4 h-4 text-zinc-500 hover:text-zinc-300" />
            </button>
          )}
        </div>

        {/* Category filter */}
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <select
            value={categoryFilter}
            onChange={(e) => { setCategoryFilter(e.target.value); setPage(0) }}
            className="pl-9 pr-8 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Categories</option>
            {categories.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        {/* Actions */}
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition"
        >
          <Plus className="w-4 h-4" /> Add Company
        </button>
        <button
          onClick={() => setShowBulkModal(true)}
          className="flex items-center gap-1.5 px-3 py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm rounded-lg transition"
        >
          <Upload className="w-4 h-4" /> Bulk Import
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.txt"
          className="hidden"
          onChange={handleFileUpload}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1.5 px-3 py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm rounded-lg transition"
          title="Import from CSV file"
        >
          <Upload className="w-4 h-4" /> CSV
        </button>
        <input
          ref={xlsxInputRef}
          type="file"
          accept=".xlsx,.xls"
          className="hidden"
          onChange={handleXlsxUpload}
        />
        <button
          onClick={() => xlsxInputRef.current?.click()}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-2 bg-emerald-700 hover:bg-emerald-600 text-white text-sm rounded-lg transition disabled:opacity-50"
          title="Import from Excel (.xlsx) file"
        >
          <Upload className="w-4 h-4" /> Excel
        </button>

        <div className="border-l border-zinc-700 h-8 mx-1" />

        {/* Select All / Deselect All toggle */}
        <button
          onClick={() => handleToggleAllActive(true)}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-2 bg-green-700 hover:bg-green-600 text-white text-sm rounded-lg transition disabled:opacity-50"
          title="Activate all exclusions (block all listed companies)"
        >
          <ToggleRight className="w-4 h-4" /> Select All
        </button>
        <button
          onClick={() => handleToggleAllActive(false)}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-2 bg-amber-700 hover:bg-amber-600 text-white text-sm rounded-lg transition disabled:opacity-50"
          title="Deactivate all exclusions (bypass = allow all companies)"
        >
          <ToggleLeft className="w-4 h-4" /> Unselect All
        </button>

        {selectedIds.size > 0 && (
          <button
            onClick={handleBulkDelete}
            disabled={saving}
            className="flex items-center gap-1.5 px-3 py-2 bg-red-700 hover:bg-red-600 text-white text-sm rounded-lg transition disabled:opacity-50"
          >
            <Trash2 className="w-4 h-4" /> Delete ({selectedIds.size})
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-zinc-800/50 text-left">
                <th className="px-4 py-3 w-10">
                  <button onClick={handleSelectAll} className="text-zinc-400 hover:text-white">
                    {allSelected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                  </button>
                </th>
                <th className="px-4 py-3 text-xs font-medium text-zinc-400 uppercase tracking-wider">Company Name</th>
                <th className="px-4 py-3 text-xs font-medium text-zinc-400 uppercase tracking-wider">Category</th>
                <th className="px-4 py-3 text-xs font-medium text-zinc-400 uppercase tracking-wider text-center">Status</th>
                <th className="px-4 py-3 text-xs font-medium text-zinc-400 uppercase tracking-wider text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-zinc-500">
                    <div className="flex items-center justify-center gap-2">
                      <div className="w-4 h-4 border-2 border-zinc-500 border-t-transparent rounded-full animate-spin" />
                      Loading...
                    </div>
                  </td>
                </tr>
              ) : exclusions.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-zinc-500">
                    {search || categoryFilter
                      ? 'No companies match your filters'
                      : 'No excluded companies yet. Add companies to block them from lead sourcing.'}
                  </td>
                </tr>
              ) : (
                exclusions.map((item) => (
                  <tr key={item.exclusion_id} className="hover:bg-zinc-800/30 transition">
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleSelectOne(item.exclusion_id)}
                        className="text-zinc-400 hover:text-white"
                      >
                        {selectedIds.has(item.exclusion_id)
                          ? <CheckSquare className="w-4 h-4 text-blue-400" />
                          : <Square className="w-4 h-4" />}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      {editingId === item.exclusion_id ? (
                        <input
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          className="w-full px-2 py-1 bg-zinc-800 border border-zinc-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                          autoFocus
                        />
                      ) : (
                        <span className="text-white text-sm font-medium">{item.company_name}</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {editingId === item.exclusion_id ? (
                        <input
                          value={editCategory}
                          onChange={(e) => setEditCategory(e.target.value)}
                          placeholder="Category"
                          className="w-full px-2 py-1 bg-zinc-800 border border-zinc-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                      ) : (
                        item.category && (
                          <span className={`inline-flex px-2 py-0.5 text-xs rounded-full ${
                            item.category === 'IT Staffing' ? 'bg-blue-900/50 text-blue-300' :
                            item.category === 'Healthcare Staffing' ? 'bg-emerald-900/50 text-emerald-300' :
                            item.category === 'General Staffing' ? 'bg-purple-900/50 text-purple-300' :
                            'bg-zinc-700 text-zinc-300'
                          }`}>
                            {item.category}
                          </span>
                        )
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => handleToggleActive(item)}
                        className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-full transition ${
                          item.is_active
                            ? 'bg-red-900/40 text-red-300 hover:bg-red-900/60'
                            : 'bg-zinc-700/50 text-zinc-400 hover:bg-zinc-700'
                        }`}
                        title={item.is_active ? 'Active — company is blocked. Click to bypass.' : 'Bypassed — company is NOT blocked. Click to activate.'}
                      >
                        {item.is_active ? (
                          <><ToggleRight className="w-3.5 h-3.5" /> Blocked</>
                        ) : (
                          <><ToggleLeft className="w-3.5 h-3.5" /> Bypassed</>
                        )}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-1">
                        {editingId === item.exclusion_id ? (
                          <>
                            <button
                              onClick={handleSaveEdit}
                              disabled={saving}
                              className="p-1.5 text-green-400 hover:bg-green-900/30 rounded transition"
                              title="Save"
                            >
                              <Save className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => setEditingId(null)}
                              className="p-1.5 text-zinc-400 hover:bg-zinc-700 rounded transition"
                              title="Cancel"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              onClick={() => handleStartEdit(item)}
                              className="p-1.5 text-zinc-400 hover:text-blue-400 hover:bg-zinc-800 rounded transition"
                              title="Edit"
                            >
                              <Edit2 className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDelete(item)}
                              className="p-1.5 text-zinc-400 hover:text-red-400 hover:bg-zinc-800 rounded transition"
                              title="Delete"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </>
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
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-zinc-800">
            <span className="text-sm text-zinc-400">
              Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalCount)} of {totalCount}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="p-1.5 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded disabled:opacity-30 disabled:cursor-not-allowed transition"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-sm text-zinc-400 px-2">
                Page {page + 1} of {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="p-1.5 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded disabled:opacity-30 disabled:cursor-not-allowed transition"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Add Company Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Add Excluded Company</h2>
              <button onClick={() => setShowAddModal(false)} className="text-zinc-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-zinc-400 mb-1">Company Name *</label>
                <input
                  value={newCompanyName}
                  onChange={(e) => setNewCompanyName(e.target.value)}
                  placeholder="e.g. Robert Half"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  autoFocus
                  onKeyDown={(e) => e.key === 'Enter' && handleAddCompany()}
                />
              </div>
              <div>
                <label className="block text-sm text-zinc-400 mb-1">Category (optional)</label>
                <input
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  placeholder="e.g. IT Staffing, Healthcare Staffing"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-white transition"
              >
                Cancel
              </button>
              <button
                onClick={handleAddCompany}
                disabled={!newCompanyName.trim() || saving}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg disabled:opacity-50 transition"
              >
                {saving ? 'Adding...' : 'Add Company'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Import Modal */}
      {showBulkModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Bulk Import Companies</h2>
              <button onClick={() => setShowBulkModal(false)} className="text-zinc-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-zinc-400 mb-1">
                  Company Names (one per line)
                </label>
                <textarea
                  value={bulkText}
                  onChange={(e) => setBulkText(e.target.value)}
                  placeholder={"Robert Half\nRandstad USA\nAdecco USA\n..."}
                  rows={10}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-zinc-500 mt-1">
                  {bulkText.split('\n').filter(l => l.trim()).length} companies to import
                </p>
              </div>
              <div>
                <label className="block text-sm text-zinc-400 mb-1">Category for all (optional)</label>
                <input
                  value={bulkCategory}
                  onChange={(e) => setBulkCategory(e.target.value)}
                  placeholder="e.g. General Staffing"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowBulkModal(false)}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-white transition"
              >
                Cancel
              </button>
              <button
                onClick={handleBulkImport}
                disabled={!bulkText.trim() || saving}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg disabled:opacity-50 transition"
              >
                {saving ? 'Importing...' : 'Import'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
