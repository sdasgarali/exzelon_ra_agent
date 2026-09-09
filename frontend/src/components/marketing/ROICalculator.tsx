'use client'

import { useMemo, useState } from 'react'

/**
 * Cost comparison. Homepage-only, so it carries the light ground.
 *
 * The competitor baseline is an explicit, stated assumption (per-seat pricing at
 * ~$79/seat/month plus volume add-ons) rather than an unsourced claim — the note
 * under the result says so, because a savings figure with a hidden model is just
 * a number we made up.
 */

const SEAT_PRICE = 79
const VOLUME_BLOCK = 20 // per 500 emails/day on typical per-seat tools

export default function ROICalculator() {
  const [teamSize, setTeamSize] = useState(3)
  const [emailsPerDay, setEmailsPerDay] = useState(500)

  const { theirCost, ourCost, monthly, yearly, pct } = useMemo(() => {
    const theirs = teamSize * SEAT_PRICE + Math.ceil(emailsPerDay / 500) * VOLUME_BLOCK
    const ours = emailsPerDay <= 500 ? 49 : emailsPerDay <= 2500 ? 99 : 199
    const m = Math.max(0, theirs - ours)
    return {
      theirCost: theirs,
      ourCost: ours,
      monthly: m,
      yearly: m * 12,
      pct: theirs > 0 ? Math.round((m / theirs) * 100) : 0,
    }
  }, [teamSize, emailsPerDay])

  return (
    <section className="border-t border-paper-200 bg-paper px-6 py-20 lg:py-24">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-14 lg:grid-cols-[0.9fr_1.1fr] lg:gap-20">
        <div>
          <h2 className="text-balance text-[clamp(1.9rem,3.6vw,2.9rem)] font-extrabold leading-[1.08] tracking-[-0.03em] text-ink">
            Seats are where it gets expensive.
          </h2>
          <p className="mt-5 max-w-[46ch] text-[17px] leading-relaxed text-ink-700">
            Per-seat outreach tools charge again every time you add a recruiter. Move the
            sliders to your team and see what the difference looks like over a year.
          </p>
        </div>

        <div>
          <div className="grid gap-8 sm:grid-cols-2">
            <Slider
              label="Team size"
              value={`${teamSize} ${teamSize === 1 ? 'seat' : 'seats'}`}
              min={1}
              max={20}
              step={1}
              raw={teamSize}
              onChange={setTeamSize}
            />
            <Slider
              label="Emails per day"
              value={emailsPerDay.toLocaleString()}
              min={100}
              max={10000}
              step={100}
              raw={emailsPerDay}
              onChange={setEmailsPerDay}
            />
          </div>

          <dl className="mt-10 border-t border-paper-200">
            <Row label="Typical per-seat tool" value={`$${theirCost.toLocaleString()}/mo`} />
            <Row label="NeuraLeads" value={`$${ourCost}/mo`} accent />
          </dl>

          <div className="mt-8 flex flex-wrap items-baseline gap-x-4 gap-y-1 border-t-2 border-ink pt-6">
            <span
              className="text-[clamp(2.25rem,5vw,3.5rem)] font-extrabold leading-none tracking-[-0.035em] tabular-nums text-ink"
              aria-live="polite"
            >
              ${yearly.toLocaleString()}
            </span>
            <span className="text-[15px] font-medium text-ink-700">
              a year back{pct > 0 ? `, ${pct}% less` : ''}
            </span>
          </div>

          <p className="mt-4 max-w-[58ch] text-[12px] leading-relaxed text-ink-500">
            Assumes a competitor at ${SEAT_PRICE}/seat/month plus ${VOLUME_BLOCK} per 500
            emails/day of volume — a common shape, not a specific vendor&rsquo;s quote. Your own
            provider API costs are additional on either side and billed at cost here.
          </p>
        </div>
      </div>
    </section>
  )
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  raw,
  onChange,
}: {
  label: string
  value: string
  min: number
  max: number
  step: number
  raw: number
  onChange: (n: number) => void
}) {
  return (
    <div>
      <label className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="text-[14px] font-medium text-ink-700">{label}</span>
        <span className="text-[14px] font-bold tabular-nums text-ink">{value}</span>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={raw}
          onChange={(e) => onChange(+e.target.value)}
          className="mt-3 w-full basis-full accent-brand"
          aria-label={label}
        />
      </label>
    </div>
  )
}

function Row({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex items-center justify-between border-b border-paper-200 py-3.5">
      <dt className="text-[14px] text-ink-700">{label}</dt>
      <dd
        className={`text-[17px] font-bold tabular-nums ${accent ? 'text-brand' : 'text-ink'}`}
      >
        {value}
      </dd>
    </div>
  )
}
