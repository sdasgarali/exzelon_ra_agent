import axios from 'axios'
import { useAuthStore } from './store'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
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

// Handle 401 errors + clean up pending requests
api.interceptors.response.use(
  (response) => {
    const key = getRequestKey(response.config)
    pendingRequests.delete(key)
    return response
  },
  (error) => {
    if (error.config) {
      const key = getRequestKey(error.config)
      pendingRequests.delete(key)
    }
    if (error.response?.status === 401) {
      // Don't redirect if we're already on the login page or the request was a login attempt
      const isLoginRequest = error.config?.url?.includes('/auth/login')
      if (!isLoginRequest) {
        useAuthStore.getState().logout()
        window.location.href = '/login'
      }
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
  stats: async () => {
    const response = await api.get('/leads/stats/summary')
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
  filterOptions: async () => {
    const response = await api.get('/leads/filter-options')
    return response.data
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
  runEmailValidation: async () => {
    const response = await api.post('/pipelines/email-validation/run')
    return response.data
  },
  runOutreach: async (mode: string, dryRun: boolean = true, leadIds?: number[]) => {
    const response = await api.post('/pipelines/outreach/run',
      leadIds ? { lead_ids: leadIds } : undefined,
      { params: { mode, dry_run: dryRun } })
    return response.data
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
  analytics: async (id: number) => {
    const response = await api.get(`/campaigns/${id}/analytics`)
    return response.data
  },
  abResults: async (campaignId: number, stepId: number) => {
    const response = await api.get(`/campaigns/${campaignId}/steps/${stepId}/ab-results`)
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
}

// Integrations API (API Keys)
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
