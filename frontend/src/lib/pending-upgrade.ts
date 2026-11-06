/**
 * The plan a visitor picked on /pricing, carried through signup → email verification
 * → login so they land on the upgrade instead of a plain dashboard.
 *
 * Kept in localStorage because verification happens in a new tab (the email link).
 * Everything is best-effort: storage can be blocked or empty, and the flow still works
 * without it — the user just lands on the dashboard as before.
 */

export type UpgradePlan = 'pro' | 'max'

export interface PendingUpgrade {
  plan: UpgradePlan
  annual: boolean
  savedAt: number
}

const KEY = 'nl_pending_upgrade'
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000

/** Only the self-serve paid tiers. Anything else (free, custom, junk) is ignored. */
export function parseUpgradePlan(value: string | null | undefined): UpgradePlan | null {
  const v = (value || '').toLowerCase().trim()
  return v === 'pro' || v === 'max' ? v : null
}

export function parseAnnual(value: string | null | undefined): boolean {
  return (value || '').toLowerCase() === 'annual'
}

/** Read `?plan=` / `?billing=` from a query string. */
export function upgradeFromSearch(search: string): { plan: UpgradePlan; annual: boolean } | null {
  const params = new URLSearchParams(search)
  const plan = parseUpgradePlan(params.get('plan'))
  if (!plan) return null
  return { plan, annual: parseAnnual(params.get('billing')) }
}

export function savePendingUpgrade(plan: UpgradePlan, annual: boolean): void {
  try {
    const value: PendingUpgrade = { plan, annual, savedAt: Date.now() }
    window.localStorage.setItem(KEY, JSON.stringify(value))
  } catch {
    // Storage blocked (private mode, site data cleared) — the flow degrades gracefully.
  }
}

export function readPendingUpgrade(now: number = Date.now()): PendingUpgrade | null {
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<PendingUpgrade>
    const plan = parseUpgradePlan(parsed.plan)
    if (!plan || typeof parsed.savedAt !== 'number' || now - parsed.savedAt > MAX_AGE_MS) {
      window.localStorage.removeItem(KEY)
      return null
    }
    return { plan, annual: Boolean(parsed.annual), savedAt: parsed.savedAt }
  } catch {
    return null
  }
}

export function clearPendingUpgrade(): void {
  try {
    window.localStorage.removeItem(KEY)
  } catch {
    // ignore
  }
}

/** Where the plan picker lives, with the choice preselected. */
export function upgradeUrl(plan: UpgradePlan, annual: boolean): string {
  return `/dashboard/billing?upgrade=${plan}&billing=${annual ? 'annual' : 'monthly'}#plans`
}
