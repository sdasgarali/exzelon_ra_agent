/**
 * Lead-sourcing run size: the "How many jobs?" field, its hints, and the
 * "what happened" message. A run fetches at most that many jobs from all job
 * APIs together and charges 1 credit only for each new lead it saves.
 */

export type StoppedReason =
  | 'max_leads_reached'
  | 'credits_exhausted'
  | 'fetch_limit_reached'
  | null
  | undefined

export interface LeadSourcingRunSummary {
  records_success?: number
  requested_max_leads?: number | null
  stopped_reason?: StoppedReason
  leads_not_saved?: number
  fetch_limit?: number | null
  jobs_fetched?: number | null
}

/** Field label, e.g. "How many jobs? (min 10 · max 5,000)". */
export function jobsFieldLabel(min: number, max: number): string {
  return `How many jobs? (min ${min.toLocaleString()} · max ${max.toLocaleString()})`
}

/**
 * Parse the "How many jobs?" field. Required: a whole number from `min` to `max`.
 */
export function parseMaxLeads(
  raw: string,
  min: number,
  max: number,
): { value: number | null; error: string | null } {
  const text = raw.trim()
  const range = `Enter a number from ${min.toLocaleString()} to ${max.toLocaleString()}.`
  if (text === '' || !/^\d+$/.test(text)) return { value: null, error: range }
  const value = Number(text)
  if (value < min || value > max) return { value: null, error: range }
  return { value, error: null }
}

/** Hint under the field: what the run fetches and how it's charged. */
export function fetchHint(affordableLeads: number | null | undefined): string {
  const charge = 'We fetch at most this many jobs. You pay 1 credit only for each new lead saved — duplicates and filtered jobs are free.'
  if (affordableLeads === null || affordableLeads === undefined) return charge
  if (affordableLeads <= 0) return 'You are out of credits. Top up to run lead sourcing.'
  return `${charge} Your credits cover ${affordableLeads.toLocaleString()} new lead${affordableLeads === 1 ? '' : 's'}.`
}

/** The workspace default shown on the Pipelines page. */
export function defaultLeadsLabel(defaultMaxLeads: number | null | undefined): string {
  if (!defaultMaxLeads) return 'No default set'
  return `Default: ${defaultMaxLeads.toLocaleString()} job${defaultMaxLeads === 1 ? '' : 's'} per run`
}

/**
 * What the saved default should become when a run starts: the run's number when
 * "use this number for every run" is ticked, otherwise cleared. `undefined` means
 * the saved default already matches and needs no write.
 */
export function nextDefaultMaxLeads(
  saveAsDefault: boolean,
  maxLeads: number | null,
  currentDefault: number | null,
): number | null | undefined {
  const desired = saveAsDefault ? maxLeads : null
  return desired === (currentDefault ?? null) ? undefined : desired
}

const n = (v: number) => v.toLocaleString()
const plural = (v: number, word: string) => `${n(v)} ${word}${v === 1 ? '' : 's'}`

/** One-line account of a capped run, or null for a run without a number. */
export function stopMessage(run: LeadSourcingRunSummary): string | null {
  const saved = run.records_success ?? 0
  const fetched = run.jobs_fetched ?? null
  if (run.stopped_reason === 'credits_exhausted') {
    return `Stopped: out of credits — ${plural(saved, 'new lead')} saved (${plural(saved, 'credit')}). Top up to continue.`
  }
  if (run.stopped_reason === 'fetch_limit_reached' && fetched !== null) {
    const free = Math.max(0, fetched - saved)
    return `Fetched ${plural(fetched, 'job')} → ${plural(saved, 'new lead')} (${plural(saved, 'credit')}).`
      + (free ? ` ${n(free)} ${free === 1 ? 'was a duplicate or filtered out' : 'were duplicates or filtered out'} — not charged.` : '')
  }
  if (run.stopped_reason === 'max_leads_reached') {
    return `Saved ${plural(saved, 'new lead')} — the ${n(run.requested_max_leads ?? saved)} you asked for (${plural(saved, 'credit')}).`
  }
  return null
}
