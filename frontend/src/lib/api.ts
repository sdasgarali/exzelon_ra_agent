import axios from 'axios'
import { useAuthStore } from './store'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  paramsSerializer: (params) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([key, val]) => {
      if (val === undefined || val === null || val === '') return
      if (Array.isArray(val)) {
        val.forEach(v => qs.append(key, String(v)))
      } else {
        qs.append(key, String(val))
      }
    })
    return qs.toString()
  },
})

// Request deduplication - cancel duplicate in-flight requests
const pendingRequests = new Map<string, AbortController>()

function getRequestKey(config: any): string {
  return `${config.method}:${config.url}:${JSON.stringify(config.params || {})}`
}

// Add auth token to requests + deduplicate GET requests + inject X-Tenant-ID for impersonation
api.interceptors.request.use((config) => {
  const { token, impersonation } = useAuthStore.getState()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  if (impersonation?.tenantId) {
    config.headers['X-Tenant-ID'] = String(impersonation.tenantId)
  }

  // Only deduplicate GET requests
  if (config.method?.toLowerCase() === 'get') {
    const key = getRequestKey(config)
    const existing = pendingRequests.get(key)
    if (existing) {
      existing.abort()
    }
    const controller = new AbortController()
    config.signal = controller.signal
    pendingRequests.set(key, controller)
  }

  return config
})

// Silent refresh state — prevents concurrent refresh attempts
let isRefreshing = false
let failedQueue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = []

function processQueue(error: unknown, token: string | null) {
  failedQueue.forEach((p) => {
    if (token) p.resolve(token)
    else p.reject(error)
  })
  failedQueue = []
}

// Handle 401 errors + silent token refresh + clean up pending requests
api.interceptors.response.use(
  (response) => {
    const key = getRequestKey(response.config)
    pendingRequests.delete(key)
    return response
  },
  async (error) => {
    if (error.config) {
      const key = getRequestKey(error.config)
      pendingRequests.delete(key)
    }

    const originalRequest = error.config
    const isLoginRequest = originalRequest?.url?.includes('/auth/login')
    const isRefreshRequest = originalRequest?.url?.includes('/auth/refresh')

    if (error.response?.status === 401 && !isLoginRequest && !isRefreshRequest && !originalRequest._retry) {
      const { refreshToken } = useAuthStore.getState()

      if (refreshToken) {
        if (isRefreshing) {
          // Queue this request until refresh completes
          return new Promise((resolve, reject) => {
            failedQueue.push({
              resolve: (newToken: string) => {
                originalRequest.headers.Authorization = `Bearer ${newToken}`
                originalRequest._retry = true
                resolve(api(originalRequest))
              },
              reject,
            })
          })
        }

        isRefreshing = true
        try {
          const resp = await axios.post(`${API_URL}/auth/refresh`, { refresh_token: refreshToken })
          const { access_token, refresh_token: newRefresh, user } = resp.data
          useAuthStore.getState().setAuth(access_token, user, newRefresh)
          processQueue(null, access_token)

          // Retry original request with new token
          originalRequest.headers.Authorization = `Bearer ${access_token}`
          originalRequest._retry = true
          return api(originalRequest)
        } catch (refreshError) {
          processQueue(refreshError, null)
          useAuthStore.getState().logout()
          window.location.href = '/login'
          return Promise.reject(refreshError)
        } finally {
          isRefreshing = false
        }
      }

      // No refresh token — redirect to login
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }

    return Promise.reject(error)
  }
)

// Auth API
export const authApi = {
  login: async (email: string, password: string) => {
    const formData = new URLSearchParams()
    formData.append('username', email)
    formData.append('password', password)
    const response = await api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    return response.data
  },
  register: async (data: { email: string; password: string; full_name?: string }) => {
    const response = await api.post('/auth/register', data)
    return response.data
  },
  me: async () => {
    const response = await api.get('/auth/me')
    return response.data
  },
  signup: async (data: { email: string; password: string; full_name: string; company_name: string }) => {
    const response = await api.post('/auth/signup', data)
    return response.data
  },
  verify: async (token: string) => {
    const response = await api.get('/auth/verify', { params: { token } })
    return response.data
  },
  resendVerification: async (email: string) => {
    const response = await api.post('/auth/resend-verification', { email })
    return response.data
  },
  forgotPassword: async (email: string) => {
    const response = await api.post('/auth/forgot-password', { email })
    return response.data
  },
  resetPassword: async (token: string, new_password: string) => {
    const response = await api.post('/auth/reset-password', { token, new_password })
    return response.data
  },
}

