/**
 * Public site details — support email, legal entity, payments availability.
 *
 * Served by `GET /api/v1/public/site-info` (no auth) from backend config, so the
 * contact page, legal pages, footer and billing buttons never hardcode a value
 * that changes when the company is registered or Stripe is switched on.
 * Contract: Plan_Launch_Readiness_6.md. Server-safe (no React); the hook lives in
 * `use-site-info.ts` for client components.
 */
export interface SiteInfo {
  support_email: string
  privacy_email: string
  /** Empty until the company is registered — render a neutral line, never a placeholder. */
  legal_entity_name: string
  legal_address: string
  legal_jurisdiction: string
  terms_version: string
  /** False while Stripe isn't configured: paid upgrades/top-ups must not be offered as buttons that fail. */
  payments_enabled: boolean
}

export const SITE_INFO_FALLBACK: SiteInfo = {
  support_email: 'info@neuraleads.ai',
  privacy_email: 'info@neuraleads.ai',
  legal_entity_name: '',
  legal_address: '',
  legal_jurisdiction: '',
  terms_version: '',
  payments_enabled: false,
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export async function fetchSiteInfo(): Promise<SiteInfo> {
  // Server components: revalidate every 5 minutes; client calls go through the hook.
  const res = await fetch(`${API_URL}/public/site-info`, { next: { revalidate: 300 } })
  if (!res.ok) throw new Error(`site-info ${res.status}`)
  return { ...SITE_INFO_FALLBACK, ...(await res.json()) }
}
