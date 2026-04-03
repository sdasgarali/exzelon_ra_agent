'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  Search, X, LayoutDashboard, FileText, Users, Mail, Settings,
  CheckCircle, Building, BarChart3, Inbox, Flame, FileEdit,
  Zap, MessageSquare, DollarSign, TrendingUp, Target, Shield,
  UserCog, HardDrive, Building2, Receipt, ScrollText, ListChecks,
  Eye, ArrowRight, Play, PlusCircle, Download,
} from 'lucide-react'
import { api } from '@/lib/api'

interface CommandItem {
  id: string
  label: string
  description?: string
  icon: React.ReactNode
  action: () => void
  section: 'navigate' | 'actions' | 'search'
}

export function CommandPalette() {
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const [searchResults, setSearchResults] = useState<CommandItem[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const router = useRouter()
  const searchTimeout = useRef<NodeJS.Timeout | null>(null)

  // Listen for Cmd+K / Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setIsOpen(prev => !prev)
      }
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen])

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setActiveIndex(0)
      setSearchResults([])
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  // Navigation items
  const navigationItems: CommandItem[] = [
    { id: 'nav-dashboard', label: 'Dashboard', icon: <LayoutDashboard className="w-4 h-4 text-sky-400" />, action: () => router.push('/dashboard'), section: 'navigate' },
    { id: 'nav-mailboxes', label: 'Mailboxes', icon: <Inbox className="w-4 h-4 text-purple-400" />, action: () => router.push('/dashboard/mailboxes'), section: 'navigate' },
    { id: 'nav-warmup', label: 'Warmup Engine', icon: <Flame className="w-4 h-4 text-orange-500" />, action: () => router.push('/dashboard/warmup'), section: 'navigate' },
    { id: 'nav-pipelines', label: 'Pipelines', icon: <BarChart3 className="w-4 h-4 text-blue-500" />, action: () => router.push('/dashboard/pipelines'), section: 'navigate' },
    { id: 'nav-leads', label: 'Leads', icon: <FileText className="w-4 h-4 text-indigo-400" />, action: () => router.push('/dashboard/leads'), section: 'navigate' },
    { id: 'nav-clients', label: 'Clients', icon: <Building className="w-4 h-4 text-slate-400" />, action: () => router.push('/dashboard/clients'), section: 'navigate' },
    { id: 'nav-contacts', label: 'Contacts', icon: <Users className="w-4 h-4 text-violet-400" />, action: () => router.push('/dashboard/contacts'), section: 'navigate' },
    { id: 'nav-validation', label: 'Validation', icon: <CheckCircle className="w-4 h-4 text-emerald-400" />, action: () => router.push('/dashboard/validation'), section: 'navigate' },
    { id: 'nav-icp', label: 'ICP Wizard', icon: <Target className="w-4 h-4 text-rose-400" />, action: () => router.push('/dashboard/icp-wizard'), section: 'navigate' },
    { id: 'nav-templates', label: 'Email Templates', icon: <FileEdit className="w-4 h-4 text-blue-400" />, action: () => router.push('/dashboard/templates'), section: 'navigate' },
    { id: 'nav-campaigns', label: 'Campaigns', icon: <Zap className="w-4 h-4 text-amber-400" />, action: () => router.push('/dashboard/campaigns'), section: 'navigate' },
    { id: 'nav-outreach', label: 'Outreach', icon: <Mail className="w-4 h-4 text-orange-400" />, action: () => router.push('/dashboard/outreach'), section: 'navigate' },
    { id: 'nav-inbox', label: 'Inbox', icon: <MessageSquare className="w-4 h-4 text-teal-400" />, action: () => router.push('/dashboard/inbox'), section: 'navigate' },
    { id: 'nav-deals', label: 'Deals', icon: <DollarSign className="w-4 h-4 text-green-400" />, action: () => router.push('/dashboard/deals'), section: 'navigate' },
    { id: 'nav-analytics', label: 'Analytics', icon: <TrendingUp className="w-4 h-4 text-cyan-400" />, action: () => router.push('/dashboard/analytics'), section: 'navigate' },
    { id: 'nav-visitors', label: 'Visitors', icon: <Eye className="w-4 h-4 text-pink-400" />, action: () => router.push('/dashboard/visitors'), section: 'navigate' },
    { id: 'nav-automation', label: 'Automation', icon: <ListChecks className="w-4 h-4 text-lime-400" />, action: () => router.push('/dashboard/automation'), section: 'navigate' },
    { id: 'nav-users', label: 'User Management', icon: <UserCog className="w-4 h-4 text-pink-400" />, action: () => router.push('/dashboard/users'), section: 'navigate' },
    { id: 'nav-roles', label: 'Roles & Permissions', icon: <Shield className="w-4 h-4 text-yellow-400" />, action: () => router.push('/dashboard/roles'), section: 'navigate' },
    { id: 'nav-tenants', label: 'Tenant Management', icon: <Building2 className="w-4 h-4 text-red-400" />, action: () => router.push('/dashboard/tenants'), section: 'navigate' },
    { id: 'nav-billing', label: 'Billing', icon: <Receipt className="w-4 h-4 text-emerald-400" />, action: () => router.push('/dashboard/billing'), section: 'navigate' },
    { id: 'nav-backups', label: 'Data Backups', icon: <HardDrive className="w-4 h-4 text-gray-400" />, action: () => router.push('/dashboard/backups'), section: 'navigate' },
    { id: 'nav-settings', label: 'Settings', icon: <Settings className="w-4 h-4 text-zinc-400" />, action: () => router.push('/dashboard/settings'), section: 'navigate' },
    { id: 'nav-activity', label: 'Activity Log', icon: <ScrollText className="w-4 h-4 text-cyan-400" />, action: () => router.push('/dashboard/activity-log'), section: 'navigate' },
  ]

  // Action items
  const actionItems: CommandItem[] = [
    { id: 'act-run-pipeline', label: 'Run Lead Sourcing Pipeline', description: 'Scrape jobs from all sources', icon: <Play className="w-4 h-4 text-indigo-500" />, action: () => router.push('/dashboard/pipelines'), section: 'actions' },
    { id: 'act-create-campaign', label: 'Create Campaign', description: 'Start a new email campaign', icon: <PlusCircle className="w-4 h-4 text-amber-500" />, action: () => router.push('/dashboard/campaigns'), section: 'actions' },
    { id: 'act-add-mailbox', label: 'Add Mailbox', description: 'Connect a new email account', icon: <PlusCircle className="w-4 h-4 text-purple-500" />, action: () => router.push('/dashboard/mailboxes'), section: 'actions' },
    { id: 'act-export', label: 'Export Lead Data', description: 'Download leads as CSV', icon: <Download className="w-4 h-4 text-green-500" />, action: () => router.push('/dashboard/leads'), section: 'actions' },
    { id: 'act-new-deal', label: 'Create New Deal', description: 'Add a deal to the pipeline', icon: <PlusCircle className="w-4 h-4 text-green-500" />, action: () => router.push('/dashboard/deals'), section: 'actions' },
    { id: 'act-sync-inbox', label: 'Sync Inbox', description: 'Pull new messages from mailboxes', icon: <MessageSquare className="w-4 h-4 text-teal-500" />, action: () => router.push('/dashboard/inbox'), section: 'actions' },
  ]

  // Search API for leads/contacts
  const searchApi = useCallback(async (q: string) => {
    if (q.length < 2) {
      setSearchResults([])
      return
    }
    setSearchLoading(true)
    try {
      const [leadsRes, contactsRes] = await Promise.allSettled([
        api.get('/leads', { params: { search: q, page: 1, page_size: 5 } }),
        api.get('/contacts', { params: { search: q, page: 1, page_size: 5 } }),
      ])

      const results: CommandItem[] = []

      if (leadsRes.status === 'fulfilled') {
        const leads = leadsRes.value.data?.items || []
        leads.forEach((lead: any) => {
          results.push({
            id: `lead-${lead.lead_id}`,
            label: lead.client_name || `Lead #${lead.lead_id}`,
            description: lead.job_title || '',
            icon: <FileText className="w-4 h-4 text-indigo-400" />,
            action: () => router.push(`/dashboard/leads`),
            section: 'search',
          })
        })
      }

      if (contactsRes.status === 'fulfilled') {
        const contacts = contactsRes.value.data?.items || []
        contacts.forEach((contact: any) => {
          results.push({
            id: `contact-${contact.contact_id}`,
            label: `${contact.first_name || ''} ${contact.last_name || ''}`.trim() || contact.email,
            description: contact.email,
            icon: <Users className="w-4 h-4 text-violet-400" />,
            action: () => router.push(`/dashboard/contacts`),
            section: 'search',
          })
        })
      }

      setSearchResults(results)
    } catch {
      setSearchResults([])
    }
    setSearchLoading(false)
  }, [router])

  // Debounced search
  useEffect(() => {
    if (searchTimeout.current) clearTimeout(searchTimeout.current)
    if (query.length >= 2) {
      searchTimeout.current = setTimeout(() => searchApi(query), 300)
    } else {
      setSearchResults([])
    }
    return () => { if (searchTimeout.current) clearTimeout(searchTimeout.current) }
  }, [query, searchApi])

  // Filter items by query
  const fuzzyMatch = (text: string, q: string) => {
    const lower = text.toLowerCase()
    const qLower = q.toLowerCase()
    return lower.includes(qLower)
  }

  const filteredNav = query ? navigationItems.filter(i => fuzzyMatch(i.label, query)) : navigationItems.slice(0, 8)
  const filteredActions = query ? actionItems.filter(i => fuzzyMatch(i.label, query) || fuzzyMatch(i.description || '', query)) : actionItems

  const allItems = [...filteredNav, ...filteredActions, ...searchResults]

  // Keyboard navigation
  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex(prev => Math.min(prev + 1, allItems.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex(prev => Math.max(prev - 1, 0))
    } else if (e.key === 'Enter' && allItems[activeIndex]) {
      e.preventDefault()
      allItems[activeIndex].action()
      setIsOpen(false)
    }
  }

  // Scroll active item into view
  useEffect(() => {
    if (listRef.current) {
      const activeEl = listRef.current.querySelector(`[data-index="${activeIndex}"]`)
      activeEl?.scrollIntoView({ block: 'nearest' })
    }
  }, [activeIndex])

  if (!isOpen) return null

  const renderSection = (title: string, items: CommandItem[], startIdx: number) => {
    if (items.length === 0) return null
    return (
      <div>
        <div className="px-4 py-2 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
          {title}
        </div>
        {items.map((item, idx) => {
          const globalIdx = startIdx + idx
          return (
            <button
              key={item.id}
              data-index={globalIdx}
              onClick={() => { item.action(); setIsOpen(false) }}
              onMouseEnter={() => setActiveIndex(globalIdx)}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                activeIndex === globalIdx
                  ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-900 dark:text-indigo-100'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              <div className="flex-shrink-0">{item.icon}</div>
              <div className="flex-1 min-w-0">
                <span className="text-sm font-medium">{item.label}</span>
                {item.description && (
                  <span className="text-xs text-gray-400 dark:text-gray-500 ml-2">{item.description}</span>
                )}
              </div>
              {activeIndex === globalIdx && (
                <ArrowRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
              )}
            </button>
          )
        })}
      </div>
    )
  }

  let currentIdx = 0
  const navStartIdx = currentIdx
  currentIdx += filteredNav.length
  const actStartIdx = currentIdx
  currentIdx += filteredActions.length
  const searchStartIdx = currentIdx

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[70]"
        onClick={() => setIsOpen(false)}
      />

      {/* Palette */}
      <div className="fixed top-[20%] left-1/2 -translate-x-1/2 z-[71] w-full max-w-xl">
        <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          {/* Search Input */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
            <Search className="w-5 h-5 text-gray-400 flex-shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search pages, actions, leads, contacts..."
              className="flex-1 text-sm bg-transparent outline-none text-gray-900 dark:text-gray-100 placeholder-gray-400"
            />
            <kbd className="hidden sm:inline-flex items-center px-2 py-0.5 text-[10px] font-mono text-gray-400 bg-gray-100 dark:bg-gray-800 rounded">
              ESC
            </kbd>
            <button onClick={() => setIsOpen(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Results */}
          <div ref={listRef} className="max-h-[400px] overflow-y-auto py-2">
            {allItems.length === 0 && query.length > 0 && !searchLoading && (
              <div className="px-4 py-8 text-center text-sm text-gray-400">
                No results found for &quot;{query}&quot;
              </div>
            )}

            {renderSection('Navigate', filteredNav, navStartIdx)}
            {renderSection('Actions', filteredActions, actStartIdx)}
            {searchLoading && (
              <div className="px-4 py-3 text-center text-xs text-gray-400">
                Searching...
              </div>
            )}
            {renderSection('Search Results', searchResults, searchStartIdx)}
          </div>

          {/* Footer */}
          <div className="flex items-center gap-4 px-4 py-2 border-t border-gray-200 dark:border-gray-700 text-[10px] text-gray-400">
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded font-mono">Up/Down</kbd> navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded font-mono">Enter</kbd> select
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded font-mono">Esc</kbd> close
            </span>
          </div>
        </div>
      </div>
    </>
  )
}
