'use client'

import { useEffect, useState, useRef } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { useAuthStore } from '@/lib/store'
import { warmupApi, tenantsApi } from '@/lib/api'
import type { TenantSummary } from '@/types/api'
import { ErrorBoundary } from '@/components/error-boundary'
import { OfflineBanner } from '@/components/offline-banner'
import { ImpersonationBanner } from '@/components/impersonation-banner'
import { useTheme } from '@/components/theme-provider'
import { useKeyboardShortcuts } from '@/hooks/use-keyboard-shortcuts'
import { useTour } from '@/hooks/use-tour'
import { CopilotChat } from '@/components/copilot-chat'
import { CommandPalette } from '@/components/command-palette'
import { NotificationCenter } from '@/components/notification-center'
import { LobSelector } from '@/components/lob-selector'
import {
  LayoutDashboard,
  Users,
  FileText,
  Mail,
  Settings,
  LogOut,
  CheckCircle,
  Building,
  BarChart3,
  Inbox,
  Flame,
  FileEdit,
  Menu,
  X,
  Sun,
  Moon,
  Keyboard,
  UserCog,
  Shield,
  HardDrive,
  Zap,
  MessageSquare,
  DollarSign,
  Search,
  Target,
  TrendingUp,
  Wand2,
  ListChecks,
  Building2,
  Receipt,
  ScrollText,
  HelpCircle,
  Eye,
  FileSearch,
  ChevronsLeft,
  ChevronsRight,
  FileBarChart,
  Layers,
  Ban,
} from 'lucide-react'