// Leads API
export const leadsApi = {
  list: async (params?: Record<string, any>) => {
    const response = await api.get('/leads', { params })
    return response.data
  },
  get: async (id: number) => {
    const response = await api.get(`/leads/${id}`)
    return response.data
  },
  create: async (data: any) => {
    const response = await api.post('/leads', data)
    return response.data
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/leads/${id}`, data)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/leads/${id}`)
  },
  stats: async (params?: Record<string, any>) => {
    const response = await api.get('/leads/stats', { params })
    return response.data
  },
  listWithContactCounts: async (params?: Record<string, any>) => {
    const response = await api.get('/leads/with-contact-counts', { params })
    return response.data
  },
  getDetail: async (id: number) => {
    const response = await api.get(`/leads/${id}/detail`)
    return response.data
  },
  manageContacts: async (id: number, data: { add_contact_ids?: number[]; remove_contact_ids?: number[] }) => {
    const response = await api.post(`/leads/${id}/contacts`, data)
    return response.data
  },
  runOutreach: async (id: number, dryRun: boolean = true) => {
    const response = await api.post(`/leads/${id}/outreach`, null, { params: { dry_run: dryRun } })
    return response.data
  },
  bulkOutreach: async (leadIds: number[], dryRun: boolean = true) => {
    const response = await api.post('/leads/bulk/outreach', { lead_ids: leadIds, dry_run: dryRun })
    return response.data
  },
  previewOutreach: async (leadIds: number[]) => {
    const response = await api.post('/leads/bulk/outreach/preview', { lead_ids: leadIds })
    return response.data
  },
  bulkEnrichPreview: async (leadIds: number[]) => {
    const response = await api.post('/leads/bulk/enrich/preview', { lead_ids: leadIds })
    return response.data
  },
  bulkEnrich: async (leadIds: number[]) => {
    const response = await api.post('/leads/bulk/enrich', { lead_ids: leadIds })
    return response.data
  },
  bulkUpdateStatus: async (leadIds: number[], status: string) => {
    const response = await api.put('/leads/bulk/status', { lead_ids: leadIds, status })
    return response.data
  },
  bulkUnarchive: async (leadIds: number[]) => {
    const response = await api.put('/leads/bulk/unarchive', { lead_ids: leadIds })
    return response.data
  },
  bulkUpdate: async (leadIds: number[], updates: Record<string, any>) => {
    const response = await api.put('/leads/bulk/update', { lead_ids: leadIds, updates })
    return response.data
  },
  filterOptions: async () => {
    const response = await api.get('/leads/filter-options')
    return response.data
  },
  campaignEligible: async (leadIds: number[]) => {
    const params = new URLSearchParams()
    leadIds.forEach(id => params.append('lead_ids', String(id)))
    const response = await api.get(`/leads/campaign-eligible?${params.toString()}`)
    return response.data
  },
  importPreview: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post('/leads/import/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },
  importCsv: async (file: File, skipDuplicates: boolean = true) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post('/leads/import/csv', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { skip_duplicates: skipDuplicates },
    })
    return response.data
  },
  importGoogleSheetPreview: async (sheetUrl: string) => {
    const response = await api.post('/leads/import/google-sheet/preview', { sheet_url: sheetUrl })
    return response.data
  },
  importGoogleSheet: async (sheetUrl: string, skipDuplicates: boolean = true) => {
    const response = await api.post('/leads/import/google-sheet', { sheet_url: sheetUrl, skip_duplicates: skipDuplicates })
    return response.data
  },
  downloadTemplate: async () => {
    const response = await api.get('/leads/import/template', { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = 'lead_import_template.csv'
    a.click()
    window.URL.revokeObjectURL(url)
  },
}

// Clients API
export const clientsApi = {
  list: async (params?: Record<string, any>) => {
    const response = await api.get('/clients', { params })
    return response.data
  },
  get: async (id: number) => {
    const response = await api.get(`/clients/${id}`)
    return response.data
  },
  create: async (data: any) => {
    const response = await api.post('/clients', data)
    return response.data
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/clients/${id}`, data)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/clients/${id}`)
  },
  bulkDelete: async (ids: number[]) => {
    const response = await api.delete('/clients/bulk', { data: { client_ids: ids } })
    return response.data
  },
  exportCsv: async (params?: Record<string, any>) => {
    const response = await api.get('/clients/export/csv', { params, responseType: 'blob' })
    return response.data
  },
  filterOptions: async () => {
    const response = await api.get('/clients/filter-options')
    return response.data
  },
  enrich: async (id: number) => {
    const response = await api.post(`/clients/${id}/enrich`)
    return response.data
  },
  bulkEnrich: async (ids: number[]) => {
    const response = await api.post('/clients/bulk/enrich', { client_ids: ids })
    return response.data
  },
  bulkUpdate: async (ids: number[], updates: Record<string, any>) => {
    const response = await api.put('/clients/bulk/update', { client_ids: ids, updates })
    return response.data
  },
}

// Contacts API
export const contactsApi = {
  list: async (params?: Record<string, any>) => {
    const response = await api.get('/contacts', { params })
    return response.data
  },
  get: async (id: number) => {
    const response = await api.get(`/contacts/${id}`)
    return response.data
  },
  create: async (data: any) => {
    const response = await api.post('/contacts', data)
    return response.data
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/contacts/${id}`, data)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/contacts/${id}`)
  },
  databaseSearch: async (data: { job_title?: string; company?: string; industry?: string; location?: string; limit?: number }) => {
    const response = await api.post('/leads/database-search', data)
    return response.data
  },
  replyPrediction: async (id: number) => {
    const response = await api.get(`/contacts/${id}/reply-prediction`)
    return response.data
  },
  bulkUpdate: async (ids: number[], updates: Record<string, any>) => {
    const response = await api.put('/contacts/bulk/update', { contact_ids: ids, updates })
    return response.data
  },
  bulkRestore: async (ids: number[]) => {
    const response = await api.put('/contacts/bulk/restore', { contact_ids: ids })
    return response.data
  },
}

// Dashboard API
export const dashboardApi = {
  kpis: async (params?: Record<string, any>) => {
    const response = await api.get('/dashboard/kpis', { params })
    return response.data
  },
  leadsSourced: async (params?: Record<string, any>) => {
    const response = await api.get('/dashboard/leads-sourced', { params })
    return response.data
  },
  contactsIdentified: async (params?: Record<string, any>) => {
    const response = await api.get('/dashboard/contacts-identified', { params })
    return response.data
  },
  outreachSent: async (params?: Record<string, any>) => {
    const response = await api.get('/dashboard/outreach-sent', { params })
    return response.data
  },
  clientCategories: async () => {
    const response = await api.get('/dashboard/client-categories')
    return response.data
  },
  trends: async (days?: number) => {
    const response = await api.get('/dashboard/trends', { params: { days } })
    return response.data
  },
  stats: async () => {
    const response = await api.get('/dashboard/stats')
    return response.data
  },
}

