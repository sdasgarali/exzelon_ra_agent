'use client'

import { Eye, X } from 'lucide-react'
import { useAuthStore } from '@/lib/store'

export function ImpersonationBanner() {
  const { impersonation, stopImpersonation } = useAuthStore()

  if (!impersonation) return null

  const handleExit = () => {
    stopImpersonation()
    window.location.reload()
  }

  const planLabel = impersonation.tenantPlan.charAt(0).toUpperCase() + impersonation.tenantPlan.slice(1)

  return (
    <div className="sticky top-0 z-40 bg-amber-500 text-amber-950 px-4 py-2 flex items-center justify-between text-sm font-medium">
      <div className="flex items-center gap-2">
        <Eye className="w-4 h-4" />
        <span>
          Viewing as: <strong>{impersonation.tenantName}</strong>
        </span>
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-600/30">
          {planLabel}
        </span>
      </div>
      <button
        onClick={handleExit}
        className="flex items-center gap-1 px-3 py-1 rounded bg-amber-600/30 hover:bg-amber-600/50 transition-colors"
      >
        <X className="w-3.5 h-3.5" />
        Exit Impersonation
      </button>
    </div>
  )
}
