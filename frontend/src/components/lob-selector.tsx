'use client'

import { useEffect, useState, useRef } from 'react'
import { useLobStore, type LOB } from '@/lib/lob-store'
import { useAuthStore } from '@/lib/store'
import { lobApi } from '@/lib/api'
import {
  Briefcase,
  HeartPulse,
  Code,
  Brain,
  Megaphone,
  Settings,
  ChevronDown,
  Check,
  Layers,
} from 'lucide-react'

const LOB_ICONS: Record<string, React.ElementType> = {
  briefcase: Briefcase,
  'heart-pulse': HeartPulse,
  code: Code,
  brain: Brain,
  megaphone: Megaphone,
  settings: Settings,
}

function getLobIcon(iconName: string | null): React.ElementType {
  if (!iconName) return Layers
  return LOB_ICONS[iconName] || Layers
}

interface LobSelectorProps {
  collapsed?: boolean
}

export function LobSelector({ collapsed = false }: LobSelectorProps) {
  const { lobs, activeLobId, setLobs, setActiveLob } = useLobStore()
  // Subscribe to impersonation so the selector re-evaluates when a super_admin
  // switches tenant (or back to "All Tenants").
  const impersonation = useAuthStore((s) => s.impersonation)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadLobs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [impersonation])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  async function loadLobs() {
    setLoading(true)
    try {
      const data = await lobApi.list()
      setLobs(data)

      // Decide the active LOB now that tenant context is known.
      const superAdmin = useAuthStore.getState().isSuperAdmin()
      const impersonating = !!useAuthStore.getState().impersonation
      if (superAdmin && !impersonating) {
        // "All Tenants" view → default to "All Lines of Business" (no LOB filter).
        setActiveLob(null)
      } else {
        // Keep the current selection if it still belongs to this tenant's LOBs;
        // otherwise fall back to the default LOB.
        const current = useLobStore.getState().activeLobId
        const stillValid = current !== null && data.some((l: LOB) => l.lob_id === current)
        if (!stillValid && data.length > 0) {
          const defaultLob = data.find((l: LOB) => l.is_default) || data[0]
          setActiveLob(defaultLob.lob_id)
        }
      }
    } catch {
      // LOB endpoint may not exist on older backends — graceful fallback
    } finally {
      setLoading(false)
    }
  }

  const activeLob = lobs.find(l => l.lob_id === activeLobId) || null

  if (loading || lobs.length === 0) return null

  // Don't show selector if there's only 1 LOB
  if (lobs.length === 1) return null

  const Icon = getLobIcon(activeLob?.icon || null)

  if (collapsed) {
    return (
      <div className="px-2 mb-3">
        <button
          onClick={() => setOpen(!open)}
          className="w-full flex items-center justify-center p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          title={activeLob?.name || 'All Lines of Business'}
        >
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: activeLob?.color || '#6366F1' }}
          />
        </button>
      </div>
    )
  }

  return (
    <div ref={ref} className="relative px-3 mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-sm"
      >
        <div
          className="w-2.5 h-2.5 rounded-full flex-shrink-0"
          style={{ backgroundColor: activeLob?.color || '#6366F1' }}
        />
        <Icon className="w-4 h-4 flex-shrink-0 text-gray-500 dark:text-gray-400" />
        <span className="truncate flex-1 text-left font-medium text-gray-700 dark:text-gray-200">
          {activeLob?.name || 'All Lines of Business'}
        </span>
        <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute left-3 right-3 top-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg z-50 py-1 max-h-60 overflow-y-auto">
          {/* All LOBs option */}
          <button
            onClick={() => {
              setActiveLob(null)
              setOpen(false)
            }}
            className={`w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
              activeLobId === null ? 'bg-blue-50 dark:bg-blue-900/20' : ''
            }`}
          >
            <Layers className="w-4 h-4 text-gray-400" />
            <span className="flex-1 text-left text-gray-600 dark:text-gray-300">All Lines of Business</span>
            {activeLobId === null && <Check className="w-4 h-4 text-blue-500" />}
          </button>

          <div className="border-t border-gray-100 dark:border-gray-700 my-1" />

          {lobs.filter(l => l.status === 'active').map(lob => {
            const LobIcon = getLobIcon(lob.icon)
            const isActive = activeLobId === lob.lob_id
            return (
              <button
                key={lob.lob_id}
                onClick={() => {
                  setActiveLob(lob.lob_id)
                  setOpen(false)
                }}
                className={`w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
                  isActive ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                }`}
              >
                <div
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: lob.color || '#6366F1' }}
                />
                <LobIcon className="w-4 h-4 flex-shrink-0 text-gray-500 dark:text-gray-400" />
                <span className="flex-1 text-left text-gray-700 dark:text-gray-200">
                  {lob.name}
                </span>
                {lob.is_default && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-gray-100 dark:bg-gray-600 text-gray-500 dark:text-gray-300 rounded">
                    Default
                  </span>
                )}
                {isActive && <Check className="w-4 h-4 text-blue-500" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

/** Small LOB badge for list items (leads, contacts, campaigns) */
export function LobBadge({ lobId, className = '' }: { lobId: number | null; className?: string }) {
  const { lobs } = useLobStore()

  if (lobId === null) return null

  const lob = lobs.find(l => l.lob_id === lobId)
  if (!lob) return null

  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-medium ${className}`}
      style={{
        backgroundColor: `${lob.color}15`,
        color: lob.color || '#6366F1',
        border: `1px solid ${lob.color}30`,
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: lob.color || '#6366F1' }}
      />
      {lob.name}
    </span>
  )
}
