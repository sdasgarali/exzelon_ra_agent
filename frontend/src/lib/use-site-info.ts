'use client'

import { useQuery } from '@tanstack/react-query'
import { fetchSiteInfo, SITE_INFO_FALLBACK, type SiteInfo } from './site-info'

/** Site details for client components; safe defaults (payments off) while loading or on error. */
export function useSiteInfo(): SiteInfo {
  const { data } = useQuery<SiteInfo>({
    queryKey: ['site-info'],
    queryFn: fetchSiteInfo,
    staleTime: 10 * 60_000,
    retry: 1,
  })
  return data ?? SITE_INFO_FALLBACK
}
