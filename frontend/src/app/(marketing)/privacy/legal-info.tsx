/**
 * Shared helpers for the config-driven legal pages (/privacy, /terms).
 *
 * Legal details (entity, address, jurisdiction, contact emails) come from
 * `GET /public/site-info` so nothing is hardcoded and no placeholder text is ever
 * shown: unset values are omitted and the operator reads as "NeuraLeads".
 * Not a route — Next only routes `page.tsx`.
 */
import { fetchSiteInfo, SITE_INFO_FALLBACK, type SiteInfo } from '@/lib/site-info'

export async function loadSiteInfo(): Promise<SiteInfo> {
  try {
    return await fetchSiteInfo()
  } catch {
    // Backend unreachable at build/render time: neutral defaults, never placeholders.
    return SITE_INFO_FALLBACK
  }
}

/** The legal operator's name, or the product name while no entity is configured. */
export function operatorName(info: SiteInfo): string {
  return info.legal_entity_name.trim() || 'NeuraLeads'
}

export function MailLink({ email }: { email: string }) {
  const addr = email.trim() || SITE_INFO_FALLBACK.support_email
  return <a href={`mailto:${addr}`}>{addr}</a>
}
