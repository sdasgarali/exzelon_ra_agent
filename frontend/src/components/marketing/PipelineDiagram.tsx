'use client'

import { useEffect, useRef, useState } from 'react'

/**
 * The funnel, drawn to scale.
 *
 * Every stage below is a real stage in the pipeline (`services/pipelines/`) and
 * every capability figure is real config: 10 job-source adapters, 3-layer dedup,
 * 7 contact providers, 7 validation providers, the 10 ordered checks in
 * `services/send_gate.py`, and DAILY_SEND_LIMIT = 30/mailbox/day.
 *
 * The volumes are an illustrative overnight run, labelled as such in the UI —
 * they are not measured customer results. The bar widths are computed from those
 * numbers rather than eyeballed, so the taper is honest: the shape you see IS
 * the ratio.
 */

export interface Stage {
  /** Stage name as it appears in the pipeline. */
  label: string
  /** What the stage does, in one clause. */
  detail: string
  /** Records leaving this stage. */
  kept: number
  /** Records this stage removed (0 for stages that only add). */
  dropped?: number
  /** Shown right-aligned — the real capability behind the stage. */
  meta: string
}

const STAGES: Stage[] = [
  {
    label: 'Sourced',
    detail: '10 job boards, queried in parallel',
    kept: 4000,
    meta: '10 adapters',
  },
  {
    label: 'Deduplicated',
    detail: 'external job ID → employer LinkedIn → company + title + state',
    kept: 2760,
    dropped: 1240,
    meta: '3 layers',
  },
  {
    label: 'Company gate',
    detail: 'over headcount ceiling, excluded industry, or confidential employer',
    kept: 812,
    dropped: 1948,
    meta: '22 target industries',
  },
  {
    label: 'Validated',
    detail: 'contacts discovered, then every address verified before it can queue',
    kept: 470,
    dropped: 1430,
    meta: '7 providers',
  },
  {
    label: 'Cleared to send',
    detail: 'suppression, cooldown, per-company cap, fatigue, domain throttle',
    kept: 30,
    dropped: 440,
    meta: '10 ordered checks',
  },
]

const MAX = STAGES[0].kept
const MIN_BAR = 1.6 // floor % so the final stage stays visible

function pct(n: number) {
  return Math.max(MIN_BAR, (n / MAX) * 100)
}

interface PipelineDiagramProps {
  /** 'brand' = sits on the indigo drench. 'paper' = sits on the light ground. */
  tone?: 'brand' | 'paper'
  className?: string
}

export default function PipelineDiagram({ tone = 'brand', className = '' }: PipelineDiagramProps) {
  const onBrand = tone === 'brand'
  const ref = useRef<HTMLDivElement>(null)
  // Bars render at full width by default and only animate when we know motion is
  // wanted — a reveal must never be the thing that makes content visible.
  const [run, setRun] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setRun(true)
          io.disconnect()
        }
      },
      { threshold: 0.25 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  const track = onBrand ? 'bg-white/12' : 'bg-paper-200'
  const fill = onBrand ? 'bg-white' : 'bg-brand'
  const labelC = onBrand ? 'text-white' : 'text-ink'
  const detailC = onBrand ? 'text-white/75' : 'text-ink-500'
  const metaC = onBrand ? 'text-white/70' : 'text-ink-300'
  const numC = onBrand ? 'text-white' : 'text-ink'
  const dropC = onBrand ? 'text-[#FFB3A0]' : 'text-signal'
  const rule = onBrand ? 'border-white/12' : 'border-paper-200'

  return (
    <div ref={ref} className={className}>
      <ol className="space-y-0">
        {STAGES.map((s, i) => {
          const width = pct(s.kept)
          const isLast = i === STAGES.length - 1
          return (
            <li
              key={s.label}
              className={`border-t ${rule} py-4 first:border-t-0 first:pt-0`}
            >
              <div className="flex items-baseline justify-between gap-4">
                <span className={`text-[13px] font-semibold tracking-tight ${labelC}`}>
                  {s.label}
                </span>
                <span className={`shrink-0 text-[11px] tabular-nums ${metaC}`}>{s.meta}</span>
              </div>

              {/* Bar — width is the real ratio of records surviving this stage */}
              <div className="relative mt-2.5 h-7 w-full">
                <div className={`absolute inset-0 rounded-[3px] ${track}`} />
                <div
                  className={`absolute inset-y-0 left-0 origin-left rounded-[3px] ${fill}`}
                  style={{
                    width: `${width}%`,
                    animation: run
                      ? `pipe-grow 900ms cubic-bezier(0.16,1,0.3,1) ${i * 110}ms both`
                      : undefined,
                  }}
                />
                {/* Count sits inside the bar while it still fits, otherwise beside it */}
                {width > 16 ? (
                  <span
                    className={`absolute inset-y-0 left-0 flex items-center pl-3 text-[13px] font-bold tabular-nums ${
                      onBrand ? 'text-brand-700' : 'text-white'
                    }`}
                  >
                    {s.kept.toLocaleString()}
                  </span>
                ) : (
                  <span
                    className={`absolute inset-y-0 flex items-center text-[13px] font-bold tabular-nums ${numC}`}
                    style={{ left: `calc(${width}% + 0.5rem)` }}
                  >
                    {s.kept.toLocaleString()}
                    {isLast && <span className={`ml-1.5 font-medium ${metaC}`}>/ mailbox / day</span>}
                  </span>
                )}
              </div>

              <div className="mt-2 flex items-start justify-between gap-4">
                <p className={`max-w-[46ch] text-[12px] leading-snug ${detailC}`}>{s.detail}</p>
                {s.dropped ? (
                  <span className={`shrink-0 text-[12px] font-medium tabular-nums ${dropC}`}>
                    −{s.dropped.toLocaleString()}
                  </span>
                ) : null}
              </div>
            </li>
          )
        })}
      </ol>

      <p className={`mt-5 border-t ${rule} pt-3 text-[11px] leading-relaxed ${metaC}`}>
        Stage names, provider counts and the 30/mailbox/day ceiling are the product&rsquo;s real
        configuration. Volumes are illustrative and vary by ICP.
      </p>
    </div>
  )
}
