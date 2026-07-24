'use client'

import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/store'

/**
 * A super-admin who isn't impersonating a tenant has no tenant context, so the
 * backend blocks tenant-scoped actions (pipeline runs, sends, validation, enrich)
 * with 400 "Select a tenant first". This hook flags that state so the UI can
 * disable the trigger buttons + explain, instead of letting the user hit the error.
 */
export function useNeedsTenantSelection() {
  const user = useAuthStore((s) => s.user)
  const impersonation = useAuthStore((s) => s.impersonation)
  const needsTenantSelection = user?.role === 'super_admin' && !impersonation
  const runDisabledTitle = needsTenantSelection
    ? 'Select a tenant first — impersonate a tenant (Tenants page) to run this.'
    : undefined
  return { needsTenantSelection, runDisabledTitle }
}

/** Amber banner shown when a super-admin must select a tenant before acting. */
export function SelectTenantBanner({
  action = 'run these',
  className = '',
}: {
  action?: string
  className?: string
}) {
  const router = useRouter()
  const { needsTenantSelection } = useNeedsTenantSelection()
  if (!needsTenantSelection) return null
  return (
    <div className={`bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-lg mb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 ${className}`}>
      <span className="text-sm">
        You&rsquo;re signed in as a super-admin with <strong>no tenant selected</strong>. These actions run under a specific tenant (using that tenant&rsquo;s API keys &amp; settings), so select a tenant to {action}.
      </span>
      <button
        onClick={() => router.push('/dashboard/tenants')}
        className="shrink-0 text-sm font-medium bg-amber-600 hover:bg-amber-700 text-white rounded-lg px-3 py-1.5"
      >
        Select a tenant
      </button>
    </div>
  )
}
