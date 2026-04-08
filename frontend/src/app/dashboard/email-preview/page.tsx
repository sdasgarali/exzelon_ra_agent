'use client'

import { useState, useEffect, useCallback } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { emailPreviewApi, mailboxesApi } from '@/lib/api'
import {
  Search, RefreshCw, CheckCircle, XCircle, Send, Sparkles,
  Mail, User, Building, FileSearch, Shield, AlertTriangle,
  Check, X, Loader2, ArrowLeftRight, ChevronDown, Eye,
  Zap, BarChart3, ChevronRight,
} from 'lucide-react'

// ─── Types ─────────────────────────────────────────────────────────

interface Draft {
  draft_id: number
  tenant_id: number
  contact_id: number
  lead_id: number | null
  campaign_id: number | null
  step_id: number | null
  mailbox_id: number
  subject: string
  body_html: string
  body_text: string | null
  original_subject: string | null
  original_body_html: string | null
  status: string
  source: string | null
  spam_score: number
  spam_grade: string
  flagged_words: Array<{ word: string; severity: string; count: number; location: string; points: number }>
  deliverability_score: number | null
  ai_rewritten: boolean
  approved_by: number | null
  approved_at: string | null
  rejected_by: number | null
  rejected_at: string | null
  sent_at: string | null
  expires_at: string | null
  batch_id: string | null
  variant_index: number | null
  created_at: string | null
  contact: { contact_id: number; first_name: string; last_name: string; email: string; title: string; client_name: string } | null
  mailbox: { mailbox_id: number; email: string; display_name: string } | null
  lead?: { lead_id: number; job_title: string; client_name: string; state: string } | null
}

interface SpamSuggestion {
  original: string
  replacement: string
}

interface DeliverabilityData {
  overall_score: number
  dns: { score: number; weight: number; spf: any; dkim: any; dmarc: any }
  spam: { score: number; raw_score: number; weight: number; grade: string; flagged_words: any[] }
  blacklist: { score: number; weight: number; is_clean: boolean; ip: string; total_checked: number; total_listed: number; results: any[] }
  reputation: { score: number; weight: number; domain: string; bounce_rate: number; is_blacklisted: boolean }
}

// ─── Helpers ───────────────────────────────────────────────────────

function spamBadgeColor(grade: string) {
  switch (grade) {
    case 'clean': return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
    case 'low_risk': return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300'
    case 'medium_risk': return 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300'
    case 'high_risk': return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
    case 'spam': return 'bg-red-200 text-red-900 dark:bg-red-900/40 dark:text-red-200'
    default: return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
  }
}

function statusBadgeColor(status: string) {
  switch (status) {
    case 'pending': return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300'
    case 'approved': return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
    case 'rejected': return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
    case 'sent': return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'
    case 'expired': return 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
    default: return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
  }
}

function scoreColor(score: number): string {
  if (score >= 80) return '#22c55e'
  if (score >= 60) return '#eab308'
  if (score >= 40) return '#f97316'
  return '#ef4444'
}

function ScoreGauge({ score, size = 120 }: { score: number; size?: number }) {
  const radius = (size - 16) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference
  const color = scoreColor(score)

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#e5e7eb" strokeWidth="8" className="dark:stroke-gray-700" />
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth="8" strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round" className="transition-all duration-700" />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-2xl font-bold" style={{ color }}>{Math.round(score)}</span>
      </div>
    </div>
  )
}

// ─── Main Component ────────────────────────────────────────────────

