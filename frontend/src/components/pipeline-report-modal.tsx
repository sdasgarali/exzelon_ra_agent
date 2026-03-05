'use client'

import { useState, useEffect } from 'react'
import { pipelinesApi } from '@/lib/api'
import {
  X,
  FileText,
  RefreshCw,
  CheckCircle,
  AlertTriangle,
  Sparkles,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'

interface PipelineReportModalProps {
  open: boolean
  onClose: () => void
  runId: number
  pipelineName: string
  status: string
  durationSeconds: number | null
}

interface SourceBreakdown {
  source_name: string
  source_label: string
  status: string
  status_detail: string | null
  total_retrieved: number
  new_records: number
  existing_in_db: number
  skipped: number
  errors: number
  is_sub_source?: boolean
  parent_source?: string | null
}

interface ApiDiagnostic {
  adapter_name: string
  adapter_label: string
  status: string
  status_detail: string | null
  error_message: string | null
  records_returned: number
}

interface RunMetadata {
  run_id: number
  pipeline_name: string
  pipeline_label: string
  status: string
  triggered_by: string
  started_at: string | null
  ended_at: string | null
  duration_seconds: number | null
}

interface SummaryData {
  success_score: number
  summary: string
  suggestions: string[]
  highlights: string[]
  generated_at: string
  ai_generated: boolean
  run_metadata?: RunMetadata
  source_breakdown?: SourceBreakdown[]
  api_diagnostics?: ApiDiagnostic[]
  counters?: Record<string, number | string>
}

export function PipelineReportModal({
  open,
  onClose,
  runId,
  pipelineName,
  status,
  durationSeconds,
}: PipelineReportModalProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [data, setData] = useState<SummaryData | null>(null)
  const [diagExpanded, setDiagExpanded] = useState(false)

  useEffect(() => {
    if (open && runId) {
      fetchSummary(false)
    }
    if (!open) {
      setData(null)
      setError('')
      setDiagExpanded(false)
    }
  }, [open, runId])

  const fetchSummary = async (regenerate: boolean) => {
    setLoading(true)
    setError('')
    try {
      const result = await pipelinesApi.getRunSummary(runId, regenerate)
      setData(result)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate summary report')
    } finally {
      setLoading(false)
    }
  }

  if (!open) return null

  const formatPipelineName = (name: string) =>
    name?.replace(/_/g, ' ').replace(/-/g, ' ').split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')

  const formatDuration = (seconds: number | null) => {
    if (seconds == null) return 'N/A'
    if (seconds < 60) return `${seconds}s`
    return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  }

  const getScoreColor = (score: number) => {
    if (score >= 80) return { bg: 'bg-green-50', text: 'text-green-700', bar: 'bg-green-500', ring: 'ring-green-200' }
    if (score >= 60) return { bg: 'bg-yellow-50', text: 'text-yellow-700', bar: 'bg-yellow-500', ring: 'ring-yellow-200' }
    return { bg: 'bg-red-50', text: 'text-red-700', bar: 'bg-red-500', ring: 'ring-red-200' }
  }

  const getStatusBadge = (s: string) => {
    const map: Record<string, string> = {
      completed: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800',
      cancelled: 'bg-gray-100 text-gray-800',
    }
    return map[s?.toLowerCase()] || 'bg-gray-100 text-gray-800'
  }

  const getStatusDot = (s: string) => {
    if (s === 'success') return 'bg-green-500'
    if (s === 'warning') return 'bg-yellow-500'
    return 'bg-red-500'
  }

  const sourceBreakdown = data?.source_breakdown || []
  const apiDiagnostics = data?.api_diagnostics || []
  const showDiagToggle = apiDiagnostics.length > 3

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-gray-600" />
            <h3 className="text-lg font-semibold text-gray-800">Pipeline Run Report</h3>
            <span className="text-sm text-gray-400 font-mono">#{runId}</span>
          </div>
          <div className="flex items-center gap-2">
            {data && !loading && (
              <button
                onClick={() => fetchSummary(true)}
                className="text-gray-400 hover:text-blue-600 p-1 rounded transition-colors"
                title="Regenerate report"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="overflow-y-auto flex-1 px-6 py-4">
          {/* Pipeline info bar */}
          <div className="flex items-center gap-3 mb-5 p-3 bg-gray-50 rounded-lg">
            <span className="font-medium text-gray-800">
              {data?.run_metadata?.pipeline_label || formatPipelineName(pipelineName)}
            </span>
            <span className={`px-2 py-0.5 text-xs rounded-full ${getStatusBadge(status)}`}>
              {status}
            </span>
            {data?.run_metadata?.triggered_by && (
              <span className="text-xs text-gray-400">
                by {data.run_metadata.triggered_by}
              </span>
            )}
            <span className="text-sm text-gray-500 ml-auto">
              Duration: {formatDuration(data?.run_metadata?.duration_seconds ?? durationSeconds)}
            </span>
          </div>

          {loading && (
            <div className="flex flex-col items-center justify-center py-12">
              <RefreshCw className="w-8 h-8 text-blue-500 animate-spin mb-3" />
              <span className="text-gray-500">Generating summary report...</span>
            </div>
          )}

          {error && (
            <div className="flex flex-col items-center justify-center py-8">
              <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm w-full">
                {error}
              </div>
              <button
                onClick={() => fetchSummary(false)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
              >
                Retry
              </button>
            </div>
          )}

          {data && !loading && (
            <>
              {/* Success Score */}
              {(() => {
                const colors = getScoreColor(data.success_score)
                return (
                  <div className={`mb-5 p-4 rounded-lg ${colors.bg} ring-1 ${colors.ring}`}>
                    <div className="flex items-center gap-4">
                      <div className="text-center">
                        <div className={`text-3xl font-bold ${colors.text}`}>{data.success_score}</div>
                        <div className="text-xs text-gray-500 font-medium">/100</div>
                      </div>
                      <div className="flex-1">
                        <div className="text-sm font-medium text-gray-700 mb-1.5">Success Score</div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div
                            className={`h-2.5 rounded-full ${colors.bar} transition-all`}
                            style={{ width: `${data.success_score}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })()}

              {/* Source Breakdown Table */}
              {sourceBreakdown.length > 0 && (
                <div className="mb-5">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">Source Breakdown</h4>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="text-left px-3 py-2 text-gray-600 font-medium">Source</th>
                          <th className="text-center px-3 py-2 text-gray-600 font-medium">Status</th>
                          <th className="text-right px-3 py-2 text-gray-600 font-medium">Retrieved</th>
                          <th className="text-right px-3 py-2 text-gray-600 font-medium">New</th>
                          <th className="text-right px-3 py-2 text-gray-600 font-medium">Existing</th>
                          <th className="text-right px-3 py-2 text-gray-600 font-medium">Skipped</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {sourceBreakdown.map((sb, i) => {
                          const isSubSource = sb.is_sub_source === true
                          // Check if this is the last sub-source in a group
                          const isLastSub = isSubSource && (
                            i === sourceBreakdown.length - 1 ||
                            !sourceBreakdown[i + 1]?.is_sub_source
                          )
                          return (
                            <tr
                              key={i}
                              className={`hover:bg-gray-50 ${isSubSource ? 'bg-blue-50/30' : ''}`}
                            >
                              <td className="px-3 py-2 text-gray-800 font-medium">
                                {isSubSource ? (
                                  <span className="flex items-center gap-1.5 pl-4">
                                    <span className="text-gray-300 text-xs">{isLastSub ? '└' : '├'}</span>
                                    <span className="text-gray-600 font-normal text-xs">{sb.source_label}</span>
                                  </span>
                                ) : (
                                  sb.source_label
                                )}
                              </td>
                              <td className="px-3 py-2 text-center">
                                <span className="inline-flex items-center gap-1.5">
                                  <span className={`w-2 h-2 rounded-full ${getStatusDot(sb.status)}`} />
                                  <span className="text-xs text-gray-500">
                                    {sb.status_detail || sb.status}
                                  </span>
                                </span>
                              </td>
                              <td className={`px-3 py-2 text-right ${isSubSource ? 'text-gray-500 text-xs' : 'text-gray-700'}`}>
                                {sb.total_retrieved}
                              </td>
                              <td className={`px-3 py-2 text-right ${isSubSource ? 'text-green-600 text-xs' : 'text-green-700 font-medium'}`}>
                                {sb.new_records}
                              </td>
                              <td className={`px-3 py-2 text-right text-gray-500 ${isSubSource ? 'text-xs' : ''}`}>
                                {sb.existing_in_db}
                              </td>
                              <td className={`px-3 py-2 text-right text-gray-500 ${isSubSource ? 'text-xs' : ''}`}>
                                {sb.skipped}
                              </td>
                            </tr>
                          )
                        })}
                        {/* Total row: only sum top-level sources (not sub-sources) */}
                        {(() => {
                          const topLevel = sourceBreakdown.filter(sb => !sb.is_sub_source)
                          return topLevel.length > 1 ? (
                            <tr className="bg-gray-50 font-medium">
                              <td className="px-3 py-2 text-gray-700">Total</td>
                              <td className="px-3 py-2" />
                              <td className="px-3 py-2 text-right text-gray-700">
                                {topLevel.reduce((s, b) => s + b.total_retrieved, 0)}
                              </td>
                              <td className="px-3 py-2 text-right text-green-700">
                                {topLevel.reduce((s, b) => s + b.new_records, 0)}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-500">
                                {topLevel.reduce((s, b) => s + b.existing_in_db, 0)}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-500">
                                {topLevel.reduce((s, b) => s + b.skipped, 0)}
                              </td>
                            </tr>
                          ) : null
                        })()}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* API / Tool Status */}
              {apiDiagnostics.length > 0 && (
                <div className="mb-5">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">API / Tool Status</h4>
                  <div className="border rounded-lg p-3 space-y-2">
                    {(showDiagToggle && !diagExpanded ? apiDiagnostics.slice(0, 3) : apiDiagnostics).map((ad, i) => (
                      <div key={i} className="flex items-center justify-between">
                        <span className="inline-flex items-center gap-2 text-sm">
                          <span className={`w-2 h-2 rounded-full ${getStatusDot(ad.status)}`} />
                          <span className="text-gray-700 font-medium">{ad.adapter_label}</span>
                        </span>
                        <span className="text-sm">
                          {ad.status === 'success' ? (
                            <span className="text-green-600">
                              {ad.records_returned > 0 ? `${ad.records_returned} records` : 'OK'}
                            </span>
                          ) : ad.status === 'warning' ? (
                            <span className="text-yellow-600">
                              {ad.status_detail || 'Warning'}{ad.error_message ? ` - ${ad.error_message.slice(0, 60)}` : ''}
                            </span>
                          ) : (
                            <span className="text-red-600">
                              {ad.status_detail || 'Error'}{ad.error_message ? ` - ${ad.error_message.slice(0, 60)}` : ''}
                            </span>
                          )}
                        </span>
                      </div>
                    ))}
                    {showDiagToggle && (
                      <button
                        onClick={() => setDiagExpanded(!diagExpanded)}
                        className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1 mt-1"
                      >
                        {diagExpanded ? (
                          <>Show less <ChevronUp className="w-3 h-3" /></>
                        ) : (
                          <>Show {apiDiagnostics.length - 3} more <ChevronDown className="w-3 h-3" /></>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Summary */}
              <div className="mb-5">
                <h4 className="text-sm font-semibold text-gray-700 mb-2">Summary</h4>
                <div className="p-3 bg-gray-50 rounded-lg text-sm text-gray-700 leading-relaxed">
                  {data.summary}
                </div>
              </div>

              {/* Highlights */}
              {data.highlights && data.highlights.length > 0 && (
                <div className="mb-5">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
                    <CheckCircle className="w-4 h-4 text-green-600" />
                    Highlights
                  </h4>
                  <ul className="space-y-1.5">
                    {data.highlights.map((h, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                        <span className="text-green-500 mt-0.5">&#8226;</span>
                        {h}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Suggestions */}
              {data.suggestions && data.suggestions.length > 0 && data.success_score < 100 && (
                <div className="mb-5">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
                    <AlertTriangle className="w-4 h-4 text-yellow-600" />
                    Suggestions
                  </h4>
                  <ol className="space-y-1.5 list-decimal list-inside">
                    {data.suggestions.map((s, i) => (
                      <li key={i} className="text-sm text-gray-700">{s}</li>
                    ))}
                  </ol>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {data && !loading && (
          <div className="px-6 py-3 border-t bg-gray-50 flex items-center justify-between text-xs text-gray-400">
            <span>
              Generated {new Date(data.generated_at).toLocaleString()}
            </span>
            <span className="flex items-center gap-1">
              {data.ai_generated ? (
                <>
                  <Sparkles className="w-3 h-3" />
                  AI-powered
                </>
              ) : (
                'Deterministic analysis'
              )}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
