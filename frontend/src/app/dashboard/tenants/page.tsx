'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/store'
import { tenantsApi } from '@/lib/api'
import { Modal } from '@/components/modal'
import type { TenantSummary, TenantDetail, TenantUser } from '@/types/api'
import {
  Building2,
  Search,
  Eye,
  Pencil,
  Power,
  Users,
  FileText,
  Mail,
  Inbox,
  Zap,
  RefreshCw,
  AlertTriangle,
  Plus,
  MapPin,
  Phone,
  AtSign,
} from 'lucide-react'

const PLAN_COLORS: Record<string, string> = {
  starter: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  professional: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  enterprise: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
}

const ROLE_COLORS: Record<string, string> = {
  super_admin: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  admin: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  operator: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  viewer: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
}

const LOB_TYPE_LABELS: Record<string, string> = {
  staffing: 'Staffing & Recruiting',
  rcm: 'Revenue Cycle Management',
  software_dev: 'Software Development',
  ai_services: 'AI & Agent Services',
  digital_marketing: 'Digital Marketing',
}

const LOB_TYPE_COLORS: Record<string, string> = {
  staffing: '#1A3C6E',
  rcm: '#10B981',
  software_dev: '#6366F1',
  ai_services: '#F59E0B',
  digital_marketing: '#EC4899',
}