// Pipelines API
export const pipelinesApi = {
  runs: async (params?: Record<string, any>) => {
    const response = await api.get('/pipelines/runs', { params })
    return response.data
  },
  runLeadSourcing: async (sources: string[]) => {
    const response = await api.post('/pipelines/lead-sourcing/run', null, {
      params: { sources },
    })
    return response.data
  },
  runContactEnrichment: async (leadIds?: number[]) => {
    const response = await api.post('/pipelines/contact-enrichment/run',
      leadIds ? { lead_ids: leadIds } : undefined)
    return response.data
  },
  estimateContactEnrichment: async () => {
    const response = await api.get('/pipelines/contact-enrichment/estimate')
    return response.data
  },
  runEmailValidation: async () => {
    const response = await api.post('/pipelines/email-validation/run')
    return response.data
  },
  runOutreach: async (mode: string, dryRun: boolean = false, leadIds?: number[]) => {
    const response = await api.post('/pipelines/outreach/run',
      leadIds ? { lead_ids: leadIds } : undefined,
      { params: { mode, dry_run: dryRun } })
    return response.data
  },
  downloadExport: async (runId: number) => {
    const response = await api.get(`/pipelines/runs/${runId}/download`, {
      responseType: 'blob',
    })
    // Validate we got actual CSV data, not an error JSON wrapped in a blob
    const blob = response.data as Blob
    if (blob.size === 0) {
      throw new Error('Downloaded file is empty')
    }
    if (blob.type && blob.type.includes('application/json')) {
      const text = await blob.text()
      const err = JSON.parse(text)
      throw new Error(err.detail || 'Download failed')
    }
    const url = window.URL.createObjectURL(new Blob([blob]))
    const link = document.createElement('a')
    link.href = url
    const disposition = response.headers['content-disposition']
    const filename = disposition
      ? disposition.split('filename=')[1]?.replace(/"/g, '')
      : `mailmerge_export_${runId}.csv`
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },
  getRunDetail: async (runId: number) => {
    const response = await api.get(`/pipelines/runs/${runId}`)
    return response.data
  },
  cancelJob: async (runId: number) => {
    const response = await api.post(`/pipelines/jobs/${runId}/cancel`)
    return response.data
  },
  runEmailValidationSelected: async (contactIds: number[]) => {
    const response = await api.post('/pipelines/email-validation/run-selected', {
      contact_ids: contactIds,
    })
    return response.data
  },
  getRunSummary: async (runId: number, regenerate: boolean = false) => {
    const response = await api.get(`/pipelines/runs/${runId}/summary`, {
      params: regenerate ? { regenerate: true } : undefined,
    })
    return response.data
  },
  getFeatureStatus: async () => {
    const response = await api.get('/pipelines/feature-status')
    return response.data
  },
  getBusinessRules: async () => {
    const response = await api.get('/pipelines/business-rules')
    return response.data
  },
}

// Settings API
export const settingsApi = {
  list: async () => {
    const response = await api.get('/settings')
    return response.data
  },
  get: async (key: string) => {
    const response = await api.get(`/settings/${key}`)
    return response.data
  },
  update: async (key: string, data: any) => {
    const response = await api.put(`/settings/${key}`, data)
    return response.data
  },
  initialize: async () => {
    const response = await api.post('/settings/initialize')
    return response.data
  },
  testConnection: async (provider: string) => {
    const response = await api.post(`/settings/test-connection/${provider}`)
    return response.data
  },
  getMySettingsTabPermissions: async (): Promise<Record<string, string>> => {
    const response = await api.get('/settings/my-permissions/settings-tabs')
    return response.data
  },
  getMyPermissions: async (): Promise<Record<string, string>> => {
    const response = await api.get('/settings/my-permissions')
    return response.data
  },
  getCompanyProfile: async () => {
    const response = await api.get('/settings/company-profile')
    return response.data
  },
  updateCompanyProfile: async (data: { name?: string; website?: string; industry?: string; company_address?: string }) => {
    const response = await api.put('/settings/company-profile', data)
    return response.data
  },
}

// Mailboxes API
export const mailboxesApi = {
  list: async (params?: Record<string, any>) => {
    const response = await api.get('/mailboxes', { params })
    return response.data
  },
  get: async (id: number) => {
    const response = await api.get(`/mailboxes/${id}`)
    return response.data
  },
  create: async (data: any) => {
    const response = await api.post('/mailboxes', data)
    return response.data
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/mailboxes/${id}`, data)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/mailboxes/${id}`)
  },
  restore: async (id: number) => {
    const response = await api.post(`/mailboxes/${id}/restore`)
    return response.data
  },
  permanentDelete: async (id: number) => {
    await api.delete(`/mailboxes/${id}/permanent`)
  },
  stats: async () => {
    const response = await api.get('/mailboxes/stats')
    return response.data
  },
  testConnection: async (id: number) => {
    const response = await api.post(`/mailboxes/${id}/test-connection`)
    return response.data
  },
  testNewConnection: async (data: any) => {
    const response = await api.post('/mailboxes/test-connection', data)
    return response.data
  },
  updateStatus: async (id: number, status: string) => {
    const response = await api.post(`/mailboxes/${id}/update-status`, null, {
      params: { new_status: status }
    })
    return response.data
  },
  resetDailyCounts: async () => {
    const response = await api.post('/mailboxes/reset-daily-counts')
    return response.data
  },
  getAvailable: async (count: number = 1) => {
    const response = await api.get('/mailboxes/available/for-sending', {
      params: { count }
    })
    return response.data
  },
  getDetail: async (id: number) => {
    const response = await api.get(`/mailboxes/${id}/detail`)
    return response.data
  },
  oauthInitiate: async (mailboxId?: number, email?: string) => {
    const response = await api.get('/mailboxes/oauth/initiate', {
      params: { mailbox_id: mailboxId, email }
    })
    return response.data
  },
  oauthCallback: async (code: string, state: string) => {
    const response = await api.post('/mailboxes/oauth/callback', { code, state })
    return response.data
  },
  bulkUpdate: async (ids: number[], updates: Record<string, any>) => {
    const response = await api.put('/mailboxes/bulk/update', { mailbox_ids: ids, updates })
    return response.data
  },
}

