'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAuthStore } from '@/lib/store'
import { billingApi } from '@/lib/api'
import { Modal } from '@/components/modal'
import type { Invoice, PaymentRecord, BillingStats } from '@/types/api'
import {
  Receipt,
  DollarSign,
  AlertTriangle,
  TrendingUp,
  Download,
  CheckCircle,
  Trash2,
  RefreshCw,
  CreditCard,
  Search,
  FileText,
  Zap,
} from 'lucide-react'

// ─── Helpers ────────────────────────────────────────────────────────────

function formatCents(cents: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100)
}

function formatPeriod(start: string | null, end: string | null): string {
  if (!start) return 'N/A'
  const d = new Date(start)
  return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
  sent: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  paid: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  overdue: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  cancelled: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  void: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300',
}

const PAYMENT_STATUS_COLORS: Record<string, string> = {
  succeeded: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  refunded: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300',
}

function StatusBadge({ status, colors }: { status: string; colors: Record<string, string> }) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${colors[status] || colors.draft || 'bg-gray-100 text-gray-800'}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

// ─── Component ──────────────────────────────────────────────────────────

export default function BillingPage() {
  const { user } = useAuthStore()
  const isSuperAdmin = user?.role === 'super_admin'

  // Data state
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [payments, setPayments] = useState<PaymentRecord[]>([])
  const [stats, setStats] = useState<BillingStats | null>(null)
  const [loading, setLoading] = useState(true)

  // Tab state (super admin only)
  const [activeTab, setActiveTab] = useState<'invoices' | 'payments'>('invoices')

  // Filter state (super admin only)
  const [filterStatus, setFilterStatus] = useState('all')
  const [filterTenant, setFilterTenant] = useState('')
  const [filterDateFrom, setFilterDateFrom] = useState('')
  const [filterDateTo, setFilterDateTo] = useState('')

  // Modal state
  const [markPaidModal, setMarkPaidModal] = useState<Invoice | null>(null)
  const [markPaidForm, setMarkPaidForm] = useState({ payment_method: 'manual', reference: '', notes: '' })
  const [markPaidSaving, setMarkPaidSaving] = useState(false)

  const [bulkGenerateModal, setBulkGenerateModal] = useState(false)
  const [bulkForm, setBulkForm] = useState({ tenant_ids_str: '', period_start: '', period_end: '' })
  const [bulkGenerating, setBulkGenerating] = useState(false)

  const [deleteConfirm, setDeleteConfirm] = useState<Invoice | null>(null)
  const [deleting, setDeleting] = useState(false)

  const [payingInvoiceId, setPayingInvoiceId] = useState<number | null>(null)

  // Feedback
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Auto-clear messages
  useEffect(() => {
    if (success) { const t = setTimeout(() => setSuccess(null), 4000); return () => clearTimeout(t) }
  }, [success])
  useEffect(() => {
    if (error) { const t = setTimeout(() => setError(null), 6000); return () => clearTimeout(t) }
  }, [error])

  // ─── Data Fetching ──────────────────────────────────────────────────

  const fetchSuperAdminData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, any> = {}
      if (filterStatus && filterStatus !== 'all') params.status = filterStatus
      if (filterTenant) {
        const tenantId = parseInt(filterTenant, 10)
        if (!isNaN(tenantId)) params.tenant_id = tenantId
      }
      if (filterDateFrom) params.date_from = filterDateFrom
      if (filterDateTo) params.date_to = filterDateTo

      const [invoiceData, paymentData, statsData] = await Promise.all([
        billingApi.listInvoices(params),
        billingApi.listPayments(),
        billingApi.stats(),
      ])
      setInvoices(invoiceData.invoices || [])
      setPayments(paymentData.payments || [])
      setStats(statsData)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load billing data')
    } finally {
      setLoading(false)
    }
  }, [filterStatus, filterTenant, filterDateFrom, filterDateTo])

  const fetchTenantData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [invoiceData, paymentData] = await Promise.all([
        billingApi.myInvoices(),
        billingApi.myPayments(),
      ])
      setInvoices(invoiceData.invoices || [])
      setPayments(paymentData.payments || [])
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load billing data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isSuperAdmin) {
      fetchSuperAdminData()
    } else {
      fetchTenantData()
    }
  }, [isSuperAdmin, fetchSuperAdminData, fetchTenantData])

  // ─── Handlers ─────────────────────────────────────────────────────────

  const handleDownloadPdf = async (invoice: Invoice) => {
    try {
      const blob = isSuperAdmin
        ? await billingApi.downloadPdf(invoice.invoice_id)
        : await billingApi.myInvoicePdf(invoice.invoice_id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `invoice_${invoice.invoice_number}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to download invoice PDF')
    }
  }

  const handleMarkPaid = async () => {
    if (!markPaidModal) return
    setMarkPaidSaving(true)
    try {
      await billingApi.markPaid(markPaidModal.invoice_id, {
        payment_method: markPaidForm.payment_method,
        reference: markPaidForm.reference || undefined,
        notes: markPaidForm.notes || undefined,
      })
      setSuccess(`Invoice #${markPaidModal.invoice_number} marked as paid`)
      setMarkPaidModal(null)
      setMarkPaidForm({ payment_method: 'manual', reference: '', notes: '' })
      fetchSuperAdminData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to mark invoice as paid')
    } finally {
      setMarkPaidSaving(false)
    }
  }

  const handleBulkGenerate = async () => {
    setBulkGenerating(true)
    try {
      const tenantIds = bulkForm.tenant_ids_str
        .split(',')
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !isNaN(n))
      if (tenantIds.length === 0) {
        setError('Please provide at least one valid tenant ID')
        setBulkGenerating(false)
        return
      }
      if (!bulkForm.period_start || !bulkForm.period_end) {
        setError('Please provide both period start and end dates')
        setBulkGenerating(false)
        return
      }
      const result = await billingApi.bulkGenerate({
        tenant_ids: tenantIds,
        period_start: bulkForm.period_start,
        period_end: bulkForm.period_end,
      })
      const count = result.created || result.invoices?.length || tenantIds.length
      setSuccess(`${count} invoice(s) generated successfully`)
      setBulkGenerateModal(false)
      setBulkForm({ tenant_ids_str: '', period_start: '', period_end: '' })
      fetchSuperAdminData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate invoices')
    } finally {
      setBulkGenerating(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteConfirm) return
    setDeleting(true)
    try {
      await billingApi.softDelete(deleteConfirm.invoice_id)
      setSuccess(`Invoice #${deleteConfirm.invoice_number} deleted`)
      setDeleteConfirm(null)
      fetchSuperAdminData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete invoice')
    } finally {
      setDeleting(false)
    }
  }

  const handlePayOnline = async (invoice: Invoice) => {
    setPayingInvoiceId(invoice.invoice_id)
    try {
      const result = await billingApi.pay(invoice.invoice_id, {
        success_url: window.location.href,
        cancel_url: window.location.href,
      })
      if (result.checkout_url) {
        window.location.href = result.checkout_url
      } else {
        setSuccess('Payment initiated')
        fetchTenantData()
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to initiate payment')
    } finally {
      setPayingInvoiceId(null)
    }
  }

  const handleRefresh = () => {
    if (isSuperAdmin) {
      fetchSuperAdminData()
    } else {
      fetchTenantData()
    }
  }

  // ─── Render ───────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <Receipt className="w-7 h-7 text-emerald-500" />
            Billing
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {isSuperAdmin ? 'Manage invoices and payments across all tenants' : 'View your invoices and payment history'}
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Alerts */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-4 text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-200">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}
      {success && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 px-4 py-3 rounded-lg text-sm">
          {success}
        </div>
      )}

      {/* ═══ SUPER ADMIN VIEW ════════════════════════════════════════════ */}
      {isSuperAdmin ? (
        <>
          {/* Stats Cards */}
          {stats && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-5">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-amber-100 dark:bg-amber-900/40 rounded-lg">
                    <DollarSign className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-amber-600 dark:text-amber-400 uppercase tracking-wider">Outstanding</p>
                    <p className="text-xl font-bold text-amber-900 dark:text-amber-100 mt-0.5">{formatCents(stats.total_outstanding_cents)}</p>
                  </div>
                </div>
              </div>
              <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-5">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-green-100 dark:bg-green-900/40 rounded-lg">
                    <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-green-600 dark:text-green-400 uppercase tracking-wider">Collected This Month</p>
                    <p className="text-xl font-bold text-green-900 dark:text-green-100 mt-0.5">{formatCents(stats.collected_this_month_cents)}</p>
                  </div>
                </div>
              </div>
              <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-5">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-red-100 dark:bg-red-900/40 rounded-lg">
                    <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-red-600 dark:text-red-400 uppercase tracking-wider">Overdue Count</p>
                    <p className="text-xl font-bold text-red-900 dark:text-red-100 mt-0.5">{stats.overdue_count}</p>
                  </div>
                </div>
              </div>
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-5">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
                    <TrendingUp className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-blue-600 dark:text-blue-400 uppercase tracking-wider">MRR</p>
                    <p className="text-xl font-bold text-blue-900 dark:text-blue-100 mt-0.5">{formatCents(stats.mrr_cents)}</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Filter Bar */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-end gap-3 flex-wrap">
              <div className="flex-1 min-w-[140px]">
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Status</label>
                <select
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="all">All Statuses</option>
                  <option value="draft">Draft</option>
                  <option value="sent">Sent</option>
                  <option value="paid">Paid</option>
                  <option value="overdue">Overdue</option>
                  <option value="cancelled">Cancelled</option>
                  <option value="void">Void</option>
                </select>
              </div>
              <div className="flex-1 min-w-[140px]">
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Tenant ID</label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Filter by tenant ID..."
                    value={filterTenant}
                    onChange={(e) => setFilterTenant(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>
              </div>
              <div className="flex-1 min-w-[140px]">
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Date From</label>
                <input
                  type="date"
                  value={filterDateFrom}
                  onChange={(e) => setFilterDateFrom(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              <div className="flex-1 min-w-[140px]">
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Date To</label>
                <input
                  type="date"
                  value={filterDateTo}
                  onChange={(e) => setFilterDateTo(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              <button
                onClick={() => setBulkGenerateModal(true)}
                className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors whitespace-nowrap"
              >
                <Zap className="w-4 h-4" />
                Bulk Generate
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="border-b border-gray-200 dark:border-gray-700">
            <nav className="flex gap-6" aria-label="Tabs">
              <button
                onClick={() => setActiveTab('invoices')}
                className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'invoices'
                    ? 'border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400'
                    : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
                }`}
              >
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  Invoices
                  <span className="bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-xs font-medium px-2 py-0.5 rounded-full">
                    {invoices.length}
                  </span>
                </div>
              </button>
              <button
                onClick={() => setActiveTab('payments')}
                className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'payments'
                    ? 'border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400'
                    : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
                }`}
              >
                <div className="flex items-center gap-2">
                  <CreditCard className="w-4 h-4" />
                  Payments
                  <span className="bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-xs font-medium px-2 py-0.5 rounded-full">
                    {payments.length}
                  </span>
                </div>
              </button>
            </nav>
          </div>

          {/* Super Admin - Invoices Tab */}
          {activeTab === 'invoices' && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              {loading ? (
                <div className="flex items-center justify-center h-48">
                  <div className="text-gray-500 dark:text-gray-400">Loading invoices...</div>
                </div>
              ) : invoices.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 text-gray-500 dark:text-gray-400">
                  <FileText className="w-12 h-12 mb-3 opacity-40" />
                  <p className="text-lg font-medium">No invoices found</p>
                  <p className="text-sm mt-1">Use Bulk Generate to create invoices for tenants.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                    <thead className="bg-gray-50 dark:bg-gray-900/50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">#</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Tenant ID</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Period</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Amount</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Due Date</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {invoices.map((inv) => (
                        <tr key={inv.invoice_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                          <td className="px-4 py-3 text-sm font-mono font-medium text-gray-900 dark:text-white">
                            {inv.invoice_number}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                            {inv.tenant_id}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                            {formatPeriod(inv.period_start, inv.period_end)}
                          </td>
                          <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white text-right">
                            {formatCents(inv.total_cents)}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <StatusBadge status={inv.status} colors={STATUS_COLORS} />
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                            {inv.due_date ? new Date(inv.due_date).toLocaleDateString() : '--'}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                onClick={() => handleDownloadPdf(inv)}
                                className="p-1.5 text-gray-500 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                                title="Download PDF"
                              >
                                <Download className="w-4 h-4" />
                              </button>
                              {inv.status !== 'paid' && inv.status !== 'cancelled' && inv.status !== 'void' && (
                                <button
                                  onClick={() => {
                                    setMarkPaidModal(inv)
                                    setMarkPaidForm({ payment_method: 'manual', reference: '', notes: '' })
                                  }}
                                  className="p-1.5 text-gray-500 hover:text-green-600 dark:text-gray-400 dark:hover:text-green-400 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                                  title="Mark as Paid"
                                >
                                  <CheckCircle className="w-4 h-4" />
                                </button>
                              )}
                              <button
                                onClick={() => setDeleteConfirm(inv)}
                                className="p-1.5 text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                                title="Delete"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Super Admin - Payments Tab */}
          {activeTab === 'payments' && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              {loading ? (
                <div className="flex items-center justify-center h-48">
                  <div className="text-gray-500 dark:text-gray-400">Loading payments...</div>
                </div>
              ) : payments.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 text-gray-500 dark:text-gray-400">
                  <CreditCard className="w-12 h-12 mb-3 opacity-40" />
                  <p className="text-lg font-medium">No payments recorded</p>
                  <p className="text-sm mt-1">Payments will appear here when invoices are paid.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                    <thead className="bg-gray-50 dark:bg-gray-900/50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Date</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Invoice #</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Tenant</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Amount</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Method</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {payments.map((pmt) => (
                        <tr key={pmt.payment_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                          <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                            {pmt.created_at ? new Date(pmt.created_at).toLocaleDateString() : '--'}
                          </td>
                          <td className="px-4 py-3 text-sm font-mono text-gray-900 dark:text-white">
                            {pmt.invoice_id || '--'}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                            {pmt.tenant_id}
                          </td>
                          <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white text-right">
                            {formatCents(pmt.amount_cents)}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 capitalize">
                            {pmt.payment_method.replace('_', ' ')}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <StatusBadge status={pmt.status} colors={PAYMENT_STATUS_COLORS} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      ) : (
        /* ═══ TENANT USER VIEW ══════════════════════════════════════════ */
        <>
          {/* My Invoices */}
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
              <FileText className="w-5 h-5 text-gray-500" />
              My Invoices
            </h2>
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              {loading ? (
                <div className="flex items-center justify-center h-48">
                  <div className="text-gray-500 dark:text-gray-400">Loading invoices...</div>
                </div>
              ) : invoices.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 text-gray-500 dark:text-gray-400">
                  <FileText className="w-12 h-12 mb-3 opacity-40" />
                  <p className="text-lg font-medium">No invoices</p>
                  <p className="text-sm mt-1">Your invoices will appear here.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                    <thead className="bg-gray-50 dark:bg-gray-900/50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">#</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Period</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Amount</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Due Date</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {invoices.map((inv) => (
                        <tr key={inv.invoice_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                          <td className="px-4 py-3 text-sm font-mono font-medium text-gray-900 dark:text-white">
                            {inv.invoice_number}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                            {formatPeriod(inv.period_start, inv.period_end)}
                          </td>
                          <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white text-right">
                            {formatCents(inv.total_cents)}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <StatusBadge status={inv.status} colors={STATUS_COLORS} />
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                            {inv.due_date ? new Date(inv.due_date).toLocaleDateString() : '--'}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                onClick={() => handleDownloadPdf(inv)}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors"
                                title="Download PDF"
                              >
                                <Download className="w-3.5 h-3.5" />
                                PDF
                              </button>
                              {inv.status !== 'paid' && inv.status !== 'cancelled' && inv.status !== 'void' && (
                                <button
                                  onClick={() => handlePayOnline(inv)}
                                  disabled={payingInvoiceId === inv.invoice_id}
                                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50"
                                  title="Pay Online"
                                >
                                  {payingInvoiceId === inv.invoice_id ? (
                                    <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24">
                                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                    </svg>
                                  ) : (
                                    <CreditCard className="w-3.5 h-3.5" />
                                  )}
                                  Pay Online
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

          {/* Payment History */}
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
              <CreditCard className="w-5 h-5 text-gray-500" />
              Payment History
            </h2>
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              {loading ? (
                <div className="flex items-center justify-center h-48">
                  <div className="text-gray-500 dark:text-gray-400">Loading payments...</div>
                </div>
              ) : payments.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 text-gray-500 dark:text-gray-400">
                  <CreditCard className="w-12 h-12 mb-3 opacity-40" />
                  <p className="text-lg font-medium">No payment history</p>
                  <p className="text-sm mt-1">Your payments will appear here after you pay an invoice.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                    <thead className="bg-gray-50 dark:bg-gray-900/50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Date</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Invoice</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Amount</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Method</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {payments.map((pmt) => (
                        <tr key={pmt.payment_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                          <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                            {pmt.created_at ? new Date(pmt.created_at).toLocaleDateString() : '--'}
                          </td>
                          <td className="px-4 py-3 text-sm font-mono text-gray-900 dark:text-white">
                            {pmt.invoice_id || '--'}
                          </td>
                          <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white text-right">
                            {formatCents(pmt.amount_cents)}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 capitalize">
                            {pmt.payment_method.replace('_', ' ')}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <StatusBadge status={pmt.status} colors={PAYMENT_STATUS_COLORS} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {/* ═══ MODALS ═════════════════════════════════════════════════════ */}

      {/* Mark as Paid Modal */}
      <Modal
        open={!!markPaidModal}
        onClose={() => { setMarkPaidModal(null); setMarkPaidForm({ payment_method: 'manual', reference: '', notes: '' }) }}
        title={`Mark Invoice #${markPaidModal?.invoice_number || ''} as Paid`}
        size="md"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Payment Method</label>
            <select
              value={markPaidForm.payment_method}
              onChange={(e) => setMarkPaidForm({ ...markPaidForm, payment_method: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="manual">Manual</option>
              <option value="bank_transfer">Bank Transfer</option>
              <option value="check">Check</option>
              <option value="card">Card</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Reference</label>
            <input
              type="text"
              value={markPaidForm.reference}
              onChange={(e) => setMarkPaidForm({ ...markPaidForm, reference: e.target.value })}
              placeholder="Payment reference or transaction ID"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Notes</label>
            <textarea
              value={markPaidForm.notes}
              onChange={(e) => setMarkPaidForm({ ...markPaidForm, notes: e.target.value })}
              placeholder="Optional notes about this payment"
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
            />
          </div>
          {markPaidModal && (
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Amount: <span className="font-semibold text-gray-900 dark:text-white">{formatCents(markPaidModal.total_cents)}</span>
              </p>
            </div>
          )}
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={() => { setMarkPaidModal(null); setMarkPaidForm({ payment_method: 'manual', reference: '', notes: '' }) }}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleMarkPaid}
              disabled={markPaidSaving}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50"
            >
              {markPaidSaving ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Saving...
                </>
              ) : (
                <>
                  <CheckCircle className="w-4 h-4" />
                  Mark as Paid
                </>
              )}
            </button>
          </div>
        </div>
      </Modal>

      {/* Bulk Generate Modal */}
      <Modal
        open={bulkGenerateModal}
        onClose={() => { setBulkGenerateModal(false); setBulkForm({ tenant_ids_str: '', period_start: '', period_end: '' }) }}
        title="Bulk Generate Invoices"
        size="md"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tenant IDs</label>
            <input
              type="text"
              value={bulkForm.tenant_ids_str}
              onChange={(e) => setBulkForm({ ...bulkForm, tenant_ids_str: e.target.value })}
              placeholder="e.g. 1, 2, 5, 12"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Comma-separated list of tenant IDs to generate invoices for.</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Period Start</label>
              <input
                type="date"
                value={bulkForm.period_start}
                onChange={(e) => setBulkForm({ ...bulkForm, period_start: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Period End</label>
              <input
                type="date"
                value={bulkForm.period_end}
                onChange={(e) => setBulkForm({ ...bulkForm, period_end: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={() => { setBulkGenerateModal(false); setBulkForm({ tenant_ids_str: '', period_start: '', period_end: '' }) }}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleBulkGenerate}
              disabled={bulkGenerating || !bulkForm.tenant_ids_str.trim() || !bulkForm.period_start || !bulkForm.period_end}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {bulkGenerating ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Generating...
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  Generate Invoices
                </>
              )}
            </button>
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50" onClick={() => setDeleteConfirm(null)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-full">
                <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Delete Invoice</h3>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
              Are you sure you want to delete invoice <strong className="text-gray-900 dark:text-white">#{deleteConfirm.invoice_number}</strong>?
              This will archive the invoice and it will no longer appear in listings.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50"
              >
                {deleting ? (
                  <>
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Deleting...
                  </>
                ) : (
                  <>
                    <Trash2 className="w-4 h-4" />
                    Delete Invoice
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
