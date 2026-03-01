'use client';

import { useAuthStore } from '@/lib/store';
import { settingsApi } from '@/lib/api';
import { useRouter } from 'next/navigation';
import { useEffect, useState, useCallback } from 'react';
import {
  Shield, ShieldCheck, ShieldAlert, Eye, UserCog, Crown, Users,
  ChevronDown, ChevronRight, Save, RotateCcw, Check, Loader2,
} from 'lucide-react';

/* ─── Types ──────────────────────────────────────────────────── */
type AccessLevel = 'full' | 'read_write' | 'read' | 'no_access';
type EditableRole = 'tenant_admin' | 'operator' | 'viewer';

interface ActionDef { id: string; name: string }
interface TabDef { id: string; name: string; actions?: ActionDef[] }
interface ModuleDef {
  id: string; name: string; superAdminOnly?: boolean; tabs?: TabDef[];
}

interface TabPermission { visible: boolean; actions?: Record<string, boolean> }
interface ModulePermission { access: AccessLevel; tabs?: Record<string, TabPermission> }
type PermissionConfig = Record<EditableRole, Record<string, ModulePermission>>;

const EDITABLE_ROLES: { key: EditableRole; label: string; color: string }[] = [
  { key: 'tenant_admin', label: 'Admin', color: 'text-blue-600 dark:text-blue-400' },
  { key: 'operator', label: 'Operator', color: 'text-green-600 dark:text-green-400' },
  { key: 'viewer', label: 'Viewer', color: 'text-amber-600 dark:text-amber-400' },
];

const ACCESS_OPTIONS: { value: AccessLevel; label: string }[] = [
  { value: 'full', label: 'Full' },
  { value: 'read_write', label: 'Read/Write' },
  { value: 'read', label: 'Read' },
  { value: 'no_access', label: 'No Access' },
];

/* ─── Module Definitions ─────────────────────────────────────── */
const MODULES: ModuleDef[] = [
  { id: 'dashboard', name: 'Dashboard' },
  { id: 'leads', name: 'Leads' },
  { id: 'clients', name: 'Clients' },
  { id: 'contacts', name: 'Contacts' },
  { id: 'validation', name: 'Validation' },
  { id: 'outreach', name: 'Outreach' },
  { id: 'templates', name: 'Email Templates' },
  { id: 'mailboxes', name: 'Mailboxes' },
  {
    id: 'warmup', name: 'Warmup Engine',
    tabs: [
      { id: 'overview', name: 'Overview', actions: [
        { id: 'assess_all', name: 'Assess All Mailboxes' },
        { id: 'trigger_cycle', name: 'Trigger Warmup Cycle' },
        { id: 'assess_mailbox', name: 'Assess Individual Mailbox' },
        { id: 'recovery', name: 'Start Recovery' },
      ]},
      { id: 'analytics', name: 'Analytics' },
      { id: 'emails', name: 'Email Threads' },
      { id: 'dns', name: 'DNS & Blacklist', actions: [
        { id: 'run_dns', name: 'Run DNS Check' },
        { id: 'run_blacklist', name: 'Run Blacklist Check' },
      ]},
      { id: 'profiles', name: 'Profiles', actions: [
        { id: 'create_profile', name: 'Create Profile' },
        { id: 'apply_profile', name: 'Apply Profile to Mailbox' },
      ]},
      { id: 'alerts', name: 'Alerts', actions: [
        { id: 'mark_read', name: 'Mark Alerts Read' },
      ]},
      { id: 'settings', name: 'Settings', actions: [
        { id: 'edit_config', name: 'Edit Configuration' },
        { id: 'export_report', name: 'Export Report' },
      ]},
    ],
  },
  {
    id: 'pipelines', name: 'Pipelines',
    tabs: [
      { id: 'lead_sourcing', name: 'Lead Sourcing', actions: [{ id: 'run', name: 'Run Pipeline' }] },
      { id: 'contact_enrichment', name: 'Contact Enrichment', actions: [{ id: 'run', name: 'Run Pipeline' }] },
      { id: 'email_validation', name: 'Email Validation', actions: [{ id: 'run', name: 'Run Pipeline' }] },
      { id: 'outreach_pipeline', name: 'Outreach', actions: [{ id: 'run', name: 'Run Pipeline' }] },
    ],
  },
  { id: 'settings', name: 'Settings', superAdminOnly: true },
  { id: 'users', name: 'User Management', superAdminOnly: true },
  { id: 'tenants', name: 'Tenants', superAdminOnly: true },
  { id: 'roles', name: 'Roles & Permissions', superAdminOnly: true },
];

