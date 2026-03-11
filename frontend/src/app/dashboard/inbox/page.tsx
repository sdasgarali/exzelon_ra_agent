'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { inboxApi, mailboxesApi, automationApi } from '@/lib/api'
import type { InboxThread, InboxMessage, InboxThreadDetail, AutomationEvent } from '@/types/api'
import {
  Search, RefreshCw, ChevronDown, Send, Sparkles, User,
  Mail, MessageSquare, X, Inbox, ArrowUpRight, ArrowDownLeft,
  Clock, Tag, ThumbsUp, ThumbsDown, Minus, AlertCircle,
  Phone, Building, Briefcase, ExternalLink, Filter, Info,
  Bot, Zap, Activity, Trash2, CheckSquare, Square, CheckCheck,
} from 'lucide-react'

// ─── Category & sentiment config ────────────────────────────────────
const categoryConfig: Record<string, { label: string; color: string; bg: string; border: string; icon: string; dot: string }> = {
  interested:      { label: 'Interested',      color: 'text-emerald-700 dark:text-emerald-300', bg: 'bg-emerald-50 dark:bg-emerald-900/30',   border: 'border-l-emerald-500', icon: '🟢', dot: 'bg-emerald-500' },
  not_interested:  { label: 'Not Interested',  color: 'text-rose-700 dark:text-rose-300',       bg: 'bg-rose-50 dark:bg-rose-900/30',         border: 'border-l-rose-500',    icon: '🔴', dot: 'bg-rose-500' },
  ooo:             { label: 'Out of Office',   color: 'text-amber-700 dark:text-amber-300',     bg: 'bg-amber-50 dark:bg-amber-900/30',       border: 'border-l-amber-500',   icon: '🟡', dot: 'bg-amber-400' },
  question:        { label: 'Question',        color: 'text-blue-700 dark:text-blue-300',       bg: 'bg-blue-50 dark:bg-blue-900/30',         border: 'border-l-blue-500',    icon: '🔵', dot: 'bg-blue-500' },
  referral:        { label: 'Referral',        color: 'text-violet-700 dark:text-violet-300',   bg: 'bg-violet-50 dark:bg-violet-900/30',     border: 'border-l-violet-500',  icon: '🟣', dot: 'bg-violet-500' },
  do_not_contact:  { label: 'Do Not Contact',  color: 'text-gray-700 dark:text-gray-400',       bg: 'bg-gray-100 dark:bg-gray-800',           border: 'border-l-gray-500',    icon: '⛔', dot: 'bg-gray-500' },
  other:           { label: 'Other',           color: 'text-slate-600 dark:text-slate-400',     bg: 'bg-slate-50 dark:bg-slate-800',           border: 'border-l-slate-400',   icon: '⚪', dot: 'bg-slate-400' },
}

const sentimentConfig: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  positive: { label: 'Positive', icon: <ThumbsUp className="w-3 h-3" />, color: 'text-emerald-600 dark:text-emerald-400' },
  negative: { label: 'Negative', icon: <ThumbsDown className="w-3 h-3" />, color: 'text-rose-600 dark:text-rose-400' },
  neutral:  { label: 'Neutral',  icon: <Minus className="w-3 h-3" />,      color: 'text-gray-500 dark:text-gray-400' },
}

const categories = Object.keys(categoryConfig)

// Avatar colors - deterministic by first char of name
const avatarColors = [
  'from-blue-500 to-blue-600',
  'from-emerald-500 to-emerald-600',
  'from-violet-500 to-violet-600',
  'from-amber-500 to-amber-600',
  'from-rose-500 to-rose-600',
  'from-cyan-500 to-cyan-600',
  'from-pink-500 to-pink-600',
  'from-indigo-500 to-indigo-600',
]

function getAvatarColor(name: string) {
  const idx = (name?.charCodeAt(0) || 0) % avatarColors.length
  return avatarColors[idx]
}