export default function EmailPreviewPage() {
  const searchParams = useSearchParams()
  const router = useRouter()

  const [drafts, setDrafts] = useState<Draft[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedDraft, setSelectedDraft] = useState<Draft | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || '')
  const [batchId, setBatchId] = useState(searchParams.get('batch_id') || '')
  const [sourceFilter, setSourceFilter] = useState(searchParams.get('source') || '')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [mailboxes, setMailboxes] = useState<{ mailbox_id: number; email: string; display_name: string }[]>([])

  // Right panel state
  const [spamSuggestions, setSpamSuggestions] = useState<SpamSuggestion[]>([])
  const [loadingSpam, setLoadingSpam] = useState(false)
  const [showDeliverability, setShowDeliverability] = useState(false)
  const [deliverabilityData, setDeliverabilityData] = useState<DeliverabilityData | null>(null)
  const [loadingDeliverability, setLoadingDeliverability] = useState(false)

  // Action states
  const [rewriting, setRewriting] = useState(false)
  const [approving, setApproving] = useState(false)
  const [sending, setSending] = useState(false)
  const [showOriginal, setShowOriginal] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editSubject, setEditSubject] = useState('')
  const [editBody, setEditBody] = useState('')

  // Batch actions
  const [approvingAll, setApprovingAll] = useState(false)
  const [sendingBatch, setSendingBatch] = useState(false)
  const [sendError, setSendError] = useState('')

  // Stats
  const pendingCount = drafts.filter(d => d.status === 'pending').length
  const approvedCount = drafts.filter(d => d.status === 'approved').length
  const sentCount = drafts.filter(d => d.status === 'sent').length

  const fetchDrafts = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { page, per_page: 50 }
      if (batchId) params.batch_id = batchId
      if (statusFilter) params.status = statusFilter
      if (sourceFilter) params.source = sourceFilter
      const data = await emailPreviewApi.listDrafts(params)
      setDrafts(data.drafts || [])
      setTotal(data.total || 0)
      setTotalPages(data.pages || 1)
    } catch (err) {
      console.error('Failed to fetch drafts:', err)
    } finally {
      setLoading(false)
    }
  }, [page, batchId, statusFilter, sourceFilter])

  useEffect(() => { fetchDrafts() }, [fetchDrafts])
  useEffect(() => {
    mailboxesApi.list().then((data: any) => {
      setMailboxes((data.mailboxes || data || []).map((m: any) => ({
        mailbox_id: m.mailbox_id,
        email: m.email,
        display_name: m.display_name || m.email,
      })))
    }).catch(() => {})
  }, [])

  const selectDraft = async (draft: Draft) => {
    try {
      const full = await emailPreviewApi.getDraft(draft.draft_id)
      setSelectedDraft(full)
      setShowOriginal(false)
      setEditing(false)
      // Auto-load spam suggestions
      if (full.flagged_words?.length > 0) {
        loadSpamSuggestions(full)
      } else {
        setSpamSuggestions([])
      }
    } catch {
      setSelectedDraft(draft)
    }
  }

  const loadSpamSuggestions = async (draft: Draft) => {
    setLoadingSpam(true)
    try {
      const data = await emailPreviewApi.spamCheck({ subject: draft.subject, body_html: draft.body_html })
      setSpamSuggestions(data.suggestions || [])
    } catch {
      setSpamSuggestions([])
    } finally {
      setLoadingSpam(false)
    }
  }

  const handleApprove = async (draftId: number) => {
    setApproving(true)
    try {
      await emailPreviewApi.approveDraft(draftId)
      await fetchDrafts()
      if (selectedDraft?.draft_id === draftId) {
        setSelectedDraft(prev => prev ? { ...prev, status: 'approved' } : null)
      }
    } catch (err) { console.error(err) }
    finally { setApproving(false) }
  }

  const handleReject = async (draftId: number) => {
    try {
      await emailPreviewApi.rejectDraft(draftId)
      await fetchDrafts()
      if (selectedDraft?.draft_id === draftId) {
        setSelectedDraft(prev => prev ? { ...prev, status: 'rejected' } : null)
      }
    } catch (err) { console.error(err) }
  }

  const handleAiRewrite = async () => {
    if (!selectedDraft) return
    setRewriting(true)
    try {
      const data = await emailPreviewApi.aiRewrite(selectedDraft.draft_id)
      setSelectedDraft(prev => prev ? {
        ...prev,
        subject: data.subject,
        body_html: data.body_html,
        spam_score: data.spam_score,
        spam_grade: data.spam_grade,
        ai_rewritten: true,
      } : null)
      await fetchDrafts()
      if (data.spam_score > 0) {
        loadSpamSuggestions({ ...selectedDraft, subject: data.subject, body_html: data.body_html })
      }
    } catch (err) { console.error(err) }
    finally { setRewriting(false) }
  }

  const handleSend = async (draftId: number) => {
    setSending(true)
    setSendError('')
    try {
      await emailPreviewApi.sendDraft(draftId)
      await fetchDrafts()
      if (selectedDraft?.draft_id === draftId) {
        setSelectedDraft(prev => prev ? { ...prev, status: 'sent' } : null)
      }
    } catch (err: any) {
      if (err?.response?.status === 409) {
        const detail = err.response.data?.detail
        setSendError(detail?.message || 'Send blocked by safety checks')
      } else {
        console.error(err)
      }
    }
    finally { setSending(false) }
  }

  const handleApproveAll = async () => {
    if (!batchId) return
    setApprovingAll(true)
    try {
      await emailPreviewApi.approveAll(batchId)
      await fetchDrafts()
    } catch (err) { console.error(err) }
    finally { setApprovingAll(false) }
  }

  const handleSendBatch = async () => {
    if (!batchId) return
    setSendingBatch(true)
    try {
      await emailPreviewApi.sendBatch(batchId)
      await fetchDrafts()
    } catch (err) { console.error(err) }
    finally { setSendingBatch(false) }
  }

  const handleDeliverabilityScore = async () => {
    if (!selectedDraft) return
    setLoadingDeliverability(true)
    setShowDeliverability(true)
    try {
      const data = await emailPreviewApi.deliverabilityScore({
        mailbox_id: selectedDraft.mailbox_id,
        subject: selectedDraft.subject,
        body_html: selectedDraft.body_html,
      })
      setDeliverabilityData(data)
    } catch (err) { console.error(err) }
    finally { setLoadingDeliverability(false) }
  }

  const handleSpamFix = async (original: string, replacement: string) => {
    if (!selectedDraft) return
    try {
      const data = await emailPreviewApi.spamFix(selectedDraft.draft_id, [{ original, replacement }])
      setSelectedDraft(prev => prev ? {
        ...prev,
        subject: data.subject,
        body_html: data.body_html,
        spam_score: data.spam_score,
        spam_grade: data.spam_grade,
        flagged_words: data.flagged_words,
      } : null)
      // Remove the fixed suggestion
      setSpamSuggestions(prev => prev.filter(s => s.original !== original))
      await fetchDrafts()
    } catch (err) { console.error(err) }
  }

  const handleSaveEdit = async () => {
    if (!selectedDraft) return
    try {
      const data = await emailPreviewApi.updateDraft(selectedDraft.draft_id, {
        subject: editSubject,
        body_html: editBody,
      })
      setSelectedDraft(data)
      setEditing(false)
      await fetchDrafts()
    } catch (err) { console.error(err) }
  }

  const startEdit = () => {
    if (!selectedDraft) return
    setEditSubject(selectedDraft.subject)
    setEditBody(selectedDraft.body_html)
    setEditing(true)
  }

  // Filter drafts by search
  const filteredDrafts = drafts.filter(d => {
    if (!search) return true
    const s = search.toLowerCase()
    return (
      d.subject?.toLowerCase().includes(s) ||
      d.contact?.first_name?.toLowerCase().includes(s) ||
      d.contact?.last_name?.toLowerCase().includes(s) ||
      d.contact?.email?.toLowerCase().includes(s) ||
      d.contact?.client_name?.toLowerCase().includes(s)
    )
  })

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      {/* Top Bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shrink-0">
        <div className="flex items-center gap-3">
          <FileSearch className="w-5 h-5 text-teal-600 dark:text-teal-400" />
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Email Preview & Approve</h1>
          {batchId && (
            <span className="text-xs px-2 py-0.5 bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300 rounded-full">
              Batch: {batchId.slice(0, 8)}...
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Stats */}
          <span className="text-xs text-gray-500 dark:text-gray-400">{total} drafts</span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${statusBadgeColor('pending')}`}>{pendingCount} pending</span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${statusBadgeColor('approved')}`}>{approvedCount} approved</span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${statusBadgeColor('sent')}`}>{sentCount} sent</span>

          <div className="h-4 w-px bg-gray-300 dark:bg-gray-600 mx-1" />

          {/* Status filter */}
          <select
            className="text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); setPage(1) }}
          >
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="sent">Sent</option>
          </select>

          {/* Bulk actions */}
          {batchId && pendingCount > 0 && (
            <button
              onClick={handleApproveAll}
              disabled={approvingAll}
              className="text-xs px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 flex items-center gap-1"
            >
              {approvingAll ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
              Approve All
            </button>
          )}
          {batchId && approvedCount > 0 && (
            <button
              onClick={handleSendBatch}
              disabled={sendingBatch}
              className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1"
            >
              {sendingBatch ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
              Send Batch
            </button>
          )}

          <button onClick={fetchDrafts} className="p-1.5 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* 3-Panel Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel — Draft List */}
        <div className="w-[320px] border-r border-gray-200 dark:border-gray-700 flex flex-col bg-white dark:bg-gray-900">
          {/* Search */}
          <div className="p-2 border-b border-gray-200 dark:border-gray-700">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
              <input
                type="text"
                placeholder="Search contacts..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 placeholder-gray-400"
              />
            </div>
          </div>

          {/* Draft cards */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
              </div>
            ) : filteredDrafts.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 text-gray-500 dark:text-gray-400">
                <Mail className="w-8 h-8 mb-2 opacity-50" />
                <p className="text-sm">No drafts found</p>
              </div>
            ) : (
              filteredDrafts.map(draft => (
                <div
                  key={draft.draft_id}
                  onClick={() => selectDraft(draft)}
                  className={`px-3 py-2.5 border-b border-gray-100 dark:border-gray-800 cursor-pointer transition-colors ${
                    selectedDraft?.draft_id === draft.draft_id
                      ? 'bg-teal-50 dark:bg-teal-900/20 border-l-2 border-l-teal-500'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800/50 border-l-2 border-l-transparent'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-teal-500 to-teal-600 flex items-center justify-center text-white text-xs font-medium shrink-0">
                        {draft.contact?.first_name?.[0] || '?'}
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">
                          {draft.contact?.first_name} {draft.contact?.last_name}
                        </p>
                        <p className="text-[10px] text-gray-500 dark:text-gray-400 truncate">
                          {draft.contact?.client_name}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${spamBadgeColor(draft.spam_grade)}`}>
                        {draft.spam_score}
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${statusBadgeColor(draft.status)}`}>
                        {draft.status}
                      </span>
                    </div>
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 truncate">{draft.subject}</p>
                </div>
              ))
            )}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between p-2 border-t border-gray-200 dark:border-gray-700">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-50"
              >
                Prev
              </button>
              <span className="text-xs text-gray-500">{page}/{totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          )}
        </div>

        {/* Center Panel — Email Preview */}
        <div className="flex-1 flex flex-col overflow-hidden bg-gray-50 dark:bg-gray-950">
          {selectedDraft ? (
            <>
              {/* Email header */}
              <div className="p-4 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 space-y-2">
                <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <span className="font-medium text-gray-700 dark:text-gray-300">From:</span>
                  <span>{selectedDraft.mailbox?.display_name || selectedDraft.mailbox?.email}</span>
                  <span className="text-gray-400">{'<'}{selectedDraft.mailbox?.email}{'>'}</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <span className="font-medium text-gray-700 dark:text-gray-300">To:</span>
                  <span>{selectedDraft.contact?.first_name} {selectedDraft.contact?.last_name}</span>
                  <span className="text-gray-400">{'<'}{selectedDraft.contact?.email}{'>'}</span>
                </div>
                {editing ? (
                  <input
                    value={editSubject}
                    onChange={e => setEditSubject(e.target.value)}
                    className="w-full text-sm font-semibold border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                ) : (
                  <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{selectedDraft.subject}</h2>
                )}
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${statusBadgeColor(selectedDraft.status)}`}>
                    {selectedDraft.status}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${spamBadgeColor(selectedDraft.spam_grade)}`}>
                    Spam: {selectedDraft.spam_score}
                  </span>
                  {selectedDraft.ai_rewritten && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300">
                      AI Rewritten
                    </span>
                  )}
                  {selectedDraft.source && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                      {selectedDraft.source}
                    </span>
                  )}
                </div>
              </div>

              {/* Toggle: Original vs Rewritten */}
              {selectedDraft.ai_rewritten && selectedDraft.original_body_html && (
                <div className="px-4 py-2 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 flex items-center gap-2">
                  <button
                    onClick={() => setShowOriginal(!showOriginal)}
                    className="text-xs flex items-center gap-1.5 px-3 py-1 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300"
                  >
                    <ArrowLeftRight className="w-3 h-3" />
                    {showOriginal ? 'Show Rewritten' : 'Show Original'}
                  </button>
                </div>
              )}

              {/* Email body */}
              <div className="flex-1 overflow-y-auto p-4">
                {editing ? (
                  <textarea
                    value={editBody}
                    onChange={e => setEditBody(e.target.value)}
                    className="w-full h-full min-h-[300px] text-sm border border-gray-300 dark:border-gray-600 rounded p-3 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 font-mono resize-none"
                  />
                ) : (
                  <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                    <div
                      className="prose prose-sm dark:prose-invert max-w-none"
                      dangerouslySetInnerHTML={{
                        __html: showOriginal
                          ? (selectedDraft.original_body_html || selectedDraft.body_html)
                          : selectedDraft.body_html
                      }}
                    />
                  </div>
                )}
              </div>

              {/* Action bar */}
              <div className="px-4 py-3 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 flex items-center gap-2">
                {selectedDraft.status === 'pending' && (
                  <>
                    <button
                      onClick={() => handleReject(selectedDraft.draft_id)}
                      className="text-xs px-3 py-1.5 border border-red-300 text-red-700 dark:border-red-700 dark:text-red-300 rounded hover:bg-red-50 dark:hover:bg-red-900/20 flex items-center gap-1"
                    >
                      <X className="w-3 h-3" /> Reject
                    </button>
                    <button
                      onClick={() => handleApprove(selectedDraft.draft_id)}
                      disabled={approving}
                      className="text-xs px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 flex items-center gap-1"
                    >
                      {approving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                      Approve
                    </button>
                  </>
                )}
                {selectedDraft.status === 'approved' && (
                  <button
                    onClick={() => handleSend(selectedDraft.draft_id)}
                    disabled={sending}
                    className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1"
                  >
                    {sending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                    Send
                  </button>
                )}

                <div className="flex-1" />

                {editing ? (
                  <>
                    <button onClick={() => setEditing(false)} className="text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800">
                      Cancel
                    </button>
                    <button onClick={handleSaveEdit} className="text-xs px-3 py-1.5 bg-teal-600 text-white rounded hover:bg-teal-700 flex items-center gap-1">
                      <Check className="w-3 h-3" /> Save
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={startEdit}
                      className="text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 flex items-center gap-1"
                    >
                      <Eye className="w-3 h-3" /> Edit
                    </button>
                    <button
                      onClick={handleAiRewrite}
                      disabled={rewriting}
                      className="text-xs px-3 py-1.5 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 flex items-center gap-1"
                    >
                      {rewriting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                      AI Rewrite
                    </button>
                    <button
                      onClick={handleDeliverabilityScore}
                      disabled={loadingDeliverability}
                      className="text-xs px-3 py-1.5 border border-teal-300 text-teal-700 dark:border-teal-700 dark:text-teal-300 rounded hover:bg-teal-50 dark:hover:bg-teal-900/20 flex items-center gap-1"
                    >
                      {loadingDeliverability ? <Loader2 className="w-3 h-3 animate-spin" /> : <Shield className="w-3 h-3" />}
                      Deliverability
                    </button>
                  </>
                )}
              </div>

              {/* Send gate error banner */}
              {sendError && (
                <div className="mx-4 mt-2 p-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded text-xs text-red-700 dark:text-red-300 flex items-start gap-2">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  <div className="flex-1">{sendError}</div>
                  <button onClick={() => setSendError('')} className="text-red-400 hover:text-red-600">
                    <X className="w-3 h-3" />
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-400 dark:text-gray-500">
              <FileSearch className="w-12 h-12 mb-3 opacity-50" />
              <p className="text-sm font-medium">Select a draft to preview</p>
              <p className="text-xs mt-1">Click on a draft from the list to view its content</p>
            </div>
          )}
        </div>

        {/* Right Panel — Spam Checker / Deliverability */}
        <div className="w-[350px] border-l border-gray-200 dark:border-gray-700 flex flex-col bg-white dark:bg-gray-900 overflow-hidden">
          {showDeliverability && deliverabilityData ? (
            /* Deliverability Score Panel */
            <div className="flex-1 overflow-y-auto">
              <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  <Shield className="w-4 h-4 text-teal-600" />
                  Deliverability Score
                </h3>
                <button onClick={() => setShowDeliverability(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Overall gauge */}
              <div className="flex justify-center py-4">
                <ScoreGauge score={deliverabilityData.overall_score} size={140} />
              </div>
              <p className="text-center text-xs text-gray-500 dark:text-gray-400 mb-4">Overall Score</p>

              {/* Breakdown cards */}
              <div className="px-4 space-y-3 pb-4">
                {/* DNS */}
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-gray-700 dark:text-gray-300">DNS ({deliverabilityData.dns.weight}%)</span>
                    <span className="text-xs font-bold" style={{ color: scoreColor(deliverabilityData.dns.score) }}>{deliverabilityData.dns.score}/100</span>
                  </div>
                  <div className="space-y-1.5">
                    {['spf', 'dkim', 'dmarc'].map(type => {
                      const data = deliverabilityData.dns[type as keyof typeof deliverabilityData.dns] as any
                      const valid = data?.valid
                      return (
                        <div key={type} className="flex items-center justify-between text-xs">
                          <span className="uppercase text-gray-500 dark:text-gray-400">{type}</span>
                          <span className={valid ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                            {valid ? 'Pass' : 'Fail'}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* Spam */}
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-gray-700 dark:text-gray-300">Spam Filter ({deliverabilityData.spam.weight}%)</span>
                    <span className="text-xs font-bold" style={{ color: scoreColor(deliverabilityData.spam.score) }}>{deliverabilityData.spam.score}/100</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${spamBadgeColor(deliverabilityData.spam.grade)}`}>
                      {deliverabilityData.spam.grade}
                    </span>
                    <span className="text-xs text-gray-500">Raw: {deliverabilityData.spam.raw_score}</span>
                  </div>
                </div>

                {/* Blacklist */}
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-gray-700 dark:text-gray-300">Blacklist ({deliverabilityData.blacklist.weight}%)</span>
                    <span className="text-xs font-bold" style={{ color: scoreColor(deliverabilityData.blacklist.score) }}>{deliverabilityData.blacklist.score}/100</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${deliverabilityData.blacklist.is_clean ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'}`}>
                      {deliverabilityData.blacklist.is_clean ? 'Clean' : 'Listed'}
                    </span>
                    {deliverabilityData.blacklist.ip && (
                      <span className="text-xs text-gray-500">IP: {deliverabilityData.blacklist.ip}</span>
                    )}
                  </div>
                  <p className="text-[10px] text-gray-400 mt-1">
                    {deliverabilityData.blacklist.total_checked} providers checked, {deliverabilityData.blacklist.total_listed} listed
                  </p>
                </div>

                {/* Reputation */}
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-gray-700 dark:text-gray-300">Reputation ({deliverabilityData.reputation.weight}%)</span>
                    <span className="text-xs font-bold" style={{ color: scoreColor(deliverabilityData.reputation.score) }}>{deliverabilityData.reputation.score}/100</span>
                  </div>
                  {deliverabilityData.reputation.domain && (
                    <p className="text-xs text-gray-500">Domain: {deliverabilityData.reputation.domain}</p>
                  )}
                  <p className="text-xs text-gray-500">Bounce rate: {deliverabilityData.reputation.bounce_rate}%</p>
                </div>
              </div>
            </div>
          ) : selectedDraft ? (
            /* Spam Free Maker Panel */
            <div className="flex-1 overflow-y-auto">
              <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                  Spam Free Maker
                  {selectedDraft.flagged_words?.length > 0 && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
                      {selectedDraft.flagged_words.length} words
                    </span>
                  )}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Click a card to replace the spam phrase with its AI-suggested alternative
                </p>
              </div>

              <div className="p-3 space-y-2">
                {loadingSpam ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
                  </div>
                ) : selectedDraft.flagged_words?.length === 0 ? (
                  <div className="text-center py-8 text-gray-400 dark:text-gray-500">
                    <CheckCircle className="w-8 h-8 mx-auto mb-2 text-green-500" />
                    <p className="text-sm font-medium text-green-600 dark:text-green-400">No spam words detected</p>
                    <p className="text-xs mt-1">This email looks clean</p>
                  </div>
                ) : (
                  <>
                    {spamSuggestions.map((s, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSpamFix(s.original, s.replacement)}
                        className="w-full text-left p-2.5 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors group"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300 line-through">
                            {s.original}
                          </span>
                          <ChevronRight className="w-3 h-3 text-gray-400 group-hover:text-teal-500" />
                          <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
                            {s.replacement}
                          </span>
                        </div>
                      </button>
                    ))}
                    {/* Show flagged words without suggestions */}
                    {selectedDraft.flagged_words?.filter(fw =>
                      !spamSuggestions.some(s => s.original === fw.word) && !fw.word.startsWith('[pattern:')
                    ).map((fw, idx) => (
                      <div key={`fw-${idx}`} className="p-2.5 border border-gray-200 dark:border-gray-700 rounded-lg opacity-70">
                        <div className="flex items-center justify-between">
                          <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
                            {fw.word}
                          </span>
                          <span className="text-[10px] text-gray-400">
                            {fw.severity} | {fw.location} | {fw.points}pts
                          </span>
                        </div>
                      </div>
                    ))}
                    <button
                      onClick={() => selectedDraft && loadSpamSuggestions(selectedDraft)}
                      className="w-full text-xs py-2 text-center text-teal-600 dark:text-teal-400 hover:underline flex items-center justify-center gap-1"
                    >
                      <RefreshCw className="w-3 h-3" /> Re-check spam
                    </button>
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-400 dark:text-gray-500 p-4">
              <AlertTriangle className="w-8 h-8 mb-2 opacity-50" />
              <p className="text-sm text-center">Select a draft to see spam analysis</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
