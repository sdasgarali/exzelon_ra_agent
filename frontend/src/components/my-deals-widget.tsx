'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { dealsApi } from '@/lib/api'
import { ClaimTag, AgeBadge } from '@/components/deal-badges'
import type { Deal } from '@/types/api'
import { Briefcase, ArrowRight } from 'lucide-react'

const fmt = (v: number) => (v >= 1000 ? `$${(v / 1000).toFixed(1)}K` : `$${v.toFixed(0)}`)

/**
 * "My Deals / My Queue" — a BDM/Recruiter's claimed + assigned deals, shown on the
 * dashboard landing page. Self-fetches `GET /deals?mine=true`.
 */
export function MyDealsWidget() {
  const [deals, setDeals] = useState<Deal[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    dealsApi.list({ mine: true, page_size: 50 })
      .then((res) => setDeals(res?.items || []))
      .catch(() => setDeals([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
          <Briefcase className="w-5 h-5 text-primary-600" /> My Queue
          <span className="text-sm font-normal text-gray-400">({deals.length})</span>
        </h2>
        <Link href="/dashboard/deals" className="text-sm text-primary-600 hover:underline flex items-center gap-1">
          All deals <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {loading ? (
        <p className="text-sm text-gray-400 py-6 text-center">Loading…</p>
      ) : deals.length === 0 ? (
        <div className="text-center py-8">
          <p className="text-sm text-gray-500">No deals claimed or assigned to you yet.</p>
          <Link href="/dashboard/deals?claimed_by=unclaimed" className="text-sm text-primary-600 hover:underline mt-1 inline-block">
            View the unclaimed queue →
          </Link>
        </div>
      ) : (
        <div className="divide-y divide-gray-100 dark:divide-gray-700/50">
          {deals.slice(0, 8).map((d) => (
            <Link key={d.deal_id} href={`/dashboard/deals?deal=${d.deal_id}`} className="flex items-center gap-3 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-700/40 -mx-2 px-2 rounded">
              <ClaimTag claimedBy={d.claimed_by} owner={d.owner} />
              <AgeBadge days={d.age_days} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{d.name}</p>
                <p className="text-xs text-gray-400 truncate">{d.stage_name}{d.client_name ? ` · ${d.client_name}` : ''}</p>
              </div>
              <span className="text-sm font-semibold text-gray-700 dark:text-gray-200 whitespace-nowrap">{fmt(d.value || 0)}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
