'use client'

import { useState, useEffect, useCallback } from 'react'
import { automationApi } from '@/lib/api'
import {
  Zap, Power, Link2, ChevronDown, ChevronRight,
  Clock, AlertCircle, CheckCircle2, XCircle,
  Flame, Search, Mail, Brain, Server, Users,
} from 'lucide-react'

// ─── Types ───────────────────────────────────────────────────────────────────

interface JobInfo {
  id: string
  name: string
  group: string
  schedule: string
  enabled: boolean
  next_run: string | null
}

interface ControlsData {
  scheduler_running: boolean
  master_enabled: boolean
  chain_enrichment: boolean
  chain_validation: boolean
  chain_enrollment: boolean
  jobs: JobInfo[]
}

interface AutomationEvent {
  event_id: number
  event_type: string
  source: string
  title: string
  status: string
  created_at: string | null
}

const GROUP_ORDER = ['Warmup Engine', 'Lead Pipeline', 'Campaign & Outreach', 'Intelligence', 'System']
const GROUP_ICONS: Record<string, typeof Flame> = {
  'Warmup Engine': Flame,
  'Lead Pipeline': Search,
  'Campaign & Outreach': Mail,
  'Intelligence': Brain,
  'System': Server,
}

// ─── Toggle Switch ──────────────────────────────────────────────────────────

function Toggle({ enabled, onChange, disabled, size = 'md' }: {
  enabled: boolean
  onChange: (val: boolean) => void
  disabled?: boolean
  size?: 'sm' | 'md'
}) {
  const w = size === 'sm' ? 'w-9 h-5' : 'w-11 h-6'
  const dot = size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4'
  const translate = size === 'sm' ? 'translate-x-4' : 'translate-x-5'

  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      disabled={disabled}
      onClick={() => onChange(!enabled)}
      className={`
        relative inline-flex ${w} items-center rounded-full transition-colors duration-200
        focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2
        ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}
        ${enabled ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'}
      `}
    >
      <span className={`
        inline-block ${dot} transform rounded-full bg-white shadow transition-transform duration-200
        ${enabled ? translate : 'translate-x-1'}
      `} />
    </button>
  )
}

// ─── Main Component ─────────────────────────────────────────────────────────