// Outreach Roles API
export const outreachRolesApi = {
  list: async () => {
    const response = await api.get('/outreach-roles')
    return response.data
  },
  create: async (data: { role_name: string; description?: string }) => {
    const response = await api.post('/outreach-roles', data)
    return response.data
  },
  update: async (id: number, data: { role_name?: string; description?: string }) => {
    const response = await api.put(`/outreach-roles/${id}`, data)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/outreach-roles/${id}`)
  },
}

// Warmup Engine API
export const warmupApi = {
  getStatus: async () => {
    const response = await api.get('/warmup/status')
    return response.data
  },
  getConfig: async () => {
    const response = await api.get('/warmup/config')
    return response.data
  },
  updateConfig: async (data: any) => {
    const response = await api.put('/warmup/config', data)
    return response.data
  },
  assessAll: async () => {
    const response = await api.post('/warmup/assess')
    return response.data
  },
  assessMailbox: async (id: number) => {
    const response = await api.post(`/warmup/assess/${id}`)
    return response.data
  },
  getSchedule: async () => {
    const response = await api.get('/warmup/schedule')
    return response.data
  },
  getHealthScores: async () => {
    const response = await api.get('/warmup/health-scores')
    return response.data
  },
  // Enterprise Warmup API
  triggerPeerWarmup: async (mailboxId?: number) => {
    const response = await api.post('/warmup/peer/send', null, { params: mailboxId ? { mailbox_id: mailboxId } : {} })
    return response.data
  },
  getPeerHistory: async (page: number = 1, limit: number = 50, mailboxId?: number, direction?: string) => {
    const params: Record<string, any> = { page, limit }
    if (mailboxId) params.mailbox_id = mailboxId
    if (direction) params.direction = direction
    const response = await api.get('/warmup/peer/history', { params })
    return response.data
  },
  getPeerEmailDetail: async (emailId: number) => {
    const response = await api.get(`/warmup/peer/history/${emailId}`)
    return response.data
  },
  getAnalytics: async (days?: number, mailboxId?: number) => {
    const response = await api.get('/warmup/analytics', { params: { days, mailbox_id: mailboxId } })
    return response.data
  },
  runDnsCheck: async (mailboxId?: number) => {
    const response = await api.post('/warmup/dns-check', null, { params: mailboxId ? { mailbox_id: mailboxId } : {} })
    return response.data
  },
  getDnsResults: async (mailboxId: number) => {
    const response = await api.get(`/warmup/dns/${mailboxId}`)
    return response.data
  },
  runBlacklistCheck: async (mailboxId?: number) => {
    const response = await api.post('/warmup/blacklist-check', null, { params: mailboxId ? { mailbox_id: mailboxId } : {} })
    return response.data
  },
  getBlacklistResults: async (mailboxId: number) => {
    const response = await api.get(`/warmup/blacklist/${mailboxId}`)
    return response.data
  },
  runPlacementTest: async (mailboxId: number) => {
    const response = await api.post(`/warmup/placement-test/${mailboxId}`)
    return response.data
  },
  getAlerts: async (params?: Record<string, any>) => {
    const response = await api.get('/warmup/alerts', { params })
    return response.data
  },
  markAlertRead: async (id: number) => {
    const response = await api.put(`/warmup/alerts/${id}/read`)
    return response.data
  },
  markAllAlertsRead: async () => {
    const response = await api.put('/warmup/alerts/read-all')
    return response.data
  },
  getUnreadCount: async () => {
    const response = await api.get('/warmup/alerts/unread-count')
    return response.data
  },
  getProfiles: async () => {
    const response = await api.get('/warmup/profiles')
    return response.data
  },
  createProfile: async (data: any) => {
    const response = await api.post('/warmup/profiles', data)
    return response.data
  },
  updateProfile: async (id: number, data: any) => {
    const response = await api.put(`/warmup/profiles/${id}`, data)
    return response.data
  },
  deleteProfile: async (id: number) => {
    const response = await api.delete(`/warmup/profiles/${id}`)
    return response.data
  },
  applyProfile: async (profileId: number, mailboxId: number) => {
    const response = await api.post(`/warmup/profiles/${profileId}/apply/${mailboxId}`)
    return response.data
  },
  startRecovery: async (mailboxId: number) => {
    const response = await api.post(`/warmup/recovery/${mailboxId}/start`)
    return response.data
  },
  exportReport: async (format: string = 'csv', params?: Record<string, any>) => {
    const response = await api.get('/warmup/export', { params: { format, ...params }, responseType: format === 'csv' ? 'blob' : 'json' })
    return response.data
  },
  getSchedulerStatus: async () => {
    const response = await api.get('/warmup/scheduler/status')
    return response.data
  },
}


// Email Templates API
export const templatesApi = {
  list: async (params?: Record<string, any>) => {
    const response = await api.get('/templates', { params })
    return response.data
  },
  get: async (id: number) => {
    const response = await api.get(`/templates/${id}`)
    return response.data
  },
  getActive: async () => {
    const response = await api.get('/templates/active')
    return response.data
  },
  create: async (data: any) => {
    const response = await api.post('/templates', data)
    return response.data
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/templates/${id}`, data)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/templates/${id}`)
  },
  activate: async (id: number) => {
    const response = await api.post(`/templates/${id}/activate`)
    return response.data
  },
  preview: async (id: number) => {
    const response = await api.post(`/templates/${id}/preview`)
    return response.data
  },
  seedLibrary: async () => {
    const response = await api.post('/templates/seed-library')
    return response.data
  },
  importToStep: async (templateId: number, stepId: number) => {
    const response = await api.post(`/templates/${templateId}/import-to-step`, null, { params: { step_id: stepId } })
    return response.data
  },
  score: async (data: { subject: string; body_html: string; body_text?: string }) => {
    const response = await api.post('/templates/score', data)
    return response.data
  },
  fixes: async (data: { subject: string; body_html: string; body_text?: string }) => {
    const response = await api.post('/templates/fixes', data)
    return response.data
  },
  applyFixes: async (data: { subject: string; body_html: string; body_text?: string; fix_ids: string[] }) => {
    const response = await api.post('/templates/apply-fixes', data)
    return response.data
  },
}

// Users API (Admin+)
export const usersApi = {
  list: async (params?: Record<string, any>) => {
    const response = await api.get('/users', { params })
    return response.data
  },
  get: async (id: number) => {
    const response = await api.get(`/users/${id}`)
    return response.data
  },
  create: async (data: { email: string; password: string; full_name?: string; role?: string; is_active?: boolean }) => {
    const response = await api.post('/users', data)
    return response.data
  },
  update: async (id: number, data: Record<string, any>) => {
    const response = await api.put(`/users/${id}`, data)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/users/${id}`)
  },
}

// Backups API (admin+ for list/create/download, super_admin for delete/restore)
export const backupsApi = {
  list: async () => {
    const response = await api.get('/backups')
    return response.data
  },
  create: async () => {
    const response = await api.post('/backups')
    return response.data
  },
  download: async (filename: string) => {
    const response = await api.get(`/backups/${filename}/download`, { responseType: 'blob' })
    return response.data
  },
  delete: async (filename: string) => {
    const response = await api.delete(`/backups/${filename}`)
    return response.data
  },
  restore: async (filename: string) => {
    const response = await api.post(`/backups/${filename}/restore`, { confirm: true })
    return response.data
  },
}

// Outreach API
export const outreachApi = {
  listEvents: async (params?: Record<string, any>) => {
    const response = await api.get("/outreach/events", { params })
    return response.data
  },
  getEvent: async (eventId: number) => {
    const response = await api.get(`/outreach/events/${eventId}`)
    return response.data
  },
  getThread: async (eventId: number) => {
    const response = await api.get(`/outreach/events/${eventId}/thread`)
    return response.data
  },
  checkReplies: async () => {
    const response = await api.post("/outreach/check-replies")
    return response.data
  },
  getStats: async () => {
    const response = await api.get("/outreach/stats/summary")
    return response.data
  },
  deleteEvents: async (eventIds: number[]) => {
    const response = await api.delete("/outreach/events/bulk", { data: { event_ids: eventIds } })
    return response.data
  },
}

