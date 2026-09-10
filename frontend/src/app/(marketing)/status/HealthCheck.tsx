'use client'

import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'

type State = 'checking' | 'operational' | 'degraded' | 'unreachable'

const SLOW_MS = 2000
const TIMEOUT_MS = 8000

const PRESENTATION: Record<State, { label: string; dot: string; text: string; ring: string }> = {
  checking: {
    label: 'Checking…',
    dot: 'bg-slate-400',
    text: 'text-slate-300',
    ring: 'border-white/10',
  },
  operational: {
    label: 'Operational',
    dot: 'bg-emerald-400',
    text: 'text-emerald-300',
    ring: 'border-emerald-400/30',
  },
  degraded: {
    label: 'Reachable but slow',
    dot: 'bg-amber-400',
    text: 'text-amber-300',
    ring: 'border-amber-400/30',
  },
  unreachable: {
    label: 'Not reachable',
    dot: 'bg-rose-400',
    text: 'text-rose-300',
    ring: 'border-rose-400/30',
  },
}

/**
 * Live reachability check, run from the visitor's own browser against the public
 * health endpoint. Deliberately not a fabricated uptime dashboard: it reports
 * only what it can actually observe, right now, from where the visitor is.
 */
export default function HealthCheck() {
  const [state, setState] = useState<State>('checking')
  const [latency, setLatency] = useState<number | null>(null)
  const [checkedAt, setCheckedAt] = useState<string | null>(null)

  const check = useCallback(async () => {
    setState('checking')
    setLatency(null)

    const started = performance.now()
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)

    try {
      const res = await fetch(`/health?t=${Date.now()}`, {
        cache: 'no-store',
        signal: controller.signal,
      })
      const elapsed = Math.round(performance.now() - started)
      setLatency(elapsed)
      if (!res.ok) {
        setState('unreachable')
      } else {
        setState(elapsed > SLOW_MS ? 'degraded' : 'operational')
      }
    } catch {
      setState('unreachable')
    } finally {
      clearTimeout(timer)
      setCheckedAt(
        new Date().toLocaleTimeString(undefined, {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
      )
    }
  }, [])

  useEffect(() => {
    check()
    const id = setInterval(check, 60_000)
    return () => clearInterval(id)
  }, [check])

  const p = PRESENTATION[state]

  return (
    <div className={`rounded-2xl border ${p.ring} bg-white/[0.03] p-6 md:p-8`}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="relative flex h-3 w-3" aria-hidden="true">
            {state === 'operational' && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:hidden" />
            )}
            <span className={`relative inline-flex h-3 w-3 rounded-full ${p.dot}`} />
          </span>
          <div>
            <p className={`text-xl font-semibold ${p.text}`} role="status" aria-live="polite">
              {p.label}
            </p>
            <p className="text-slate-500 text-sm">
              {checkedAt ? `Checked at ${checkedAt}` : 'Checking now'}
              {latency !== null ? ` · responded in ${latency} ms` : ''}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={check}
          disabled={state === 'checking'}
          className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw
            className={`h-4 w-4 ${state === 'checking' ? 'animate-spin motion-reduce:animate-none' : ''}`}
            aria-hidden="true"
          />
          Check again
        </button>
      </div>

      {state === 'unreachable' && (
        <p className="mt-5 border-t border-white/10 pt-5 text-sm leading-relaxed text-slate-400">
          The check could not reach the platform from this browser. That can mean the service is
          down, but it can equally mean your own network, VPN or firewall is blocking the request.
          Trying from another network is the quickest way to tell the two apart.
        </p>
      )}
    </div>
  )
}
