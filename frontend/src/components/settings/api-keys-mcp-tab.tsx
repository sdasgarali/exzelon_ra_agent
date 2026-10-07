'use client'

import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as Dialog from '@radix-ui/react-dialog'
import * as Tabs from '@radix-ui/react-tabs'
import {
  AlertTriangle,
  Check,
  Copy,
  KeyRound,
  Loader2,
  Plug,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react'
import {
  getApiError,
  integrationsApi,
  type ApiKeyCreated,
  type ApiKeyCreatePayload,
  type ApiKeyRecord,
  type ApiKeyScope,
} from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { useToast } from '@/components/toast'
import {
  EXPIRY_OPTIONS,
  SCOPE_OPTIONS,
  buildMcpSnippets,
  getMcpEndpoints,
  parseApiDate,
} from './mcp-snippets'

// ─── Helpers ──────────────────────────────────────────────────────────────

/** Map an API error to a message an admin can act on. */
function describeApiKeyError(err: unknown, fallback: string): string {
  const status = (err as any)?.response?.status
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) {
    return 'You do not have permission to manage API keys. Only tenant admins (or a super admin viewing a tenant) can create, list or revoke keys.'
  }
  if (status === 404) return 'That API key no longer exists. It may already have been revoked.'
  return getApiError(err, fallback)
}

function isNonRetryable(err: unknown): boolean {
  const status = (err as any)?.response?.status
  return typeof status === 'number' && status >= 400 && status < 500
}

function formatDate(value: string | null | undefined, withTime = false): string {
  const d = parseApiDate(value)
  if (!d) return '—'
  return withTime
    ? d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

/** Copy text to the clipboard, falling back to execCommand on non-secure origins. */
async function copyText(text: string): Promise<boolean> {
  try {
    // navigator.clipboard is only exposed on secure origins (https / localhost).
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // fall through to legacy path
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

const SCOPE_BADGE: Record<string, string> = {
  read: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  write: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
  admin: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
}

function ScopeBadge({ scope }: { scope: string }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        SCOPE_BADGE[scope] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200'
      }`}
    >
      {scope}
    </span>
  )
}

function CopyButton({
  text,
  label,
  className = '',
}: {
  text: string
  /** Accessible name, e.g. "Copy Claude Code snippet". */
  label: string
  className?: string
}) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current)
  }, [])

  const onCopy = async () => {
    const ok = await copyText(text)
    setState(ok ? 'copied' : 'failed')
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => setState('idle'), 2000)
  }

  return (
    <button
      type="button"
      onClick={onCopy}
      aria-label={label}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100 dark:hover:bg-gray-600 ${className}`}
    >
      {state === 'copied' ? <Check className="w-4 h-4 text-green-600" aria-hidden /> : <Copy className="w-4 h-4" aria-hidden />}
      <span aria-live="polite">{state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy failed' : 'Copy'}</span>
    </button>
  )
}

// ─── Create dialog ────────────────────────────────────────────────────────

interface CreateKeyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onUseInSnippets: (key: string) => void
}

