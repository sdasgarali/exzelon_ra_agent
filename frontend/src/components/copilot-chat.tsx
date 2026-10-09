'use client'

import { useState, useRef, useEffect, useCallback, type ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { X, Send, Minimize2, Sparkles, Trash2, RotateCcw, AlertCircle, Loader2 } from 'lucide-react'
import { copilotApi, getApiError } from '@/lib/api'
import { useAuthStore } from '@/lib/store'

interface ChatItem {
  key: string
  role: 'user' | 'assistant' | 'error'
  content: string
  /** Only on error items: the user message that failed, for Retry. */
  failedMessage?: string
  /** Only on error items: HTTP status of the failure, if any. */
  status?: number
}

const NOT_CONFIGURED_HINT = 'Ask an admin to set the AI provider in Settings → AI/LLM.'

const DEFAULT_SUGGESTIONS = [
  'What should I do next?',
  'How do I launch my first campaign?',
  'Why are my emails not sending?',
]

/** Suggested prompts per dashboard section (first path segment after /dashboard). */
export const PAGE_SUGGESTIONS: Record<string, string[]> = {
  dashboard: DEFAULT_SUGGESTIONS,
  mailboxes: [
    'How do I connect a Gmail account?',
    'How does warmup work?',
    'Why is my mailbox health score low?',
  ],
  warmup: [
    'How does warmup work?',
    'How long should I warm up a new mailbox?',
    'What do the warmup alerts mean?',
  ],
  leads: [
    'How do I find contacts for these leads?',
    'How does lead sourcing work?',
    'Which leads should I prioritise?',
  ],
  contacts: [
    'Why can only valid emails be contacted?',
    'How do I validate contact emails?',
    'How do I add contacts to a campaign?',
  ],
  campaigns: [
    'Write a 3-step cold email sequence',
    'How do I improve my reply rate?',
    'Why is my campaign not sending?',
  ],
  templates: [
    'Write a short cold email template',
    'Suggest 5 subject lines for a staffing offer',
    'How do I avoid spam words?',
  ],
  inbox: [
    'How should I reply to an interested lead?',
    'How do I handle a "not now" reply?',
    'What are reply macros?',
  ],
  settings: [
    'How do I set up the AI provider?',
    'What do the business rules control?',
    'How do I invite a teammate?',
  ],
}

/** Current dashboard section, e.g. "/dashboard/campaigns/12" → "campaigns". */
export function getPageContext(pathname: string | null | undefined): string {
  const parts = (pathname || '').split('/').filter(Boolean)
  const i = parts.indexOf('dashboard')
  if (i === -1) return parts[parts.length - 1] || 'dashboard'
  return parts[i + 1] || 'dashboard'
}

// ---------------------------------------------------------------------------
// Light, safe formatting of assistant replies. Everything is rendered as React
// text nodes (auto-escaped); only **bold**, `code`, "- " bullets, paragraphs and
// /dashboard/... route tokens get structure. No HTML from the model is injected.
// ---------------------------------------------------------------------------

const INLINE_RE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\/dashboard(?:\/[A-Za-z0-9_-]+)*)/g
const ROUTE_RE = /^\/dashboard(?:\/[A-Za-z0-9_-]+)*$/

function renderInline(text: string, onNavigate: () => void, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0
  let n = 0
  for (const m of Array.from(text.matchAll(INLINE_RE))) {
    const token = m[0]
    const start = m.index ?? 0
    // A route token glued to a preceding word/URL (e.g. "https://x.com/dashboard") is plain text.
    if (token.startsWith('/') && start > 0 && /[A-Za-z0-9_:/.-]/.test(text[start - 1])) continue
    if (start > last) out.push(text.slice(last, start))
    const key = `${keyPrefix}-${n++}`
    if (token.startsWith('**')) {
      out.push(
        <strong key={key} className="font-semibold">
          {renderInline(token.slice(2, -2), onNavigate, key)}
        </strong>,
      )
    } else if (token.startsWith('`')) {
      const inner = token.slice(1, -1)
      if (ROUTE_RE.test(inner)) {
        out.push(<RouteLink key={key} href={inner} onNavigate={onNavigate} />)
      } else {
        out.push(
          <code key={key} className="px-1 py-0.5 rounded bg-zinc-200 dark:bg-zinc-700 text-zinc-800 dark:text-zinc-100 text-xs">
            {inner}
          </code>,
        )
      }
    } else {
      out.push(<RouteLink key={key} href={token} onNavigate={onNavigate} />)
    }
    last = start + token.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function RouteLink({ href, onNavigate }: { href: string; onNavigate: () => void }) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className="font-medium text-indigo-600 dark:text-indigo-300 underline underline-offset-2 hover:text-indigo-800 dark:hover:text-indigo-200"
    >
      {href}
    </Link>
  )
}

