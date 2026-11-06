'use client'

import Link from 'next/link'
import { Sparkles } from 'lucide-react'
import { usePlanFeatures } from '@/hooks/use-plan-features'
import { useAuthStore } from '@/lib/store'

/**
 * Always-visible "Upgrade" entry point for workspace admins on Free or Pro.
 *
 * Before this, the only way to upgrade was the Billing page's plan panel, which a new
 * customer had to find on their own. Hidden for super admins (no plan of their own),
 * non-admins (checkout is admin-only server-side), Max (nothing self-serve above it)
 * and Custom.
 */
export function UpgradeButton({ variant = 'topbar', collapsed = false }: {
  variant?: 'topbar' | 'sidebar'
  collapsed?: boolean
}) {
  const { user } = useAuthStore()
  const { plan, isLoading } = usePlanFeatures()
  const role = user?.base_role || user?.role
  if (isLoading || role !== 'admin' || !plan?.upgrade_to) return null

  if (variant === 'sidebar') {
    return (
      <Link
        href="/dashboard/billing#plans"
        title={collapsed ? 'Upgrade plan' : undefined}
        aria-label={collapsed ? 'Upgrade plan' : undefined}
        className={`flex min-h-[44px] items-center gap-2 rounded-lg bg-primary-600 text-sm font-semibold text-white hover:bg-primary-700 ${
          collapsed ? 'justify-center px-2' : 'px-3'
        }`}
      >
        <Sparkles className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
        {!collapsed && <span>Upgrade plan</span>}
      </Link>
    )
  }

  return (
    <Link
      href="/dashboard/billing#plans"
      className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-primary-700"
    >
      <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
      Upgrade
    </Link>
  )
}
