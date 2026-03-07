import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock API
const mockMailboxList = jest.fn()
const mockMailboxStats = jest.fn()

jest.mock('@/lib/api', () => ({
  mailboxesApi: {
    list: (...args: any[]) => mockMailboxList(...args),
    stats: () => mockMailboxStats(),
    create: jest.fn(),
    delete: jest.fn(),
    update: jest.fn(),
    testConnection: jest.fn(),
    testNewConnection: jest.fn(),
    oauthInitiate: jest.fn(),
    updateStatus: jest.fn(),
    resetDailyCounts: jest.fn(),
    getAvailable: jest.fn(),
    get: jest.fn(),
    oauthCallback: jest.fn(),
  },
}))

jest.mock('@/components/toast', () => ({
  useToast: () => ({
    toast: jest.fn(),
  }),
}))

import MailboxesPage from '../page'

const mockMailboxes = [
  {
    mailbox_id: 1,
    email: 'sender1@example.com',
    display_name: 'Sender One',
    provider: 'microsoft_365',
    smtp_host: 'smtp.office365.com',
    smtp_port: 587,
    warmup_status: 'cold_ready',
    is_active: true,
    daily_send_limit: 30,
    emails_sent_today: 5,
    total_emails_sent: 150,
    last_sent_at: '2026-03-07T10:00:00',
    bounce_count: 1,
    reply_count: 10,
    complaint_count: 0,
    warmup_days_completed: 30,
    can_send: true,
    remaining_daily_quota: 25,
    notes: null,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-03-07T10:00:00',
    connection_status: 'successful',
    connection_error: null,
    last_connection_test_at: '2026-03-07T10:00:00',
    email_signature_json: null,
    auth_method: 'password',
    oauth_tenant_id: null,
    oauth_connected: false,
  },
  {
    mailbox_id: 2,
    email: 'sender2@example.com',
    display_name: 'Sender Two',
    provider: 'gmail',
    smtp_host: 'smtp.gmail.com',
    smtp_port: 587,
    warmup_status: 'warming_up',
    is_active: true,
    daily_send_limit: 20,
    emails_sent_today: 0,
    total_emails_sent: 50,
    last_sent_at: null,
    bounce_count: 0,
    reply_count: 5,
    complaint_count: 0,
    warmup_days_completed: 10,
    can_send: false,
    remaining_daily_quota: 20,
    notes: null,
    created_at: '2026-02-01T00:00:00',
    updated_at: '2026-03-06T10:00:00',
    connection_status: 'untested',
    connection_error: null,
    last_connection_test_at: null,
    email_signature_json: null,
    auth_method: 'oauth2',
    oauth_tenant_id: 'test-tenant',
    oauth_connected: true,
  },
]

const mockStatsData = {
  total_mailboxes: 2,
  active_mailboxes: 2,
  cold_ready_mailboxes: 1,
  warming_up_mailboxes: 1,
  paused_mailboxes: 0,
  total_daily_capacity: 50,
  used_today: 5,
  available_today: 45,
  total_emails_sent: 200,
  total_bounces: 1,
  total_replies: 15,
}

describe('MailboxesPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockMailboxList.mockResolvedValue({ items: mockMailboxes, total: 2, active_count: 2, ready_count: 1 })
    mockMailboxStats.mockResolvedValue(mockStatsData)
  })

  test('renders page title', async () => {
    await act(async () => {
      render(<MailboxesPage />)
    })
    expect(screen.getByText('Sender Mailboxes')).toBeInTheDocument()
  })

  test('loads and displays mailbox list', async () => {
    await act(async () => {
      render(<MailboxesPage />)
    })
    await waitFor(() => {
      expect(screen.getByText('sender1@example.com')).toBeInTheDocument()
      expect(screen.getByText('sender2@example.com')).toBeInTheDocument()
    })
  })

  test('displays mailbox provider labels', async () => {
    await act(async () => {
      render(<MailboxesPage />)
    })
    await waitFor(() => {
      expect(screen.getByText('sender1@example.com')).toBeInTheDocument()
    })
    expect(screen.getAllByText('Microsoft 365').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Gmail').length).toBeGreaterThanOrEqual(1)
  })

  test('shows warmup status badges', async () => {
    await act(async () => {
      render(<MailboxesPage />)
    })
    await waitFor(() => {
      expect(screen.getByText('sender1@example.com')).toBeInTheDocument()
    })
    expect(screen.getAllByText('Cold Ready').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Warming Up').length).toBeGreaterThanOrEqual(1)
  })

  test('calls list and stats API on mount', async () => {
    await act(async () => {
      render(<MailboxesPage />)
    })
    await waitFor(() => {
      expect(mockMailboxList).toHaveBeenCalled()
      expect(mockMailboxStats).toHaveBeenCalled()
    })
  })

  test('shows add mailbox button', async () => {
    await act(async () => {
      render(<MailboxesPage />)
    })
    expect(screen.getByText('Add Mailbox')).toBeInTheDocument()
  })

  test('opens add mailbox modal on button click', async () => {
    await act(async () => {
      render(<MailboxesPage />)
    })
    // There's an "Add Mailbox" button in the header — click it
    const addButtons = screen.getAllByText('Add Mailbox')
    await userEvent.click(addButtons[0])
    await waitFor(() => {
      // Modal shows Cancel button
      expect(screen.getByText('Cancel')).toBeInTheDocument()
    })
  })

  test('handles API error gracefully', async () => {
    mockMailboxList.mockRejectedValueOnce(new Error('API Error'))
    mockMailboxStats.mockRejectedValueOnce(new Error('API Error'))
    await act(async () => {
      render(<MailboxesPage />)
    })
    // Page should still render without crashing
    expect(screen.getByText('Sender Mailboxes')).toBeInTheDocument()
  })
})
