'use client'

import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { useAuthStore } from '@/lib/store'
import { warmupApi } from '@/lib/api'
import { ErrorBoundary } from '@/components/error-boundary'
import { OfflineBanner } from '@/components/offline-banner'
import { useTheme } from '@/components/theme-provider'
import { useKeyboardShortcuts } from '@/hooks/use-keyboard-shortcuts'
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
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Leads', href: '/dashboard/leads', icon: FileText },
  { name: 'Clients', href: '/dashboard/clients', icon: Building },
  { name: 'Contacts', href: '/dashboard/contacts', icon: Users },
  { name: 'Validation', href: '/dashboard/validation', icon: CheckCircle },
  { name: 'Outreach', href: '/dashboard/outreach', icon: Mail, roles: ['super_admin', 'admin', 'operator'] as string[] },
  { name: 'Email Templates', href: '/dashboard/templates', icon: FileEdit, roles: ['super_admin', 'admin', 'operator'] as string[] },
  { name: 'Mailboxes', href: '/dashboard/mailboxes', icon: Inbox, roles: ['super_admin', 'admin', 'operator'] as string[] },
  { name: 'Warmup Engine', href: '/dashboard/warmup', icon: Flame, roles: ['super_admin', 'admin', 'operator'] as string[] },
  { name: 'Pipelines', href: '/dashboard/pipelines', icon: BarChart3, roles: ['super_admin', 'admin', 'operator'] as string[] },
  { name: 'User Management', href: '/dashboard/users', icon: UserCog, roles: ['super_admin', 'admin'] as string[] },
  { name: 'Roles & Permissions', href: '/dashboard/roles', icon: Shield, roles: ['super_admin'] as string[] },
  { name: 'Data Backups', href: '/dashboard/backups', icon: HardDrive, roles: ['super_admin'] as string[] },
  { name: 'Settings', href: '/dashboard/settings', icon: Settings, roles: ['super_admin', 'admin'] as string[] },
]

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const pathname = usePathname()
  const { user, logout, isAuthenticated } = useAuthStore()
  const { theme, toggleTheme } = useTheme()
  const { helpOpen, setHelpOpen, shortcuts } = useKeyboardShortcuts()
  const [mounted, setMounted] = useState(false)
  const [unreadAlerts, setUnreadAlerts] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Handle mounting to avoid hydration mismatch
  useEffect(() => {
    setMounted(true)
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

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false)
  }, [pathname])

  const handleLogout = () => {
    logout()
    router.push('/login')
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

  const sidebarContent = (
    <>
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold">Exzelon RA</h1>
            <p className="text-gray-400 text-sm mt-1">Admin Panel</p>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden text-gray-400 hover:text-white"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      <nav className="flex-1 p-4 space-y-1" aria-label="Main navigation">
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
              className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                isActive
                  ? 'bg-primary-600 text-white font-medium'
                  : 'text-gray-300 hover:bg-gray-800 hover:text-white'
              }`}
            >
              <item.icon className="w-5 h-5" aria-hidden="true" />
              {item.name}
              {item.name === 'Warmup Engine' && unreadAlerts > 0 && (
                <span className="ml-auto bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center" aria-label={`${unreadAlerts} unread alerts`}>{unreadAlerts > 9 ? '9+' : unreadAlerts}</span>
              )}
            </Link>
          )
        })}
      </nav>

      <div className="p-4 border-t border-gray-700">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-8 h-8 rounded-full bg-primary-600 flex items-center justify-center" aria-hidden="true">
            {user?.email?.[0]?.toUpperCase() || 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{user?.full_name || user?.email}</p>
            <p className="text-xs text-gray-400 capitalize">{user?.role}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 mb-2">
          <button
            onClick={toggleTheme}
            className="flex items-center gap-2 text-gray-400 hover:text-white text-sm"
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
          >
            {theme === 'light' ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
            {theme === 'light' ? 'Dark mode' : 'Light mode'}
          </button>
          <button
            onClick={() => setHelpOpen(true)}
            className="ml-auto text-gray-400 hover:text-white"
            aria-label="Keyboard shortcuts"
            title="Keyboard shortcuts (Shift+?)"
          >
            <Keyboard className="w-4 h-4" />
          </button>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 text-gray-400 hover:text-white text-sm"
        >
          <LogOut className="w-4 h-4" aria-hidden="true" />
          Sign out
        </button>
      </div>
    </>
  )

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
      <div className={`
        fixed inset-y-0 left-0 z-50 w-64 bg-gray-900 text-white flex flex-col
        transform transition-transform duration-200 ease-in-out
        lg:relative lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {sidebarContent}
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-auto min-w-0">
        {/* Mobile header */}
        <div className="lg:hidden flex items-center gap-3 p-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white"
            aria-label="Open sidebar"
          >
            <Menu className="w-6 h-6" />
          </button>
          <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100">Exzelon RA</h1>
        </div>
        <main className="p-4 lg:p-8 dark:text-gray-100"><ErrorBoundary>{children}</ErrorBoundary></main>
      </div>

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