export function FormattedReply({ content, onNavigate }: { content: string; onNavigate: () => void }) {
  const blocks: ReactNode[] = []
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  let para: string[] = []
  let list: string[] = []

  const flushPara = () => {
    if (para.length) {
      const k = `p${blocks.length}`
      blocks.push(
        <p key={k} className="whitespace-pre-wrap">
          {renderInline(para.join('\n'), onNavigate, k)}
        </p>,
      )
      para = []
    }
  }
  const flushList = () => {
    if (list.length) {
      const k = `l${blocks.length}`
      blocks.push(
        <ul key={k} className="list-disc pl-5 space-y-1">
          {list.map((item, i) => (
            <li key={i}>{renderInline(item, onNavigate, `${k}-${i}`)}</li>
          ))}
        </ul>,
      )
      list = []
    }
  }

  for (const raw of lines) {
    const bullet = raw.match(/^\s*[-*]\s+(.*)$/)
    if (bullet) {
      flushPara()
      list.push(bullet[1])
    } else if (!raw.trim()) {
      flushPara()
      flushList()
    } else {
      flushList()
      para.push(raw)
    }
  }
  flushPara()
  flushList()
  return <div className="space-y-2 break-words">{blocks}</div>
}

// ---------------------------------------------------------------------------

let keySeq = 0
const nextKey = () => `local-${++keySeq}`

