'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { settingsApi, rolesApi, type RoleDef } from '@/lib/api'
import { useAuthStore } from '@/lib/store'

// ─── Types ───────────────────────────────────────────────────────────────────

type AccessLevel = 'full' | 'read_write' | 'read' | 'no_access'

interface ModuleDef {
  key: string
  label: string
  tabs?: string[]
  tabKeys?: string[]  // machine-readable keys for sub-tabs (parallel to tabs)
  superAdminOnly?: boolean
  independentTabs?: boolean  // if true, sub-tabs have independent per-tab permissions
}

type ModulePermission = AccessLevel | { [tabKey: string]: AccessLevel }

interface RolePermissions {
  [role: string]: {
    [moduleKey: string]: ModulePermission
  }
}

// ─── Constants ───────────────────────────────────────────────────────────────

// Built-in roles (fallback + defaults source). Live role list is loaded from the
// roles API so custom, settings-backed roles appear as matrix columns too.
const BUILTIN_ROLES: RoleDef[] = [
  { key: 'super_admin', label: 'Super Admin', description: 'Full system access. Cannot be restricted.', base_role: 'super_admin', builtin: true, static: true },
  { key: 'admin', label: 'Admin', description: 'Manage operations, users, and settings.', base_role: 'admin', builtin: true },
  { key: 'bdm', label: 'BDM', description: 'Business Development Manager — day-to-day lead management and outreach.', base_role: 'bdm', builtin: true },
  { key: 'recruiter', label: 'Recruiter', description: 'Read-only access to data.', base_role: 'recruiter', builtin: true },
]
const BASE_ROLE_OPTIONS = ['admin', 'bdm', 'recruiter'] as const

const MODULES: ModuleDef[] = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'leads', label: 'Leads' },
  { key: 'clients', label: 'Clients' },
  { key: 'contacts', label: 'Contacts' },
  { key: 'validation', label: 'Validation' },
  { key: 'icp_wizard', label: 'ICP Wizard' },
  { key: 'outreach', label: 'Outreach' },
  { key: 'templates', label: 'Email Templates' },
  { key: 'campaigns', label: 'Campaigns' },
  { key: 'email_preview', label: 'Email Preview' },
  { key: 'inbox', label: 'Inbox' },
  { key: 'mailboxes', label: 'Mailboxes' },
  { key: 'warmup', label: 'Warmup Engine', tabs: ['Overview', 'Analytics', 'Emails', 'DNS & Blacklist', 'Profiles', 'Alerts', 'Settings'], tabKeys: ['overview', 'analytics', 'emails', 'dns', 'profiles', 'alerts', 'settings'], independentTabs: true },
  { key: 'pipelines', label: 'Pipelines', tabs: ['Lead Sourcing', 'Contact Enrichment', 'Email Validation', 'Outreach'], tabKeys: ['lead_sourcing', 'contact_enrichment', 'email_validation', 'outreach'], independentTabs: true },
  { key: 'deals', label: 'Deals' },
  { key: 'reports', label: 'Reports' },
  { key: 'analytics', label: 'Analytics' },
  { key: 'attribution', label: 'Attribution' },
  { key: 'visitors', label: 'Visitors' },
  { key: 'automation', label: 'Automation Control' },
  { key: 'settings', label: 'Settings', tabs: ['Job Filters', 'Job Source APIs', 'AI/LLM', 'Contacts', 'Validation', 'Outreach', 'Business Rules', 'Deliverability', 'LOB Lead Sources', 'Source Tuning'], tabKeys: ['job_filters', 'job_source_apis', 'ai_llm', 'contacts', 'validation', 'outreach', 'business_rules', 'deliverability', 'lob_lead_sources', 'source_tuning'], independentTabs: true },
  { key: 'lob', label: 'Lines of Business' },
  { key: 'billing', label: 'Billing' },
  { key: 'backups', label: 'Data Backups' },
  { key: 'users', label: 'User Management', superAdminOnly: true },
  { key: 'roles', label: 'Roles & Permissions', superAdminOnly: true },
  { key: 'activity_log', label: 'Activity Log', superAdminOnly: true },
  { key: 'tenants', label: 'Tenant Management', superAdminOnly: true },
]

