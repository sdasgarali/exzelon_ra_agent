'use client'

import type { DealUserRef } from '@/types/api'

/**
 * Claim tag: red filled "Unclaimed" pill, OR green filled initials avatar of the
 * claimer (hover → full name). Reused on board cards, list rows, and the detail view.
 */
export function ClaimTag({ claimedBy, size = 'sm' }: { claimedBy?: DealUserRef | null; size?: 'sm' | 'md' }) {
  if (!claimedBy) {
    return (
      <span
        className={`inline-flex items-center rounded-full font-semibold bg-red-600 text-white ${
          size === 'md' ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
        }`}
      >
        Unclaimed
      </span>
    )
  }
  const dim = size === 'md' ? 'w-7 h-7 text-xs' : 'w-6 h-6 text-[10px]'
  return (
    <span
      title={claimedBy.name || 'Claimed'}
      className={`inline-flex items-center justify-center rounded-full font-bold bg-green-600 text-white cursor-default ${dim}`}
    >
      {claimedBy.initials || '?'}
    </span>
  )
}

/**
 * Live age badge: yellow filled "N Days" (days since the deal was created).
 */
export function AgeBadge({ days, size = 'sm' }: { days?: number | null; size?: 'sm' | 'md' }) {
  const n = typeof days === 'number' ? days : 0
  return (
    <span
      title="Days since created"
      className={`inline-flex items-center rounded-full font-semibold bg-yellow-400 text-yellow-950 ${
        size === 'md' ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
      }`}
    >
      {n} {n === 1 ? 'Day' : 'Days'}
    </span>
  )
}

/**
 * Assigned-owner chip (distinct from claim): small gray initials avatar with hover name.
 */
export function OwnerChip({ owner }: { owner?: DealUserRef | null }) {
  if (!owner) return null
  return (
    <span
      title={`Assigned: ${owner.name || ''}`}
      className="inline-flex items-center justify-center w-6 h-6 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200 cursor-default"
    >
      {owner.initials || '?'}
    </span>
  )
}
