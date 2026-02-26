'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuthStore } from '@/lib/store'
import { warmupApi } from '@/lib/api'
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
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Leads', href: '/dashboard/leads', icon: FileText },
  { name: 'Clients', href: '/dashboard/clients', icon: Building },
  { name: 'Contacts', href: '/dashboard/contacts', icon: Users },
  { name: 'Validation', href: '/dashboard/validation', icon: CheckCircle },
  { name: 'Outreach', href: '/dashboard/outreach', icon: Mail },
  { name: 'Email Templates', href: '/dashboard/templates', icon: FileEdit },
  { name: 'Mailboxes', href: '/dashboard/mailboxes', icon: Inbox },
  { name: 'Warmup Engine', href: '/dashboard/warmup', icon: Flame },
  { name: 'Pipelines', href: '/dashboard/pipelines', icon: BarChart3 },
  { name: 'Settings', href: '/dashboard/settings', icon: Settings },
]

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const { user, logout, isAuthenticated } = useAuthStore()
  const [mounted, setMounted] = useState(false)
  const [unreadAlerts, setUnreadAlerts] = useState(0)

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

  const handleLogout = () => {
    logout()
    router.push('/login')
  }

  // Show loading state until mounted to avoid hydration mismatch
  if (!mounted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  if (!isAuthenticated()) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="text-gray-500">Redirecting to login...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <div className="w-64 bg-gray-900 text-white flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <h1 className="text-xl font-bold">Exzelon RA</h1>
          <p className="text-gray-400 text-sm mt-1">Admin Panel</p>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navigation.map((item) => (
            <Link
              key={item.name}
              href={item.href}
              className="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-300 hover:bg-gray-800 hover:text-white transition-colors"
            >
              <item.icon className="w-5 h-5" />
              {item.name}
              {item.name === 'Warmup Engine' && unreadAlerts > 0 && (
                <span className="ml-auto bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">{unreadAlerts > 9 ? '9+' : unreadAlerts}</span>
              )}
            </Link>
          ))}
        </nav>

        <div className="p-4 border-t border-gray-700">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-full bg-primary-600 flex items-center justify-center">
              {user?.email?.[0]?.toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.full_name || user?.email}</p>
              <p className="text-xs text-gray-400 capitalize">{user?.role}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-gray-400 hover:text-white text-sm"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-auto">
        <main className="p-8">{children}</main>
      </div>
    </div>
  )
}
