'use client'

import type { DealUserRef } from '@/types/api'

/**
 * Claim tag. Three states:
 *  - Claimed → green filled initials of the claimer (hover → full name).
 *  - Assigned but not claimed → blue filled initials of the owner (hover → "Assigned: name").
 *  - Neither (open pool) → red filled "Unclaimed" pill.
 */
export function ClaimTag({ claimedBy, owner, size = 'sm' }: { claimedBy?: DealUserRef | null; owner?: DealUserRef | null; size?: 'sm' | 'md' }) {
  const dim = size === 'md' ? 'w-7 h-7 text-xs' : 'w-6 h-6 text-[10px]'
  if (claimedBy) {
    return (
      <span title={`Claimed by ${claimedBy.name || ''}`}
        className={`inline-flex items-center justify-center rounded-full font-bold bg-green-600 text-white cursor-default ${dim}`}>
        {claimedBy.initials || '?'}
      </span>
    )
  }
  if (owner) {
    return (
      <span title={`Assigned to ${owner.name || ''}`}
        className={`inline-flex items-center justify-center rounded-full font-bold bg-blue-600 text-white cursor-default ${dim}`}>
        {owner.initials || '?'}
      </span>
    )
  }
  return (
    <span className={`inline-flex items-center rounded-full font-semibold bg-red-600 text-white ${
      size === 'md' ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
    }`}>
      Unclaimed
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