/* ─── Default Permissions ────────────────────────────────────── */
function buildTabDefaults(tabs: TabDef[], allVisible: boolean, allActions: boolean): Record<string, TabPermission> {
  const result: Record<string, TabPermission> = {};
  for (const tab of tabs) {
    const actions: Record<string, boolean> = {};
    for (const a of (tab.actions || [])) { actions[a.id] = allActions; }
    result[tab.id] = { visible: allVisible, actions };
  }
  return result;
}

function getDefaultPermissions(): PermissionConfig {
  return {
    tenant_admin: {
      dashboard: { access: 'full' },
      leads: { access: 'full' },
      clients: { access: 'full' },
      contacts: { access: 'full' },
      validation: { access: 'full' },
      outreach: { access: 'full' },
      templates: { access: 'full' },
      mailboxes: { access: 'full' },
      warmup: {
        access: 'read',
        tabs: {
          overview: { visible: true, actions: { assess_all: false, trigger_cycle: false, assess_mailbox: false, recovery: false } },
          analytics: { visible: true, actions: {} },
          emails: { visible: false, actions: {} },
          dns: { visible: false, actions: { run_dns: false, run_blacklist: false } },
          profiles: { visible: false, actions: { create_profile: false, apply_profile: false } },
          alerts: { visible: false, actions: { mark_read: false } },
          settings: { visible: false, actions: { edit_config: false, export_report: false } },
        },
      },
      pipelines: {
        access: 'full',
        tabs: buildTabDefaults(MODULES.find(m => m.id === 'pipelines')!.tabs!, true, true),
      },
      settings: { access: 'no_access' },
      users: { access: 'no_access' },
      tenants: { access: 'no_access' },
      roles: { access: 'no_access' },
    },
    operator: {
      dashboard: { access: 'read' },
      leads: { access: 'read_write' },
      clients: { access: 'read_write' },
      contacts: { access: 'read_write' },
      validation: { access: 'read_write' },
      outreach: { access: 'read_write' },
      templates: { access: 'read_write' },
      mailboxes: { access: 'read_write' },
      warmup: {
        access: 'read_write',
        tabs: {
          overview: { visible: true, actions: { assess_all: true, trigger_cycle: true, assess_mailbox: true, recovery: true } },
          analytics: { visible: true, actions: {} },
          emails: { visible: true, actions: {} },
          dns: { visible: true, actions: { run_dns: true, run_blacklist: true } },
          profiles: { visible: true, actions: { create_profile: true, apply_profile: true } },
          alerts: { visible: true, actions: { mark_read: true } },
          settings: { visible: false, actions: { edit_config: false, export_report: false } },
        },
      },
      pipelines: {
        access: 'read_write',
        tabs: buildTabDefaults(MODULES.find(m => m.id === 'pipelines')!.tabs!, true, true),
      },
      settings: { access: 'no_access' },
      users: { access: 'no_access' },
      tenants: { access: 'no_access' },
      roles: { access: 'no_access' },
    },
    viewer: {
      dashboard: { access: 'read' },
      leads: { access: 'read' },
      clients: { access: 'read' },
      contacts: { access: 'read' },
      validation: { access: 'read' },
      outreach: { access: 'no_access' },
      templates: { access: 'no_access' },
      mailboxes: { access: 'no_access' },
      warmup: { access: 'no_access', tabs: buildTabDefaults(MODULES.find(m => m.id === 'warmup')!.tabs!, false, false) },
      pipelines: { access: 'no_access', tabs: buildTabDefaults(MODULES.find(m => m.id === 'pipelines')!.tabs!, false, false) },
      settings: { access: 'no_access' },
      users: { access: 'no_access' },
      tenants: { access: 'no_access' },
      roles: { access: 'no_access' },
    },
  };
}

const SETTINGS_KEY = 'role_permissions';