// Campaigns API
export const campaignsApi = {
  list: async (params?: Record<string, any>) => {
    const response = await api.get('/campaigns', { params })
    return response.data
  },
  get: async (id: number) => {
    const response = await api.get(`/campaigns/${id}`)
    return response.data
  },
  create: async (data: any) => {
    const response = await api.post('/campaigns', data)
    return response.data
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/campaigns/${id}`, data)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/campaigns/${id}`)
  },
  bulkArchive: async (ids: number[]) => {
    const response = await api.post('/campaigns/bulk-archive', { campaign_ids: ids })
    return response.data
  },
  activate: async (id: number) => {
    const response = await api.post(`/campaigns/${id}/activate`)
    return response.data
  },
  pause: async (id: number) => {
    const response = await api.post(`/campaigns/${id}/pause`)
    return response.data
  },
  resume: async (id: number) => {
    const response = await api.post(`/campaigns/${id}/resume`)
    return response.data
  },
  complete: async (id: number) => {
    const response = await api.post(`/campaigns/${id}/complete`)
    return response.data
  },
  duplicate: async (id: number) => {
    const response = await api.post(`/campaigns/${id}/duplicate`)
    return response.data
  },
  // Steps
  listSteps: async (campaignId: number) => {
    const response = await api.get(`/campaigns/${campaignId}/steps`)
    return response.data
  },
  addStep: async (campaignId: number, data: any) => {
    const response = await api.post(`/campaigns/${campaignId}/steps`, data)
    return response.data
  },
  updateStep: async (campaignId: number, stepId: number, data: any) => {
    const response = await api.put(`/campaigns/${campaignId}/steps/${stepId}`, data)
    return response.data
  },
  deleteStep: async (campaignId: number, stepId: number) => {
    await api.delete(`/campaigns/${campaignId}/steps/${stepId}`)
  },
  reorderSteps: async (campaignId: number, stepIds: number[]) => {
    const response = await api.put(`/campaigns/${campaignId}/steps/reorder`, { step_ids: stepIds })
    return response.data
  },
  // Contacts
  listContacts: async (campaignId: number, params?: Record<string, any>) => {
    const response = await api.get(`/campaigns/${campaignId}/contacts`, { params })
    return response.data
  },
  enrollContacts: async (campaignId: number, contactIds: number[], leadId?: number) => {
    const response = await api.post(`/campaigns/${campaignId}/contacts`, { contact_ids: contactIds, lead_id: leadId })
    return response.data
  },
  removeContacts: async (campaignId: number, contactIds: number[]) => {
    const response = await api.delete(`/campaigns/${campaignId}/contacts`, { data: { contact_ids: contactIds } })
    return response.data
  },
  // Analytics
  analytics: async (id: number, dateFrom?: string, dateTo?: string) => {
    const params: Record<string, string> = {}
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    const response = await api.get(`/campaigns/${id}/analytics`, { params })
    return response.data
  },
  dailyAnalytics: async (id: number, days = 30) => {
    const response = await api.get(`/campaigns/${id}/analytics/daily`, { params: { days } })
    return response.data
  },
  exportCsv: async (id: number) => {
    const response = await api.get(`/campaigns/${id}/analytics/export`, { responseType: 'blob' })
    return response.data
  },
  health: async (id: number) => {
    const response = await api.get(`/campaigns/${id}/health`)
    return response.data
  },
  compare: async (campaignIds: number[]) => {
    const response = await api.post('/campaigns/compare', { campaign_ids: campaignIds })
    return response.data
  },
  abStats: async (campaignId: number, stepId: number) => {
    const response = await api.get(`/campaigns/${campaignId}/steps/${stepId}/ab-stats`)
    return response.data
  },
  abOptimize: async (campaignId: number, stepId: number) => {
    const response = await api.post(`/campaigns/${campaignId}/steps/${stepId}/ab-optimize`)
    return response.data
  },
  abResults: async (campaignId: number, stepId: number) => {
    const response = await api.get(`/campaigns/${campaignId}/steps/${stepId}/ab-results`)
    return response.data
  },
  // Activity feed
  activity: async (campaignId: number, params?: { limit?: number; offset?: number; event_type?: string }) => {
    const response = await api.get(`/campaigns/${campaignId}/activity`, { params })
    return response.data
  },
  // Thread preview
  threadPreview: async (campaignId: number, contactId: number) => {
    const response = await api.get(`/campaigns/${campaignId}/thread-preview`, { params: { contact_id: contactId } })
    return response.data
  },
  // Date-aware CSV export
  exportCsvWithDates: async (id: number, dateFrom?: string, dateTo?: string) => {
    const params: Record<string, string> = {}
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    const response = await api.get(`/campaigns/${id}/analytics/export`, { params, responseType: 'blob' })
    return response.data
  },
  // Auto-enrollment
  enrollmentPreview: async (campaignId: number, rules: any) => {
    const response = await api.post(`/campaigns/${campaignId}/enrollment-preview`, { rules })
    return response.data
  },
  triggerAutoEnroll: async (campaignId: number) => {
    const response = await api.post(`/campaigns/${campaignId}/auto-enroll`)
    return response.data
  },
  getAvailableLeads: async (params?: Record<string, any>) => {
    const qs = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([key, val]) => {
        if (val === undefined || val === null || val === '') return
        if (Array.isArray(val)) {
          val.forEach(v => qs.append(key, String(v)))
        } else {
          qs.append(key, String(val))
        }
      })
    }
    const response = await api.get(`/campaigns/available-leads?${qs.toString()}`)
    return response.data
  },
  createFromLeads: async (data: { lead_ids: number[]; preview_mode?: boolean; timezone?: string; send_window_start?: string; send_window_end?: string; send_days?: string[] }) => {
    const response = await api.post('/campaigns/from-leads', data)
    return response.data
  },
  getContactSchedule: async (campaignId: number) => {
    const response = await api.get(`/campaigns/${campaignId}/contact-schedule`)
    return response.data
  },
  getMailboxStats: async (campaignId: number) => {
    const response = await api.get(`/campaigns/${campaignId}/mailbox-stats`)
    return response.data
  },
  aiEnhance: async (campaignId: number) => {
    const response = await api.post(`/campaigns/${campaignId}/ai-enhance`)
    return response.data
  },
  aiSuggestSubjects: async (campaignId: number) => {
    const response = await api.post(`/campaigns/${campaignId}/ai-suggest-subjects`)
    return response.data
  },
  // Schedules
  listSchedules: async (campaignId: number) => {
    const response = await api.get(`/campaigns/${campaignId}/schedules`)
    return response.data
  },
  addSchedule: async (campaignId: number, data: any) => {
    const response = await api.post(`/campaigns/${campaignId}/schedules`, data)
    return response.data
  },
  updateSchedule: async (campaignId: number, scheduleId: number, data: any) => {
    const response = await api.put(`/campaigns/${campaignId}/schedules/${scheduleId}`, data)
    return response.data
  },
  deleteSchedule: async (campaignId: number, scheduleId: number) => {
    await api.delete(`/campaigns/${campaignId}/schedules/${scheduleId}`)
  },
}