export default function TenantManagementPage() {
  const router = useRouter()
  const { isSuperAdmin, startImpersonation } = useAuthStore()

  const [tenants, setTenants] = useState<TenantSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Detail modal
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailTenant, setDetailTenant] = useState<TenantDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailLobTypes, setDetailLobTypes] = useState<string[]>([])

  // Edit modal
  const [editOpen, setEditOpen] = useState(false)
  const [editTenant, setEditTenant] = useState<TenantDetail | null>(null)
  const [editForm, setEditForm] = useState({
    name: '',
    domain: '',
    plan: 'starter',
    is_active: true,
    max_users: 5,
    max_mailboxes: 3,
    max_contacts: 1000,
    max_campaigns: 5,
    max_leads: 5000,
    website: '',
    industry: '',
    company_address: '',
    phone: '',
    contact_email: '',
  })
  const [editFeatures, setEditFeatures] = useState({
    feature_email_validation_enabled: true,
    feature_campaigns_enabled: true,
    feature_outreach_enabled: true,
    feature_export_mailmerge_enabled: true,
  })
  const [editSaving, setEditSaving] = useState(false)
  const [editLobAssignments, setEditLobAssignments] = useState<string[]>([])
  const [availableLobTypes, setAvailableLobTypes] = useState<string[]>([])

  // Create modal
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState({
    name: '',
    domain: '',
    plan: 'starter',
    website: '',
    industry: '',
    company_address: '',
    phone: '',
    contact_email: '',
    max_users: 3,
    max_mailboxes: 0,
    max_contacts: 0,
    max_campaigns: 0,
    max_leads: 0,
  })
  const [createSaving, setCreateSaving] = useState(false)

  // Deactivate confirmation
  const [deactivateId, setDeactivateId] = useState<number | null>(null)
  const [deactivateName, setDeactivateName] = useState('')
  const [deactivating, setDeactivating] = useState(false)

  // SA guard
  useEffect(() => {
    if (!isSuperAdmin()) {
      router.push('/dashboard')
    }
  }, [isSuperAdmin, router])

  const fetchTenants = useCallback(async () => {
    try {
      setLoading(true)
      const data = await tenantsApi.list({ search: search || undefined, limit: 200 })
      setTenants(data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load tenants')
    } finally {
      setLoading(false)
    }
  }, [search])

  useEffect(() => {
    if (isSuperAdmin()) {
      fetchTenants()
    }
  }, [fetchTenants, isSuperAdmin])

  // Auto-clear messages
  useEffect(() => {
    if (success) {
      const t = setTimeout(() => setSuccess(''), 4000)
      return () => clearTimeout(t)
    }
  }, [success])
  useEffect(() => {
    if (error) {
      const t = setTimeout(() => setError(''), 6000)
      return () => clearTimeout(t)
    }
  }, [error])

  const handleViewDetail = async (tenantId: number) => {
    try {
      setDetailLoading(true)
      setDetailOpen(true)
      const [data, lobAssignments] = await Promise.all([
        tenantsApi.get(tenantId),
        tenantsApi.getLobAssignments(tenantId),
      ])
      setDetailTenant(data)
      setDetailLobTypes(lobAssignments.assigned_lob_types || [])
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load tenant detail')
      setDetailOpen(false)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleOpenEdit = async (tenantId: number) => {
    try {
      const [data, features, lobAssignments] = await Promise.all([
        tenantsApi.get(tenantId),
        tenantsApi.getFeatures(tenantId),
        tenantsApi.getLobAssignments(tenantId),
      ])
      setEditTenant(data)
      setEditForm({
        name: data.name,
        domain: data.domain || '',
        plan: data.plan,
        is_active: data.is_active,
        max_users: data.max_users,
        max_mailboxes: data.max_mailboxes,
        max_contacts: data.max_contacts,
        max_campaigns: data.max_campaigns,
        max_leads: data.max_leads,
        website: data.website || '',
        industry: data.industry || '',
        company_address: data.company_address || '',
        phone: data.phone || '',
        contact_email: data.contact_email || '',
      })
      setEditFeatures({
        feature_email_validation_enabled: features.feature_email_validation_enabled ?? true,
        feature_campaigns_enabled: features.feature_campaigns_enabled ?? true,
        feature_outreach_enabled: features.feature_outreach_enabled ?? true,
        feature_export_mailmerge_enabled: features.feature_export_mailmerge_enabled ?? true,
      })
      setEditLobAssignments(lobAssignments.assigned_lob_types || [])
      setAvailableLobTypes(lobAssignments.available_lob_types || [])
      setEditOpen(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load tenant for editing')
    }
  }

  const handleSaveEdit = async () => {
    if (!editTenant) return
    try {
      setEditSaving(true)
      const promises: Promise<any>[] = [
        tenantsApi.update(editTenant.tenant_id, editForm),
        tenantsApi.updateFeatures(editTenant.tenant_id, editFeatures),
      ]
      if (editLobAssignments.length > 0) {
        promises.push(tenantsApi.updateLobAssignments(editTenant.tenant_id, editLobAssignments))
      }
      await Promise.all(promises)
      setSuccess(`Tenant "${editForm.name}" updated successfully`)
      setEditOpen(false)
      fetchTenants()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update tenant')
    } finally {
      setEditSaving(false)
    }
  }

  const handleDeactivate = async () => {
    if (!deactivateId) return
    try {
      setDeactivating(true)
      await tenantsApi.deactivate(deactivateId)
      setSuccess(`Tenant "${deactivateName}" deactivated`)
      setDeactivateId(null)
      fetchTenants()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to deactivate tenant')
    } finally {
      setDeactivating(false)
    }
  }

  const handleImpersonate = async (tenant: TenantSummary) => {
    try {
      const result = await tenantsApi.impersonate(tenant.tenant_id)
      startImpersonation(result.tenant_id, result.tenant_name, tenant.plan)
      setSuccess(`Now viewing as: ${result.tenant_name}`)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to impersonate tenant')
    }
  }

  const handleCreateTenant = async () => {
    if (!createForm.name.trim()) {
      setError('Tenant name is required')
      return
    }
    try {
      setCreateSaving(true)
      await tenantsApi.create(createForm)
      setSuccess(`Tenant "${createForm.name}" created successfully`)
      setCreateOpen(false)
      setCreateForm({
        name: '', domain: '', plan: 'starter', website: '', industry: '',
        company_address: '', phone: '', contact_email: '',
        max_users: 3, max_mailboxes: 0, max_contacts: 0, max_campaigns: 0, max_leads: 0,
      })
      fetchTenants()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create tenant')
    } finally {
      setCreateSaving(false)
    }
  }

  const activeTenants = tenants.filter(t => t.is_active).length

  if (!isSuperAdmin()) return null

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <Building2 className="w-7 h-7 text-red-400" />
            Tenant Management
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {tenants.length} total tenants, {activeTenants} active
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add New Tenant
          </button>
          <button
            onClick={fetchTenants}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 px-4 py-3 rounded-lg text-sm">
          {success}
        </div>
      )}

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search tenants by name or slug..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
        />
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Tenant</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Registered Domain</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Plan</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Industry</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Website</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Users</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Leads</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Contacts</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Mailboxes</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Campaigns</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Created</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {loading ? (
                <tr>
                  <td colSpan={13} className="px-4 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                    Loading tenants...
                  </td>
                </tr>
              ) : tenants.length === 0 ? (
                <tr>
                  <td colSpan={13} className="px-4 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                    No tenants found
                  </td>
                </tr>
              ) : (
                tenants.map((t) => (
                  <tr key={t.tenant_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium text-gray-900 dark:text-white">{t.name}</div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">{t.slug}</div>
                    </td>
                    <td className="px-4 py-3 text-sm font-mono text-gray-700 dark:text-gray-300">
                      {t.domain || <span className="text-gray-400 font-sans">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${PLAN_COLORS[t.plan] || PLAN_COLORS.starter}`}>
                        {t.plan}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 capitalize">
                      {t.industry || <span className="text-gray-400">—</span>}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                      {t.website ? (
                        <a href={t.website} target="_blank" rel="noopener noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline truncate block max-w-[160px]">
                          {t.website.replace(/^https?:\/\//, '')}
                        </a>
                      ) : <span className="text-gray-400">—</span>}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        t.is_active
                          ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
                          : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
                      }`}>
                        {t.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center text-sm text-gray-700 dark:text-gray-300">{t.user_count}</td>
                    <td className="px-4 py-3 text-center text-sm text-gray-700 dark:text-gray-300">{t.lead_count.toLocaleString()}</td>
                    <td className="px-4 py-3 text-center text-sm text-gray-700 dark:text-gray-300">{t.contact_count.toLocaleString()}</td>
                    <td className="px-4 py-3 text-center text-sm text-gray-700 dark:text-gray-300">{t.mailbox_count}</td>
                    <td className="px-4 py-3 text-center text-sm text-gray-700 dark:text-gray-300">{t.campaign_count}</td>
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      {t.created_at ? new Date(t.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleViewDetail(t.tenant_id)}
                          className="p-1.5 text-gray-500 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
                          title="View details"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleOpenEdit(t.tenant_id)}
                          className="p-1.5 text-gray-500 hover:text-amber-600 dark:text-gray-400 dark:hover:text-amber-400 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
                          title="Edit tenant"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleImpersonate(t)}
                          className="p-1.5 text-gray-500 hover:text-purple-600 dark:text-gray-400 dark:hover:text-purple-400 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
                          title="View as this tenant"
                        >
                          <Users className="w-4 h-4" />
                        </button>
                        {t.tenant_id !== 1 && t.is_active && (
                          <button
                            onClick={() => { setDeactivateId(t.tenant_id); setDeactivateName(t.name) }}
                            className="p-1.5 text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
                            title="Deactivate tenant"
                          >
                            <Power className="w-4 h-4" />
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
      </div>

      {/* Detail Modal */}
      <Modal open={detailOpen} onClose={() => { setDetailOpen(false); setDetailTenant(null) }} title={detailTenant?.name || 'Tenant Details'} size="xl">
        {detailLoading ? (
          <div className="py-12 text-center text-gray-500">Loading...</div>
        ) : detailTenant ? (
          <div className="space-y-6">
            {/* Stats grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <StatCard icon={Users} label="Users" value={detailTenant.user_count} limit={detailTenant.max_users} color="text-blue-500" />
              <StatCard icon={FileText} label="Leads" value={detailTenant.lead_count} limit={detailTenant.max_leads} color="text-indigo-500" />
              <StatCard icon={Mail} label="Contacts" value={detailTenant.contact_count} limit={detailTenant.max_contacts} color="text-violet-500" />
              <StatCard icon={Inbox} label="Mailboxes" value={detailTenant.mailbox_count} limit={detailTenant.max_mailboxes} color="text-purple-500" />
              <StatCard icon={Zap} label="Campaigns" value={detailTenant.campaign_count} limit={detailTenant.max_campaigns} color="text-amber-500" />
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                <div className="text-xs text-gray-500 dark:text-gray-400 uppercase mb-1">Plan</div>
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-sm font-semibold capitalize ${PLAN_COLORS[detailTenant.plan] || PLAN_COLORS.starter}`}>
                  {detailTenant.plan}
                </span>
              </div>
            </div>

            {/* Contact Info */}
            {(detailTenant.company_address || detailTenant.phone || detailTenant.contact_email || detailTenant.website) && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Contact Information</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {detailTenant.company_address && (
                    <div className="flex items-start gap-2">
                      <MapPin className="w-4 h-4 text-gray-400 mt-0.5 shrink-0" />
                      <div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 uppercase">Address</div>
                        <div className="text-sm text-gray-900 dark:text-white">{detailTenant.company_address}</div>
                      </div>
                    </div>
                  )}
                  {detailTenant.phone && (
                    <div className="flex items-start gap-2">
                      <Phone className="w-4 h-4 text-gray-400 mt-0.5 shrink-0" />
                      <div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 uppercase">Phone</div>
                        <a href={`tel:${detailTenant.phone}`} className="text-sm text-blue-600 dark:text-blue-400 hover:underline">{detailTenant.phone}</a>
                      </div>
                    </div>
                  )}
                  {detailTenant.contact_email && (
                    <div className="flex items-start gap-2">
                      <AtSign className="w-4 h-4 text-gray-400 mt-0.5 shrink-0" />
                      <div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 uppercase">Email</div>
                        <a href={`mailto:${detailTenant.contact_email}`} className="text-sm text-blue-600 dark:text-blue-400 hover:underline">{detailTenant.contact_email}</a>
                      </div>
                    </div>
                  )}
                  {detailTenant.website && (
                    <div className="flex items-start gap-2">
                      <Building2 className="w-4 h-4 text-gray-400 mt-0.5 shrink-0" />
                      <div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 uppercase">Website</div>
                        <a href={detailTenant.website} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 dark:text-blue-400 hover:underline">{detailTenant.website.replace(/^https?:\/\//, '')}</a>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* LOB Assignments */}
            {detailLobTypes.length > 0 && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">LOB Assignments</h3>
                <div className="flex flex-wrap gap-2">
                  {detailLobTypes.map((lt) => (
                    <span
                      key={lt}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white"
                    >
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: LOB_TYPE_COLORS[lt] || '#8B5CF6' }}
                      />
                      {LOB_TYPE_LABELS[lt] || lt}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Users table */}
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Users ({detailTenant.users.length})</h3>
              <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-lg">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-900/50">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Email</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Name</th>
                      <th className="px-3 py-2 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Role</th>
                      <th className="px-3 py-2 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Last Login</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {detailTenant.users.map((u: TenantUser) => (
                      <tr key={u.user_id}>
                        <td className="px-3 py-2 text-sm text-gray-900 dark:text-white">{u.email}</td>
                        <td className="px-3 py-2 text-sm text-gray-700 dark:text-gray-300">{u.full_name || '—'}</td>
                        <td className="px-3 py-2 text-center">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${ROLE_COLORS[u.role] || ROLE_COLORS.viewer}`}>
                            {u.role.replace('_', ' ')}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-center">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                            u.is_active && u.is_verified
                              ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
                              : !u.is_verified
                              ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300'
                              : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
                          }`}>
                            {!u.is_verified ? 'Unverified' : u.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
                          {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'Never'}
                        </td>
                      </tr>
                    ))}
                    {detailTenant.users.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-3 py-6 text-center text-sm text-gray-500">No users</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) : null}
      </Modal>

      {/* Edit Modal */}
      <Modal open={editOpen} onClose={() => setEditOpen(false)} title={`Edit: ${editTenant?.name || ''}`} size="md">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
            <input
              type="text"
              value={editForm.name}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Registered domain</label>
            <input
              type="text"
              value={editForm.domain}
              onChange={(e) => setEditForm({ ...editForm, domain: e.target.value })}
              placeholder="acme.com"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Enter the SAME registered domain here and in Resource Pool to uniquely link this tenant across both systems.</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Website</label>
              <input
                type="url"
                value={editForm.website}
                onChange={(e) => setEditForm({ ...editForm, website: e.target.value })}
                placeholder="https://example.com"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Industry</label>
              <select
                value={editForm.industry}
                onChange={(e) => setEditForm({ ...editForm, industry: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
              >
                <option value="">— Select —</option>
                <option value="saas">SaaS</option>
                <option value="recruiting">Recruiting</option>
                <option value="healthcare">Healthcare</option>
                <option value="ecommerce">E-Commerce</option>
                <option value="finance">Finance</option>
                <option value="general">General</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Address</label>
            <input
              type="text"
              value={editForm.company_address}
              onChange={(e) => setEditForm({ ...editForm, company_address: e.target.value })}
              placeholder="123 Main St, City, State, ZIP"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Phone No.</label>
              <input
                type="tel"
                value={editForm.phone}
                onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                placeholder="+1 (555) 000-0000"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
              <input
                type="email"
                value={editForm.contact_email}
                onChange={(e) => setEditForm({ ...editForm, contact_email: e.target.value })}
                placeholder="contact@company.com"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Plan</label>
              <select
                value={editForm.plan}
                onChange={(e) => setEditForm({ ...editForm, plan: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
              >
                <option value="starter">Starter</option>
                <option value="professional">Professional</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Status</label>
              <label className="flex items-center gap-2 mt-2">
                <input
                  type="checkbox"
                  checked={editForm.is_active}
                  onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                  className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Active</span>
              </label>
            </div>
          </div>

          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Plan Limits</h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                { key: 'max_users', label: 'Max Users' },
                { key: 'max_mailboxes', label: 'Max Mailboxes' },
                { key: 'max_contacts', label: 'Max Contacts' },
                { key: 'max_campaigns', label: 'Max Campaigns' },
                { key: 'max_leads', label: 'Max Leads' },
              ].map(({ key, label }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{label}</label>
                  <input
                    type="number"
                    min={0}
                    value={(editForm as any)[key]}
                    onChange={(e) => setEditForm({ ...editForm, [key]: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Feature Flags</h4>
            <div className="space-y-3">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={editFeatures.feature_email_validation_enabled}
                  onChange={(e) => setEditFeatures({ ...editFeatures, feature_email_validation_enabled: e.target.checked })}
                  className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                />
                <div>
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Email Validation</span>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Allow this tenant to run email validation pipelines</p>
                </div>
              </label>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={editFeatures.feature_campaigns_enabled}
                  onChange={(e) => setEditFeatures({ ...editFeatures, feature_campaigns_enabled: e.target.checked })}
                  className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                />
                <div>
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Campaign Execution</span>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Allow this tenant to activate and run campaigns</p>
                </div>
              </label>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={editFeatures.feature_outreach_enabled}
                  onChange={(e) => setEditFeatures({ ...editFeatures, feature_outreach_enabled: e.target.checked })}
                  className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                />
                <div>
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Outreach Pipeline</span>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Allow this tenant to run outreach send pipelines</p>
                </div>
              </label>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={editFeatures.feature_export_mailmerge_enabled}
                  onChange={(e) => setEditFeatures({ ...editFeatures, feature_export_mailmerge_enabled: e.target.checked })}
                  className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                />
                <div>
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Export Mailmerge</span>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Allow this tenant to export mailmerge CSV files</p>
                </div>
              </label>
            </div>
          </div>

          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">LOB Assignments</h4>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">Select which Lines of Business this tenant can access</p>
            <div className="space-y-3">
              {availableLobTypes.map((lt) => (
                <label key={lt} className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editLobAssignments.includes(lt)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setEditLobAssignments([...editLobAssignments, lt])
                      } else {
                        if (editLobAssignments.length <= 1) return
                        setEditLobAssignments(editLobAssignments.filter((t) => t !== lt))
                      }
                    }}
                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                  />
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: LOB_TYPE_COLORS[lt] || '#8B5CF6' }}
                    />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      {LOB_TYPE_LABELS[lt] || lt}
                    </span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={() => setEditOpen(false)}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              Cancel
            </button>
            <button
              onClick={handleSaveEdit}
              disabled={editSaving}
              className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
            >
              {editSaving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </Modal>

      {/* Create Tenant Modal */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Add New Tenant" size="md">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tenant Name *</label>
            <input
              type="text"
              value={createForm.name}
              onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
              placeholder="Company Name"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Registered domain</label>
            <input
              type="text"
              value={createForm.domain}
              onChange={(e) => setCreateForm({ ...createForm, domain: e.target.value })}
              placeholder="acme.com"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Enter the SAME registered domain here and in Resource Pool to uniquely link this tenant across both systems.</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Website</label>
              <input
                type="url"
                value={createForm.website}
                onChange={(e) => setCreateForm({ ...createForm, website: e.target.value })}
                placeholder="https://example.com"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Industry</label>
              <select
                value={createForm.industry}
                onChange={(e) => setCreateForm({ ...createForm, industry: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
              >
                <option value="">— Select —</option>
                <option value="saas">SaaS</option>
                <option value="recruiting">Recruiting</option>
                <option value="healthcare">Healthcare</option>
                <option value="ecommerce">E-Commerce</option>
                <option value="finance">Finance</option>
                <option value="general">General</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Address</label>
            <input
              type="text"
              value={createForm.company_address}
              onChange={(e) => setCreateForm({ ...createForm, company_address: e.target.value })}
              placeholder="123 Main St, City, State, ZIP"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Phone No.</label>
              <input
                type="tel"
                value={createForm.phone}
                onChange={(e) => setCreateForm({ ...createForm, phone: e.target.value })}
                placeholder="+1 (555) 000-0000"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
              <input
                type="email"
                value={createForm.contact_email}
                onChange={(e) => setCreateForm({ ...createForm, contact_email: e.target.value })}
                placeholder="contact@company.com"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Plan</label>
              <select
                value={createForm.plan}
                onChange={(e) => setCreateForm({ ...createForm, plan: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
              >
                <option value="starter">Starter</option>
                <option value="professional">Professional</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>
          </div>

          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Plan Limits</h4>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {[
                { key: 'max_users', label: 'Max Users' },
                { key: 'max_mailboxes', label: 'Max Mailboxes' },
                { key: 'max_contacts', label: 'Max Contacts' },
                { key: 'max_campaigns', label: 'Max Campaigns' },
                { key: 'max_leads', label: 'Max Leads' },
              ].map(({ key, label }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{label}</label>
                  <input
                    type="number"
                    min={0}
                    value={(createForm as any)[key]}
                    onChange={(e) => setCreateForm({ ...createForm, [key]: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={() => setCreateOpen(false)}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              Cancel
            </button>
            <button
              onClick={handleCreateTenant}
              disabled={createSaving}
              className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
            >
              {createSaving ? 'Creating...' : 'Create Tenant'}
            </button>
          </div>
        </div>
      </Modal>

      {/* Deactivate Confirmation */}
      {deactivateId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50" onClick={() => setDeactivateId(null)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-full">
                <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Deactivate Tenant</h3>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
              Are you sure you want to deactivate <strong>{deactivateName}</strong>? All users in this tenant will be deactivated and unable to log in.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeactivateId(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                Cancel
              </button>
              <button
                onClick={handleDeactivate}
                disabled={deactivating}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {deactivating ? 'Deactivating...' : 'Deactivate'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon: Icon, label, value, limit, color }: {
  icon: any
  label: string
  value: number
  limit: number
  color: string
}) {
  const pct = limit > 0 ? Math.round((value / limit) * 100) : 0
  return (
    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-4 h-4 ${color}`} />
        <span className="text-xs text-gray-500 dark:text-gray-400 uppercase">{label}</span>
      </div>
      <div className="text-xl font-bold text-gray-900 dark:text-white">{value.toLocaleString()}</div>
      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
        of {limit.toLocaleString()} ({pct}%)
      </div>
      <div className="mt-2 h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-amber-500' : 'bg-green-500'}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  )
}