function timeAgo(dateStr: string | null) {
  if (!dateStr) return ''
  const now = new Date()
  const date = new Date(dateStr)
  const diff = Math.floor((now.getTime() - date.getTime()) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
  return date.toLocaleDateString()
}

export default function InboxPage() {
  const [threads, setThreads] = useState<InboxThread[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [mailboxFilter, setMailboxFilter] = useState<number | ''>('')
  const [mailboxes, setMailboxes] = useState<{ mailbox_id: number; email: string }[]>([])
  const [selectedThread, setSelectedThread] = useState<InboxThreadDetail | null>(null)
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null)
  const [replyText, setReplyText] = useState('')
  const [sending, setSending] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [showCategoryMenu, setShowCategoryMenu] = useState(false)
  const [stats, setStats] = useState<any>(null)
  const [suggestingReply, setSuggestingReply] = useState(false)
  const [showContactPanel, setShowContactPanel] = useState(true)
  const [showAutomationPanel, setShowAutomationPanel] = useState(false)
  const [automationEvents, setAutomationEvents] = useState<AutomationEvent[]>([])
  const [automationLoading, setAutomationLoading] = useState(false)
  const [selectedThreadIds, setSelectedThreadIds] = useState<Set<string>>(new Set())
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<{ type: 'single' | 'bulk'; threadId?: string } | null>(null)
  const [deleting, setDeleting] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const fetchThreads = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page: 1, page_size: 50 }
      if (search) params.search = search
      if (categoryFilter) params.category = categoryFilter
      if (mailboxFilter) params.mailbox_id = mailboxFilter
      const data = await inboxApi.listThreads(params)
      setThreads(data?.items || [])
    } catch {
      setThreads([])
    } finally {
      setLoading(false)
    }
  }, [search, categoryFilter, mailboxFilter])

  useEffect(() => { fetchThreads() }, [fetchThreads])

  useEffect(() => {
    inboxApi.stats().then(setStats).catch(() => {})
    mailboxesApi.list({ page: 1, page_size: 100 }).then((data: any) => {
      setMailboxes(data?.items || data || [])
    }).catch(() => {})
  }, [])

  const openThread = async (threadId: string) => {
    setSelectedThreadId(threadId)
    try {
      const detail = await inboxApi.getThread(threadId)
      setSelectedThread(detail)
      await inboxApi.markRead(threadId)
      setThreads(prev => prev.map(t => t.thread_id === threadId ? { ...t, unread_count: 0 } : t))
    } catch { /* ignore */ }
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [selectedThread?.messages])

  const [replyError, setReplyError] = useState('')

  const handleReply = async () => {
    if (!selectedThreadId || !replyText.trim()) return
    setReplyError('')

    // Determine mailbox_id from the thread's messages (use the mailbox that sent/received in this thread)
    const threadMailboxId = selectedThread?.messages?.find(m => m.mailbox_id)?.mailbox_id
      || threads.find(t => t.thread_id === selectedThreadId)?.mailbox_id
    if (!threadMailboxId) {
      setReplyError('No mailbox associated with this thread. Cannot send reply.')
      return
    }

    setSending(true)
    try {
      await inboxApi.reply({ thread_id: selectedThreadId, mailbox_id: threadMailboxId, body_html: `<p>${replyText}</p>`, body_text: replyText })
      setReplyText('')
      const detail = await inboxApi.getThread(selectedThreadId)
      setSelectedThread(detail)
    } catch (err: any) {
      setReplyError(err?.response?.data?.detail || err?.message || 'Failed to send reply')
    }
    setSending(false)
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      await inboxApi.sync()
      await fetchThreads()
      const s = await inboxApi.stats()
      setStats(s)
    } catch { /* ignore */ }
    setSyncing(false)
  }

  const handleCategory = async (category: string) => {
    if (!selectedThreadId) return
    setShowCategoryMenu(false)
    try {
      await inboxApi.setCategory(selectedThreadId, category)
      setThreads(prev => prev.map(t => t.thread_id === selectedThreadId ? { ...t, category } : t))
    } catch { /* ignore */ }
  }

  const handleSuggestReply = async () => {
    if (!selectedThreadId) return
    setSuggestingReply(true)
    try {
      const suggestion = await inboxApi.suggestReply(selectedThreadId)
      if (suggestion?.body_text) setReplyText(suggestion.body_text)
    } catch { /* ignore */ }
    setSuggestingReply(false)
  }

  const fetchAutomationEvents = useCallback(async () => {
    setAutomationLoading(true)
    try {
      const data = await automationApi.events({ hours: 24, page_size: 30 })
      setAutomationEvents(data?.items || [])
    } catch { setAutomationEvents([]) }
    finally { setAutomationLoading(false) }
  }, [])

  useEffect(() => {
    if (showAutomationPanel) fetchAutomationEvents()
  }, [showAutomationPanel, fetchAutomationEvents])

  // ─── Multi-select helpers ──────────────────────────────────────
  const toggleThreadSelect = (threadId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setSelectedThreadIds(prev => {
      const next = new Set(prev)
      if (next.has(threadId)) next.delete(threadId)
      else next.add(threadId)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedThreadIds.size === threads.length) {
      setSelectedThreadIds(new Set())
    } else {
      setSelectedThreadIds(new Set(threads.map(t => t.thread_id)))
    }
  }

  const handleDeleteConfirm = async () => {
    if (!showDeleteConfirm) return
    setDeleting(true)
    try {
      if (showDeleteConfirm.type === 'single' && showDeleteConfirm.threadId) {
        await inboxApi.deleteThread(showDeleteConfirm.threadId)
        if (selectedThreadId === showDeleteConfirm.threadId) {
          setSelectedThread(null)
          setSelectedThreadId(null)
        }
        selectedThreadIds.delete(showDeleteConfirm.threadId)
        setSelectedThreadIds(new Set(selectedThreadIds))
      } else {
        const ids = Array.from(selectedThreadIds)
        await inboxApi.bulkDeleteThreads(ids)
        if (selectedThreadId && ids.includes(selectedThreadId)) {
          setSelectedThread(null)
          setSelectedThreadId(null)
        }
        setSelectedThreadIds(new Set())
      }
      setShowDeleteConfirm(null)
      await fetchThreads()
      const s = await inboxApi.stats()
      setStats(s)
    } catch { /* ignore */ }
    setDeleting(false)
  }

  const [showCategoryFilter, setShowCategoryFilter] = useState(false)
  const [showLegend, setShowLegend] = useState(false)
  const totalThreads = threads.length
  const unreadCount = threads.filter(t => t.unread_count > 0).length

  return (
    <div className="h-[calc(100vh-120px)] flex flex-col">
      {/* ─── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <MessageSquare className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Inbox</h1>
            <p className="text-gray-500 dark:text-gray-400 text-sm">
              {totalThreads} conversations
              {unreadCount > 0 && <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300">{unreadCount} unread</span>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Mailbox Filter Dropdown */}
          {mailboxes.length > 0 && (
            <div className="relative">
              <select
                value={mailboxFilter}
                onChange={e => setMailboxFilter(e.target.value ? Number(e.target.value) : '')}
                className={`appearance-none pl-8 pr-8 py-2 border rounded-xl text-sm font-medium shadow-sm transition-all cursor-pointer ${
                  mailboxFilter
                    ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-700'
                    : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                }`}
              >
                <option value="">All Mailboxes</option>
                {mailboxes.map(mb => (
                  <option key={mb.mailbox_id} value={mb.mailbox_id}>{mb.email}</option>
                ))}
              </select>
              <Mail className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
            </div>
          )}
          {/* Category Filter Dropdown */}
          <div className="relative">
            <button onClick={() => setShowCategoryFilter(!showCategoryFilter)}
              className={`flex items-center gap-2 px-3 py-2 border rounded-xl text-sm font-medium shadow-sm transition-all ${
                categoryFilter
                  ? `${categoryConfig[categoryFilter].bg} ${categoryConfig[categoryFilter].color} border-current`
                  : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
              }`}>
              <Filter className="w-4 h-4" />
              {categoryFilter ? (
                <span className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${categoryConfig[categoryFilter].dot}`} />
                  {categoryConfig[categoryFilter].label}
                  {stats?.categories?.[categoryFilter] != null && (
                    <span className="opacity-70">({stats.categories[categoryFilter]})</span>
                  )}
                </span>
              ) : (
                'All Categories'
              )}
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
            {showCategoryFilter && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setShowCategoryFilter(false)} />
                <div className="absolute right-0 top-11 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-xl shadow-xl w-56 py-1 overflow-hidden">
                  {/* All option */}
                  <button onClick={() => { setCategoryFilter(''); setShowCategoryFilter(false) }}
                    className={`w-full px-3 py-2.5 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2.5 transition-colors ${!categoryFilter ? 'bg-gray-50 dark:bg-gray-700 font-semibold' : ''}`}>
                    <span className="w-2.5 h-2.5 rounded-full bg-gray-400" />
                    <span className="text-gray-700 dark:text-gray-300 font-medium">All Categories</span>
                    <span className="ml-auto text-xs text-gray-400">({stats?.total_threads || totalThreads})</span>
                  </button>
                  <div className="border-t border-gray-100 dark:border-gray-700 my-1" />
                  {/* Category options */}
                  {categories.map(c => {
                    const cfg = categoryConfig[c]
                    const count = stats?.categories?.[c] || 0
                    const isActive = categoryFilter === c
                    return (
                      <button key={c} onClick={() => { setCategoryFilter(isActive ? '' : c); setShowCategoryFilter(false) }}
                        className={`w-full px-3 py-2.5 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2.5 transition-colors ${isActive ? 'bg-gray-50 dark:bg-gray-700' : ''}`}>
                        <span className={`w-2.5 h-2.5 rounded-full ${cfg.dot}`} />
                        <span className={`font-medium ${cfg.color}`}>{cfg.label}</span>
                        {count > 0 && <span className="ml-auto text-xs text-gray-400">({count})</span>}
                      </button>
                    )
                  })}
                  {/* Uncategorized */}
                  {stats?.categories?.uncategorized > 0 && (
                    <>
                      <div className="border-t border-gray-100 dark:border-gray-700 my-1" />
                      <div className="px-3 py-2 text-xs text-gray-400 flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full bg-gray-300" />
                        Uncategorized ({stats.categories.uncategorized})
                      </div>
                    </>
                  )}
                </div>
              </>
            )}
          </div>
          {/* Category Legend Toggle */}
          <button onClick={() => setShowLegend(!showLegend)}
            className={`p-2 border rounded-xl shadow-sm transition-all ${showLegend ? 'bg-indigo-50 dark:bg-indigo-900/30 border-indigo-200 dark:border-indigo-700 text-indigo-600' : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-500'}`}
            title="Category Legend">
            <Info className="w-4 h-4" />
          </button>
          {/* Automation Activity Toggle */}
          <button onClick={() => setShowAutomationPanel(!showAutomationPanel)}
            className={`flex items-center gap-2 px-3 py-2 border rounded-xl text-sm font-medium shadow-sm transition-all ${
              showAutomationPanel
                ? 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-700'
                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
            }`}
            title="Automation Activity">
            <Activity className="w-4 h-4" />
            Activity
          </button>
          {/* Sync */}
          <button onClick={handleSync} disabled={syncing}
            className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700 text-sm font-medium shadow-sm transition-all">
            <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin text-indigo-500' : 'text-gray-500'}`} />
            {syncing ? 'Syncing...' : 'Sync'}
          </button>
        </div>
      </div>

      {/* ─── Category Legend ──────────────────────────────────────────── */}
      {showLegend && (
        <div className="mb-3 p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Category Legend</h4>
            <button onClick={() => setShowLegend(false)} className="text-gray-400 hover:text-gray-600"><X className="w-3.5 h-3.5" /></button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {categories.map(c => {
              const cfg = categoryConfig[c]
              return (
                <div key={c} className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg ${cfg.bg}`}>
                  <span className={`w-2.5 h-2.5 rounded-full ${cfg.dot} flex-shrink-0`} />
                  <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>
                </div>
              )
            })}
          </div>
          <div className="flex items-center gap-4 mt-2 pt-2 border-t border-gray-100 dark:border-gray-700">
            <span className="text-[10px] text-gray-400 uppercase tracking-wider font-medium">Sentiment:</span>
            {Object.entries(sentimentConfig).map(([key, cfg]) => (
              <span key={key} className={`flex items-center gap-1 text-xs ${cfg.color}`}>
                {cfg.icon} {cfg.label}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ─── Automation Activity Panel ───────────────────────────────── */}
      {showAutomationPanel && (
        <div className="mb-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-gray-700 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              <h4 className="text-sm font-semibold text-amber-800 dark:text-amber-300">Automation Activity</h4>
              <span className="text-xs text-amber-600/70 dark:text-amber-400/70">Last 24 hours</span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={fetchAutomationEvents} className="p-1 hover:bg-amber-100 dark:hover:bg-amber-800/30 rounded transition-colors">
                <RefreshCw className={`w-3.5 h-3.5 text-amber-600 dark:text-amber-400 ${automationLoading ? 'animate-spin' : ''}`} />
              </button>
              <button onClick={() => setShowAutomationPanel(false)} className="p-1 hover:bg-amber-100 dark:hover:bg-amber-800/30 rounded transition-colors">
                <X className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
              </button>
            </div>
          </div>
          <div className="max-h-48 overflow-y-auto">
            {automationLoading ? (
              <div className="p-4 text-center">
                <div className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto" />
              </div>
            ) : automationEvents.length === 0 ? (
              <div className="p-4 text-center text-sm text-gray-500">No automation events in the last 24 hours</div>
            ) : (
              <div className="divide-y divide-gray-50 dark:divide-gray-800">
                {automationEvents.map(evt => {
                  const typeIcons: Record<string, React.ReactNode> = {
                    ai_classify: <Bot className="w-3.5 h-3.5 text-violet-500" />,
                    ai_suggest: <Sparkles className="w-3.5 h-3.5 text-amber-500" />,
                    campaign_send: <Send className="w-3.5 h-3.5 text-indigo-500" />,
                    inbox_sync: <RefreshCw className="w-3.5 h-3.5 text-blue-500" />,
                    reply_detected: <Mail className="w-3.5 h-3.5 text-emerald-500" />,
                    lead_sourcing: <Zap className="w-3.5 h-3.5 text-orange-500" />,
                    scheduler_run: <Clock className="w-3.5 h-3.5 text-gray-500" />,
                  }
                  const icon = typeIcons[evt.event_type] || <Activity className="w-3.5 h-3.5 text-gray-400" />
                  const statusColor = evt.status === 'error' ? 'text-rose-600 bg-rose-50 dark:text-rose-400 dark:bg-rose-900/30' :
                                      evt.status === 'skipped' ? 'text-gray-500 bg-gray-50 dark:text-gray-400 dark:bg-gray-800' :
                                      'text-emerald-600 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-900/30'
                  return (
                    <div key={evt.event_id} className="flex items-center gap-3 px-4 py-2 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                      <div className="flex-shrink-0">{icon}</div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-gray-800 dark:text-gray-200 truncate">{evt.title}</p>
                      </div>
                      <span className={`flex-shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium ${statusColor}`}>{evt.status}</span>
                      <span className="flex-shrink-0 text-[10px] text-gray-400">{timeAgo(evt.created_at)}</span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── Main 3-Panel Layout ─────────────────────────────────────── */}
      <div className="flex-1 flex rounded-xl overflow-hidden bg-white dark:bg-gray-800 shadow-sm border border-gray-200 dark:border-gray-700">

        {/* ── Left: Thread List ──────────────────────────────────────── */}
        <div className="w-[340px] border-r border-gray-200 dark:border-gray-700 flex flex-col bg-gray-50/50 dark:bg-gray-900/30">
          <div className="p-3 border-b border-gray-200 dark:border-gray-700">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search conversations..."
                className="w-full pl-9 pr-3 py-2 border border-gray-200 dark:border-gray-600 rounded-xl text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
            </div>
            {/* Select All / Bulk Actions */}
            {threads.length > 0 && (
              <div className="flex items-center gap-2 mt-2">
                <button onClick={toggleSelectAll} className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors" title={selectedThreadIds.size === threads.length ? 'Deselect all' : 'Select all'}>
                  {selectedThreadIds.size === threads.length && threads.length > 0 ? (
                    <CheckSquare className="w-3.5 h-3.5 text-indigo-500" />
                  ) : selectedThreadIds.size > 0 ? (
                    <CheckCheck className="w-3.5 h-3.5 text-indigo-400" />
                  ) : (
                    <Square className="w-3.5 h-3.5" />
                  )}
                  {selectedThreadIds.size > 0 ? `${selectedThreadIds.size} selected` : 'Select'}
                </button>
                {selectedThreadIds.size > 0 && (
                  <>
                    <button onClick={() => setShowDeleteConfirm({ type: 'bulk' })}
                      className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-rose-600 bg-rose-50 dark:bg-rose-900/30 hover:bg-rose-100 dark:hover:bg-rose-900/50 transition-colors"
                      title={`Delete ${selectedThreadIds.size} thread(s)`}>
                      <Trash2 className="w-3.5 h-3.5" />
                      Delete
                    </button>
                    <button onClick={() => setSelectedThreadIds(new Set())}
                      className="ml-auto px-2 py-1 rounded-lg text-xs text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                      Clear
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="p-8 text-center">
                <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm text-gray-500">Loading conversations...</p>
              </div>
            ) : threads.length === 0 ? (
              <div className="p-8 text-center">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-100 to-purple-100 dark:from-indigo-900/30 dark:to-purple-900/30 flex items-center justify-center mx-auto mb-3">
                  <Inbox className="w-8 h-8 text-indigo-400" />
                </div>
                <p className="font-medium text-gray-700 dark:text-gray-300">No conversations</p>
                <p className="text-xs text-gray-500 mt-1">Hit Sync to pull in new messages</p>
              </div>
            ) : (
              threads.map(t => {
                const cat = t.category ? categoryConfig[t.category] : null
                const isSelected = selectedThreadId === t.thread_id
                const isChecked = selectedThreadIds.has(t.thread_id)
                const isUnread = t.unread_count > 0
                return (
                  <button key={t.thread_id} onClick={() => openThread(t.thread_id)}
                    className={`w-full text-left px-3 py-3 border-b border-gray-100 dark:border-gray-800 transition-all
                      ${isChecked ? 'bg-indigo-50/50 dark:bg-indigo-900/10' : ''}
                      ${isSelected ? 'bg-indigo-50 dark:bg-indigo-900/20 border-l-2 border-l-indigo-500' : `border-l-2 ${cat ? cat.border : 'border-l-transparent'} hover:bg-white dark:hover:bg-gray-800`}`}>
                    <div className="flex items-start gap-2">
                      {/* Checkbox */}
                      <div onClick={(e) => toggleThreadSelect(t.thread_id, e)}
                        className="flex-shrink-0 mt-1 p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors cursor-pointer">
                        {isChecked ? (
                          <CheckSquare className="w-4 h-4 text-indigo-500" />
                        ) : (
                          <Square className="w-4 h-4 text-gray-300 dark:text-gray-600" />
                        )}
                      </div>
                      {/* Avatar */}
                      <div className={`w-9 h-9 rounded-full bg-gradient-to-br ${getAvatarColor(t.contact_name || t.from_email)} flex items-center justify-center flex-shrink-0 shadow-sm`}>
                        <span className="text-xs font-bold text-white">{(t.contact_name || t.from_email)?.[0]?.toUpperCase() || '?'}</span>
                      </div>
                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={`text-sm truncate ${isUnread ? 'font-semibold text-gray-900 dark:text-white' : 'text-gray-700 dark:text-gray-300'}`}>
                            {t.contact_name || t.from_email}
                          </span>
                          {isUnread && <span className="w-2 h-2 rounded-full bg-indigo-500 flex-shrink-0" />}
                          <span className="text-[10px] text-gray-400 ml-auto flex-shrink-0">{timeAgo(t.latest_message_at)}</span>
                        </div>
                        <p className={`text-xs truncate mt-0.5 ${isUnread ? 'text-gray-700 dark:text-gray-300' : 'text-gray-500 dark:text-gray-500'}`}>
                          {t.subject || '(no subject)'}
                        </p>
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className="text-[11px] text-gray-400 truncate flex-1">{t.snippet}</span>
                          {cat && (
                            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${cat.bg} ${cat.color} flex-shrink-0`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${cat.dot}`} />
                              {cat.label}
                            </span>
                          )}
                          {t.sentiment && sentimentConfig[t.sentiment] && (
                            <span className={`flex-shrink-0 ${sentimentConfig[t.sentiment].color}`} title={sentimentConfig[t.sentiment].label}>
                              {sentimentConfig[t.sentiment].icon}
                            </span>
                          )}
                          {t.message_count > 1 && (
                            <span className="text-[10px] text-gray-400 bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded-full flex-shrink-0">{t.message_count}</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </button>
                )
              })
            )}
          </div>
        </div>

        {/* ── Center: Message Thread ─────────────────────────────────── */}
        <div className="flex-1 flex flex-col min-w-0">
          {!selectedThread ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-700 dark:to-gray-800 flex items-center justify-center mx-auto mb-4">
                  <Mail className="w-10 h-10 text-gray-400" />
                </div>
                <p className="text-gray-500 font-medium">Select a conversation</p>
                <p className="text-xs text-gray-400 mt-1">Choose a thread from the left to read messages</p>
              </div>
            </div>
          ) : (
            <>
              {/* Thread header */}
              <div className="px-5 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
                    {selectedThread.messages?.[0]?.subject || '(no subject)'}
                  </h3>
                  <div className="flex items-center gap-3 mt-0.5">
                    <span className="text-xs text-gray-500 flex items-center gap-1">
                      <MessageSquare className="w-3 h-3" /> {selectedThread.messages?.length || 0} messages
                    </span>
                    {selectedThread.contact && (
                      <span className="text-xs text-gray-500 flex items-center gap-1">
                        <ArrowDownLeft className="w-3 h-3" /> {selectedThread.contact.email}
                      </span>
                    )}
                  </div>
                </div>
                {/* Category Label Dropdown */}
                <div className="relative">
                  <button onClick={() => setShowCategoryMenu(!showCategoryMenu)}
                    className="flex items-center gap-2 px-3 py-1.5 border border-gray-200 dark:border-gray-600 rounded-lg text-xs font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-all">
                    <Tag className="w-3 h-3 text-gray-400" />
                    Label
                    <ChevronDown className="w-3 h-3 text-gray-400" />
                  </button>
                  {showCategoryMenu && (
                    <>
                      <div className="fixed inset-0 z-10" onClick={() => setShowCategoryMenu(false)} />
                      <div className="absolute right-0 top-9 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-xl shadow-xl w-48 py-1 overflow-hidden">
                        {categories.map(c => {
                          const cfg = categoryConfig[c]
                          return (
                            <button key={c} onClick={() => handleCategory(c)}
                              className="w-full px-3 py-2 text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2.5 transition-colors">
                              <span className={`w-2.5 h-2.5 rounded-full ${cfg.dot}`} />
                              <span className="font-medium">{cfg.label}</span>
                            </button>
                          )
                        })}
                      </div>
                    </>
                  )}
                </div>
                <button onClick={() => setShowDeleteConfirm({ type: 'single', threadId: selectedThreadId! })}
                  className="p-2 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-900/20 text-gray-400 hover:text-rose-500 transition-all"
                  title="Delete thread">
                  <Trash2 className="w-4 h-4" />
                </button>
                <button onClick={() => setShowContactPanel(!showContactPanel)}
                  className={`p-2 rounded-lg transition-all ${showContactPanel ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400' : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400'}`}
                  title="Toggle contact panel">
                  <User className="w-4 h-4" />
                </button>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 bg-gray-50/50 dark:bg-gray-900/20">
                {selectedThread.messages?.map((msg: InboxMessage, idx: number) => {
                  const isSent = msg.direction === 'sent'
                  const msgCat = msg.category ? categoryConfig[msg.category] : null
                  const msgSent = msg.sentiment ? sentimentConfig[msg.sentiment] : null
                  return (
                    <div key={msg.message_id} className={`flex ${isSent ? 'justify-end' : 'justify-start'}`}>
                      {/* Received avatar */}
                      {!isSent && (
                        <div className={`w-8 h-8 rounded-full bg-gradient-to-br ${getAvatarColor(msg.from_email)} flex items-center justify-center flex-shrink-0 mr-2 mt-1 shadow-sm`}>
                          <span className="text-[10px] font-bold text-white">{msg.from_email?.[0]?.toUpperCase() || '?'}</span>
                        </div>
                      )}
                      <div className={`max-w-[70%] rounded-2xl px-4 py-3 shadow-sm ${
                        isSent
                          ? 'bg-gradient-to-br from-indigo-500 to-indigo-600 text-white rounded-br-md'
                          : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-bl-md'
                      }`}>
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className={`text-[11px] font-semibold ${isSent ? 'text-indigo-100' : 'text-gray-700 dark:text-gray-300'}`}>
                            {isSent ? (
                              <span className="flex items-center gap-1"><ArrowUpRight className="w-3 h-3" /> You</span>
                            ) : msg.from_email}
                          </span>
                          <span className={`text-[10px] ${isSent ? 'text-indigo-200' : 'text-gray-400'} flex items-center gap-1`}>
                            <Clock className="w-2.5 h-2.5" />
                            {msg.received_at ? timeAgo(msg.received_at) : ''}
                          </span>
                        </div>
                        {msg.body_text ? (
                          <p className={`text-sm whitespace-pre-wrap leading-relaxed ${isSent ? 'text-white' : 'text-gray-800 dark:text-gray-200'}`}>{msg.body_text}</p>
                        ) : msg.body_html ? (
                          <div className={`text-sm leading-relaxed ${isSent ? 'text-white' : 'text-gray-800 dark:text-gray-200'} [&_a]:underline`} dangerouslySetInnerHTML={{ __html: msg.body_html }} />
                        ) : (
                          <p className={`text-sm italic ${isSent ? 'text-indigo-200' : 'text-gray-400'}`}>(empty message)</p>
                        )}
                        {/* Category + Sentiment badges */}
                        {(msgCat || msgSent) && (
                          <div className="flex items-center gap-2 mt-2 pt-1.5 border-t border-white/10">
                            {msgCat && (
                              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${isSent ? 'bg-white/15 text-white' : `${msgCat.bg} ${msgCat.color}`}`}>
                                <span className={`w-1.5 h-1.5 rounded-full ${isSent ? 'bg-white/60' : msgCat.dot}`} />
                                {msgCat.label}
                              </span>
                            )}
                            {msgSent && (
                              <span className={`inline-flex items-center gap-1 text-[10px] ${isSent ? 'text-indigo-200' : msgSent.color}`}>
                                {msgSent.icon} {msgSent.label}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                      {/* Sent avatar */}
                      {isSent && (
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-indigo-600 flex items-center justify-center flex-shrink-0 ml-2 mt-1 shadow-sm">
                          <ArrowUpRight className="w-3.5 h-3.5 text-white" />
                        </div>
                      )}
                    </div>
                  )
                })}
                <div ref={messagesEndRef} />
              </div>

              {/* Reply Composer */}
              <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
                {replyError && (
                  <div className="mb-2 px-3 py-2 bg-rose-50 dark:bg-rose-900/30 border border-rose-200 dark:border-rose-700 rounded-lg text-xs text-rose-700 dark:text-rose-300 flex items-center gap-2">
                    <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                    {replyError}
                    <button onClick={() => setReplyError('')} className="ml-auto"><X className="w-3 h-3" /></button>
                  </div>
                )}
                <div className="flex gap-3">
                  <div className="flex-1 relative">
                    <textarea value={replyText} onChange={e => setReplyText(e.target.value)}
                      placeholder="Write your reply... (Ctrl+Enter to send)"
                      rows={3}
                      className="w-full px-4 py-3 border border-gray-200 dark:border-gray-600 rounded-xl text-sm resize-none bg-gray-50 dark:bg-gray-900/50 focus:bg-white dark:focus:bg-gray-800 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
                      onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleReply() }}
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <button onClick={handleSuggestReply} disabled={suggestingReply}
                      className="p-2.5 border border-gray-200 dark:border-gray-600 rounded-xl hover:bg-amber-50 dark:hover:bg-amber-900/20 hover:border-amber-300 disabled:opacity-50 transition-all group"
                      title="AI Suggest Reply">
                      <Sparkles className={`w-4 h-4 transition-colors ${suggestingReply ? 'animate-pulse text-amber-500' : 'text-gray-400 group-hover:text-amber-500'}`} />
                    </button>
                    <button onClick={handleReply} disabled={sending || !replyText.trim()}
                      className="p-2.5 bg-gradient-to-r from-indigo-500 to-indigo-600 text-white rounded-xl hover:from-indigo-600 hover:to-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm"
                      title="Send (Ctrl+Enter)">
                      <Send className={`w-4 h-4 ${sending ? 'animate-pulse' : ''}`} />
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* ── Right: Contact Panel ───────────────────────────────────── */}
        {showContactPanel && selectedThread?.contact && (
          <div className="w-72 border-l border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 flex flex-col">
            {/* Contact Header with gradient */}
            <div className="bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 p-6 text-center">
              <div className="w-16 h-16 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center mx-auto mb-3 ring-2 ring-white/30">
                <span className="text-2xl font-bold text-white">{selectedThread.contact.name?.[0]?.toUpperCase() || '?'}</span>
              </div>
              <h3 className="font-semibold text-white text-base">{selectedThread.contact.name}</h3>
              <p className="text-indigo-100 text-xs mt-0.5">{selectedThread.contact.email}</p>
            </div>
            {/* Contact Details */}
            <div className="p-4 space-y-4 flex-1 overflow-y-auto">
              {selectedThread.contact.title && (
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0">
                    <Briefcase className="w-4 h-4 text-blue-500" />
                  </div>
                  <div>
                    <span className="text-[10px] font-medium text-gray-400 uppercase tracking-wider">Title</span>
                    <p className="text-sm text-gray-800 dark:text-gray-200">{selectedThread.contact.title}</p>
                  </div>
                </div>
              )}
              {selectedThread.contact.company && (
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 flex items-center justify-center flex-shrink-0">
                    <Building className="w-4 h-4 text-emerald-500" />
                  </div>
                  <div>
                    <span className="text-[10px] font-medium text-gray-400 uppercase tracking-wider">Company</span>
                    <p className="text-sm text-gray-800 dark:text-gray-200">{selectedThread.contact.company}</p>
                  </div>
                </div>
              )}
              {selectedThread.contact.phone && (
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-amber-50 dark:bg-amber-900/30 flex items-center justify-center flex-shrink-0">
                    <Phone className="w-4 h-4 text-amber-500" />
                  </div>
                  <div>
                    <span className="text-[10px] font-medium text-gray-400 uppercase tracking-wider">Phone</span>
                    <a href={`tel:${selectedThread.contact.phone}`} className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline block">{selectedThread.contact.phone}</a>
                  </div>
                </div>
              )}
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-violet-50 dark:bg-violet-900/30 flex items-center justify-center flex-shrink-0">
                  <Mail className="w-4 h-4 text-violet-500" />
                </div>
                <div>
                  <span className="text-[10px] font-medium text-gray-400 uppercase tracking-wider">Email</span>
                  <a href={`mailto:${selectedThread.contact.email}`} className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline block truncate">{selectedThread.contact.email}</a>
                </div>
              </div>
            </div>
            {/* Quick Actions */}
            <div className="p-3 border-t border-gray-200 dark:border-gray-700">
              <div className="flex gap-2">
                {selectedThread.contact.phone && (
                  <a href={`tel:${selectedThread.contact.phone}`}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                    <Phone className="w-3.5 h-3.5" /> Call
                  </a>
                )}
                <a href={`mailto:${selectedThread.contact.email}`}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                  <ExternalLink className="w-3.5 h-3.5" /> Email
                </a>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ─── Delete Confirmation Modal ──────────────────────────────── */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => !deleting && setShowDeleteConfirm(null)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 w-full max-w-sm mx-4 overflow-hidden">
            <div className="p-6">
              <div className="w-12 h-12 rounded-full bg-rose-100 dark:bg-rose-900/30 flex items-center justify-center mx-auto mb-4">
                <Trash2 className="w-6 h-6 text-rose-500" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 text-center">
                Delete {showDeleteConfirm.type === 'bulk' ? `${selectedThreadIds.size} thread${selectedThreadIds.size > 1 ? 's' : ''}` : 'thread'}?
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center mt-2">
                {showDeleteConfirm.type === 'bulk'
                  ? `This will remove ${selectedThreadIds.size} conversation${selectedThreadIds.size > 1 ? 's' : ''} from your inbox.`
                  : 'This will remove the conversation from your inbox.'}
              </p>
            </div>
            <div className="flex gap-3 px-6 pb-6">
              <button onClick={() => setShowDeleteConfirm(null)} disabled={deleting}
                className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-gray-600 rounded-xl text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-all disabled:opacity-50">
                Cancel
              </button>
              <button onClick={handleDeleteConfirm} disabled={deleting}
                className="flex-1 px-4 py-2.5 bg-rose-500 hover:bg-rose-600 text-white rounded-xl text-sm font-medium transition-all disabled:opacity-50 flex items-center justify-center gap-2">
                {deleting ? (
                  <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Deleting...</>
                ) : (
                  <><Trash2 className="w-4 h-4" /> Delete</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