// Inbox API (Unibox)
export const inboxApi = {
  listThreads: async (params?: Record<string, any>) => {
    const response = await api.get('/inbox/threads', { params })
    return response.data
  },
  getThread: async (threadId: string) => {
    const response = await api.get(`/inbox/threads/${threadId}`)
    return response.data
  },
  markRead: async (threadId: string) => {
    const response = await api.put(`/inbox/threads/${threadId}/read`)
    return response.data
  },
  setCategory: async (threadId: string, category: string) => {
    const response = await api.put(`/inbox/threads/${threadId}/category`, { category })
    return response.data
  },
  reply: async (data: { thread_id: string; mailbox_id: number; body_html: string; body_text?: string }) => {
    const response = await api.post('/inbox/reply', data)
    return response.data
  },
  stats: async () => {
    const response = await api.get('/inbox/stats')
    return response.data
  },
  sync: async () => {
    const response = await api.post('/inbox/sync')
    return response.data
  },
  suggestReply: async (threadId: string) => {
    const response = await api.post(`/inbox/threads/${threadId}/suggest-reply`)
    return response.data
  },
  deleteThread: async (threadId: string) => {
    const response = await api.delete(`/inbox/threads/${threadId}`)
    return response.data
  },
  bulkDeleteThreads: async (threadIds: string[]) => {
    const response = await api.post('/inbox/threads/bulk-delete', { thread_ids: threadIds })
    return response.data
  },
}

// Deals API (CRM Pipeline)
export const dealsApi = {
  list: async (params?: Record<string, any>) => {
    const response = await api.get('/deals', { params })
    return response.data
  },
  get: async (id: number) => {
    const response = await api.get(`/deals/${id}`)
    return response.data
  },
  create: async (data: any) => {
    const response = await api.post('/deals', data)
    return response.data
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/deals/${id}`, data)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/deals/${id}`)
  },
  pipeline: async () => {
    const response = await api.get('/deals/pipeline')
    return response.data
  },
  stats: async () => {
    const response = await api.get('/deals/stats')
    return response.data
  },
  addActivity: async (dealId: number, data: any) => {
    const response = await api.post(`/deals/${dealId}/activities`, data)
    return response.data
  },
  // Stages
  listStages: async () => {
    const response = await api.get('/deals/stages')
    return response.data
  },
  createStage: async (data: any) => {
    const response = await api.post('/deals/stages', data)
    return response.data
  },
  updateStage: async (id: number, data: any) => {
    const response = await api.put(`/deals/stages/${id}`, data)
    return response.data
  },
  deleteStage: async (id: number) => {
    await api.delete(`/deals/stages/${id}`)
  },
  // Automation extras
  forecast: async () => {
    const response = await api.get('/deals/forecast')
    return response.data
  },
  stale: async (days?: number) => {
    const response = await api.get('/deals/stale', { params: days ? { days } : {} })
    return response.data
  },
  searchContacts: async (q: string) => {
    const response = await api.get('/deals/search/contacts', { params: { q } })
    return response.data
  },
  searchClients: async (q: string) => {
    const response = await api.get('/deals/search/clients', { params: { q } })
    return response.data
  },
}

// Webhooks API
export const webhooksApi = {
  list: async (params?: Record<string, any>) => {
    const response = await api.get('/webhooks', { params })
    return response.data
  },
  get: async (id: number) => {
    const response = await api.get(`/webhooks/${id}`)
    return response.data
  },
  create: async (data: any) => {
    const response = await api.post('/webhooks', data)
    return response.data
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/webhooks/${id}`, data)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/webhooks/${id}`)
  },
  deliveries: async (id: number, params?: Record<string, any>) => {
    const response = await api.get(`/webhooks/${id}/deliveries`, { params })
    return response.data
  },
}

// Automation Activity API
export const automationApi = {
  events: async (params?: Record<string, any>) => {
    const response = await api.get('/automation/events', { params })
    return response.data
  },
  summary: async () => {
    const response = await api.get('/automation/events/summary')
    return response.data
  },
  getControls: async () => {
    const response = await api.get('/automation/controls')
    return response.data
  },
  updateControls: async (data: Record<string, any>) => {
    const response = await api.put('/automation/controls', data)
    return response.data
  },
}

// AI Copilot API
export const copilotApi = {
  chat: async (messages: { role: string; content: string }[], context?: string) => {
    const response = await api.post('/copilot/chat', { messages, context })
    return response.data
  },
}

// Analytics API
export const analyticsApi = {
  teamLeaderboard: async () => {
    const response = await api.get('/analytics/team-leaderboard')
    return response.data
  },
  campaignComparison: async () => {
    const response = await api.get('/analytics/campaign-comparison')
    return response.data
  },
  revenue: async () => {
    const response = await api.get('/analytics/revenue')
    return response.data
  },
  costs: async (params?: Record<string, any>) => {
    const response = await api.get('/analytics/costs', { params })
    return response.data
  },
  addCost: async (data: { category: string; amount: number; entry_date: string; notes?: string; source_adapter?: string }) => {
    const response = await api.post('/analytics/costs', data)
    return response.data
  },
  updateCost: async (id: number, data: Record<string, any>) => {
    const response = await api.put(`/analytics/costs/${id}`, data)
    return response.data
  },
  deleteCost: async (id: number) => {
    await api.delete(`/analytics/costs/${id}`)
  },
  costsBySource: async (params?: Record<string, any>) => {
    const response = await api.get('/analytics/costs/per-source', { params })
    return response.data
  },
  costsDailyTrend: async (params?: Record<string, any>) => {
    const response = await api.get('/analytics/costs/daily-trend', { params })
    return response.data
  },
  budgetStatus: async () => {
    const response = await api.get('/analytics/costs/budget-status')
    return response.data
  },
}

// ICP Wizard API
export const icpWizardApi = {
  generate: async (data: { company_description: string; offering: string; pain_points: string }) => {
    const response = await api.post('/icp/generate', data)
    return response.data
  },
  listProfiles: async () => {
    const response = await api.get('/icp/profiles')
    return response.data
  },
  getProfile: async (id: number) => {
    const response = await api.get(`/icp/profiles/${id}`)
    return response.data
  },
  saveProfile: async (data: any) => {
    const response = await api.post('/icp/profiles', data)
    return response.data
  },
  updateProfile: async (id: number, data: any) => {
    const response = await api.put(`/icp/profiles/${id}`, data)
    return response.data
  },
  deleteProfile: async (id: number) => {
    await api.delete(`/icp/profiles/${id}`)
  },
  applyProfile: async (id: number) => {
    const response = await api.post(`/icp/profiles/${id}/apply`)
    return response.data
  },
}

