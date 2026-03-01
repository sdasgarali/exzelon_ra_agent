'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { backupsApi, settingsApi } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import { HardDrive, Download, Trash2, Plus, RefreshCw, Clock, Database } from 'lucide-react'

interface BackupFile {
  filename: string
  size_bytes: number
  size_human: string
  created_at: string
}

export default function BackupsPage() {
  const router = useRouter()
  const { user } = useAuthStore()
  const isSuperAdmin = user?.role === 'super_admin'

  const [backups, setBackups] = useState<BackupFile[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [downloading, setDownloading] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [retentionDays, setRetentionDays] = useState<number>(3)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => {
    if (user && !isSuperAdmin) {
      router.replace('/dashboard')
    }
  }, [user, isSuperAdmin, router])

  const loadBackups = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await backupsApi.list()
      setBackups(data)
    } catch {
      setError('Failed to load backups')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadRetention = useCallback(async () => {
    try {
      const data = await settingsApi.get('backup_retention_days')
      if (data?.value_json) {
        setRetentionDays(JSON.parse(data.value_json))
      }
    } catch {
      // Setting may not exist yet — use default
    }
  }, [])

  useEffect(() => {
    if (isSuperAdmin) {
      loadBackups()
      loadRetention()
    }
  }, [isSuperAdmin, loadBackups, loadRetention])

  // Auto-clear messages
  useEffect(() => {
    if (success) { const t = setTimeout(() => setSuccess(null), 4000); return () => clearTimeout(t) }
  }, [success])
  useEffect(() => {
    if (error) { const t = setTimeout(() => setError(null), 6000); return () => clearTimeout(t) }
  }, [error])

  const handleCreate = async () => {
    setCreating(true)
    setError(null)
    try {
      const result = await backupsApi.create()
      setSuccess(`Backup created: ${result.filename} (${result.size_human})`)
      await loadBackups()
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      setError(detail || 'Failed to create backup')
    } finally {
      setCreating(false)
    }
  }

  const handleDownload = async (filename: string) => {
    setDownloading(filename)
    try {
      const blob = await backupsApi.download(filename)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      setError('Failed to download backup')
    } finally {
      setDownloading(null)
    }
  }

  const handleDelete = async (filename: string) => {
    setDeleting(filename)
    setConfirmDelete(null)
    try {
      await backupsApi.delete(filename)
      setSuccess(`Backup '${filename}' deleted`)
      await loadBackups()
    } catch {
      setError('Failed to delete backup')
    } finally {
      setDeleting(null)
    }
  }

  const formatTimestamp = (iso: string) => {
    try {
      const d = new Date(iso)
      return d.toLocaleString()
    } catch {
      return iso
    }
  }

  if (!isSuperAdmin) return null

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <HardDrive className="w-7 h-7" />
            Data Backups
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Manage database backups. Daily backups run automatically at 2:00 AM UTC.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadBackups}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={handleCreate}
            disabled={creating}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors disabled:opacity-50"
          >
            {creating ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Creating...
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                Create Backup Now
              </>
            )}
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 px-4 py-3 rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-4 text-red-600 dark:text-red-300 hover:text-red-800">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}
      {success && (
        <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-200 px-4 py-3 rounded-lg">
          {success}
        </div>
      )}

      {/* Retention info banner */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg px-4 py-3 flex items-center gap-3">
        <Clock className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0" />
        <p className="text-sm text-blue-800 dark:text-blue-200">
          Backups older than <strong>{retentionDays} days</strong> are automatically deleted.
          You can change this in <a href="/dashboard/settings" className="underline hover:no-underline">Settings &rarr; Business Rules</a>.
        </p>
      </div>

      {/* Backups table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-48">
            <div className="text-gray-500 dark:text-gray-400">Loading backups...</div>
          </div>
        ) : backups.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-gray-500 dark:text-gray-400">
            <Database className="w-12 h-12 mb-3 opacity-40" />
            <p className="text-lg font-medium">No backups yet</p>
            <p className="text-sm mt-1">Click &quot;Create Backup Now&quot; to create your first backup.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-900">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Filename
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Size
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Created At
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {backups.map((backup) => (
                  <tr key={backup.filename} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <Database className="w-4 h-4 text-gray-400 flex-shrink-0" />
                        <span className="text-sm font-mono text-gray-900 dark:text-white">
                          {backup.filename}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                      {backup.size_human}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                      {formatTimestamp(backup.created_at)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleDownload(backup.filename)}
                          disabled={downloading === backup.filename}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors disabled:opacity-50"
                          title="Download backup"
                        >
                          {downloading === backup.filename ? (
                            <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                            </svg>
                          ) : (
                            <Download className="w-3.5 h-3.5" />
                          )}
                          Download
                        </button>
                        {confirmDelete === backup.filename ? (
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => handleDelete(backup.filename)}
                              disabled={deleting === backup.filename}
                              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50"
                            >
                              {deleting === backup.filename ? 'Deleting...' : 'Confirm'}
                            </button>
                            <button
                              onClick={() => setConfirmDelete(null)}
                              className="px-2 py-1.5 text-xs font-medium text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setConfirmDelete(backup.filename)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/30 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors"
                            title="Delete backup"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