export default function AutomationControlCenter() {
  const [controls, setControls] = useState<ControlsData | null>(null)
  const [events, setEvents] = useState<AutomationEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(GROUP_ORDER))

  const fetchData = useCallback(async () => {
    try {
      const [controlsData, eventsData] = await Promise.all([
        automationApi.getControls(),
        automationApi.events({ page_size: 10, hours: 48 }),
      ])
      setControls(controlsData)
      setEvents(eventsData.items || [])
      setError(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load automation controls')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const updateControls = async (patch: Record<string, any>) => {
    if (!controls) return
    setSaving(true)
    try {
      await automationApi.updateControls(patch)
      // Optimistic update
      setControls(prev => {
        if (!prev) return prev
        const updated = { ...prev }
        if ('master_enabled' in patch) updated.master_enabled = patch.master_enabled
        if ('chain_enrichment' in patch) updated.chain_enrichment = patch.chain_enrichment
        if ('chain_validation' in patch) updated.chain_validation = patch.chain_validation
        if ('chain_enrollment' in patch) updated.chain_enrollment = patch.chain_enrollment
        if (patch.jobs) {
          updated.jobs = prev.jobs.map(j =>
            j.id in patch.jobs ? { ...j, enabled: patch.jobs[j.id] } : j
          )
        }
        return updated
      })
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update')
      // Refetch to get correct state
      fetchData()
    } finally {
      setSaving(false)
    }
  }

  const toggleGroup = (group: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  const toggleGroupJobs = (group: string, enabled: boolean) => {
    if (!controls) return
    const groupJobs = controls.jobs.filter(j => j.group === group)
    const jobs: Record<string, boolean> = {}
    groupJobs.forEach(j => { jobs[j.id] = enabled })
    updateControls({ jobs })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
      </div>
    )
  }

  if (error && !controls) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <div className="flex items-center gap-2 text-red-700 dark:text-red-400">
          <AlertCircle className="w-5 h-5" />
          <span>{error}</span>
        </div>
      </div>
    )
  }

  if (!controls) return null

  const masterOff = !controls.master_enabled
  const groupedJobs: Record<string, JobInfo[]> = {}
  for (const j of controls.jobs) {
    if (!groupedJobs[j.group]) groupedJobs[j.group] = []
    groupedJobs[j.group].push(j)
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Automation Control Center</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Manage scheduler jobs, pipeline chaining, and automation toggles
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${
            controls.scheduler_running
              ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
              : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
          }`}>
            <span className={`w-2 h-2 rounded-full ${controls.scheduler_running ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
            Scheduler {controls.scheduler_running ? 'Running' : 'Stopped'}
          </span>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Master Toggle */}
      <div className={`rounded-xl border-2 p-5 transition-colors ${
        controls.master_enabled
          ? 'border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/10'
          : 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/10'
      }`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${controls.master_enabled ? 'bg-green-100 dark:bg-green-900/30' : 'bg-red-100 dark:bg-red-900/30'}`}>
              <Power className={`w-6 h-6 ${controls.master_enabled ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Master Automation</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {controls.master_enabled ? 'All enabled jobs are running on schedule' : 'All automation is paused — no jobs will execute'}
              </p>
            </div>
          </div>
          <Toggle
            enabled={controls.master_enabled}
            onChange={(val) => updateControls({ master_enabled: val })}
            disabled={saving}
          />
        </div>
      </div>

      {/* Pipeline Chain */}
      <div className={`bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 ${masterOff ? 'opacity-50' : ''}`}>
        <div className="flex items-center gap-2 mb-4">
          <Link2 className="w-5 h-5 text-primary-600 dark:text-primary-400" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Pipeline Auto-Chain</h2>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          When enabled, completing one pipeline stage automatically triggers the next.
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Step 1: Lead Sourcing (always runs) */}
          <div className="flex items-center gap-2 px-3 py-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
            <Search className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <span className="text-sm font-medium text-blue-700 dark:text-blue-300">Lead Sourcing</span>
          </div>

          {/* Arrow + toggle: enrichment */}
          <div className="flex items-center gap-1">
            <span className="text-gray-400">→</span>
            <Toggle
              enabled={controls.chain_enrichment}
              onChange={(val) => updateControls({ chain_enrichment: val })}
              disabled={saving || masterOff}
              size="sm"
            />
          </div>

          {/* Step 2: Contact Enrichment */}
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${
            controls.chain_enrichment
              ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'
              : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
          }`}>
            <Zap className={`w-4 h-4 ${controls.chain_enrichment ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400'}`} />
            <span className={`text-sm font-medium ${controls.chain_enrichment ? 'text-blue-700 dark:text-blue-300' : 'text-gray-400'}`}>
              Contact Enrichment
            </span>
          </div>

          {/* Arrow + toggle: validation */}
          <div className="flex items-center gap-1">
            <span className="text-gray-400">→</span>
            <Toggle
              enabled={controls.chain_validation}
              onChange={(val) => updateControls({ chain_validation: val })}
              disabled={saving || masterOff || !controls.chain_enrichment}
              size="sm"
            />
          </div>

          {/* Step 3: Email Validation */}
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${
            controls.chain_validation && controls.chain_enrichment
              ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'
              : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
          }`}>
            <CheckCircle2 className={`w-4 h-4 ${
              controls.chain_validation && controls.chain_enrichment ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400'
            }`} />
            <span className={`text-sm font-medium ${
              controls.chain_validation && controls.chain_enrichment ? 'text-blue-700 dark:text-blue-300' : 'text-gray-400'
            }`}>
              Email Validation
            </span>
          </div>

          {/* Arrow + toggle: enrollment */}
          <div className="flex items-center gap-1">
            <span className="text-gray-400">→</span>
            <Toggle
              enabled={controls.chain_enrollment}
              onChange={(val) => updateControls({ chain_enrollment: val })}
              disabled={saving || masterOff || !controls.chain_enrichment || !controls.chain_validation}
              size="sm"
            />
          </div>

          {/* Step 4: Campaign Enrollment */}
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${
            controls.chain_enrollment && controls.chain_validation && controls.chain_enrichment
              ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'
              : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
          }`}>
            <Users className={`w-4 h-4 ${
              controls.chain_enrollment && controls.chain_validation && controls.chain_enrichment ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400'
            }`} />
            <span className={`text-sm font-medium ${
              controls.chain_enrollment && controls.chain_validation && controls.chain_enrichment ? 'text-blue-700 dark:text-blue-300' : 'text-gray-400'
            }`}>
              Campaign Enrollment
            </span>
          </div>
        </div>
      </div>

      {/* Job Groups */}
      <div className={`space-y-3 ${masterOff ? 'opacity-50' : ''}`}>
        {GROUP_ORDER.map(group => {
          const jobs = groupedJobs[group] || []
          if (jobs.length === 0) return null
          const expanded = expandedGroups.has(group)
          const allEnabled = jobs.every(j => j.enabled)
          const noneEnabled = jobs.every(j => !j.enabled)
          const GroupIcon = GROUP_ICONS[group] || Zap

          return (
            <div key={group} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              {/* Group Header */}
              <div
                className="flex items-center justify-between px-5 py-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-750"
                onClick={() => toggleGroup(group)}
              >
                <div className="flex items-center gap-3">
                  <button className="text-gray-400">
                    {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </button>
                  <GroupIcon className="w-5 h-5 text-gray-500 dark:text-gray-400" />
                  <span className="font-medium text-gray-900 dark:text-gray-100">{group}</span>
                  <span className="text-xs text-gray-400">({jobs.filter(j => j.enabled).length}/{jobs.length} active)</span>
                </div>
                <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => toggleGroupJobs(group, !allEnabled)}
                    disabled={saving || masterOff}
                    className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40"
                  >
                    {allEnabled ? 'Disable All' : noneEnabled ? 'Enable All' : 'Enable All'}
                  </button>
                </div>
              </div>

              {/* Job Rows */}
              {expanded && (
                <div className="border-t border-gray-100 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700">
                  {jobs.map(job => (
                    <div key={job.id} className="flex items-center justify-between px-5 py-3 pl-14">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gray-800 dark:text-gray-200">{job.name}</span>
                        </div>
                        <div className="flex items-center gap-3 mt-0.5">
                          <span className="text-xs text-gray-400 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {job.schedule}
                          </span>
                          {job.next_run && job.enabled && (
                            <span className="text-xs text-gray-400">
                              Next: {new Date(job.next_run).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          )}
                        </div>
                      </div>
                      <Toggle
                        enabled={job.enabled}
                        onChange={(val) => updateControls({ jobs: { [job.id]: val } })}
                        disabled={saving || masterOff}
                        size="sm"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Recent Activity */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Recent Activity</h2>
        {events.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-6">No recent automation events</p>
        ) : (
          <div className="space-y-2">
            {events.map(evt => (
              <div key={evt.event_id} className="flex items-start gap-3 py-2">
                <div className="mt-0.5">
                  {evt.status === 'success' ? (
                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                  ) : evt.status === 'error' ? (
                    <XCircle className="w-4 h-4 text-red-500" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-yellow-500" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-800 dark:text-gray-200 truncate">{evt.title}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-gray-400">{evt.event_type}</span>
                    <span className="text-xs text-gray-300 dark:text-gray-600">|</span>
                    <span className="text-xs text-gray-400">
                      {evt.created_at ? new Date(evt.created_at).toLocaleString() : '—'}
                    </span>
                  </div>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  evt.status === 'success' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                  evt.status === 'error' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                  'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                }`}>
                  {evt.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