// Saved Searches API
export const savedSearchesApi = {
  list: async () => {
    const response = await api.get('/saved-searches')
    return response.data
  },
  create: async (data: { name: string; description?: string; filters_json: string; is_shared?: boolean }) => {
    const response = await api.post('/saved-searches', data)
    return response.data
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/saved-searches/${id}`, data)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/saved-searches/${id}`)
  },
  execute: async (id: number, params?: Record<string, any>) => {
    const response = await api.post(`/saved-searches/${id}/execute`, null, { params })
    return response.data
  },
}

// Lead AI Search API
export const leadSearchApi = {
  aiSearch: async (query: string, limit?: number, offset?: number) => {
    const response = await api.post('/leads/ai-search', { query, limit, offset })
    return response.data
  },
}

// Sequence Generator API
export const sequenceGeneratorApi = {
  generate: async (data: { goal: string; product: string; tone?: string; num_steps?: number }) => {
    const response = await api.post('/sequence-generator/generate', data)
    return response.data
  },
}

// CRM Sync API
export const crmSyncApi = {
  run: async (crm_type?: string) => {
    const response = await api.post('/crm-sync/run', null, { params: crm_type ? { crm_type } : {} })
    return response.data
  },
  history: async (params?: Record<string, any>) => {
    const response = await api.get('/crm-sync/history', { params })
    return response.data
  },
}

// Deal Tasks API
export const dealTasksApi = {
  listForDeal: async (dealId: number) => {
    const response = await api.get(`/deals/${dealId}/tasks`)
    return response.data
  },
  create: async (dealId: number, data: any) => {
    const response = await api.post(`/deals/${dealId}/tasks`, data)
    return response.data
  },
  update: async (taskId: number, data: any) => {
    const response = await api.put(`/tasks/${taskId}`, data)
    return response.data
  },
  complete: async (taskId: number) => {
    const response = await api.post(`/tasks/${taskId}/complete`)
    return response.data
  },
  myTasks: async (params?: Record<string, any>) => {
    const response = await api.get('/tasks/my-tasks', { params })
    return response.data
  },
}

// Spam Check API
export const spamCheckApi = {
  check: async (data: { subject: string; body_html: string }) => {
    const response = await api.post('/spam-check', data)
    return response.data
  },
}

// Tracking Domains API
export const trackingDomainsApi = {
  list: async () => {
    const response = await api.get('/tracking-domains')
    return response.data
  },
  create: async (data: { domain_name: string; cname_target?: string; mailbox_id?: number }) => {
    const response = await api.post('/tracking-domains', data)
    return response.data
  },
  verify: async (id: number) => {
    const response = await api.post(`/tracking-domains/${id}/verify`)
    return response.data
  },
  delete: async (id: number) => {
    await api.delete(`/tracking-domains/${id}`)
  },
  setDefault: async (id: number) => {
    const response = await api.put(`/tracking-domains/${id}/default`)
    return response.data
  },
}

// Admin Tenants API (Super Admin only)
export const tenantsApi = {
  list: async (params?: Record<string, any>) => {
    const response = await api.get('/admin/tenants', { params })
    return response.data
  },
  create: async (data: Record<string, any>) => {
    const response = await api.post('/admin/tenants', data)
    return response.data
  },
  get: async (id: number) => {
    const response = await api.get(`/admin/tenants/${id}`)
    return response.data
  },
  update: async (id: number, data: Record<string, any>) => {
    const response = await api.put(`/admin/tenants/${id}`, data)
    return response.data
  },
  deactivate: async (id: number) => {
    const response = await api.delete(`/admin/tenants/${id}`)
    return response.data
  },
  impersonate: async (id: number) => {
    const response = await api.post(`/admin/tenants/${id}/impersonate`)
    return response.data
  },
  getFeatures: async (id: number) => {
    const response = await api.get(`/admin/tenants/${id}/features`)
    return response.data
  },
  updateFeatures: async (id: number, data: { feature_email_validation_enabled?: boolean; feature_campaigns_enabled?: boolean }) => {
    const response = await api.put(`/admin/tenants/${id}/features`, data)
    return response.data
  },
}

// Billing API
export const billingApi = {
  // Super admin
  listInvoices: async (params?: { status?: string; tenant_id?: number; date_from?: string; date_to?: string; page?: number; page_size?: number }) => {
    const response = await api.get('/billing/invoices', { params })
    return response.data
  },
  bulkGenerate: async (data: { tenant_ids: number[]; period_start: string; period_end: string }) => {
    const response = await api.post('/billing/invoices/bulk-generate', data)
    return response.data
  },
  markPaid: async (invoiceId: number, data: { payment_method: string; reference?: string; notes?: string }) => {
    const response = await api.put(`/billing/invoices/${invoiceId}/mark-paid`, data)
    return response.data
  },
  overrideAmount: async (invoiceId: number, data: { new_amount_cents: number; reason: string }) => {
    const response = await api.put(`/billing/invoices/${invoiceId}/override-amount`, data)
    return response.data
  },
  softDelete: async (invoiceId: number) => {
    const response = await api.delete(`/billing/invoices/${invoiceId}`)
    return response.data
  },
  listPayments: async (params?: { tenant_id?: number; page?: number; page_size?: number }) => {
    const response = await api.get('/billing/payments', { params })
    return response.data
  },
  stats: async () => {
    const response = await api.get('/billing/stats')
    return response.data
  },
  downloadPdf: async (invoiceId: number) => {
    const response = await api.get(`/billing/invoices/${invoiceId}/pdf`, { responseType: 'blob' })
    return response.data
  },
  // Tenant routes
  myInvoices: async (params?: { page?: number; page_size?: number }) => {
    const response = await api.get('/billing/my-invoices', { params })
    return response.data
  },
  myInvoice: async (invoiceId: number) => {
    const response = await api.get(`/billing/my-invoices/${invoiceId}`)
    return response.data
  },
  myInvoicePdf: async (invoiceId: number) => {
    const response = await api.get(`/billing/my-invoices/${invoiceId}/pdf`, { responseType: 'blob' })
    return response.data
  },
  pay: async (invoiceId: number, data?: { success_url?: string; cancel_url?: string }) => {
    const response = await api.post(`/billing/my-invoices/${invoiceId}/pay`, data || {})
    return response.data
  },
  myPayments: async (params?: { page?: number; page_size?: number }) => {
    const response = await api.get('/billing/my-payments', { params })
    return response.data
  },
}

