import axios from 'axios'

// Mock zustand store before importing api
const mockGetState = jest.fn()
jest.mock('@/lib/store', () => ({
  useAuthStore: {
    getState: () => mockGetState(),
  },
}))

// Must import after mocks
import { api, authApi, leadsApi, contactsApi, mailboxesApi, dashboardApi, pipelinesApi, settingsApi, templatesApi, usersApi, backupsApi, outreachApi, warmupApi } from '@/lib/api'

describe('API Client', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetState.mockReturnValue({ token: null, logout: jest.fn() })
  })

  describe('axios instance configuration', () => {
    test('has correct baseURL', () => {
      expect(api.defaults.baseURL).toBe('http://localhost:8000/api/v1')
    })

    test('has Content-Type header set to JSON', () => {
      expect(api.defaults.headers['Content-Type']).toBe('application/json')
    })

    test('has request interceptors configured', () => {
      expect(api.interceptors.request.handlers.length).toBeGreaterThan(0)
    })

    test('has response interceptors configured', () => {
      expect(api.interceptors.response.handlers.length).toBeGreaterThan(0)
    })
  })

  describe('API namespaces', () => {
    test('authApi has login, register, me methods', () => {
      expect(typeof authApi.login).toBe('function')
      expect(typeof authApi.register).toBe('function')
      expect(typeof authApi.me).toBe('function')
    })

    test('leadsApi has list, get, create, update, delete methods', () => {
      expect(typeof leadsApi.list).toBe('function')
      expect(typeof leadsApi.get).toBe('function')
      expect(typeof leadsApi.create).toBe('function')
      expect(typeof leadsApi.update).toBe('function')
      expect(typeof leadsApi.delete).toBe('function')
      expect(typeof leadsApi.stats).toBe('function')
      expect(typeof leadsApi.bulkOutreach).toBe('function')
      expect(typeof leadsApi.filterOptions).toBe('function')
    })

    test('contactsApi has CRUD methods', () => {
      expect(typeof contactsApi.list).toBe('function')
      expect(typeof contactsApi.get).toBe('function')
      expect(typeof contactsApi.create).toBe('function')
      expect(typeof contactsApi.update).toBe('function')
      expect(typeof contactsApi.delete).toBe('function')
    })

    test('mailboxesApi has CRUD + OAuth methods', () => {
      expect(typeof mailboxesApi.list).toBe('function')
      expect(typeof mailboxesApi.get).toBe('function')
      expect(typeof mailboxesApi.create).toBe('function')
      expect(typeof mailboxesApi.update).toBe('function')
      expect(typeof mailboxesApi.delete).toBe('function')
      expect(typeof mailboxesApi.testConnection).toBe('function')
      expect(typeof mailboxesApi.oauthInitiate).toBe('function')
      expect(typeof mailboxesApi.oauthCallback).toBe('function')
    })

    test('dashboardApi has data methods', () => {
      expect(typeof dashboardApi.kpis).toBe('function')
      expect(typeof dashboardApi.leadsSourced).toBe('function')
      expect(typeof dashboardApi.contactsIdentified).toBe('function')
      expect(typeof dashboardApi.outreachSent).toBe('function')
      expect(typeof dashboardApi.trends).toBe('function')
      expect(typeof dashboardApi.stats).toBe('function')
    })

    test('pipelinesApi has run methods', () => {
      expect(typeof pipelinesApi.runs).toBe('function')
      expect(typeof pipelinesApi.runLeadSourcing).toBe('function')
      expect(typeof pipelinesApi.runContactEnrichment).toBe('function')
      expect(typeof pipelinesApi.runEmailValidation).toBe('function')
      expect(typeof pipelinesApi.runOutreach).toBe('function')
      expect(typeof pipelinesApi.cancelJob).toBe('function')
    })

    test('settingsApi has CRUD methods', () => {
      expect(typeof settingsApi.list).toBe('function')
      expect(typeof settingsApi.get).toBe('function')
      expect(typeof settingsApi.update).toBe('function')
      expect(typeof settingsApi.testConnection).toBe('function')
    })

    test('templatesApi has CRUD + activate methods', () => {
      expect(typeof templatesApi.list).toBe('function')
      expect(typeof templatesApi.create).toBe('function')
      expect(typeof templatesApi.activate).toBe('function')
      expect(typeof templatesApi.preview).toBe('function')
    })

    test('usersApi has CRUD methods', () => {
      expect(typeof usersApi.list).toBe('function')
      expect(typeof usersApi.get).toBe('function')
      expect(typeof usersApi.create).toBe('function')
      expect(typeof usersApi.update).toBe('function')
      expect(typeof usersApi.delete).toBe('function')
    })

    test('backupsApi has backup management methods', () => {
      expect(typeof backupsApi.list).toBe('function')
      expect(typeof backupsApi.create).toBe('function')
      expect(typeof backupsApi.download).toBe('function')
      expect(typeof backupsApi.delete).toBe('function')
      expect(typeof backupsApi.restore).toBe('function')
    })

    test('outreachApi has event methods', () => {
      expect(typeof outreachApi.listEvents).toBe('function')
      expect(typeof outreachApi.getEvent).toBe('function')
      expect(typeof outreachApi.getThread).toBe('function')
      expect(typeof outreachApi.checkReplies).toBe('function')
      expect(typeof outreachApi.getStats).toBe('function')
    })

    test('warmupApi has warmup management methods', () => {
      expect(typeof warmupApi.getStatus).toBe('function')
      expect(typeof warmupApi.getConfig).toBe('function')
      expect(typeof warmupApi.triggerPeerWarmup).toBe('function')
      expect(typeof warmupApi.runDnsCheck).toBe('function')
      expect(typeof warmupApi.getProfiles).toBe('function')
    })
  })
})