function CreateKeyDialog({ open, onOpenChange, onUseInSnippets }: CreateKeyDialogProps) {
  const queryClient = useQueryClient()
  const ids = useId()
  const [name, setName] = useState('')
  const [scope, setScope] = useState<ApiKeyScope>('read')
  const [expiry, setExpiry] = useState('never')
  const [formError, setFormError] = useState('')
  // The raw key lives only in this component's memory while the dialog is open.
  const [created, setCreated] = useState<ApiKeyCreated | null>(null)
  const [usedInSnippets, setUsedInSnippets] = useState(false)

  const reset = useCallback(() => {
    setName('')
    setScope('read')
    setExpiry('never')
    setFormError('')
    setCreated(null)
    setUsedInSnippets(false)
  }, [])

  const mutation = useMutation({
    mutationFn: (payload: ApiKeyCreatePayload) => integrationsApi.createApiKey(payload),
    onSuccess: (result) => {
      setCreated(result)
      queryClient.invalidateQueries({ queryKey: ['integrations', 'api-keys'] })
    },
    onError: (err) => setFormError(describeApiKeyError(err, 'Failed to create the API key.')),
  })

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      if (mutation.isPending) return
      reset()
      mutation.reset()
    }
    onOpenChange(next)
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setFormError('Give the key a name so you can recognise it later.')
      return
    }
    if (trimmed.length > 255) {
      setFormError('Name must be 255 characters or fewer.')
      return
    }
    setFormError('')
    const days = EXPIRY_OPTIONS.find((o) => o.value === expiry)?.days ?? null
    mutation.mutate({ name: trimmed, scopes: [scope], expires_in_days: days })
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content
          className="fixed z-50 left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[calc(100%-2rem)] max-w-lg max-h-[90vh] overflow-y-auto rounded-lg bg-white dark:bg-gray-800 shadow-xl focus:outline-none"
          onInteractOutside={(e) => {
            // Never lose a freshly shown key to a stray click outside the dialog.
            if (created || mutation.isPending) e.preventDefault()
          }}
        >
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <Dialog.Title className="text-lg font-semibold text-gray-900 dark:text-white">
              {created ? 'Your new API key' : 'Create API key'}
            </Dialog.Title>
            <Dialog.Close
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 disabled:opacity-50"
              aria-label="Close"
              disabled={mutation.isPending}
            >
              <X className="w-5 h-5" aria-hidden />
            </Dialog.Close>
          </div>

          {!created ? (
            <form onSubmit={onSubmit} className="px-6 py-4 space-y-5" noValidate>
              <Dialog.Description className="text-sm text-gray-600 dark:text-gray-400">
                API keys let AI tools such as Claude or Cursor act on this workspace through the NeuraLeads MCP connector.
                Give each tool its own key so you can revoke it independently.
              </Dialog.Description>

              <div>
                <label htmlFor={`${ids}-name`} className="label">Name</label>
                <input
                  id={`${ids}-name`}
                  type="text"
                  className="input"
                  placeholder="e.g. Claude Desktop – Sarah's laptop"
                  value={name}
                  maxLength={255}
                  autoComplete="off"
                  required
                  aria-invalid={!!formError && !name.trim()}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

              <fieldset>
                <legend className="label">Access level</legend>
                <div className="space-y-2">
                  {SCOPE_OPTIONS.map((opt) => (
                    <label
                      key={opt.value}
                      className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                        scope === opt.value
                          ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                          : 'border-gray-200 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-700/50'
                      }`}
                    >
                      <input
                        type="radio"
                        name={`${ids}-scope`}
                        value={opt.value}
                        checked={scope === opt.value}
                        onChange={() => setScope(opt.value)}
                        className="mt-1"
                      />
                      <span>
                        <span className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-gray-100">
                          {opt.label}
                          {opt.value === 'read' && (
                            <span className="text-xs font-normal text-gray-500 dark:text-gray-400">(recommended)</span>
                          )}
                        </span>
                        <span className="block text-xs text-gray-600 dark:text-gray-400 mt-0.5">{opt.description}</span>
                      </span>
                    </label>
                  ))}
                </div>
                {scope === 'admin' && (
                  <div
                    role="alert"
                    className="mt-3 flex items-start gap-2 px-3 py-2 rounded-lg text-sm bg-red-50 border border-red-200 text-red-800 dark:bg-red-900/20 dark:border-red-800 dark:text-red-200"
                  >
                    <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
                    <span>
                      An admin key can do everything you can, including deleting data. Only use it with tools you fully trust,
                      and prefer a short expiry.
                    </span>
                  </div>
                )}
              </fieldset>

              <div>
                <label htmlFor={`${ids}-expiry`} className="label">Expires</label>
                <select
                  id={`${ids}-expiry`}
                  className="input"
                  value={expiry}
                  onChange={(e) => setExpiry(e.target.value)}
                >
                  {EXPIRY_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>

              {formError && (
                <div role="alert" className="px-3 py-2 rounded-lg text-sm bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/20 dark:text-red-200 dark:border-red-800">
                  {formError}
                </div>
              )}

              <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-3 pt-2">
                <Dialog.Close asChild>
                  <button type="button" className="btn-secondary" disabled={mutation.isPending}>Cancel</button>
                </Dialog.Close>
                <button type="submit" className="btn-primary inline-flex items-center justify-center gap-2 disabled:opacity-60" disabled={mutation.isPending}>
                  {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" aria-hidden />}
                  {mutation.isPending ? 'Creating…' : 'Create key'}
                </button>
              </div>
            </form>
          ) : (
            <div className="px-6 py-4 space-y-4">
              <Dialog.Description asChild>
                <div
                  role="alert"
                  className="flex items-start gap-2 px-3 py-2 rounded-lg text-sm bg-amber-50 border border-amber-200 text-amber-900 dark:bg-amber-900/20 dark:border-amber-800 dark:text-amber-100"
                >
                  <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
                  <span>
                    <strong>Copy this key now. You won&apos;t see it again.</strong> NeuraLeads stores only a hash of it.
                    If you lose it, revoke it and create a new one.
                  </span>
                </div>
              </Dialog.Description>

              <div>
                <label htmlFor={`${ids}-secret`} className="label">API key for “{created.name}”</label>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    id={`${ids}-secret`}
                    type="text"
                    readOnly
                    value={created.key}
                    className="input font-mono text-xs"
                    spellCheck={false}
                    autoComplete="off"
                    onFocus={(e) => e.currentTarget.select()}
                    data-testid="new-api-key"
                  />
                  <CopyButton text={created.key} label="Copy API key" className="shrink-0 justify-center" />
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
                  <span>Access:</span>
                  {(created.scopes || []).map((s) => <ScopeBadge key={s} scope={s} />)}
                  <span className="ml-2">Expires: {created.expires_at ? formatDate(created.expires_at) : 'Never'}</span>
                </div>
              </div>

              <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="btn-secondary disabled:opacity-60"
                  disabled={usedInSnippets}
                  onClick={() => {
                    onUseInSnippets(created.key)
                    setUsedInSnippets(true)
                  }}
                >
                  {usedInSnippets ? 'Filled into setup snippets' : 'Fill into setup snippets below'}
                </button>
                <Dialog.Close asChild>
                  <button type="button" className="btn-primary">I&apos;ve saved my key</button>
                </Dialog.Close>
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

// ─── Revoke dialog ────────────────────────────────────────────────────────

function RevokeKeyDialog({
  target,
  onClose,
}: {
  target: ApiKeyRecord | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: (id: number) => integrationsApi.revokeApiKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'api-keys'] })
      toast('success', 'API key revoked', target ? `"${target.name}" can no longer access NeuraLeads.` : undefined)
      setError('')
      onClose()
    },
    onError: (err) => setError(describeApiKeyError(err, 'Failed to revoke the API key.')),
  })

  return (
    <Dialog.Root
      open={!!target}
      onOpenChange={(next) => {
        if (!next && !mutation.isPending) {
          setError('')
          onClose()
        }
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed z-50 left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[calc(100%-2rem)] max-w-md rounded-lg bg-white dark:bg-gray-800 shadow-xl p-6 focus:outline-none">
          <div className="flex items-start gap-4">
            <div className="p-2 rounded-full bg-red-100 dark:bg-red-900/30">
              <AlertTriangle className="w-5 h-5 text-red-600" aria-hidden />
            </div>
            <div className="flex-1 min-w-0">
              <Dialog.Title className="text-lg font-semibold text-gray-900 dark:text-white">Revoke API key?</Dialog.Title>
              <Dialog.Description className="mt-2 text-sm text-gray-600 dark:text-gray-400 break-words">
                Any AI tool or integration using <strong>{target?.name}</strong> ({target?.key_prefix}…) will stop working
                immediately. This cannot be undone.
              </Dialog.Description>
            </div>
          </div>
          {error && (
            <div role="alert" className="mt-4 px-3 py-2 rounded-lg text-sm bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/20 dark:text-red-200 dark:border-red-800">
              {error}
            </div>
          )}
          <div className="mt-6 flex justify-end gap-3">
            <Dialog.Close asChild>
              <button type="button" className="btn-secondary" disabled={mutation.isPending}>Cancel</button>
            </Dialog.Close>
            <button
              type="button"
              onClick={() => target && mutation.mutate(target.key_id)}
              disabled={mutation.isPending}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-red-600 hover:bg-red-700 text-white disabled:opacity-50 inline-flex items-center gap-2"
            >
              {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" aria-hidden />}
              {mutation.isPending ? 'Revoking…' : 'Revoke key'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

// ─── Connect your AI tool ─────────────────────────────────────────────────

function ConnectSnippets({ freshKey, onForgetKey }: { freshKey: string | null; onForgetKey: () => void }) {
  const endpoints = useMemo(() => getMcpEndpoints(process.env.NEXT_PUBLIC_API_URL), [])
  const [fillKey, setFillKey] = useState(false)
  const toggleId = useId()

  // A new key arriving via "Fill into setup snippets" turns substitution on.
  useEffect(() => {
    setFillKey(!!freshKey)
  }, [freshKey])

  const snippets = useMemo(
    () => buildMcpSnippets(endpoints, fillKey && freshKey ? freshKey : null),
    [endpoints, fillKey, freshKey],
  )

  return (
    <section className="card" aria-labelledby="mcp-connect-heading">
      <h3 id="mcp-connect-heading" className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-1 flex items-center gap-2">
        <Plug className="w-5 h-5 text-primary-600" aria-hidden />
        Connect your AI tool
      </h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
        Hosted MCP endpoint:{' '}
        <code className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-100 text-xs break-all">
          {endpoints.mcpUrl}
        </code>
        . Pick your tool, copy the snippet and replace <code className="text-xs">&lt;YOUR_API_KEY&gt;</code> with a key from above.
      </p>

      {freshKey && (
        <div className="mb-4 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 px-3 py-2 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-900 dark:bg-blue-900/20 dark:border-blue-800 dark:text-blue-100">
          <label htmlFor={toggleId} className="flex items-center gap-2 cursor-pointer">
            <input id={toggleId} type="checkbox" checked={fillKey} onChange={(e) => setFillKey(e.target.checked)} />
            Fill in the key you just created (…{freshKey.slice(-4)})
          </label>
          <button type="button" onClick={onForgetKey} className="text-xs underline underline-offset-2 sm:ml-auto">
            Remove it from this page
          </button>
        </div>
      )}

      <Tabs.Root defaultValue={snippets[0].id}>
        <Tabs.List
          aria-label="AI tools"
          className="flex gap-1 overflow-x-auto border-b border-gray-200 dark:border-gray-700 mb-4"
        >
          {snippets.map((s) => (
            <Tabs.Trigger
              key={s.id}
              value={s.id}
              className="px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 data-[state=active]:border-primary-500 data-[state=active]:text-primary-600 dark:data-[state=active]:text-primary-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded-t"
            >
              {s.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        {snippets.map((s) => (
          <Tabs.Content key={s.id} value={s.id} className="focus:outline-none">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 mb-2">
              <div className="text-sm text-gray-600 dark:text-gray-400">
                <span className="font-medium text-gray-800 dark:text-gray-200">{s.location}</span>
                <span className="block text-xs mt-0.5">{s.hint}</span>
              </div>
              <CopyButton text={s.code} label={`Copy ${s.label} snippet`} className="shrink-0 self-start" />
            </div>
            <pre
              className="text-xs leading-relaxed font-mono bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto whitespace-pre"
              data-testid={`snippet-${s.id}`}
              tabIndex={0}
              aria-label={`${s.label} configuration`}
            >
              <code>{s.code}</code>
            </pre>
          </Tabs.Content>
        ))}
      </Tabs.Root>

      <div className="mt-4 flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400">
        <ShieldCheck className="w-4 h-4 mt-0.5 shrink-0 text-green-600" aria-hidden />
        <p>
          Safety: actions that send email, launch campaigns or delete data only run when the AI passes{' '}
          <code className="text-xs px-1 rounded bg-gray-100 dark:bg-gray-700">confirm: true</code>, so your AI tool will ask you first.
          A <strong>read</strong> key can never change anything.
        </p>
      </div>
    </section>
  )
}

// ─── Tab ──────────────────────────────────────────────────────────────────

export interface ApiKeysMcpTabProps {
  /** When true, creating and revoking keys is disabled (list and snippets stay visible). */
  readOnly?: boolean
}

export default function ApiKeysMcpTab({ readOnly = false }: ApiKeysMcpTabProps) {
  const { user, impersonation } = useAuthStore()
  const isSuperAdmin = user?.role === 'super_admin'
  // Keys are tenant-scoped: a super admin must be viewing a tenant first.
  const needsTenant = isSuperAdmin && !impersonation
  const tenantScope = impersonation?.tenantId ?? user?.tenant_id ?? null

  const [createOpen, setCreateOpen] = useState(false)
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyRecord | null>(null)
  // Held in memory only (never persisted) so the snippets can embed it on request.
  const [freshKey, setFreshKey] = useState<string | null>(null)

  const keysQuery = useQuery({
    queryKey: ['integrations', 'api-keys', tenantScope],
    queryFn: () => integrationsApi.listApiKeys(),
    enabled: !needsTenant,
    retry: (count, err) => !isNonRetryable(err) && count < 2,
  })

  const keys = keysQuery.data ?? []
  const now = Date.now()

  return (
    <div className="space-y-6">
      <section className="card" aria-labelledby="api-keys-heading">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
          <div>
            <h3 id="api-keys-heading" className="text-lg font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
              <KeyRound className="w-5 h-5 text-primary-600" aria-hidden />
              API Keys
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Keys authenticate AI tools and scripts against this workspace. Each key acts with your permissions, limited by its access level.
            </p>
          </div>
          {!readOnly && !needsTenant && (
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="btn-primary inline-flex items-center justify-center gap-2 shrink-0"
            >
              <Plus className="w-4 h-4" aria-hidden />
              Create API key
            </button>
          )}
        </div>

        {readOnly && (
          <div className="mb-4 bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded-lg text-sm dark:bg-yellow-900/20 dark:border-yellow-800 dark:text-yellow-200">
            You have read-only access to this tab. Contact a super admin to request edit access.
          </div>
        )}

        {needsTenant ? (
          <div className="px-4 py-3 rounded-lg text-sm bg-blue-50 border border-blue-200 text-blue-800 dark:bg-blue-900/20 dark:border-blue-800 dark:text-blue-200">
            API keys belong to a tenant. Open <strong>Tenant Management</strong> and view a tenant to create or revoke its keys.
          </div>
        ) : keysQuery.isLoading ? (
          <div className="flex items-center gap-2 py-8 justify-center text-sm text-gray-500 dark:text-gray-400" role="status">
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden /> Loading API keys…
          </div>
        ) : keysQuery.isError ? (
          <div role="alert" className="flex flex-col sm:flex-row sm:items-center gap-3 px-4 py-3 rounded-lg text-sm bg-red-50 border border-red-200 text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-200">
            <span className="flex-1">{describeApiKeyError(keysQuery.error, 'Failed to load API keys.')}</span>
            {!isNonRetryable(keysQuery.error) && (
              <button type="button" className="btn-secondary text-sm" onClick={() => keysQuery.refetch()}>Retry</button>
            )}
          </div>
        ) : keys.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <KeyRound className="w-10 h-10 text-gray-300 dark:text-gray-600 mb-3" aria-hidden />
            <h4 className="text-base font-medium text-gray-900 dark:text-gray-100 mb-1">No API keys yet</h4>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md">
              Create a key to connect Claude, Cursor or another MCP-compatible AI tool to NeuraLeads.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto -mx-6 px-6">
            <table className="min-w-full text-sm">
              <caption className="sr-only">Active API keys</caption>
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  <th scope="col" className="py-2 pr-4 font-medium">Name</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Key</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Access</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Created</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Last used</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Expires</th>
                  <th scope="col" className="py-2 font-medium"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {keys.map((k) => {
                  const expiresAt = parseApiDate(k.expires_at)
                  const expired = !!expiresAt && expiresAt.getTime() < now
                  return (
                    <tr key={k.key_id} className="align-middle">
                      <td className="py-3 pr-4 font-medium text-gray-900 dark:text-gray-100 max-w-[14rem] truncate" title={k.name}>{k.name}</td>
                      <td className="py-3 pr-4">
                        <code className="font-mono text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200">
                          {k.key_prefix}…
                        </code>
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex flex-wrap gap-1">
                          {(k.scopes?.length ? k.scopes : ['read']).map((s) => <ScopeBadge key={s} scope={s} />)}
                        </div>
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap text-gray-600 dark:text-gray-300">{formatDate(k.created_at)}</td>
                      <td className="py-3 pr-4 whitespace-nowrap text-gray-600 dark:text-gray-300">
                        {k.last_used_at ? formatDate(k.last_used_at, true) : 'Never'}
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap">
                        {expired ? (
                          <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200">
                            Expired {formatDate(k.expires_at)}
                          </span>
                        ) : (
                          <span className="text-gray-600 dark:text-gray-300">{expiresAt ? formatDate(k.expires_at) : 'Never'}</span>
                        )}
                      </td>
                      <td className="py-3 text-right">
                        {!readOnly && (
                          <button
                            type="button"
                            onClick={() => setRevokeTarget(k)}
                            aria-label={`Revoke API key ${k.name}`}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg text-red-700 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 dark:text-red-300 dark:hover:bg-red-900/30"
                          >
                            <Trash2 className="w-3.5 h-3.5" aria-hidden />
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <ConnectSnippets freshKey={freshKey} onForgetKey={() => setFreshKey(null)} />

      {!readOnly && (
        <>
          <CreateKeyDialog
            open={createOpen}
            onOpenChange={setCreateOpen}
            onUseInSnippets={(key) => setFreshKey(key)}
          />
          <RevokeKeyDialog target={revokeTarget} onClose={() => setRevokeTarget(null)} />
        </>
      )}
    </div>
  )
}
