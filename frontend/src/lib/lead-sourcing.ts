/** Lead-sourcing run cap: input validation and the "why did it stop" message. */

export type StoppedReason = 'max_leads_reached' | 'credits_exhausted' | null | undefined

export interface LeadSourcingRunSummary {
  records_success?: number
  requested_max_leads?: number | null
  stopped_reason?: StoppedReason
  leads_not_saved?: number
}

/**
 * Parse the "How many leads?" field. Blank means "use the workspace default"
 * (returns `null`); anything else must be a whole number from 1 to `limit`.
 */
export function parseMaxLeads(
  raw: string,
  limit: number,
): { value: number | null; error: string | null } {
  const text = raw.trim()
  if (text === '') return { value: null, error: null }
  if (!/^\d+$/.test(text)) return { value: null, error: 'Enter a whole number.' }
  const value = Number(text)
  if (value < 1) return { value: null, error: 'Enter at least 1.' }
  if (value > limit) return { value: null, error: `At most ${limit.toLocaleString()} per run.` }
  return { value, error: null }
}

/** Hint under the field: how many leads the balance pays for, or null when unmetered. */
export function affordableHint(affordableLeads: number | null | undefined): string | null {
  if (affordableLeads === null || affordableLeads === undefined) return null
  if (affordableLeads <= 0) return 'You are out of credits. Top up to run lead sourcing.'
  const n = affordableLeads.toLocaleString()
  return `Your credits cover about ${n} lead${affordableLeads === 1 ? '' : 's'} (1 credit each). The run stops when they run out.`
}

/** One-line explanation for a run that ended early, or null if it ran to the end. */
export function stopMessage(run: LeadSourcingRunSummary): string | null {
  const saved = run.records_success ?? 0
  if (run.stopped_reason === 'credits_exhausted') {
    const of = run.requested_max_leads ? ` of ${run.requested_max_leads.toLocaleString()}` : ''
    return `Stopped: out of credits — ${saved.toLocaleString()}${of} leads saved. Top up to continue.`
  }
  if (run.stopped_reason === 'max_leads_reached') {
    return `Reached your limit of ${(run.requested_max_leads ?? saved).toLocaleString()} leads.`
  }
  return null
}