const ACCESS_LEVELS: { value: AccessLevel; label: string; color: string }[] = [
  { value: 'full', label: 'Full Access', color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
  { value: 'read_write', label: 'Read & Write', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' },
  { value: 'read', label: 'Read Only', color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' },
  { value: 'no_access', label: 'No Access', color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
]

// Permission defaults keyed by built-in role. Custom roles inherit their base_role's
// defaults until an admin customizes them on the matrix.
const DEFAULT_PERMISSIONS: RolePermissions = {
  super_admin: Object.fromEntries(MODULES.map(m => [m.key, 'full' as AccessLevel])),
  admin: {
    dashboard: 'full',
    leads: 'full',
    clients: 'full',
    contacts: 'full',
    validation: 'full',
    outreach: 'full',
    templates: 'full',
    mailboxes: 'full',
    warmup: { overview: 'full', analytics: 'full', emails: 'full', dns: 'full', profiles: 'full', alerts: 'full', settings: 'full' },
    pipelines: { lead_sourcing: 'full', contact_enrichment: 'full', email_validation: 'full', outreach: 'full' },
    automation: 'full',
    settings: { job_filters: 'full', job_source_apis: 'full', ai_llm: 'full', contacts: 'full', validation: 'full', outreach: 'full', business_rules: 'full', deliverability: 'full', lob_lead_sources: 'full', source_tuning: 'full' },
    icp_wizard: 'full',
    campaigns: 'full',
    email_preview: 'full',
    inbox: 'full',
    deals: 'full',
    reports: 'full',
    analytics: 'full',
    attribution: 'full',
    visitors: 'full',
    lob: 'full',
    billing: 'full',
    backups: 'full',
    users: 'no_access',
    roles: 'no_access',
    activity_log: 'no_access',
    tenants: 'no_access',
  },
  bdm: {
    dashboard: 'read',
    leads: 'read_write',
    clients: 'read_write',
    contacts: 'read_write',
    validation: 'read_write',
    outreach: 'read_write',
    templates: 'read',
    mailboxes: 'read',
    warmup: { overview: 'read', analytics: 'read', emails: 'read', dns: 'read', profiles: 'read', alerts: 'read', settings: 'no_access' },
    pipelines: { lead_sourcing: 'read_write', contact_enrichment: 'read_write', email_validation: 'read_write', outreach: 'read_write' },
    automation: 'read',
    settings: { job_filters: 'read', job_source_apis: 'no_access', ai_llm: 'no_access', contacts: 'no_access', validation: 'no_access', outreach: 'no_access', business_rules: 'no_access', deliverability: 'no_access', lob_lead_sources: 'no_access', source_tuning: 'no_access' },
    icp_wizard: 'read_write',
    campaigns: 'read_write',
    email_preview: 'read_write',
    inbox: 'read_write',
    deals: 'read_write',
    reports: 'read',
    analytics: 'no_access',
    attribution: 'read',
    visitors: 'no_access',
    lob: 'no_access',
    billing: 'read',
    backups: 'no_access',
    users: 'no_access',
    roles: 'no_access',
    activity_log: 'no_access',
    tenants: 'no_access',
  },
  recruiter: {
    dashboard: 'read',
    leads: 'read',
    clients: 'read',
    contacts: 'read',
    validation: 'read',
    outreach: 'no_access',
    templates: 'read',
    mailboxes: 'no_access',
    warmup: { overview: 'no_access', analytics: 'no_access', emails: 'no_access', dns: 'no_access', profiles: 'no_access', alerts: 'no_access', settings: 'no_access' },
    pipelines: { lead_sourcing: 'no_access', contact_enrichment: 'no_access', email_validation: 'no_access', outreach: 'no_access' },
    automation: 'no_access',
    settings: { job_filters: 'read', job_source_apis: 'no_access', ai_llm: 'no_access', contacts: 'no_access', validation: 'no_access', outreach: 'no_access', business_rules: 'no_access', deliverability: 'no_access', lob_lead_sources: 'no_access', source_tuning: 'no_access' },
    icp_wizard: 'no_access',
    campaigns: 'no_access',
    email_preview: 'no_access',
    inbox: 'no_access',
    deals: 'no_access',
    reports: 'no_access',
    analytics: 'no_access',
    attribution: 'no_access',
    visitors: 'no_access',
    lob: 'no_access',
    billing: 'no_access',
    backups: 'no_access',
    users: 'no_access',
    roles: 'no_access',
    activity_log: 'no_access',
    tenants: 'no_access',
  },
}

const SETTINGS_KEY = 'role_permissions'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getAccessInfo(level: AccessLevel) {
  return ACCESS_LEVELS.find(a => a.value === level) || ACCESS_LEVELS[3]
}

function roleCardClasses(role: RoleDef) {
  if (role.key === 'super_admin') return 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20'
  if (role.key === 'admin') return 'border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/20'
  if (role.base_role === 'bdm') return 'border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20'
  return 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800'
}

// Base defaults for a role (built-in → own key, custom → its base_role).
function defaultsForRole(role: RoleDef): RolePermissions[string] {
  return DEFAULT_PERMISSIONS[role.key] || DEFAULT_PERMISSIONS[role.base_role] || DEFAULT_PERMISSIONS.recruiter
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function RolesPermissionsPage() {
  const router = useRouter()
  const { user } = useAuthStore()
  const isSuperAdmin = user?.role === 'super_admin'

  // Gate: super_admin only
  useEffect(() => {
    if (user && !isSuperAdmin) {
      router.replace('/dashboard')
    }
  }, [user, isSuperAdmin, router])

  const [activeTab, setActiveTab] = useState<'matrix' | 'management'>('matrix')
  const [roles, setRoles] = useState<RoleDef[]>(BUILTIN_ROLES)
  const [permissions, setPermissions] = useState<RolePermissions>(DEFAULT_PERMISSIONS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set())

  // Role Management modal state
  const [roleModalOpen, setRoleModalOpen] = useState(false)
  const [editingRole, setEditingRole] = useState<RoleDef | null>(null)
  const [roleForm, setRoleForm] = useState({ key: '', label: '', description: '', base_role: 'bdm' })
  const [roleSaving, setRoleSaving] = useState(false)
  const [roleFormError, setRoleFormError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<RoleDef | null>(null)
  const [deleting, setDeleting] = useState(false)

  const loadRoles = useCallback(async () => {
    try {
      const data = await rolesApi.list()
      if (Array.isArray(data) && data.length) setRoles(data)
    } catch {
      setRoles(BUILTIN_ROLES)
    }
  }, [])

  // Load saved permissions from settings API, merged with defaults for every role.
  const loadPermissions = useCallback(async (roleList: RoleDef[]) => {
    setLoading(true)
    setError(null)
    try {
      let saved: RolePermissions = {}
      try {
        const data = await settingsApi.get(SETTINGS_KEY)
        if (data && data.value_json) saved = JSON.parse(data.value_json) as RolePermissions
      } catch {
        saved = {}
      }
      const merged: RolePermissions = {}
      for (const role of roleList) {
        merged[role.key] = { ...defaultsForRole(role) }
        const savedRole = saved[role.key]
        if (savedRole) {
          for (const mod of MODULES) {
            if (role.static) {
              merged[role.key][mod.key] = 'full'
            } else if (mod.superAdminOnly) {
              merged[role.key][mod.key] = 'no_access'
            } else if (savedRole[mod.key] !== undefined) {
              merged[role.key][mod.key] = savedRole[mod.key]
            }
          }
        }
      }
      setPermissions(merged)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    (async () => {
      await loadRoles()
    })()
  }, [loadRoles])

  // Reload the matrix whenever the role list changes (e.g. after CRUD).
  useEffect(() => {
    loadPermissions(roles)
  }, [roles, loadPermissions])

  // Helper to get a flat access level for a module (handles both flat and nested)
  const getModuleAccess = (role: string, moduleKey: string): AccessLevel => {
    const perm = permissions[role]?.[moduleKey]
    if (!perm) return 'no_access'
    if (typeof perm === 'string') return perm
    const values = Object.values(perm) as AccessLevel[]
    if (values.length === 0) return 'no_access'
    if (values.every(v => v === values[0])) return values[0]
    const order: AccessLevel[] = ['full', 'read_write', 'read', 'no_access']
    for (const level of order) {
      if (values.includes(level)) return level
    }
    return 'no_access'
  }

  const getSubTabAccess = (role: string, moduleKey: string, tabKey: string): AccessLevel => {
    const perm = permissions[role]?.[moduleKey]
    if (!perm) return 'no_access'
    if (typeof perm === 'string') return perm
    return (perm as Record<string, AccessLevel>)[tabKey] || 'no_access'
  }

  // Auto-clear messages
  useEffect(() => {
    if (success) { const t = setTimeout(() => setSuccess(null), 4000); return () => clearTimeout(t) }
  }, [success])
  useEffect(() => {
    if (error) { const t = setTimeout(() => setError(null), 6000); return () => clearTimeout(t) }
  }, [error])

  const handleAccessChange = (role: string, moduleKey: string, level: AccessLevel, tabKey?: string) => {
    setPermissions(prev => {
      const mod = MODULES.find(m => m.key === moduleKey)
      if (mod?.independentTabs && mod.tabKeys) {
        if (tabKey) {
          const current = prev[role]?.[moduleKey]
          const currentObj: Record<string, AccessLevel> = typeof current === 'object' && current !== null
            ? { ...(current as Record<string, AccessLevel>) }
            : Object.fromEntries(mod.tabKeys.map(k => [k, (current as AccessLevel) || 'no_access']))
          currentObj[tabKey] = level
          return { ...prev, [role]: { ...prev[role], [moduleKey]: currentObj } }
        } else {
          const newObj = Object.fromEntries(mod.tabKeys.map(k => [k, level]))
          return { ...prev, [role]: { ...prev[role], [moduleKey]: newObj } }
        }
      }
      return { ...prev, [role]: { ...prev[role], [moduleKey]: level } }
    })
    setDirty(true)
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await settingsApi.update(SETTINGS_KEY, {
        value_json: JSON.stringify(permissions),
        type: 'json',
        description: 'Role-based permissions matrix',
      })
      setSuccess('Permissions saved successfully')
      setDirty(false)
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      setError(detail || 'Failed to save permissions')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => {
    const merged: RolePermissions = {}
    for (const role of roles) merged[role.key] = { ...defaultsForRole(role) }
    setPermissions(merged)
    setDirty(true)
  }

  const toggleModule = (key: string) => {
    setExpandedModules(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // ─── Role Management actions ───────────────────────────────────────────────

  const openCreateRole = () => {
    setEditingRole(null)
    setRoleForm({ key: '', label: '', description: '', base_role: 'bdm' })
    setRoleFormError(null)
    setRoleModalOpen(true)
  }

  const openEditRole = (role: RoleDef) => {
    setEditingRole(role)
    setRoleForm({ key: role.key, label: role.label, description: role.description || '', base_role: role.base_role })
    setRoleFormError(null)
    setRoleModalOpen(true)
  }

  const submitRole = async () => {
    setRoleSaving(true)
    setRoleFormError(null)
    try {
      if (editingRole) {
        await rolesApi.update(editingRole.key, {
          label: roleForm.label,
          description: roleForm.description,
          base_role: editingRole.builtin ? undefined : roleForm.base_role,
        })
        setSuccess(`Role "${roleForm.label}" updated`)
      } else {
        await rolesApi.create({
          key: roleForm.key,
          label: roleForm.label,
          description: roleForm.description,
          base_role: roleForm.base_role,
        })
        setSuccess(`Role "${roleForm.label}" created`)
      }
      setRoleModalOpen(false)
      await loadRoles()
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      setRoleFormError(detail || 'Failed to save role. A tenant must be selected (impersonated) to manage roles.')
    } finally {
      setRoleSaving(false)
    }
  }

  const confirmDeleteRole = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await rolesApi.delete(deleteTarget.key)
      setSuccess(`Role "${deleteTarget.label}" deleted`)
      setDeleteTarget(null)
      await loadRoles()
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      setError(detail || 'Failed to delete role')
      setDeleteTarget(null)
    } finally {
      setDeleting(false)
    }
  }

  if (!isSuperAdmin) {
    return null
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Roles &amp; Permissions</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Configure access levels for each role, and add/edit/delete custom roles.
          </p>
        </div>
        {activeTab === 'matrix' && (
          <div className="flex items-center gap-3">
            <button
              onClick={handleReset}
              disabled={saving || loading}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
            >
              Reset to Defaults
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !dirty}
              className="inline-flex items-center px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        )}
        {activeTab === 'management' && (
          <button
            onClick={openCreateRole}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            Add Role
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="-mb-px flex gap-6" aria-label="Roles tabs">
          {([['matrix', 'Permissions Matrix'], ['management', 'Role Management']] as const).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`whitespace-nowrap py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                activeTab === key
                  ? 'border-blue-600 text-blue-600 dark:text-blue-400 dark:border-blue-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </div>

      {/* Alerts */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 px-4 py-3 rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-4 text-red-600 dark:text-red-300 hover:text-red-800">✕</button>
        </div>
      )}
      {success && (
        <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-200 px-4 py-3 rounded-lg">
          {success}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="text-gray-500 dark:text-gray-400">Loading...</div>
        </div>
      ) : activeTab === 'management' ? (
        <RoleManagementPanel
          roles={roles}
          onEdit={openEditRole}
          onDelete={setDeleteTarget}
        />
      ) : (
        <>
          {dirty && (
            <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 px-4 py-3 rounded-lg text-sm">
              You have unsaved changes. Click &quot;Save Changes&quot; to persist.
            </div>
          )}

          {/* Role cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {roles.map(role => (
              <div key={role.key} className={`rounded-lg border p-4 ${roleCardClasses(role)}`}>
                <div className="flex items-center justify-between mb-1">
                  <h3 className="font-semibold text-gray-900 dark:text-white">{role.label}</h3>
                  {role.static ? (
                    <span className="px-2 py-0.5 text-xs font-medium bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded">Static</span>
                  ) : !role.builtin ? (
                    <span className="px-2 py-0.5 text-xs font-medium bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300 rounded">Custom</span>
                  ) : null}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400">{role.description}</p>
                {!role.builtin && (
                  <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-1">inherits: {role.base_role}</p>
                )}
              </div>
            ))}
          </div>

          {/* Permissions matrix — Desktop table */}
          <div className="hidden md:block bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider w-56">Module</th>
                    {roles.map(role => (
                      <th key={role.key} className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{role.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {MODULES.map(mod => (
                    <ModuleRows
                      key={mod.key}
                      mod={mod}
                      roles={roles}
                      permissions={permissions}
                      isExpanded={expandedModules.has(mod.key)}
                      hasTabs={!!(mod.tabs && mod.tabs.length > 0)}
                      onToggle={() => toggleModule(mod.key)}
                      onAccessChange={handleAccessChange}
                      getModuleAccess={getModuleAccess}
                      getSubTabAccess={getSubTabAccess}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Permissions matrix — Mobile accordion */}
          <div className="md:hidden space-y-2">
            {MODULES.map(mod => {
              const isExpanded = expandedModules.has(mod.key)
              const hasTabs = mod.tabs && mod.tabs.length > 0
              const isIndependent = mod.independentTabs && hasTabs
              return (
                <div key={mod.key} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                  <button onClick={() => toggleModule(mod.key)} className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{mod.label}</span>
                    <svg className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                  </button>
                  {isExpanded && (
                    <div className="border-t border-gray-200 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700/50">
                      {roles.map(role => {
                        const level = getModuleAccess(role.key, mod.key)
                        const isLocked = mod.superAdminOnly && role.key !== 'super_admin'
                        return (
                          <div key={role.key} className="px-4 py-2.5 flex items-center justify-between">
                            <span className="text-xs font-medium text-gray-600 dark:text-gray-400">{role.label}</span>
                            {role.static ? (
                              <AccessBadge level="full" />
                            ) : isLocked ? (
                              <AccessBadge level="no_access" locked />
                            ) : (
                              <AccessDropdown value={level} onChange={(newLevel) => handleAccessChange(role.key, mod.key, newLevel)} />
                            )}
                          </div>
                        )
                      })}
                      {isIndependent && mod.tabs!.map((tab, idx) => {
                        const tabKey = mod.tabKeys ? mod.tabKeys[idx] : undefined
                        return (
                          <div key={tab} className="bg-gray-50/50 dark:bg-gray-800/50 px-4 py-2">
                            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1.5 pl-2 border-l-2 border-gray-300 dark:border-gray-600">{tab}</div>
                            <div className="space-y-1.5 pl-4">
                              {roles.filter(r => !r.static).map(role => {
                                const isLocked = mod.superAdminOnly && role.key !== 'super_admin'
                                const tabLevel = tabKey ? getSubTabAccess(role.key, mod.key, tabKey) : getModuleAccess(role.key, mod.key)
                                return (
                                  <div key={role.key} className="flex items-center justify-between">
                                    <span className="text-[11px] text-gray-500 dark:text-gray-400">{role.label}</span>
                                    {isLocked ? (
                                      <span className="text-[10px] text-gray-400 italic">-</span>
                                    ) : tabKey ? (
                                      <AccessDropdown value={tabLevel} onChange={(newLevel) => handleAccessChange(role.key, mod.key, newLevel, tabKey)} />
                                    ) : (
                                      <span className="text-[10px] text-gray-400 italic">inherits ({getModuleAccess(role.key, mod.key)})</span>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* Legend */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Access Level Legend</h3>
            <div className="flex flex-wrap gap-3">
              {ACCESS_LEVELS.map(al => (
                <div key={al.value} className="flex items-center gap-2">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${al.color}`}>{al.label}</span>
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {al.value === 'full' && '- Create, read, update, delete, configure'}
                    {al.value === 'read_write' && '- Create, read, update (no delete/configure)'}
                    {al.value === 'read' && '- View data only'}
                    {al.value === 'no_access' && '- Hidden from navigation'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Role add/edit modal */}
      {roleModalOpen && (
        <RoleFormModal
          editingRole={editingRole}
          form={roleForm}
          setForm={setRoleForm}
          error={roleFormError}
          saving={roleSaving}
          onCancel={() => setRoleModalOpen(false)}
          onSubmit={submitRole}
        />
      )}

      {/* Delete confirm */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Delete role &quot;{deleteTarget.label}&quot;?</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
              This removes the custom role and its permission row. Users assigned to it must be reassigned first.
            </p>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setDeleteTarget(null)} className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600">Cancel</button>
              <button onClick={confirmDeleteRole} disabled={deleting} className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50">
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Role Management panel ───────────────────────────────────────────────────

function RoleManagementPanel({
  roles,
  onEdit,
  onDelete,
}: {
  roles: RoleDef[]
  onEdit: (role: RoleDef) => void
  onDelete: (role: RoleDef) => void
}) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Role</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Key</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Type</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Inherits</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Users</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {roles.map(role => (
              <tr key={role.key} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                <td className="px-4 py-3">
                  <div className="text-sm font-medium text-gray-900 dark:text-white">{role.label}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">{role.description}</div>
                </td>
                <td className="px-4 py-3 text-sm font-mono text-gray-600 dark:text-gray-400">{role.key}</td>
                <td className="px-4 py-3">
                  {role.builtin ? (
                    <span className="px-2 py-0.5 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded">Built-in</span>
                  ) : (
                    <span className="px-2 py-0.5 text-xs font-medium bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300 rounded">Custom</span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{role.builtin ? '—' : role.base_role}</td>
                <td className="px-4 py-3 text-center text-sm text-gray-600 dark:text-gray-400">{role.user_count ?? 0}</td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <button onClick={() => onEdit(role)} className="text-blue-600 dark:text-blue-400 hover:underline text-sm mr-4">Edit</button>
                  <button
                    onClick={() => onDelete(role)}
                    disabled={role.builtin || (role.user_count ?? 0) > 0}
                    title={role.builtin ? 'Built-in roles cannot be deleted' : (role.user_count ?? 0) > 0 ? 'Reassign users before deleting' : 'Delete role'}
                    className="text-red-600 dark:text-red-400 hover:underline text-sm disabled:text-gray-300 dark:disabled:text-gray-600 disabled:no-underline disabled:cursor-not-allowed"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RoleFormModal({
  editingRole,
  form,
  setForm,
  error,
  saving,
  onCancel,
  onSubmit,
}: {
  editingRole: RoleDef | null
  form: { key: string; label: string; description: string; base_role: string }
  setForm: (f: { key: string; label: string; description: string; base_role: string }) => void
  error: string | null
  saving: boolean
  onCancel: () => void
  onSubmit: () => void
}) {
  const isEdit = !!editingRole
  const isBuiltin = !!editingRole?.builtin
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6 space-y-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          {isEdit ? `Edit role: ${editingRole!.label}` : 'Add custom role'}
        </h3>
        {error && (
          <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 px-3 py-2 rounded text-sm">{error}</div>
        )}
        {!isEdit && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Key</label>
            <input
              value={form.key}
              onChange={(e) => setForm({ ...form, key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') })}
              placeholder="e.g. bdm_lead"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-400 mt-1">Lowercase letters/numbers/underscore. Immutable after creation.</p>
          </div>
        )}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Label</label>
          <input
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
            placeholder="e.g. BDM Lead"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={2}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Base role {isBuiltin && <span className="text-gray-400">(fixed for built-ins)</span>}
          </label>
          <select
            value={isBuiltin ? editingRole!.base_role : form.base_role}
            disabled={isBuiltin}
            onChange={(e) => setForm({ ...form, base_role: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60"
          >
            {(isBuiltin ? [editingRole!.base_role] : BASE_ROLE_OPTIONS).map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
          <p className="text-xs text-gray-400 mt-1">Custom roles inherit this built-in role&apos;s access for coarse checks; refine per-module on the Permissions Matrix.</p>
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button onClick={onCancel} className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600">Cancel</button>
          <button
            onClick={onSubmit}
            disabled={saving || !form.label || (!isEdit && !form.key)}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? 'Saving...' : isEdit ? 'Save' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function ModuleRows({
  mod,
  roles,
  permissions,
  isExpanded,
  hasTabs,
  onToggle,
  onAccessChange,
  getModuleAccess,
  getSubTabAccess,
}: {
  mod: ModuleDef
  roles: RoleDef[]
  permissions: RolePermissions
  isExpanded: boolean
  hasTabs: boolean
  onToggle: () => void
  onAccessChange: (role: string, moduleKey: string, level: AccessLevel, tabKey?: string) => void
  getModuleAccess: (role: string, moduleKey: string) => AccessLevel
  getSubTabAccess: (role: string, moduleKey: string, tabKey: string) => AccessLevel
}) {
  const isIndependent = mod.independentTabs && mod.tabKeys

  return (
    <>
      {/* Main module row */}
      <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            {hasTabs ? (
              <button onClick={onToggle} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-xs">{isExpanded ? '▼' : '▶'}</button>
            ) : (
              <span className="w-3" />
            )}
            <span className="text-sm font-medium text-gray-900 dark:text-white">{mod.label}</span>
            {mod.superAdminOnly && (
              <span className="px-1.5 py-0.5 text-[10px] font-medium bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300 rounded">Super Admin Only</span>
            )}
            {hasTabs && (
              <span className="text-xs text-gray-400 dark:text-gray-500">({mod.tabs!.length} tabs)</span>
            )}
            {isIndependent && (
              <span className="px-1.5 py-0.5 text-[10px] font-medium bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 rounded">Per-Tab</span>
            )}
          </div>
        </td>
        {roles.map(role => {
          const level = getModuleAccess(role.key, mod.key)
          const isStatic = role.static
          const isLocked = mod.superAdminOnly && role.key !== 'super_admin'
          return (
            <td key={role.key} className="px-4 py-3 text-center">
              {isStatic ? (
                <AccessBadge level="full" />
              ) : isLocked ? (
                <AccessBadge level="no_access" locked />
              ) : isIndependent ? (
                <div className="flex flex-col items-center gap-0.5">
                  <AccessDropdown value={level} onChange={(newLevel) => onAccessChange(role.key, mod.key, newLevel)} />
                  {(() => {
                    const perm = permissions[role.key]?.[mod.key]
                    if (typeof perm === 'object' && perm !== null) {
                      const vals = Object.values(perm) as AccessLevel[]
                      if (vals.length > 0 && !vals.every(v => v === vals[0])) {
                        return <span className="text-[10px] text-amber-600 dark:text-amber-400">mixed</span>
                      }
                    }
                    return null
                  })()}
                </div>
              ) : (
                <AccessDropdown value={level} onChange={(newLevel) => onAccessChange(role.key, mod.key, newLevel)} />
              )}
            </td>
          )
        })}
      </tr>

      {/* Tab sub-rows (expanded) */}
      {isExpanded && hasTabs && mod.tabs!.map((tab, idx) => {
        const tabKey = isIndependent && mod.tabKeys ? mod.tabKeys[idx] : undefined
        return (
          <tr key={`${mod.key}-${tab}`} className="bg-gray-50/50 dark:bg-gray-800/50">
            <td className="px-4 py-2 pl-12">
              <span className="text-xs text-gray-500 dark:text-gray-400">{tab}</span>
            </td>
            {roles.map(role => {
              if (role.static) {
                return (
                  <td key={role.key} className="px-4 py-2 text-center">
                    <span className="text-xs text-gray-400 dark:text-gray-500 italic">full</span>
                  </td>
                )
              }
              if (isIndependent && tabKey) {
                const isLocked = mod.superAdminOnly && role.key !== 'super_admin'
                const tabLevel = getSubTabAccess(role.key, mod.key, tabKey)
                return (
                  <td key={role.key} className="px-4 py-2 text-center">
                    {isLocked ? (
                      <span className="text-xs text-gray-400 dark:text-gray-500 italic">-</span>
                    ) : (
                      <AccessDropdown value={tabLevel} onChange={(newLevel) => onAccessChange(role.key, mod.key, newLevel, tabKey)} />
                    )}
                  </td>
                )
              }
              const parentLevel = getModuleAccess(role.key, mod.key)
              return (
                <td key={role.key} className="px-4 py-2 text-center">
                  <span className="text-xs text-gray-400 dark:text-gray-500 italic">
                    {parentLevel === 'no_access' ? '-' : `inherits (${parentLevel})`}
                  </span>
                </td>
              )
            })}
          </tr>
        )
      })}
    </>
  )
}

function AccessBadge({ level, locked }: { level: AccessLevel; locked?: boolean }) {
  const info = getAccessInfo(level)
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${info.color} ${locked ? 'opacity-50' : ''}`}>
      {locked ? 'Locked' : info.label}
    </span>
  )
}

function AccessDropdown({
  value,
  onChange,
}: {
  value: AccessLevel
  onChange: (level: AccessLevel) => void
}) {
  const info = getAccessInfo(value)
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as AccessLevel)}
      className={`text-xs font-medium rounded-full px-2.5 py-1 border-0 cursor-pointer focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 ${info.color}`}
    >
      {ACCESS_LEVELS.map(al => (
        <option key={al.value} value={al.value}>{al.label}</option>
      ))}
    </select>
  )
}