export function CopilotChat() {
  const pathname = usePathname()
  const { user } = useAuthStore()
  const effectiveRole = user?.base_role || user?.role
  const isAdmin = effectiveRole === 'admin' || effectiveRole === 'super_admin'

  const [isOpen, setIsOpen] = useState(false)
  const [isMinimized, setIsMinimized] = useState(false)
  const [items, setItems] = useState<ChatItem[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [historyState, setHistoryState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [clearing, setClearing] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const launcherRef = useRef<HTMLButtonElement>(null)
  const wasOpenRef = useRef(false)

  const context = getPageContext(pathname)
  const suggestions = PAGE_SUGGESTIONS[context] || DEFAULT_SUGGESTIONS

  // Load the stored conversation the first time the panel opens.
  // A ref (not the state) guards the request: flipping historyState to 'loading'
  // must not re-run/cancel this effect before the response arrives.
  const historyRequestedRef = useRef(false)
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])
  useEffect(() => {
    if (!isOpen || historyRequestedRef.current) return
    historyRequestedRef.current = true
    setHistoryState('loading')
    copilotApi
      .history(50)
      .then((data) => {
        if (!mountedRef.current) return
        const loaded: ChatItem[] = (data?.messages || []).map((m) => ({
          key: `h-${m.id}`,
          role: m.role,
          content: m.content,
        }))
        setItems(loaded)
        setHistoryState('loaded')
      })
      .catch(() => {
        if (mountedRef.current) setHistoryState('error')
      })
  }, [isOpen])

  // Autoscroll to the latest message.
  useEffect(() => {
    if (isOpen && !isMinimized) messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' })
  }, [items, sending, isOpen, isMinimized])

  // Focus management: input when the panel is shown, launcher when it closes.
  // Re-runs when sending/loading ends so focus returns to the re-enabled input.
  const historyBusy = historyState === 'loading'
  useEffect(() => {
    if (isOpen && !isMinimized) {
      if (!sending && !historyBusy) inputRef.current?.focus()
    } else if (!isOpen && wasOpenRef.current) {
      launcherRef.current?.focus()
    }
    wasOpenRef.current = isOpen
  }, [isOpen, isMinimized, sending, historyBusy])

  const minimize = useCallback(() => setIsMinimized(true), [])

  const send = useCallback(
    async (text: string, opts: { retryKey?: string } = {}) => {
      const message = text.trim()
      if (!message || sending) return
      const ctx = getPageContext(pathname)
      setSending(true)
      setItems((prev) => {
        // A retry drops its error bubble and reuses the existing user bubble.
        if (opts.retryKey) return prev.filter((it) => it.key !== opts.retryKey)
        return [...prev, { key: nextKey(), role: 'user', content: message }]
      })
      if (!opts.retryKey) setInput('')
      try {
        const data = await copilotApi.chat(message, ctx)
        setItems((prev) => [...prev, { key: nextKey(), role: 'assistant', content: data?.response ?? '' }])
      } catch (err: any) {
        const status: number | undefined = err?.response?.status
        let fallback = 'Something went wrong. Please try again.'
        if (err?.code === 'ECONNABORTED') fallback = 'The AI took too long to respond. Please try again.'
        else if (!err?.response) fallback = 'Could not reach the server. Check your connection and try again.'
        setItems((prev) => [
          ...prev,
          { key: nextKey(), role: 'error', content: getApiError(err, fallback), failedMessage: message, status },
        ])
      } finally {
        setSending(false)
      }
    },
    [pathname, sending],
  )

  const clearConversation = async () => {
    if (clearing || sending) return
    if (!window.confirm('Clear the whole Copilot conversation? This cannot be undone.')) return
    setClearing(true)
    try {
      await copilotApi.clearHistory()
      setItems([])
      setHistoryState('loaded')
    } catch (err) {
      setItems((prev) => [
        ...prev,
        { key: nextKey(), role: 'error', content: getApiError(err, 'Could not clear the conversation.') },
      ])
    } finally {
      setClearing(false)
    }
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send(input)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setIsMinimized(true)
    }
  }

  if (!isOpen) {
    return (
      <button
        ref={launcherRef}
        type="button"
        onClick={() => setIsOpen(true)}
        className="fixed bottom-20 right-6 z-50 w-12 h-12 rounded-full bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-lg hover:shadow-xl transition-all duration-200 flex items-center justify-center hover:scale-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-900"
        title="AI Copilot"
        aria-label="Open AI Copilot"
      >
        <Sparkles className="w-5 h-5" aria-hidden="true" />
      </button>
    )
  }

  if (isMinimized) {
    return (
      <div className="fixed bottom-20 right-6 z-50 w-72 bg-white dark:bg-gray-800 rounded-t-xl shadow-2xl border border-zinc-200 dark:border-gray-700">
        <div className="flex items-center justify-between px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-t-xl">
          <button
            type="button"
            onClick={() => setIsMinimized(false)}
            className="flex items-center gap-2 text-white text-sm font-medium focus:outline-none focus-visible:underline"
            aria-label="Expand AI Copilot"
          >
            <Sparkles className="w-4 h-4" aria-hidden="true" />
            AI Copilot
          </button>
          <button
            type="button"
            onClick={() => { setIsOpen(false); setIsMinimized(false) }}
            className="text-white/80 hover:text-white"
            aria-label="Close AI Copilot"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    )
  }

  const historyLoading = historyState === 'loading'
  const showEmpty = !historyLoading && items.length === 0 && !sending

  return (
    <div
      role="dialog"
      aria-label="AI Copilot"
      className="fixed bottom-20 right-6 z-50 w-96 max-w-[calc(100vw-2rem)] h-[500px] max-h-[calc(100vh-7rem)] bg-white dark:bg-gray-800 rounded-xl shadow-2xl border border-zinc-200 dark:border-gray-700 flex flex-col overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-indigo-500 to-purple-600">
        <div className="flex items-center gap-2 text-white font-medium min-w-0">
          <Sparkles className="w-5 h-5 shrink-0" aria-hidden="true" />
          AI Copilot
          <span className="text-xs bg-white/20 px-2 py-0.5 rounded-full truncate">{context}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={clearConversation}
            disabled={clearing || sending || items.length === 0}
            className="text-white/80 hover:text-white p-1 disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="Clear conversation"
            title="Clear conversation"
          >
            <Trash2 className="w-4 h-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={minimize}
            className="text-white/80 hover:text-white p-1"
            aria-label="Minimize AI Copilot"
            title="Minimize"
          >
            <Minimize2 className="w-4 h-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setIsOpen(false)}
            className="text-white/80 hover:text-white p-1"
            aria-label="Close AI Copilot"
            title="Close"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-white dark:bg-gray-800" aria-live="polite" aria-busy={sending || historyLoading}>
        {historyLoading && (
          <div className="flex items-center justify-center gap-2 text-xs text-zinc-500 dark:text-gray-400 mt-8" role="status">
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            Loading conversation…
          </div>
        )}
        {historyState === 'error' && (
          <p className="text-center text-xs text-zinc-500 dark:text-gray-400">
            Couldn&apos;t load earlier messages. You can still ask a question.
          </p>
        )}
        {showEmpty && (
          <div className="text-center text-zinc-500 dark:text-gray-400 text-sm mt-6">
            <Sparkles className="w-8 h-8 mx-auto mb-3 text-indigo-400" aria-hidden="true" />
            <p className="font-medium text-zinc-700 dark:text-gray-200">How can I help?</p>
            <p className="text-xs mt-1">Ask about campaigns, leads, email strategy, or anything about your data.</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2" aria-label="Suggested questions">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void send(s)}
                  disabled={sending}
                  className="text-xs px-3 py-1.5 rounded-full border border-indigo-200 dark:border-gray-600 bg-indigo-50 dark:bg-gray-700 text-indigo-700 dark:text-indigo-200 hover:bg-indigo-100 dark:hover:bg-gray-600 transition-colors text-left disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {items.map((msg) => {
          if (msg.role === 'error') {
            return (
              <div key={msg.key} className="flex justify-start">
                <div
                  role="alert"
                  className="max-w-[85%] px-3 py-2 rounded-lg text-sm bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200"
                >
                  <div className="flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
                    <div className="space-y-1">
                      <p>{msg.content}</p>
                      {msg.status === 503 && (
                        <p className="text-xs text-red-700 dark:text-red-300">
                          {NOT_CONFIGURED_HINT}
                          {isAdmin && (
                            <>
                              {' '}
                              <Link
                                href="/dashboard/settings"
                                onClick={minimize}
                                className="font-medium underline underline-offset-2 text-red-800 dark:text-red-100"
                              >
                                Open Settings
                              </Link>
                            </>
                          )}
                        </p>
                      )}
                      {msg.failedMessage && (
                        <button
                          type="button"
                          onClick={() => void send(msg.failedMessage as string, { retryKey: msg.key })}
                          disabled={sending}
                          className="inline-flex items-center gap-1 text-xs font-medium text-red-700 dark:text-red-200 hover:underline disabled:opacity-50"
                          aria-label="Retry sending message"
                        >
                          <RotateCcw className="w-3 h-3" aria-hidden="true" />
                          Retry
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )
          }
          return (
            <div key={msg.key} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] px-3 py-2 rounded-lg text-sm ${
                  msg.role === 'user'
                    ? 'bg-indigo-500 text-white whitespace-pre-wrap break-words'
                    : 'bg-zinc-100 dark:bg-gray-700 text-zinc-800 dark:text-gray-100'
                }`}
              >
                {msg.role === 'assistant' ? (
                  <FormattedReply content={msg.content} onNavigate={minimize} />
                ) : (
                  msg.content
                )}
              </div>
            </div>
          )
        })}
        {sending && (
          <div className="flex justify-start" role="status" aria-label="Copilot is thinking">
            <div className="bg-zinc-100 dark:bg-gray-700 px-4 py-2 rounded-lg">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-zinc-400 dark:bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-zinc-400 dark:bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-zinc-400 dark:bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-zinc-200 dark:border-gray-700 p-3 bg-white dark:bg-gray-800">
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask anything… (Shift+Enter for a new line)"
            aria-label="Message AI Copilot"
            rows={1}
            maxLength={4000}
            className="flex-1 resize-none max-h-32 px-3 py-2 text-sm rounded-lg border border-zinc-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-zinc-900 dark:text-gray-100 placeholder:text-zinc-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-60"
            disabled={sending || historyLoading}
          />
          <button
            type="button"
            onClick={() => void send(input)}
            disabled={sending || historyLoading || !input.trim()}
            className="px-3 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            aria-label="Send message"
          >
            <Send className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  )
}
