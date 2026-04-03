'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import {
  Eye, Building, FileText, TrendingUp, Copy, Check,
  Loader2, AlertCircle, Globe, Clock, ExternalLink, Users,
} from 'lucide-react'

// ---------- Types ----------

interface VisitorStats {
  total_visitors: number
  unique_companies: number
  page_views: number
  conversion_rate: number
}

interface VisitorSession {
  session_id: string
  company: string | null
  pages_visited: string[]
  duration_seconds: number
  source: string | null
  ip_address: string | null
  user_agent: string | null
  first_seen: string
  last_seen: string
  country: string | null
  city: string | null
}

// ---------- Helpers ----------

function formatDuration(seconds: number) {
  if (!seconds || seconds < 0) return '0s'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

function timeAgo(dateStr: string) {
  const now = new Date()
  const date = new Date(dateStr)
  const diff = Math.floor((now.getTime() - date.getTime()) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
  return date.toLocaleDateString()
}

// ---------- Component ----------

export default function VisitorsPage() {
  const [stats, setStats] = useState<VisitorStats | null>(null)
  const [sessions, setSessions] = useState<VisitorSession[]>([])
  const [loading, setLoading] = useState(true)
  const [statsLoading, setStatsLoading] = useState(true)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const pageSize = 20

  useEffect(() => {
    fetchStats()
    fetchVisitors()
  }, [page])

  const fetchStats = async () => {
    setStatsLoading(true)
    try {
      const { data } = await api.get('/visitors/stats')
      setStats(data)
    } catch {
      // Endpoint may not exist yet - use defaults
      setStats({ total_visitors: 0, unique_companies: 0, page_views: 0, conversion_rate: 0 })
    }
    setStatsLoading(false)
  }

  const fetchVisitors = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/visitors', { params: { page, page_size: pageSize } })
      setSessions(data?.items || data?.sessions || [])
      setTotal(data?.total || 0)
    } catch {
      setError('Visitor tracking data is not yet available. Set up the tracking pixel to get started.')
      setSessions([])
    }
    setLoading(false)
  }

  const trackingSnippet = `<!-- NeuraLeads Visitor Tracking Pixel -->
<script>
  (function() {
    var img = new Image();
    img.src = window.location.origin + '/t/visitor/px.gif' +
      '?url=' + encodeURIComponent(window.location.href) +
      '&ref=' + encodeURIComponent(document.referrer) +
      '&t=' + Date.now();
  })();
</script>`

  const handleCopy = () => {
    navigator.clipboard.writeText(trackingSnippet)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const totalPages = Math.ceil(total / pageSize) || 1

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Visitors</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">Track website visitors and identify potential leads</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {statsLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 animate-pulse">
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24 mb-2" />
              <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-16" />
            </div>
          ))
        ) : stats && (
          <>
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 text-sm mb-1">
                <Eye className="w-4 h-4 text-pink-500" /> Total Visitors
              </div>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.total_visitors.toLocaleString()}</p>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 text-sm mb-1">
                <Building className="w-4 h-4 text-blue-500" /> Unique Companies
              </div>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.unique_companies.toLocaleString()}</p>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 text-sm mb-1">
                <FileText className="w-4 h-4 text-indigo-500" /> Page Views
              </div>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.page_views.toLocaleString()}</p>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 text-sm mb-1">
                <TrendingUp className="w-4 h-4 text-green-500" /> Conversion Rate
              </div>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.conversion_rate.toFixed(1)}%</p>
            </div>
          </>
        )}
      </div>

      {/* Visitor Sessions Table */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
          <Users className="w-5 h-5 text-pink-500" /> Visitor Sessions
        </h2>

        {error && (
          <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 text-sm py-4 px-4 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800 mb-4">
            <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
          </div>
        )}

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-center py-12">
              <Eye className="w-12 h-12 mx-auto mb-3 text-gray-300 dark:text-gray-600" />
              <p className="font-medium text-gray-700 dark:text-gray-300">No visitor data yet</p>
              <p className="text-sm text-gray-500 mt-1">Add the tracking pixel to your website to start collecting data</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 dark:bg-gray-700/50">
                    <tr>
                      {['Company', 'Pages Visited', 'Duration', 'Source', 'Location', 'Time'].map(h => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {sessions.map(session => (
                      <tr key={session.session_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded-lg bg-pink-50 dark:bg-pink-900/20 flex items-center justify-center flex-shrink-0">
                              <Building className="w-4 h-4 text-pink-500" />
                            </div>
                            <span className="font-medium text-gray-900 dark:text-gray-100">{session.company || 'Unknown'}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1 max-w-xs">
                            {(session.pages_visited || []).slice(0, 3).map((page, i) => (
                              <span key={i} className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded">
                                <Globe className="w-2.5 h-2.5" />
                                {page.length > 30 ? page.slice(0, 30) + '...' : page}
                              </span>
                            ))}
                            {(session.pages_visited || []).length > 3 && (
                              <span className="text-[10px] text-gray-400">+{session.pages_visited.length - 3} more</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                          <div className="flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5 text-gray-400" />
                            {formatDuration(session.duration_seconds)}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {session.source ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-full">
                              <ExternalLink className="w-3 h-3" />
                              {session.source}
                            </span>
                          ) : (
                            <span className="text-xs text-gray-400">Direct</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-600 dark:text-gray-300">
                          {session.city && session.country
                            ? `${session.city}, ${session.country}`
                            : session.country || '-'
                          }
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-400">
                          {timeAgo(session.first_seen)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between text-sm">
                  <span className="text-gray-500">{total} sessions total</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      disabled={page === 1}
                      className="px-3 py-1 border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-50 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-gray-700 dark:text-gray-300"
                    >
                      Previous
                    </button>
                    <span className="px-3 py-1 text-gray-500">Page {page} of {totalPages}</span>
                    <button
                      onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                      disabled={page >= totalPages}
                      className="px-3 py-1 border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-50 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-gray-700 dark:text-gray-300"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </section>

      {/* Tracking Pixel Code Snippet */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
          <FileText className="w-5 h-5 text-indigo-500" /> Tracking Pixel Setup
        </h2>
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50">
            <p className="text-sm text-gray-600 dark:text-gray-300">
              Add this code to your website to track visitors
            </p>
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 rounded-lg hover:bg-indigo-100 dark:hover:bg-indigo-900/40 transition-colors"
            >
              {copied ? (
                <><Check className="w-3.5 h-3.5" /> Copied!</>
              ) : (
                <><Copy className="w-3.5 h-3.5" /> Copy Code</>
              )}
            </button>
          </div>
          <pre className="p-4 text-xs text-gray-700 dark:text-gray-300 overflow-x-auto font-mono leading-relaxed bg-gray-50/50 dark:bg-gray-900/30">
            {trackingSnippet}
          </pre>
        </div>
      </section>
    </div>
  )
}
