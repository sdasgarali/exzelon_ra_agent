'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi, pipelinesApi } from '@/lib/api'
import { useToast } from '@/components/toast'
import {
  Building,
  Users,
  Mail,
  CheckCircle,
  TrendingUp,
  TrendingDown,
} from 'lucide-react'

function StatCard({
  title,
  value,
  icon: Icon,
  trend,
  trendLabel,
}: {
  title: string
  value: string | number
  icon: any
  trend?: 'up' | 'down'
  trendLabel?: string
}) {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
          {trend && trendLabel && (
            <div className="flex items-center gap-1 mt-2">
              {trend === 'up' ? (
                <TrendingUp className="w-4 h-4 text-green-500" />
              ) : (
                <TrendingDown className="w-4 h-4 text-red-500" />
              )}
              <span
                className={`text-sm ${
                  trend === 'up' ? 'text-green-600' : 'text-red-600'
                }`}
              >
                {trendLabel}
              </span>
            </div>
          )}
        </div>
        <div className="w-12 h-12 rounded-lg bg-primary-100 flex items-center justify-center">
          <Icon className="w-6 h-6 text-primary-600" />
        </div>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [quickLoading, setQuickLoading] = useState<string | null>(null)

  const { data: kpis, isLoading } = useQuery({
    queryKey: ['dashboard-kpis'],
    queryFn: () => dashboardApi.kpis(),
  })

  const { data: trends } = useQuery({
    queryKey: ['dashboard-trends'],
    queryFn: () => dashboardApi.trends(30),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading dashboard...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
        <p className="text-gray-600 mt-1">Overview of your cold-email automation</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Companies Identified"
          value={kpis?.total_companies_identified || 0}
          icon={Building}
        />
        <StatCard
          title="Total Contacts"
          value={kpis?.total_contacts || 0}
          icon={Users}
        />
        <StatCard
          title="Valid Emails"
          value={kpis?.total_valid_emails || 0}
          icon={CheckCircle}
        />
        <StatCard
          title="Emails Sent"
          value={kpis?.emails_sent || 0}
          icon={Mail}
        />
      </div>

      {/* Performance Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Bounce Rate</h3>
          <div className="flex items-end gap-2">
            <span className="text-4xl font-bold text-primary-600">
              {kpis?.bounce_rate_percent || 0}%
            </span>
            <span className="text-sm text-gray-500 mb-1">Target: &lt;2%</span>
          </div>
          <div className="mt-4 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full ${
                (kpis?.bounce_rate_percent || 0) <= 2
                  ? 'bg-green-500'
                  : 'bg-red-500'
              }`}
              style={{ width: `${Math.min(kpis?.bounce_rate_percent || 0, 100)}%` }}
            />
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Reply Rate</h3>
          <div className="flex items-end gap-2">
            <span className="text-4xl font-bold text-primary-600">
              {kpis?.reply_rate_percent || 0}%
            </span>
          </div>
          <div className="mt-4 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-primary-500"
              style={{ width: `${Math.min(kpis?.reply_rate_percent || 0, 100)}%` }}
            />
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Total Leads</h3>
          <div className="flex items-end gap-2">
            <span className="text-4xl font-bold text-primary-600">
              {kpis?.total_leads || 0}
            </span>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Quick Actions</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <button
            className="btn-primary"
            disabled={quickLoading !== null}
            onClick={async () => {
              setQuickLoading('sourcing')
              try {
                await pipelinesApi.runLeadSourcing(['linkedin', 'indeed'])
                toast('success', 'Lead sourcing pipeline started')
                router.push('/dashboard/pipelines')
              } catch { toast('error', 'Failed to start lead sourcing') }
              setQuickLoading(null)
            }}
          >
            {quickLoading === 'sourcing' ? 'Starting...' : 'Run Lead Sourcing'}
          </button>
          <button
            className="btn-secondary"
            disabled={quickLoading !== null}
            onClick={async () => {
              setQuickLoading('enrich')
              try {
                await pipelinesApi.runContactEnrichment()
                toast('success', 'Contact enrichment pipeline started')
                router.push('/dashboard/pipelines')
              } catch { toast('error', 'Failed to start contact enrichment') }
              setQuickLoading(null)
            }}
          >
            {quickLoading === 'enrich' ? 'Starting...' : 'Enrich Contacts'}
          </button>
          <button
            className="btn-secondary"
            disabled={quickLoading !== null}
            onClick={async () => {
              setQuickLoading('validate')
              try {
                await pipelinesApi.runEmailValidation()
                toast('success', 'Email validation pipeline started')
                router.push('/dashboard/pipelines')
              } catch { toast('error', 'Failed to start email validation') }
              setQuickLoading(null)
            }}
          >
            {quickLoading === 'validate' ? 'Starting...' : 'Validate Emails'}
          </button>
          <button
            className="btn-secondary"
            disabled={quickLoading !== null}
            onClick={async () => {
              setQuickLoading('outreach')
              try {
                await pipelinesApi.runOutreach('mailmerge', true)
                toast('success', 'Mailmerge export pipeline started')
                router.push('/dashboard/pipelines')
              } catch { toast('error', 'Failed to start mailmerge export') }
              setQuickLoading(null)
            }}
          >
            {quickLoading === 'outreach' ? 'Starting...' : 'Export Mailmerge'}
          </button>
        </div>
      </div>
    </div>
  )
}
