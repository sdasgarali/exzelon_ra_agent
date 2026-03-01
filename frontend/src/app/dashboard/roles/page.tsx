'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { settingsApi } from '@/lib/api'
import { useAuthStore } from '@/lib/store'

// ─── Types ───────────────────────────────────────────────────────────────────

type AccessLevel = 'full' | 'read_write' | 'read' | 'no_access'
type RoleName = 'super_admin' | 'admin' | 'operator' | 'viewer'

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

const ROLES: { name: RoleName; label: string; description: string; static?: boolean }[] = [
  { name: 'super_admin', label: 'Super Admin', description: 'Full system access. Cannot be restricted.', static: true },
  { name: 'admin', label: 'Admin', description: 'Manage operations, users, and settings.' },
  { name: 'operator', label: 'Operator', description: 'Day-to-day lead management and outreach.' },
  { name: 'viewer', label: 'Viewer', description: 'Read-only access to data.' },
]

const MODULES: ModuleDef[] = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'leads', label: 'Leads' },
  { key: 'clients', label: 'Clients' },
  { key: 'contacts', label: 'Contacts' },
  { key: 'validation', label: 'Validation' },
  { key: 'outreach', label: 'Outreach' },
  { key: 'templates', label: 'Email Templates' },
  { key: 'mailboxes', label: 'Mailboxes' },
  { key: 'warmup', label: 'Warmup Engine', tabs: ['Overview', 'Analytics', 'Emails', 'DNS & Blacklist', 'Profiles', 'Alerts', 'Settings'] },
  { key: 'pipelines', label: 'Pipelines', tabs: ['Lead Sourcing', 'Contact Enrichment', 'Email Validation', 'Outreach'] },
  { key: 'settings', label: 'Settings', tabs: ['Job Sources', 'AI/LLM', 'Contacts', 'Validation', 'Outreach', 'Business Rules'], tabKeys: ['job_sources', 'ai_llm', 'contacts', 'validation', 'outreach', 'business_rules'], independentTabs: true },
  { key: 'users', label: 'User Management', superAdminOnly: true },
  { key: 'roles', label: 'Roles & Permissions', superAdminOnly: true },
]

