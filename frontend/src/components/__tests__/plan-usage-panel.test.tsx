import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

const mockUsage = jest.fn()
const mockSubscribe = jest.fn()
const mockBuyCredits = jest.fn()
const mockQuote = jest.fn()
const mockToast = jest.fn()

let mockSiteInfo: any = {}

jest.mock('@/lib/api', () => ({
  billingApi: {
    usage: () => mockUsage(),
    subscribe: (...a: any[]) => mockSubscribe(...a),
    buyCredits: (...a: any[]) => mockBuyCredits(...a),
    requestCustomQuote: (...a: any[]) => mockQuote(...a),
  },
  getApiError: (_e: any, fb: string) => fb,
}))

jest.mock('@/lib/use-site-info', () => ({
  useSiteInfo: () => mockSiteInfo,
}))

jest.mock('../toast', () => ({
  useToast: () => ({ toast: mockToast }),
}))

import PlanUsagePanel from '../plan-usage-panel'

const usage = {
  metered: true,
  plan: {
    key: 'pro', label: 'Pro', is_custom: false, monthly_price_cents: 4900,
    annual_price_cents: 47000, upgrade_to: 'max', upgrade_label: 'Max',
  },
  credits: {
    allowance: 1200, topup: 0, total: 1200, period_spent: 800, plan_allowance: 2000,
    percent: 40, near_limit: false,
  },
  sends: { used: 100, limit: 500, remaining: 400, percent: 20, near_limit: false, exhausted: false },
  resources: [],
  topup: { block_size: 1000, block_price_cents: 2000, validity_days: 365, available: true },
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><PlanUsagePanel /></QueryClientProvider>)
}

const base = {
  support_email: 'help@example.test', privacy_email: 'privacy@example.test',
  legal_entity_name: '', legal_address: '', legal_jurisdiction: '', terms_version: '',
}

describe('PlanUsagePanel', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUsage.mockResolvedValue(usage)
  })

  test('payments off: shows "Request upgrade" + "Request credits" mailto links and never calls Stripe', async () => {
    mockSiteInfo = { ...base, payments_enabled: false }
    renderPanel()

    const upgrade = await screen.findByRole('link', { name: /Request upgrade/ })
    const href = upgrade.getAttribute('href') || ''
    expect(href.startsWith('mailto:help@example.test?')).toBe(true)
    expect(decodeURIComponent(href)).toContain('Upgrade request: Pro to Max')

    const credits = screen.getByRole('link', { name: /Request credits/ })
    expect(decodeURIComponent(credits.getAttribute('href') || '')).toContain('1,000 credits')

    expect(screen.queryByRole('button', { name: /Upgrade to Max/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Buy credits/ })).not.toBeInTheDocument()
    expect(screen.getAllByText("Online payments open soon — we'll set it up for you.").length).toBeGreaterThan(0)

    // They are plain mailto links (no click handler), so nothing can reach Stripe.
    expect(upgrade.tagName).toBe('A')
    expect(credits.tagName).toBe('A')
    expect(mockSubscribe).not.toHaveBeenCalled()
    expect(mockBuyCredits).not.toHaveBeenCalled()
  })

  test('payments on: shows the Upgrade and Buy credits buttons that start checkout', async () => {
    mockSiteInfo = { ...base, payments_enabled: true }
    mockSubscribe.mockResolvedValue({})
    renderPanel()

    const upgrade = await screen.findByRole('button', { name: /Upgrade to Max/ })
    expect(screen.getByRole('button', { name: /Buy credits/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Request upgrade/ })).not.toBeInTheDocument()

    fireEvent.click(upgrade)
    await waitFor(() => expect(mockSubscribe).toHaveBeenCalledWith({ plan: 'max', annual: false }))
  })

  test('custom quote request path still works with payments off', async () => {
    mockSiteInfo = { ...base, payments_enabled: false }
    mockQuote.mockResolvedValue({ status: 'received' })
    renderPanel()
    fireEvent.click(await screen.findByText(/Build a custom plan/))
    fireEvent.change(screen.getByPlaceholderText('> 1,000'), { target: { value: '2000' } })
    fireEvent.click(screen.getByRole('button', { name: /Request a quote/ }))
    await waitFor(() => expect(mockQuote).toHaveBeenCalledWith({ mailboxes: 2000 }))
  })
})
