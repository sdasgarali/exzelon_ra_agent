'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, X } from 'lucide-react'
import { settingsApi } from '@/lib/api'
import { useAuthStore } from '@/lib/store'

/**
 * Amber prompt shown on the dashboard while the workspace has no postal address.
 *
 * CAN-SPAM requires the sender's physical postal address in every outreach email,
 * and the send gate now refuses outreach until one is set (Plan_Launch_Readiness_6
 * L1). Only workspace admins can set it (Settings → Business Rules → Company
 * Profile), so only they see this. Dismissal lasts for the browser session.
 */

const DISMISS_KEY = 'postal-address-banner-dismissed'
const ADMIN_ROLES = ['admin', 'super_admin']

function readDismissed(): boolean {
  try {
    return typeof window !== 'undefined' && window.sessionStorage.getItem(DISMISS_KEY) === '1'
  } catch {
    return false
  }
}

export function PostalAddressBanner() {
  const { user } = useAuthStore()
  const role = user?.base_role || user?.role || ''
  const isAdmin = ADMIN_ROLES.includes(role)
  const [dismissed, setDismissed] = useState(true)

  // Read after mount so server and first client render agree.
  useEffect(() => {
    setDismissed(readDismissed())
  }, [])

  const { data } = useQuery<{ company_address?: string | null }>({
    queryKey: ['company-profile'],
    queryFn: settingsApi.getCompanyProfile,
    enabled: isAdmin,
    staleTime: 5 * 60_000,
    retry: false,
  })

  // Hidden while loading, on error (e.g. no workspace selected), or once set.
  if (!isAdmin || dismissed || !data) return null
  if ((data.company_address || '').trim()) return null

  const dismiss = () => {
    setDismissed(true)
    try {
      window.sessionStorage.setItem(DISMISS_KEY, '1')
    } catch {
      /* storage unavailable — dismissal just won't persist */
    }
  }

  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100"
    >
      <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
      <div className="flex-1 text-sm">
        <p className="font-semibold">Add your company&apos;s postal address before sending</p>
        <p className="mt-1">
          The law (CAN-SPAM) requires a physical postal address in every outreach email, so
          campaigns and outreach won&apos;t send until one is set.{' '}
          <Link href="/dashboard/settings?tab=business" className="font-medium underline">
            Add it in Settings → Business Rules → Company Profile
          </Link>
        </p>
      </div>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss postal address reminder"
        className="rounded p-1 hover:bg-amber-100 dark:hover:bg-amber-900/50"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  )
}

export default PostalAddressBanner