const ACCESS_LEVELS: { value: AccessLevel; label: string; color: string }[] = [
  { value: 'full', label: 'Full Access', color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
  { value: 'read_write', label: 'Read & Write', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' },
  { value: 'read', label: 'Read Only', color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' },
  { value: 'no_access', label: 'No Access', color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
]

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
    warmup: 'full',
    pipelines: 'full',
    settings: 'no_access',
    users: 'no_access',
    roles: 'no_access',
  },
  operator: {
    dashboard: 'read',
    leads: 'read_write',
    clients: 'read_write',
    contacts: 'read_write',
    validation: 'read_write',
    outreach: 'read_write',
    templates: 'read',
    mailboxes: 'read',
    warmup: 'read',
    pipelines: 'read_write',
    settings: 'no_access',
    users: 'no_access',
    roles: 'no_access',
  },
  viewer: {
    dashboard: 'read',
    leads: 'read',
    clients: 'read',
    contacts: 'read',
    validation: 'read',
    outreach: 'no_access',
    templates: 'read',
    mailboxes: 'no_access',
    warmup: 'no_access',
    pipelines: 'no_access',
    settings: 'no_access',
    users: 'no_access',
    roles: 'no_access',
  },
}

const SETTINGS_KEY = 'role_permissions'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getAccessInfo(level: AccessLevel) {
  return ACCESS_LEVELS.find(a => a.value === level) || ACCESS_LEVELS[3]
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

  const [permissions, setPermissions] = useState<RolePermissions>(DEFAULT_PERMISSIONS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set())

  // Load saved permissions from settings API
  const loadPermissions = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await settingsApi.get(SETTINGS_KEY)
      if (data && data.value_json) {
        const saved = JSON.parse(data.value_json) as RolePermissions
        // Merge saved with defaults (in case new modules were added)
        const merged: RolePermissions = {}
        for (const role of ROLES) {
          merged[role.name] = { ...DEFAULT_PERMISSIONS[role.name] }
          if (saved[role.name]) {
            for (const mod of MODULES) {
              if (role.static) {
                merged[role.name][mod.key] = 'full'
              } else if (mod.superAdminOnly) {
                merged[role.name][mod.key] = 'no_access'
              } else if (saved[role.name][mod.key] !== undefined) {
                merged[role.name][mod.key] = saved[role.name][mod.key]
              }
            }
          }
        }
        setPermissions(merged)
      }
    } catch {
      // Setting may not exist yet — use defaults
      setPermissions({ ...DEFAULT_PERMISSIONS })
    } finally {
      setLoading(false)
    }
  }, [])

  // Helper to get a flat access level for a module (handles both flat and nested)
  const getModuleAccess = (role: RoleName, moduleKey: string): AccessLevel => {
    const perm = permissions[role]?.[moduleKey]
    if (!perm) return 'no_access'
    if (typeof perm === 'string') return perm
    // Nested object: compute aggregate
    const values = Object.values(perm) as AccessLevel[]
    if (values.length === 0) return 'no_access'
    if (values.every(v => v === values[0])) return values[0]
    // Mixed: return highest access as summary
    const order: AccessLevel[] = ['full', 'read_write', 'read', 'no_access']
    for (const level of order) {
      if (values.includes(level)) return level
    }
    return 'no_access'
  }

  // Helper to get sub-tab access
  const getSubTabAccess = (role: RoleName, moduleKey: string, tabKey: string): AccessLevel => {
    const perm = permissions[role]?.[moduleKey]
    if (!perm) return 'no_access'
    if (typeof perm === 'string') return perm  // flat = all tabs inherit
    return (perm as Record<string, AccessLevel>)[tabKey] || 'no_access'
  }

  useEffect(() => {
    loadPermissions()
  }, [loadPermissions])

  // Auto-clear messages
  useEffect(() => {
    if (success) { const t = setTimeout(() => setSuccess(null), 4000); return () => clearTimeout(t) }
  }, [success])
  useEffect(() => {
    if (error) { const t = setTimeout(() => setError(null), 6000); return () => clearTimeout(t) }
  }, [error])

  const handleAccessChange = (role: RoleName, moduleKey: string, level: AccessLevel, tabKey?: string) => {
    setPermissions(prev => {
      const mod = MODULES.find(m => m.key === moduleKey)
      if (mod?.independentTabs && mod.tabKeys) {
        if (tabKey) {
          // Change a single sub-tab
          const current = prev[role]?.[moduleKey]
          const currentObj: Record<string, AccessLevel> = typeof current === 'object' && current !== null
            ? { ...(current as Record<string, AccessLevel>) }
            : Object.fromEntries(mod.tabKeys.map(k => [k, (current as AccessLevel) || 'no_access']))
          currentObj[tabKey] = level
          return { ...prev, [role]: { ...prev[role], [moduleKey]: currentObj } }
        } else {
          // Parent row: set all sub-tabs at once
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
    setPermissions({ ...DEFAULT_PERMISSIONS })
    setDirty(true)
  }

  const toggleModule = (key: string) => {
    setExpandedModules(prev => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  if (!isSuperAdmin) {
    return null
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 dark:text-gray-400">Loading permissions...</div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Roles & Permissions</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Configure access levels for each role across all system modules.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleReset}
            disabled={saving}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
          >
            Reset to Defaults
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !dirty}
            className="inline-flex items-center px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? (
              <>
                <svg className="animate-spin h-4 w-4 mr-2" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Saving...
              </>
            ) : (
              'Save Changes'
            )}
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 px-4 py-3 rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-4 text-red-600 dark:text-red-300 hover:text-red-800">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}
      {success && (
        <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-200 px-4 py-3 rounded-lg">
          {success}
        </div>
      )}

      {dirty && (
        <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 px-4 py-3 rounded-lg text-sm">
          You have unsaved changes. Click &quot;Save Changes&quot; to persist.
        </div>
      )}

      {/* Role cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {ROLES.map(role => (
          <div
            key={role.name}
            className={`rounded-lg border p-4 ${
              role.name === 'super_admin'
                ? 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20'
                : role.name === 'admin'
                ? 'border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/20'
                : role.name === 'operator'
                ? 'border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20'
                : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800'
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <h3 className="font-semibold text-gray-900 dark:text-white">{role.label}</h3>
              {role.static && (
                <span className="px-2 py-0.5 text-xs font-medium bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded">
                  Static
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400">{role.description}</p>
          </div>
        ))}
      </div>

      {/* Permissions matrix */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider w-56">
                  Module
                </th>
                {ROLES.map(role => (
                  <th
                    key={role.name}
                    className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                  >
                    {role.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {MODULES.map(mod => {
                const isExpanded = expandedModules.has(mod.key)
                const hasTabs = mod.tabs && mod.tabs.length > 0

                return (
                  <ModuleRows
                    key={mod.key}
                    mod={mod}
                    permissions={permissions}
                    isExpanded={isExpanded}
                    hasTabs={!!hasTabs}
                    onToggle={() => toggleModule(mod.key)}
                    onAccessChange={handleAccessChange}
                    getModuleAccess={getModuleAccess}
                    getSubTabAccess={getSubTabAccess}
                  />
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Legend */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Access Level Legend</h3>
        <div className="flex flex-wrap gap-3">
          {ACCESS_LEVELS.map(al => (
            <div key={al.value} className="flex items-center gap-2">
              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${al.color}`}>
                {al.label}
              </span>
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
    </div>
  )
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function ModuleRows({
  mod,
  permissions,
  isExpanded,
  hasTabs,
  onToggle,
  onAccessChange,
  getModuleAccess,
  getSubTabAccess,
}: {
  mod: ModuleDef
  permissions: RolePermissions
  isExpanded: boolean
  hasTabs: boolean
  onToggle: () => void
  onAccessChange: (role: RoleName, moduleKey: string, level: AccessLevel, tabKey?: string) => void
  getModuleAccess: (role: RoleName, moduleKey: string) => AccessLevel
  getSubTabAccess: (role: RoleName, moduleKey: string, tabKey: string) => AccessLevel
}) {
  const isIndependent = mod.independentTabs && mod.tabKeys

  return (
    <>
      {/* Main module row */}
      <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            {hasTabs ? (
              <button
                onClick={onToggle}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-xs"
              >
                {isExpanded ? '▼' : '▶'}
              </button>
            ) : (
              <span className="w-3" />
            )}
            <span className="text-sm font-medium text-gray-900 dark:text-white">
              {mod.label}
            </span>
            {mod.superAdminOnly && (
              <span className="px-1.5 py-0.5 text-[10px] font-medium bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300 rounded">
                Super Admin Only
              </span>
            )}
            {hasTabs && (
              <span className="text-xs text-gray-400 dark:text-gray-500">
                ({mod.tabs!.length} tabs)
              </span>
            )}
            {isIndependent && (
              <span className="px-1.5 py-0.5 text-[10px] font-medium bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 rounded">
                Per-Tab
              </span>
            )}
          </div>
        </td>
        {ROLES.map(role => {
          const level = getModuleAccess(role.name as RoleName, mod.key)
          const isStatic = role.static
          const isLocked = mod.superAdminOnly && role.name !== 'super_admin'

          return (
            <td key={role.name} className="px-4 py-3 text-center">
              {isStatic ? (
                <AccessBadge level="full" />
              ) : isLocked ? (
                <AccessBadge level="no_access" locked />
              ) : isIndependent ? (
                <div className="flex flex-col items-center gap-0.5">
                  <AccessDropdown
                    value={level}
                    onChange={(newLevel) => onAccessChange(role.name as RoleName, mod.key, newLevel)}
                  />
                  {(() => {
                    // Show "Mixed" indicator if sub-tabs have different values
                    const perm = permissions[role.name]?.[mod.key]
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
                <AccessDropdown
                  value={level}
                  onChange={(newLevel) => onAccessChange(role.name as RoleName, mod.key, newLevel)}
                />
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
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {tab}
              </span>
            </td>
            {ROLES.map(role => {
              if (role.static) {
                return (
                  <td key={role.name} className="px-4 py-2 text-center">
                    <span className="text-xs text-gray-400 dark:text-gray-500 italic">full</span>
                  </td>
                )
              }

              if (isIndependent && tabKey) {
                const isLocked = mod.superAdminOnly && role.name !== 'super_admin'
                const tabLevel = getSubTabAccess(role.name as RoleName, mod.key, tabKey)
                return (
                  <td key={role.name} className="px-4 py-2 text-center">
                    {isLocked ? (
                      <span className="text-xs text-gray-400 dark:text-gray-500 italic">-</span>
                    ) : (
                      <AccessDropdown
                        value={tabLevel}
                        onChange={(newLevel) => onAccessChange(role.name as RoleName, mod.key, newLevel, tabKey)}
                      />
                    )}
                  </td>
                )
              }

              // Non-independent tabs: show inherits
              const parentLevel = getModuleAccess(role.name as RoleName, mod.key)
              return (
                <td key={role.name} className="px-4 py-2 text-center">
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
      {locked ? (
        <>
          <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          Locked
        </>
      ) : (
        info.label
      )}
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
        <option key={al.value} value={al.value}>
          {al.label}
        </option>
      ))}
    </select>
  )
}
