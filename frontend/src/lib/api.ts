import axios from 'axios'
import { useAuthStore } from './store'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
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
}
