'use client'

import { useQuery } from '@tanstack/react-query'
import { billingApi } from '@/lib/api'

/**
 * What the current tenant's plan includes.
 *
 * Presentation only — `api/deps/features.py` is the enforcement, and this must never
 * be treated as a security boundary. Its job is to stop the UI offering things that
 * will 402, and to stop background pollers hitting gated endpoints on every page load
 * (which fills the console with errors that read like bugs).
 *
 * Defaults to "has everything" while loading and for super admins, who are not on a
 * plan. Failing open here is right: a brief flash of a nav item the server will refuse
 * is a far better failure than hiding features a paying customer is entitled to
 * because a request was slow.
 */
export function usePlanFeatures() {
  const { data, isLoading } = useQuery({
    queryKey: ['billing-usage'],
    queryFn: billingApi.usage,
    staleTime: 5 * 60_000,
    retry: false,
  })

  const metered: boolean = data?.metered ?? false
  const features: string[] | null = metered ? data?.features ?? null : null

  return {
    isLoading,
    /**
     * True once the plan is known. Callers that START something on the back of a
     * feature — a poller, a websocket — must wait for this, because `has()` fails
     * OPEN while loading and would fire one gated request before the answer arrives.
     * Callers that merely RENDER can use `has()` directly; a flash is harmless.
     */
    ready: !isLoading,
    /** True for super admins and while loading — see the fail-open note above. */
    has: (feature: string) => (features === null ? true : features.includes(feature)),
    features,
    plan: data?.plan ?? null,
  }
}