// Activity Log API
export const activityApi = {
  getLoginHistory: async (params?: Record<string, any>) => {
    const response = await api.get('/activity/login-history', { params })
    return response.data
  },
  getLoginHistoryStats: async () => {
    const response = await api.get('/activity/login-history/stats')
    return response.data
  },
  getAuthEvents: async (params?: Record<string, any>) => {
    const response = await api.get('/activity/auth-events', { params })
    return response.data
  },
  getActiveUsers: async (params?: Record<string, any>) => {
    const response = await api.get('/activity/active-users', { params })
    return response.data
  },
  getMyLoginHistory: async (params?: Record<string, any>) => {
    const response = await api.get('/activity/my-login-history', { params })
    return response.data
  },
  unlockUser: async (userId: number) => {
    const response = await api.post(`/activity/unlock-user/${userId}`)
    return response.data
  },
}

// Integrations API (API Keys)
export const onboardingApi = {
  getStatus: async () => {
    const response = await api.get('/onboarding/status')
    return response.data
  },
  dismiss: async () => {
    const response = await api.post('/onboarding/dismiss')
    return response.data
  },
  reset: async () => {
    const response = await api.post('/onboarding/reset')
    return response.data
  },
}

export const emailPreviewApi = {
  generateDrafts: async (data: {
    source: string
    campaign_id?: number
    step_index?: number
    template_id?: number
    mailbox_id?: number
    contact_ids?: number[]
    limit?: number
  }) => {
    const response = await api.post('/email-preview/generate', data)
    return response.data
  },
  listDrafts: async (params?: {
    batch_id?: string
    status?: string
    source?: string
    campaign_id?: number
    mailbox_id?: number
    page?: number
    per_page?: number
  }) => {
    const response = await api.get('/email-preview/drafts', { params })
    return response.data
  },
  getDraft: async (id: number) => {
    const response = await api.get(`/email-preview/drafts/${id}`)
    return response.data
  },
  updateDraft: async (id: number, data: {
    subject?: string
    body_html?: string
    body_text?: string
    mailbox_id?: number
  }) => {
    const response = await api.put(`/email-preview/drafts/${id}`, data)
    return response.data
  },
  approveDraft: async (id: number) => {
    const response = await api.post(`/email-preview/drafts/${id}/approve`)
    return response.data
  },
  rejectDraft: async (id: number) => {
    const response = await api.post(`/email-preview/drafts/${id}/reject`)
    return response.data
  },
  approveAll: async (batch_id: string) => {
    const response = await api.post('/email-preview/drafts/approve-all', { batch_id })
    return response.data
  },
  sendDraft: async (id: number) => {
    const response = await api.post(`/email-preview/drafts/${id}/send`)
    return response.data
  },
  sendBatch: async (batch_id: string) => {
    const response = await api.post('/email-preview/drafts/send-batch', { batch_id })
    return response.data
  },
  aiRewrite: async (id: number) => {
    const response = await api.post(`/email-preview/drafts/${id}/ai-rewrite`)
    return response.data
  },
  deliverabilityScore: async (data: {
    mailbox_id: number
    subject: string
    body_html: string
  }) => {
    const response = await api.post('/email-preview/deliverability-score', data)
    return response.data
  },
  spamCheck: async (data: { subject: string; body_html: string }) => {
    const response = await api.post('/email-preview/spam-check', data)
    return response.data
  },
  spamFix: async (id: number, replacements: Array<{ original: string; replacement: string }>) => {
    const response = await api.post(`/email-preview/drafts/${id}/spam-fix`, { replacements })
    return response.data
  },
  bulkDeleteDrafts: async (draftIds: number[]) => {
    const response = await api.delete('/email-preview/drafts/bulk', { data: { draft_ids: draftIds } })
    return response.data
  },
  previewPersonalization: async (data: { campaign_id: number; step_index: number; contact_ids?: number[] }) => {
    const response = await api.post('/email-preview/preview-personalization', data)
    return response.data
  },
}

export const deliverabilityApi = {
  healthSummary: async () => {
    const response = await api.get('/deliverability/health-summary')
    return response.data
  },
  mailboxHealth: async (id: number) => {
    const response = await api.get(`/deliverability/mailbox/${id}/health`)
    return response.data
  },
  preSendCheck: async (data: { contact_id: number; lead_id?: number; campaign_id?: number }) => {
    const response = await api.post('/deliverability/pre-send-check', data)
    return response.data
  },
  renderingCheck: async (data: { body_html: string }) => {
    const response = await api.post('/deliverability/rendering-check', data)
    return response.data
  },
  humanize: async (data: { subject: string; body_html: string; body_text?: string; intensity?: string }) => {
    const response = await api.post('/deliverability/humanize', data)
    return response.data
  },
  sendTimes: async (params?: { state?: string; preferred_hour?: number }) => {
    const response = await api.get('/deliverability/send-times', { params })
    return response.data
  },
  engagement: async (contactId: number) => {
    const response = await api.get(`/deliverability/engagement/${contactId}`)
    return response.data
  },
  spintaxPreview: async (data: { text: string; count?: number; campaign_id?: number }) => {
    const response = await api.post('/deliverability/spintax-preview', data)
    return response.data
  },
  ispProfiles: async () => {
    const response = await api.get('/deliverability/isp-profiles')
    return response.data
  },
  complaintStats: async () => {
    const response = await api.get('/deliverability/complaint-stats')
    return response.data
  },
  spamReduce: async (data: { subject: string; body_html: string; replacements: Array<{ original: string; replacement: string }> }) => {
    const response = await api.post('/deliverability/spam-reduce', data)
    return response.data
  },
  humanizePreview: async (data: { subject: string; body_html: string; body_text?: string; intensity?: string }) => {
    const response = await api.post('/deliverability/humanize-preview', data)
    return response.data
  },
}

export const integrationsApi = {
  // API Keys
  listApiKeys: async () => {
    const response = await api.get('/integrations/api-keys')
    return response.data
  },
  createApiKey: async (data: { name: string; scopes?: string[]; expires_in_days?: number }) => {
    const response = await api.post('/integrations/api-keys', data)
    return response.data
  },
  revokeApiKey: async (id: number) => {
    await api.delete(`/integrations/api-keys/${id}`)
  },
}