const navigation = [
  // Home
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard, iconColor: 'text-sky-400' },

  // Step 1: Setup — mailboxes & warmup
  { name: 'Mailboxes', href: '/dashboard/mailboxes', icon: Inbox, iconColor: 'text-purple-400', roles: ['super_admin', 'admin', 'operator'] as string[], tourId: 'nav-mailboxes' },
  { name: 'Warmup Engine', href: '/dashboard/warmup', icon: Flame, iconColor: 'text-orange-500', roles: ['super_admin', 'admin', 'operator'] as string[] },

  // Step 2: Source — pipeline execution & lead results
  { name: 'Pipelines', href: '/dashboard/pipelines', icon: BarChart3, iconColor: 'text-blue-500', roles: ['super_admin', 'admin', 'operator'] as string[] },
  { name: 'Leads', href: '/dashboard/leads', icon: FileText, iconColor: 'text-indigo-400', tourId: 'nav-leads' },
  { name: 'Clients', href: '/dashboard/clients', icon: Building, iconColor: 'text-slate-400' },

  // Step 3: Enrich & Step 4: Validate
  { name: 'Contacts', href: '/dashboard/contacts', icon: Users, iconColor: 'text-violet-400', tourId: 'nav-contacts' },
  { name: 'Validation', href: '/dashboard/validation', icon: CheckCircle, iconColor: 'text-emerald-400', tourId: 'nav-validation' },

  // Step 5: Campaign — targeting, templates, sequences, outreach
  { name: 'ICP Wizard', href: '/dashboard/icp-wizard', icon: Target, iconColor: 'text-rose-400', roles: ['super_admin', 'admin', 'operator'] as string[] },
  { name: 'Email Templates', href: '/dashboard/templates', icon: FileEdit, iconColor: 'text-blue-400', roles: ['super_admin', 'admin', 'operator'] as string[] },
  { name: 'Campaigns', href: '/dashboard/campaigns', icon: Zap, iconColor: 'text-amber-400', roles: ['super_admin', 'admin', 'operator'] as string[], tourId: 'nav-campaigns' },
  { name: 'Outreach', href: '/dashboard/outreach', icon: Mail, iconColor: 'text-orange-400', roles: ['super_admin', 'admin', 'operator'] as string[] },
  { name: 'Email Preview', href: '/dashboard/email-preview', icon: FileSearch, iconColor: 'text-teal-400', roles: ['super_admin', 'admin', 'operator'] as string[] },

  // Step 6: Engage & Close
  { name: 'Inbox', href: '/dashboard/inbox', icon: MessageSquare, iconColor: 'text-teal-400', roles: ['super_admin', 'admin', 'operator'] as string[], tourId: 'nav-inbox' },
  { name: 'Deals', href: '/dashboard/deals', icon: DollarSign, iconColor: 'text-green-400', roles: ['super_admin', 'admin', 'operator'] as string[], tourId: 'nav-deals' },

  // Reporting & Monitoring
  { name: 'Reports', href: '/dashboard/reports', icon: FileBarChart, iconColor: 'text-emerald-500', roles: ['super_admin', 'admin', 'operator'] as string[] },
  { name: 'Analytics', href: '/dashboard/analytics', icon: TrendingUp, iconColor: 'text-cyan-400', roles: ['super_admin', 'admin'] as string[] },
  { name: 'Visitors', href: '/dashboard/visitors', icon: Eye, iconColor: 'text-pink-400', roles: ['super_admin', 'admin'] as string[] },
  { name: 'Automation', href: '/dashboard/automation', icon: ListChecks, iconColor: 'text-lime-400', roles: ['super_admin', 'admin'] as string[] },

  // Administration
  { name: 'Activity Log', href: '/dashboard/activity-log', icon: ScrollText, iconColor: 'text-cyan-400', roles: ['super_admin'] as string[] },
  { name: 'User Management', href: '/dashboard/users', icon: UserCog, iconColor: 'text-pink-400', roles: ['super_admin', 'admin'] as string[] },
  { name: 'Roles & Permissions', href: '/dashboard/roles', icon: Shield, iconColor: 'text-yellow-400', roles: ['super_admin'] as string[] },
  { name: 'Tenant Management', href: '/dashboard/tenants', icon: Building2, iconColor: 'text-red-400', roles: ['super_admin'] as string[] },
  { name: 'Billing', href: '/dashboard/billing', icon: Receipt, iconColor: 'text-emerald-400', roles: ['super_admin', 'admin', 'operator'] as string[] },
  { name: 'Data Backups', href: '/dashboard/backups', icon: HardDrive, iconColor: 'text-gray-400', roles: ['super_admin', 'admin'] as string[] },
  { name: 'Lines of Business', href: '/dashboard/lob', icon: Layers, iconColor: 'text-violet-400', roles: ['super_admin', 'admin'] as string[] },
  { name: 'Excluded Companies', href: '/dashboard/settings/excluded-companies', icon: Ban, iconColor: 'text-red-400', roles: ['super_admin', 'admin'] as string[] },
  { name: 'Settings', href: '/dashboard/settings', icon: Settings, iconColor: 'text-zinc-400', roles: ['super_admin', 'admin'] as string[] },
]

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const pathname = usePathname()
  const { user, logout, isAuthenticated, impersonation, startImpersonation, stopImpersonation } = useAuthStore()
  const { theme, toggleTheme } = useTheme()
  const { helpOpen, setHelpOpen, shortcuts } = useKeyboardShortcuts()
  const { startTour } = useTour()
  const [mounted, setMounted] = useState(false)
  const [unreadAlerts, setUnreadAlerts] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const profileRef = useRef<HTMLDivElement>(null)
  const [tenantList, setTenantList] = useState<TenantSummary[]>([])
  const [tenantLoading, setTenantLoading] = useState(false)

  useEffect(() => {
    if (!profileOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [profileOpen])

  // Handle mounting to avoid hydration mismatch
  useEffect(() => {
    setMounted(true)
    const saved = localStorage.getItem('sidebar_collapsed')
    if (saved === 'true') setSidebarCollapsed(true)
  }, [])

  useEffect(() => {
    if (mounted && !isAuthenticated()) {
      router.push('/login')
    }
  }, [router, isAuthenticated, mounted])

  useEffect(() => {
    if (mounted && isAuthenticated()) {
      warmupApi.getUnreadCount().then(data => setUnreadAlerts(data?.unread_count || 0)).catch(() => {})
      const interval = setInterval(() => {
        warmupApi.getUnreadCount().then(data => setUnreadAlerts(data?.unread_count || 0)).catch(() => {})
      }, 60000)
      return () => clearInterval(interval)
    }
  }, [mounted])

  // Auto-launch tour on first visit
  useEffect(() => {
    if (mounted && isAuthenticated() && pathname === '/dashboard') {
      const tourDone = localStorage.getItem('tour_completed')
      if (!tourDone) {
        const timer = setTimeout(() => startTour(), 1500)
        return () => clearTimeout(timer)
      }
    }
  }, [mounted, pathname])

  // Fetch tenant list for super_admin dropdown
  useEffect(() => {
    if (mounted && isAuthenticated() && user?.role === 'super_admin') {
      setTenantLoading(true)
      tenantsApi.list({ limit: 100 })
        .then(data => setTenantList(Array.isArray(data) ? data : data.tenants || []))
        .catch(() => {})
        .finally(() => setTenantLoading(false))
    }
  }, [mounted, user?.role])

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false)
  }, [pathname])

  const toggleSidebarCollapse = () => {
    const next = !sidebarCollapsed
    setSidebarCollapsed(next)
    localStorage.setItem('sidebar_collapsed', String(next))
    setProfileOpen(false)
  }

  const handleLogout = () => {
    logout()
    router.push('/login')
  }

  const handleTenantSwitch = async (tenantId: string) => {
    if (!tenantId) {
      stopImpersonation()
      window.location.reload()
      return
    }
    const tenant = tenantList.find(t => t.tenant_id === Number(tenantId))
    if (!tenant) return
    try {
      const result = await tenantsApi.impersonate(tenant.tenant_id)
      startImpersonation(result.tenant_id, result.tenant_name, tenant.plan)
      window.location.reload()
    } catch {
      // silently fail — tenant management page can show errors
    }
  }

  // Show loading state until mounted to avoid hydration mismatch
  if (!mounted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  if (!isAuthenticated()) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900">
        <div className="text-gray-500">Redirecting to login...</div>
      </div>
    )
  }

  // isCollapsed only applies on desktop; mobile sidebar is always expanded
  const isCollapsed = sidebarCollapsed && mounted

  const sidebarContent = (isMobileOverlay: boolean) => {
    const collapsed = isCollapsed && !isMobileOverlay
    return (
      <>
        <div className={`border-b border-gray-700 ${collapsed ? 'p-2' : 'p-4'}`}>
          <div className="flex items-center justify-between">
            {collapsed ? (
              <div className="w-full flex justify-center">
                <span className="text-lg font-bold">N</span>
              </div>
            ) : (
              <h1 className="text-xl font-bold">NeuraLeads</h1>
            )}
            {/* Desktop collapse toggle */}
            <button
              onClick={toggleSidebarCollapse}
              className="hidden lg:flex items-center justify-center w-7 h-7 text-gray-400 hover:text-white hover:bg-gray-700 rounded-md transition-colors group relative"
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {collapsed ? <ChevronsRight className="w-4 h-4" /> : <ChevronsLeft className="w-4 h-4" />}
              <span className="absolute left-full ml-2 px-2 py-1 bg-gray-800 text-white text-xs rounded-md shadow-lg whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-[60]">
                {collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              </span>
            </button>
            {/* Mobile close button */}
            <button
              onClick={() => setSidebarOpen(false)}
              className="lg:hidden text-gray-400 hover:text-white"
              aria-label="Close sidebar"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          {!collapsed && user?.role === 'super_admin' ? (
            <select
              value={impersonation?.tenantId?.toString() || ''}
              onChange={(e) => handleTenantSwitch(e.target.value)}
              disabled={tenantLoading}
              className="mt-2 w-full bg-gray-800 text-gray-300 text-sm border border-gray-600 rounded-md px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500 cursor-pointer disabled:opacity-50"
            >
              <option value="">All Tenants</option>
              {tenantList.filter(t => t.is_active).map(t => (
                <option key={t.tenant_id} value={t.tenant_id.toString()}>
                  {t.name} ({t.plan})
                </option>
              ))}
            </select>
          ) : !collapsed ? (
            <p className="text-gray-400 text-sm mt-1 truncate">
              {user?.tenant?.name || 'Admin Panel'}
            </p>
          ) : null}
        </div>

        {/* LOB Selector — switch between Lines of Business */}
        <LobSelector collapsed={collapsed} />

        <nav className={`flex-1 space-y-1 overflow-y-auto ${collapsed ? 'p-2' : 'p-4'}`} aria-label="Main navigation" data-tour="sidebar">
          {navigation.filter(item => {
            if (item.roles && !item.roles.includes(user?.role || 'viewer')) return false
            return true
          }).map((item) => {
            const isActive = item.href === '/dashboard'
              ? pathname === '/dashboard'
              : pathname.startsWith(item.href)
            return (
              <Link
                key={item.name}
                href={item.href}
                aria-current={isActive ? 'page' : undefined}
                data-tour={item.tourId || undefined}
                title={collapsed ? item.name : undefined}
                className={`flex items-center gap-3 rounded-lg transition-colors relative group ${
                  collapsed ? 'justify-center px-2 py-2' : 'px-3 py-2'
                } ${
                  isActive
                    ? 'bg-primary-600 text-white font-medium'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                }`}
              >
                <item.icon className={`w-5 h-5 flex-shrink-0 ${isActive ? 'text-white' : item.iconColor}`} aria-hidden="true" />
                {!collapsed && item.name}
                {!collapsed && item.name === 'Warmup Engine' && unreadAlerts > 0 && (
                  <span className="ml-auto bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center" aria-label={`${unreadAlerts} unread alerts`}>{unreadAlerts > 9 ? '9+' : unreadAlerts}</span>
                )}
                {collapsed && item.name === 'Warmup Engine' && unreadAlerts > 0 && (
                  <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">{unreadAlerts > 9 ? '9+' : unreadAlerts}</span>
                )}
                {/* Tooltip on hover when collapsed */}
                {collapsed && (
                  <span className="absolute left-full ml-2 px-2 py-1 bg-gray-800 text-white text-xs rounded-md shadow-lg whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-[60]">
                    {item.name}
                  </span>
                )}
              </Link>
            )
          })}
        </nav>

        <div ref={profileRef} className={`border-t border-gray-700 relative ${collapsed ? 'p-2' : 'p-4'}`}>
          {/* Notification bell + Cmd+K hint (desktop, expanded only) */}
          {!collapsed && (
            <div className="hidden lg:flex items-center gap-2 mb-3 px-2">
              <div className="[&_button]:text-gray-400 [&_button]:hover:text-white [&_button:hover]:bg-gray-700">
                <NotificationCenter />
              </div>
              <button
                onClick={() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))}
                className="flex items-center gap-2 flex-1 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors border border-gray-700"
                title="Command Palette"
              >
                <Search className="w-3.5 h-3.5" />
                <span>Search...</span>
                <kbd className="ml-auto text-[10px] font-mono bg-gray-700 px-1 py-0.5 rounded">Ctrl+K</kbd>
              </button>
            </div>
          )}

          {/* Collapsed: just show avatar with tooltip */}
          {collapsed ? (
            <div className="relative group">
              <button
                onClick={() => setProfileOpen(!profileOpen)}
                className="w-full flex justify-center p-1 rounded-lg hover:bg-gray-800 transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-primary-600 flex items-center justify-center flex-shrink-0" aria-hidden="true">
                  {user?.email?.[0]?.toUpperCase() || 'U'}
                </div>
              </button>
              <span className="absolute left-full ml-2 bottom-0 px-2 py-1 bg-gray-800 text-white text-xs rounded-md shadow-lg whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-[60]">
                {user?.full_name || user?.email}
              </span>
            </div>
          ) : (
            <button
              onClick={() => setProfileOpen(!profileOpen)}
              className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-gray-800 transition-colors cursor-pointer"
            >
              <div className="w-8 h-8 rounded-full bg-primary-600 flex items-center justify-center flex-shrink-0" aria-hidden="true">
                {user?.email?.[0]?.toUpperCase() || 'U'}
              </div>
              <div className="flex-1 min-w-0 text-left">
                <p className="text-sm font-medium truncate">{user?.full_name || user?.email}</p>
                <p className="text-xs text-gray-400 capitalize">{user?.role?.replace('_', ' ')}</p>
              </div>
              <svg className={`w-4 h-4 text-gray-400 transition-transform ${profileOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" /></svg>
            </button>
          )}

          {/* Profile dropdown popover */}
          {profileOpen && (
            <div className={`absolute bottom-full mb-2 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden ${collapsed ? 'left-full ml-2 w-56 bottom-0' : 'left-4 right-4'}`}>
              {/* User details */}
              <div className="p-4 border-b border-gray-700">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary-600 flex items-center justify-center text-lg font-semibold" aria-hidden="true">
                    {user?.email?.[0]?.toUpperCase() || 'U'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-white truncate">{user?.full_name || 'User'}</p>
                    <p className="text-xs text-gray-400 truncate">{user?.email}</p>
                    <span className="inline-flex items-center px-1.5 py-0.5 mt-1 rounded text-[10px] font-medium bg-primary-600/20 text-primary-400 capitalize">
                      {user?.role?.replace('_', ' ')}
                    </span>
                  </div>
                </div>
              </div>
              {/* Actions */}
              <div className="p-2">
                <button
                  onClick={() => { toggleTheme(); setProfileOpen(false); }}
                  className="w-full flex items-center gap-3 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white rounded-lg transition-colors"
                >
                  {theme === 'light' ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
                  {theme === 'light' ? 'Dark mode' : 'Light mode'}
                </button>
                <button
                  onClick={() => { setHelpOpen(true); setProfileOpen(false); }}
                  className="w-full flex items-center gap-3 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white rounded-lg transition-colors"
                >
                  <Keyboard className="w-4 h-4" />
                  Keyboard shortcuts
                </button>
                <div className="border-t border-gray-700 my-1" />
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-3 px-3 py-2 text-sm text-red-400 hover:bg-red-900/30 hover:text-red-300 rounded-lg transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </>
    )
  }

  return (
    <div className="min-h-screen flex">
      <OfflineBanner />
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar - hidden on mobile, always visible on desktop */}
      {/* Mobile sidebar (always full-width w-64) */}
      <div className={`
        fixed inset-y-0 left-0 z-50 w-64 bg-gray-900 text-white flex flex-col
        transform transition-transform duration-200 ease-in-out
        lg:hidden
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {sidebarContent(true)}
      </div>
      {/* Desktop sidebar (collapsible) */}
      <div className={`
        hidden lg:flex flex-col bg-gray-900 text-white flex-shrink-0
        transition-[width] duration-200 ease-in-out
        ${isCollapsed ? 'w-16' : 'w-64'}
      `}>
        {sidebarContent(false)}
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-auto min-w-0">
        <ImpersonationBanner />
        {/* Mobile header */}
        <div className="lg:hidden flex items-center gap-3 p-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white"
            aria-label="Open sidebar"
          >
            <Menu className="w-6 h-6" />
          </button>
          <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 flex-1">NeuraLeads</h1>
          <NotificationCenter />
        </div>
        <main className="p-4 lg:p-8 dark:text-gray-100"><ErrorBoundary>{children}</ErrorBoundary></main>
      </div>

      {/* Floating help / tour button */}
      <button
        data-tour="help-button"
        onClick={startTour}
        className="fixed bottom-6 right-6 z-40 w-10 h-10 rounded-full bg-indigo-600 hover:bg-indigo-700 text-white shadow-lg flex items-center justify-center transition-colors"
        title="Replay guided tour"
      >
        <HelpCircle className="w-5 h-5" />
      </button>

      {/* AI Copilot Chat Widget */}
      <CopilotChat />

      {/* Command Palette (Cmd+K / Ctrl+K) */}
      <CommandPalette />

      {/* Keyboard shortcuts help dialog */}
      {helpOpen && (
        <>
          <div className="fixed inset-0 bg-black bg-opacity-50 z-[60]" onClick={() => setHelpOpen(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[61] bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-96 max-w-[90vw]">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold dark:text-gray-100">Keyboard Shortcuts</h2>
              <button onClick={() => setHelpOpen(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-2">
              {shortcuts.map((s) => (
                <div key={s.key + (s.ctrl ? 'c' : '') + (s.shift ? 's' : '')} className="flex items-center justify-between text-sm">
                  <span className="text-gray-600 dark:text-gray-300">{s.description}</span>
                  <kbd className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-xs font-mono">
                    {s.ctrl ? 'Ctrl+' : ''}{s.shift ? 'Shift+' : ''}{s.key === '?' ? '?' : s.key.toUpperCase()}
                  </kbd>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
