'use client'

import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, X } from 'lucide-react'
import { settingsApi, getApiError } from '@/lib/api'
import { useAuthStore } from '@/lib/store'

/**
 * Amber prompt shown on the dashboard while the workspace has no postal address.
 *
 * CAN-SPAM requires the sender's physical postal address in every outreach email,
 * and the send gate now refuses outreach until one is set (Plan_Launch_Readiness_6
 * L1). Only workspace admins can set it, so only they see this. The address can
 * be saved right here: a workspace's role matrix may hide the Business Rules
 * settings tab, and an admin must never be told to add something they can't reach.
 * Dismissal lasts for the browser session.
 */

const DISMISS_KEY = 'postal-address-banner-dismissed'
const ADMIN_ROLES = ['admin', 'super_admin']

function readDismissed(): boolean {
  try {
    return typeof window !== 'undefined' && window.sessionStorage.getItem(DISMISS_KEY) === '1'
  } catch {
    return false
  }
}

export function PostalAddressBanner() {
  const { user } = useAuthStore()
  const role = user?.base_role || user?.role || ''
  const isAdmin = ADMIN_ROLES.includes(role)
  const [dismissed, setDismissed] = useState(true)
  const [editing, setEditing] = useState(false)
  const [address, setAddress] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const queryClient = useQueryClient()

  // Read after mount so server and first client render agree.
  useEffect(() => {
    setDismissed(readDismissed())
  }, [])

  const { data } = useQuery<{ company_address?: string | null }>({
    queryKey: ['company-profile'],
    queryFn: settingsApi.getCompanyProfile,
    enabled: isAdmin,
    staleTime: 5 * 60_000,
    retry: false,
  })

  // Hidden while loading, on error (e.g. no workspace selected), or once set.
  if (!isAdmin || dismissed || !data) return null
  if ((data.company_address || '').trim()) return null

  const save = async () => {
    const value = address.trim()
    if (value.length < 10) {
      setError('Enter your full postal address (street, city, region, postal code, country).')
      return
    }
    setSaving(true)
    setError('')
    try {
      await settingsApi.updateCompanyProfile({ company_address: value })
      await queryClient.invalidateQueries({ queryKey: ['company-profile'] })
    } catch (err) {
      setError(getApiError(err))
    } finally {
      setSaving(false)
    }
  }

  const dismiss = () => {
    setDismissed(true)
    try {
      window.sessionStorage.setItem(DISMISS_KEY, '1')
    } catch {
      /* storage unavailable — dismissal just won't persist */
    }
  }

  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100"
    >
      <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
      <div className="flex-1 text-sm">
        <p className="font-semibold">Add your company&apos;s postal address before sending</p>
        <p className="mt-1">
          The law (CAN-SPAM) requires a physical postal address in every outreach email, so
          campaigns and outreach won&apos;t send until one is set.
        </p>
        {editing ? (
          <div className="mt-3 space-y-2">
            <label htmlFor="postal-address-input" className="block text-xs font-medium">
              Company postal address
            </label>
            <textarea
              id="postal-address-input"
              rows={2}
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="123 Main St, Suite 4, Austin, TX 78701, USA"
              className="w-full rounded-md border border-amber-300 bg-white px-2 py-1.5 text-sm text-gray-900 dark:border-amber-700 dark:bg-gray-900 dark:text-gray-100"
            />
            {error && <p className="text-xs text-red-700 dark:text-red-300">{error}</p>}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-60"
              >
                {saving ? 'Saving…' : 'Save address'}
              </button>
              <button
                type="button"
                onClick={() => { setEditing(false); setError('') }}
                className="rounded-md px-3 py-1.5 text-xs font-medium hover:bg-amber-100 dark:hover:bg-amber-900/50"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="mt-2 rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700"
          >
            Add address
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss postal address reminder"
        className="rounded p-1 hover:bg-amber-100 dark:hover:bg-amber-900/50"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  )
}

export default PostalAddressBanner