/* ─── Sub-components ─────────────────────────────────────────── */
function AccessBadge({ level }: { level: AccessLevel | 'full_static' }) {
  const styles: Record<string, string> = {
    full:        'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 border-green-200 dark:border-green-800',
    full_static: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 border-green-200 dark:border-green-800',
    read_write:  'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300 border-blue-200 dark:border-blue-800',
    read:        'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800',
    no_access:   'bg-gray-100 text-gray-500 dark:bg-gray-800/40 dark:text-gray-500 border-gray-200 dark:border-gray-700',
  };
  const labels: Record<string, string> = { full: 'Full', full_static: 'Full', read_write: 'Read/Write', read: 'Read', no_access: 'No Access' };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium whitespace-nowrap border ${styles[level]}`}>
      {labels[level]}
    </span>
  );
}

function AccessDropdown({ value, onChange, disabled }: { value: AccessLevel; onChange: (v: AccessLevel) => void; disabled?: boolean }) {
  if (disabled) return <AccessBadge level={value} />;
  const bgMap: Record<AccessLevel, string> = {
    full: 'border-green-300 bg-green-50 text-green-800 dark:border-green-700 dark:bg-green-900/30 dark:text-green-300',
    read_write: 'border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    read: 'border-yellow-300 bg-yellow-50 text-yellow-800 dark:border-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
    no_access: 'border-gray-300 bg-gray-50 text-gray-600 dark:border-gray-600 dark:bg-gray-800/30 dark:text-gray-400',
  };
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value as AccessLevel)}
      className={`text-xs font-medium rounded-full px-2.5 py-1 border cursor-pointer outline-none ${bgMap[value]}`}
    >
      {ACCESS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

function ToggleSwitch({ checked, onChange, disabled, label }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <label className={`inline-flex items-center gap-2 ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${checked ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'}`}
      >
        <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${checked ? 'translate-x-[18px]' : 'translate-x-[3px]'}`} />
      </button>
      {label && <span className="text-xs text-gray-700 dark:text-gray-300">{label}</span>}
    </label>
  );
}

/* ─── Main Page Component ────────────────────────────────────── */
export default function RolesPage() {
  const { user } = useAuthStore();
  const router = useRouter();
  const isSuperAdmin = user?.role === 'super_admin';

  const [permissions, setPermissions] = useState<PermissionConfig>(getDefaultPermissions());
  const [savedPermissions, setSavedPermissions] = useState<string>('');
  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (user && !isSuperAdmin) router.replace('/dashboard');
  }, [user, isSuperAdmin, router]);

  // Load saved permissions
  useEffect(() => {
    if (!isSuperAdmin) return;
    (async () => {
      try {
        const setting = await settingsApi.get(SETTINGS_KEY);
        if (setting?.value_json) {
          const parsed = JSON.parse(setting.value_json);
          // Merge with defaults to ensure new modules/tabs are present
          const merged = getDefaultPermissions();
          for (const role of Object.keys(parsed) as EditableRole[]) {
            if (!merged[role]) continue;
            for (const modId of Object.keys(parsed[role])) {
              if (!merged[role][modId]) continue;
              merged[role][modId].access = parsed[role][modId].access ?? merged[role][modId].access;
              if (parsed[role][modId].tabs && merged[role][modId].tabs) {
                for (const tabId of Object.keys(parsed[role][modId].tabs)) {
                  if (!merged[role][modId].tabs![tabId]) continue;
                  merged[role][modId].tabs![tabId].visible = parsed[role][modId].tabs[tabId].visible ?? merged[role][modId].tabs![tabId].visible;
                  if (parsed[role][modId].tabs[tabId].actions && merged[role][modId].tabs![tabId].actions) {
                    for (const actId of Object.keys(parsed[role][modId].tabs[tabId].actions)) {
                      if (actId in merged[role][modId].tabs![tabId].actions!) {
                        merged[role][modId].tabs![tabId].actions![actId] = parsed[role][modId].tabs[tabId].actions[actId];
                      }
                    }
                  }
                }
              }
            }
          }
          setPermissions(merged);
          setSavedPermissions(JSON.stringify(merged));
        } else {
          setSavedPermissions(JSON.stringify(getDefaultPermissions()));
        }
      } catch {
        // Setting doesn't exist yet — use defaults
        setSavedPermissions(JSON.stringify(getDefaultPermissions()));
      } finally {
        setLoading(false);
      }
    })();
  }, [isSuperAdmin]);

  useEffect(() => { if (success) { const t = setTimeout(() => setSuccess(''), 3000); return () => clearTimeout(t); } }, [success]);
  useEffect(() => { if (error) { const t = setTimeout(() => setError(''), 4000); return () => clearTimeout(t); } }, [error]);

  const hasChanges = JSON.stringify(permissions) !== savedPermissions;

  const toggleExpand = (modId: string) => {
    setExpandedModules(prev => {
      const next = new Set(prev);
      next.has(modId) ? next.delete(modId) : next.add(modId);
      return next;
    });
  };

  const setAccess = useCallback((role: EditableRole, modId: string, access: AccessLevel) => {
    setPermissions(prev => {
      const next = JSON.parse(JSON.stringify(prev)) as PermissionConfig;
      next[role][modId].access = access;
      // If set to no_access, disable all tabs
      if (access === 'no_access' && next[role][modId].tabs) {
        for (const tabId of Object.keys(next[role][modId].tabs!)) {
          next[role][modId].tabs![tabId].visible = false;
          if (next[role][modId].tabs![tabId].actions) {
            for (const actId of Object.keys(next[role][modId].tabs![tabId].actions!)) {
              next[role][modId].tabs![tabId].actions![actId] = false;
            }
          }
        }
      }
      return next;
    });
  }, []);

  const setTabVisible = useCallback((role: EditableRole, modId: string, tabId: string, visible: boolean) => {
    setPermissions(prev => {
      const next = JSON.parse(JSON.stringify(prev)) as PermissionConfig;
      if (next[role][modId].tabs?.[tabId]) {
        next[role][modId].tabs![tabId].visible = visible;
        // If hiding tab, disable all its actions
        if (!visible && next[role][modId].tabs![tabId].actions) {
          for (const actId of Object.keys(next[role][modId].tabs![tabId].actions!)) {
            next[role][modId].tabs![tabId].actions![actId] = false;
          }
        }
      }
      return next;
    });
  }, []);

  const setAction = useCallback((role: EditableRole, modId: string, tabId: string, actId: string, enabled: boolean) => {
    setPermissions(prev => {
      const next = JSON.parse(JSON.stringify(prev)) as PermissionConfig;
      if (next[role][modId].tabs?.[tabId]?.actions) {
        next[role][modId].tabs![tabId].actions![actId] = enabled;
      }
      return next;
    });
  }, []);

  const handleSave = async () => {
    try {
      setSaving(true);
      await settingsApi.update(SETTINGS_KEY, {
        value_json: JSON.stringify(permissions),
        type: 'json',
        description: 'Role-based permission configuration for all modules and tabs',
      });
      setSavedPermissions(JSON.stringify(permissions));
      setSuccess('Permissions saved successfully');
    } catch {
      setError('Failed to save permissions');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setPermissions(getDefaultPermissions());
  };

  if (!user || !isSuperAdmin) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 dark:text-gray-400">
          <ShieldAlert className="h-12 w-12 mx-auto mb-3 text-red-400" />
          <p className="text-center text-lg font-medium">Access Denied</p>
          <p className="text-center text-sm mt-1">You do not have permission to view this page.</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        <span className="ml-2 text-gray-500">Loading permissions...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Toast alerts */}
      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded-lg text-sm">{error}</div>}
      {success && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-2 rounded-lg text-sm flex items-center gap-2"><Check className="h-4 w-4" />{success}</div>}

      {/* Page Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-100 dark:bg-indigo-900/30">
            <Shield className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Roles & Permissions</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Manage access levels for each role across modules, tabs, and actions.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleReset}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <RotateCcw className="h-4 w-4" /> Reset Defaults
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !hasChanges}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>

      {hasChanges && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 px-4 py-2 rounded-lg text-sm">
          You have unsaved changes. Click &quot;Save Changes&quot; to apply.
        </div>
      )}

      {/* Permission Matrix */}
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-800/50">
                <th className="px-5 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 w-[260px]">
                  Module / Tab / Action
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-purple-600 dark:text-purple-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 w-[120px]">
                  Super Admin
                </th>
                {EDITABLE_ROLES.map(r => (
                  <th key={r.key} className={`px-4 py-3 text-center text-xs font-semibold ${r.color} uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 w-[140px]`}>
                    {r.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {MODULES.map((mod) => {
                const isExpanded = expandedModules.has(mod.id);
                const hasTabs = mod.tabs && mod.tabs.length > 0;

                return (
                  <ModuleRow
                    key={mod.id}
                    mod={mod}
                    isExpanded={isExpanded}
                    hasTabs={!!hasTabs}
                    permissions={permissions}
                    onToggleExpand={() => toggleExpand(mod.id)}
                    onSetAccess={setAccess}
                    onSetTabVisible={setTabVisible}
                    onSetAction={setAction}
                  />
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Legend */}
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Legend</h3>
        <div className="flex flex-wrap gap-4">
          {ACCESS_OPTIONS.map(o => (
            <div key={o.value} className="flex items-center gap-2">
              <AccessBadge level={o.value} />
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {o.value === 'full' && 'Complete access (CRUD + admin)'}
                {o.value === 'read_write' && 'Create, read, update, delete'}
                {o.value === 'read' && 'View only'}
                {o.value === 'no_access' && 'Module hidden / inaccessible'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Role Description Cards */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Role Descriptions</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {ROLE_DESCRIPTIONS.map((rd) => (
            <div key={rd.role} className={`rounded-xl border ${rd.borderColor} ${rd.color} p-5 transition-shadow hover:shadow-md`}>
              <div className="flex items-center gap-3 mb-3">
                {rd.icon}
                <h3 className="text-base font-semibold text-gray-900 dark:text-white">{rd.role}</h3>
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-300 mb-3">{rd.description}</p>
              <ul className="space-y-1.5">
                {rd.capabilities.map((cap, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-current flex-shrink-0 opacity-40" />
                    {cap}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─── Module Row Component ───────────────────────────────────── */
function ModuleRow({
  mod, isExpanded, hasTabs, permissions, onToggleExpand, onSetAccess, onSetTabVisible, onSetAction,
}: {
  mod: ModuleDef;
  isExpanded: boolean;
  hasTabs: boolean;
  permissions: PermissionConfig;
  onToggleExpand: () => void;
  onSetAccess: (role: EditableRole, modId: string, access: AccessLevel) => void;
  onSetTabVisible: (role: EditableRole, modId: string, tabId: string, visible: boolean) => void;
  onSetAction: (role: EditableRole, modId: string, tabId: string, actId: string, enabled: boolean) => void;
}) {
  return (
    <>
      {/* Module row */}
      <tr className="hover:bg-gray-50 dark:hover:bg-gray-800/40 transition-colors">
        <td className="px-5 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">
          <div className="flex items-center gap-2">
            {hasTabs ? (
              <button onClick={onToggleExpand} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </button>
            ) : (
              <span className="w-4" />
            )}
            <span>{mod.name}</span>
            {mod.superAdminOnly && <span className="text-[10px] font-medium text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/30 px-1.5 py-0.5 rounded">SA Only</span>}
            {hasTabs && <span className="text-[10px] text-gray-400">{mod.tabs!.length} tabs</span>}
          </div>
        </td>
        {/* Super Admin — always full */}
        <td className="px-4 py-3 text-center"><AccessBadge level="full_static" /></td>
        {/* Editable roles */}
        {EDITABLE_ROLES.map(r => (
          <td key={r.key} className="px-4 py-3 text-center">
            <AccessDropdown
              value={permissions[r.key][mod.id]?.access ?? 'no_access'}
              onChange={v => onSetAccess(r.key, mod.id, v)}
              disabled={mod.superAdminOnly}
            />
          </td>
        ))}
      </tr>

      {/* Expanded tabs */}
      {isExpanded && hasTabs && mod.tabs!.map(tab => {
        const hasActions = tab.actions && tab.actions.length > 0;
        return (
          <TabRows
            key={tab.id}
            mod={mod}
            tab={tab}
            hasActions={!!hasActions}
            permissions={permissions}
            onSetTabVisible={onSetTabVisible}
            onSetAction={onSetAction}
          />
        );
      })}
    </>
  );
}

/* ─── Tab Rows Component ─────────────────────────────────────── */
function TabRows({
  mod, tab, hasActions, permissions, onSetTabVisible, onSetAction,
}: {
  mod: ModuleDef;
  tab: TabDef;
  hasActions: boolean;
  permissions: PermissionConfig;
  onSetTabVisible: (role: EditableRole, modId: string, tabId: string, visible: boolean) => void;
  onSetAction: (role: EditableRole, modId: string, tabId: string, actId: string, enabled: boolean) => void;
}) {
  return (
    <>
      {/* Tab row */}
      <tr className="bg-gray-50/80 dark:bg-gray-800/30">
        <td className="px-5 py-2.5 text-sm text-gray-700 dark:text-gray-300">
          <div className="flex items-center gap-2 pl-10">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500" />
            <span className="font-medium">{tab.name}</span>
            {hasActions && <span className="text-[10px] text-gray-400">{tab.actions!.length} actions</span>}
          </div>
        </td>
        {/* Super Admin — always visible */}
        <td className="px-4 py-2.5 text-center">
          <span className="text-green-600 dark:text-green-400 text-xs font-medium">Visible</span>
        </td>
        {/* Editable roles — tab toggle */}
        {EDITABLE_ROLES.map(r => {
          const modAccess = permissions[r.key][mod.id]?.access ?? 'no_access';
          const tabPerm = permissions[r.key][mod.id]?.tabs?.[tab.id];
          const disabled = modAccess === 'no_access';
          return (
            <td key={r.key} className="px-4 py-2.5 text-center">
              <ToggleSwitch
                checked={tabPerm?.visible ?? false}
                onChange={v => onSetTabVisible(r.key, mod.id, tab.id, v)}
                disabled={disabled}
              />
            </td>
          );
        })}
      </tr>

      {/* Action rows */}
      {hasActions && tab.actions!.map(action => (
        <tr key={action.id} className="bg-gray-50/40 dark:bg-gray-800/15">
          <td className="px-5 py-2 text-xs text-gray-500 dark:text-gray-400">
            <div className="pl-16 flex items-center gap-2">
              <span className="w-1 h-1 rounded-full bg-gray-300 dark:bg-gray-600" />
              {action.name}
            </div>
          </td>
          {/* Super Admin — always enabled */}
          <td className="px-4 py-2 text-center">
            <span className="text-green-500 text-xs"><Check className="h-3.5 w-3.5 inline" /></span>
          </td>
          {/* Editable roles — action toggle */}
          {EDITABLE_ROLES.map(r => {
            const modAccess = permissions[r.key][mod.id]?.access ?? 'no_access';
            const tabPerm = permissions[r.key][mod.id]?.tabs?.[tab.id];
            const disabled = modAccess === 'no_access' || !tabPerm?.visible;
            const checked = tabPerm?.actions?.[action.id] ?? false;
            return (
              <td key={r.key} className="px-4 py-2 text-center">
                <ToggleSwitch
                  checked={checked}
                  onChange={v => onSetAction(r.key, mod.id, tab.id, action.id, v)}
                  disabled={disabled}
                />
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}

/* ─── Role Descriptions ──────────────────────────────────────── */
const ROLE_DESCRIPTIONS = [
  {
    role: 'Super Admin',
    icon: <Crown className="h-6 w-6 text-purple-500" />,
    color: 'bg-purple-50 dark:bg-purple-950/30',
    borderColor: 'border-purple-200 dark:border-purple-800',
    description: 'Highest privilege level with unrestricted system access across all tenants.',
    capabilities: [
      'Full system access across all modules',
      'Create and manage all tenants',
      'Create and manage admin accounts',
      'Cross-tenant data access and reporting',
      'System-wide settings and configuration',
      'Manage global templates and integrations',
    ],
  },
  {
    role: 'Admin',
    icon: <ShieldCheck className="h-6 w-6 text-blue-500" />,
    color: 'bg-blue-50 dark:bg-blue-950/30',
    borderColor: 'border-blue-200 dark:border-blue-800',
    description: 'Full control within their own tenant scope. Cannot access other tenants.',
    capabilities: [
      'Full access to most modules within own tenant',
      'Run and monitor all outreach campaigns',
      'Manage mailboxes and templates',
      'Run pipelines (sourcing, enrichment, validation)',
      'View and export all tenant data',
      'Permissions managed by Super Admin',
    ],
  },
  {
    role: 'Operator',
    icon: <UserCog className="h-6 w-6 text-green-500" />,
    color: 'bg-green-50 dark:bg-green-950/30',
    borderColor: 'border-green-200 dark:border-green-800',
    description: 'Day-to-day operational access for running campaigns and managing data.',
    capabilities: [
      'Run pipelines (lead sourcing, enrichment, validation, outreach)',
      'Manage mailboxes and templates',
      'Create, read, update leads and contacts',
      'Execute and monitor outreach campaigns',
      'View dashboard metrics',
      'No access to settings or user management',
    ],
  },
  {
    role: 'Viewer',
    icon: <Eye className="h-6 w-6 text-amber-500" />,
    color: 'bg-amber-50 dark:bg-amber-950/30',
    borderColor: 'border-amber-200 dark:border-amber-800',
    description: 'Read-only access to view data within their own tenant. Cannot modify anything.',
    capabilities: [
      'View dashboard and metrics',
      'View leads, clients, and contacts',
      'View validation results',
      'No access to outreach, templates, or mailboxes',
      'No access to settings or user management',
      'Cannot create, update, or delete any records',
    ],
  },
];
