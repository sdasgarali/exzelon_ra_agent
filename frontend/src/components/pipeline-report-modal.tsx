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
  Shield,
  XCircle,
  HelpCircle,
  Clock,
  Database,
  SearchX,
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
  excluded: number
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

interface ErrorAnalysisItem {
  error_type: string
  adapter: string | null
  adapter_label: string
  message: string
  root_cause: string
  proposed_solutions: string[]
}

interface QualityFunnel {
  total_discovered: number
  new_added: number
  updated: number
  duplicates_caught: number
  errors: number
  filter_breakdown: Array<{ label: string; count: number; icon: string }>
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
  quality_funnel?: QualityFunnel
  error_analysis?: ErrorAnalysisItem[]
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
  const [funnelExpanded, setFunnelExpanded] = useState(false)
  const [errorAnalysisExpanded, setErrorAnalysisExpanded] = useState(true)

  useEffect(() => {
    if (open && runId) {
      fetchSummary(false)
    }
    if (!open) {
      setData(null)
      setError('')
      setDiagExpanded(false)
      setFunnelExpanded(false)
      setErrorAnalysisExpanded(true)
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

  const funnelIconMap: Record<string, React.ReactNode> = {
    'shield': <Shield className="w-4 h-4 text-blue-500" />,
    'refresh-cw': <RefreshCw className="w-4 h-4 text-blue-500" />,
    'alert-triangle': <AlertTriangle className="w-4 h-4 text-red-500" />,
    'database': <Database className="w-4 h-4 text-purple-500" />,
    'search-x': <SearchX className="w-4 h-4 text-gray-500" />,
    'x-circle': <XCircle className="w-4 h-4 text-red-500" />,
    'help-circle': <HelpCircle className="w-4 h-4 text-yellow-500" />,
    'clock': <Clock className="w-4 h-4 text-gray-500" />,
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
              {/* Quality Funnel */}
              {data.quality_funnel ? (() => {
                const qf = data.quality_funnel!
                const total = qf.total_discovered || 1
                const newPct = (qf.new_added / total) * 100
                const updPct = (qf.updated / total) * 100
                const filtPct = (qf.duplicates_caught / total) * 100
                const errPct = (qf.errors / total) * 100
                return (
                  <div className="mb-5 p-4 rounded-lg bg-green-50 ring-1 ring-green-200">
                    {/* Hero number */}
                    <div className="flex items-baseline gap-3 mb-1">
                      <CheckCircle className="w-6 h-6 text-green-600 flex-shrink-0 self-center" />
                      <span className="text-3xl font-bold text-green-700">{qf.new_added.toLocaleString()}</span>
                      <span className="text-sm font-medium text-gray-700">
                        {data.run_metadata?.pipeline_name === 'email_validation' ? 'Valid Emails' :
                         data.run_metadata?.pipeline_name?.includes('outreach') ? 'Emails Sent' :
                         data.run_metadata?.pipeline_name === 'contact_enrichment' ? 'Contacts Found' :
                         'New Leads Added'}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 ml-9 mb-3">
                      from {qf.total_discovered.toLocaleString()} discovered
                    </div>

                    {/* Stacked bar */}
                    {qf.total_discovered > 0 && (
                      <div className="w-full h-3 rounded-full bg-gray-200 flex overflow-hidden mb-2">
                        {newPct > 0 && <div className="bg-green-500 h-full" style={{ width: `${newPct}%` }} title={`New: ${qf.new_added}`} />}
                        {updPct > 0 && <div className="bg-blue-400 h-full" style={{ width: `${updPct}%` }} title={`Updated: ${qf.updated}`} />}
                        {filtPct > 0 && <div className="bg-gray-400 h-full" style={{ width: `${filtPct}%` }} title={`Filtered: ${qf.duplicates_caught}`} />}
                        {errPct > 0 && <div className="bg-red-400 h-full" style={{ width: `${errPct}%` }} title={`Errors: ${qf.errors}`} />}
                      </div>
                    )}

                    {/* Legend */}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600 ml-1 mb-3">
                      <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-green-500 inline-block" />{qf.new_added} new</span>
                      {qf.updated > 0 && <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-blue-400 inline-block" />{qf.updated} updated</span>}
                      {qf.duplicates_caught > 0 && <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-gray-400 inline-block" />{qf.duplicates_caught} filtered</span>}
                      {qf.errors > 0 && <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-red-400 inline-block" />{qf.errors} errors</span>}
                    </div>

                    {/* Collapsible filter breakdown */}
                    {qf.filter_breakdown.length > 0 && (
                      <div>
                        <button
                          onClick={() => setFunnelExpanded(!funnelExpanded)}
                          className="text-xs text-gray-600 hover:text-gray-800 flex items-center gap-1 font-medium"
                        >
                          {funnelExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                          Quality Filter Details
                        </button>
                        {funnelExpanded && (
                          <div className="mt-2 space-y-1.5 pl-1">
                            {qf.filter_breakdown.map((fb, i) => (
                              <div key={i} className="flex items-center justify-between text-sm">
                                <span className="flex items-center gap-2 text-gray-700">
                                  {funnelIconMap[fb.icon] || <Shield className="w-4 h-4 text-gray-400" />}
                                  {fb.label}
                                </span>
                                <span className="font-medium text-gray-600 tabular-nums">{fb.count.toLocaleString()}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })() : (
                /* Fallback for old cached data without quality_funnel */
                <div className="mb-5 p-4 rounded-lg bg-gray-50 ring-1 ring-gray-200">
                  <div className="flex items-center gap-4">
                    <div className="text-center">
                      <div className="text-3xl font-bold text-gray-700">{data.success_score}</div>
                      <div className="text-xs text-gray-500 font-medium">/100</div>
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-medium text-gray-700 mb-1.5">Success Score</div>
                      <div className="w-full bg-gray-200 rounded-full h-2.5">
                        <div
                          className="h-2.5 rounded-full bg-gray-500 transition-all"
                          style={{ width: `${data.success_score}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              )}

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
                          <th className="text-right px-3 py-2 text-gray-600 font-medium" title="Duplicate postings removed by deduplication (in-batch + existing non-archived leads)">Duplicate</th>
                          <th className="text-right px-3 py-2 text-gray-600 font-medium" title="Dropped by the ICP gates — out-of-scope industry, company size, staffing, stale posting, etc.">Excluded</th>
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
                                {sb.skipped}
                              </td>
                              <td className={`px-3 py-2 text-right text-amber-600 ${isSubSource ? 'text-xs' : ''}`}>
                                {sb.excluded}
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
                                {topLevel.reduce((s, b) => s + b.skipped, 0)}
                              </td>
                              <td className="px-3 py-2 text-right text-amber-600">
                                {topLevel.reduce((s, b) => s + b.excluded, 0)}
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

              {/* Error Analysis */}
              {data.error_analysis && data.error_analysis.length > 0 && (
                <div className="mb-5">
                  <button
                    onClick={() => setErrorAnalysisExpanded(!errorAnalysisExpanded)}
                    className="flex items-center gap-2 text-sm font-semibold text-gray-700 mb-2 w-full text-left"
                  >
                    <XCircle className="w-4 h-4 text-red-500" />
                    Error Analysis
                    <span className="bg-red-100 text-red-700 text-xs font-medium px-1.5 py-0.5 rounded-full">
                      {data.error_analysis.length}
                    </span>
                    <span className="ml-auto">
                      {errorAnalysisExpanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                    </span>
                  </button>
                  {errorAnalysisExpanded && (
                    <div className="space-y-3">
                      {data.error_analysis.map((ea, i) => (
                        <div key={i} className="border border-red-200 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0" />
                            <span className="text-sm font-medium text-gray-800">{ea.adapter_label}</span>
                            <span className="bg-red-50 text-red-600 text-xs px-1.5 py-0.5 rounded font-mono">
                              {ea.error_type.replace(/_/g, ' ')}
                            </span>
                          </div>
                          {ea.message && (
                            <div className="bg-gray-100 rounded px-2 py-1.5 mb-2">
                              <code className="text-xs text-gray-600 font-mono break-all">{ea.message}</code>
                            </div>
                          )}
                          {ea.root_cause && (
                            <p className="text-sm text-gray-700 mb-2">
                              <span className="font-medium">Root cause:</span> {ea.root_cause}
                            </p>
                          )}
                          {ea.proposed_solutions && ea.proposed_solutions.length > 0 && (
                            <div>
                              <span className="text-sm font-medium text-gray-700">Solutions:</span>
                              <ul className="mt-1 space-y-1">
                                {ea.proposed_solutions.map((sol, si) => (
                                  <li key={si} className="flex items-start gap-2 text-sm text-gray-600">
                                    <span className="text-blue-500 mt-0.5 flex-shrink-0">&#8226;</span>
                                    {sol}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
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
              {data.suggestions && data.suggestions.length > 0 && (
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
