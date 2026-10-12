import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

const mockUsage = jest.fn()
let mockRole = 'admin'

jest.mock('@/lib/api', () => ({
  billingApi: { usage: () => mockUsage() },
}))

jest.mock('@/lib/store', () => ({
  useAuthStore: () => ({ user: { role: mockRole } }),
}))

jest.mock('next/link', () => {
  return ({ children, href, ...props }: any) => <a href={href} {...props}>{children}</a>
})

import { CreditMeter, creditTone } from '../credit-meter'

function renderMeter() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><CreditMeter /></QueryClientProvider>)
}

const metered = (over: Partial<Record<string, any>> = {}) => ({
  metered: true,
  credits: {
    allowance: 1200, topup: 300, total: 1500, period_spent: 800,
    plan_allowance: 2000, percent: 40, near_limit: false, ...over,
  },
  sends: { used: 100, limit: 500, remaining: 400, percent: 20, near_limit: false, exhausted: false },
})

describe('creditTone', () => {
  test('ok, low and empty', () => {
    expect(creditTone(500, false)).toBe('ok')
    expect(creditTone(500, true)).toBe('low')
    expect(creditTone(0, false)).toBe('empty')
    expect(creditTone(-40, true)).toBe('empty')
  })
})

describe('CreditMeter', () => {
  beforeEach(() => {
    mockUsage.mockReset()
    mockRole = 'admin'
  })

  test('renders nothing when the workspace is not metered', async () => {
    mockUsage.mockResolvedValue({ metered: false })
    const { container } = renderMeter()
    await waitFor(() => expect(mockUsage).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  test('shows total remaining and opens the breakdown', async () => {
    mockUsage.mockResolvedValue(metered())
    renderMeter()
    const chip = await screen.findByTestId('credit-meter')
    expect(chip).toHaveTextContent('1,500')

    fireEvent.click(chip)
    const dialog = screen.getByRole('dialog', { name: 'Credit balance' })
    expect(dialog).toHaveTextContent('1,200 / 2,000')
    expect(dialog).toHaveTextContent('Purchased credits')
    expect(dialog).toHaveTextContent('400 / 500')
    expect(screen.getByRole('link', { name: /credit history/i })).toHaveAttribute('href', '/dashboard/billing/credits')
  })

  test('warns when out of credits', async () => {
    mockUsage.mockResolvedValue(metered({ allowance: -20, topup: 0, total: -20, near_limit: true }))
    renderMeter()
    fireEvent.click(await screen.findByTestId('credit-meter'))
    expect(screen.getByRole('dialog')).toHaveTextContent(/out of credits/i)
  })

  test('recruiters see the balance but no billing links', async () => {
    mockRole = 'recruiter'
    mockUsage.mockResolvedValue(metered())
    renderMeter()
    fireEvent.click(await screen.findByTestId('credit-meter'))
    expect(screen.queryByRole('link', { name: /credit history/i })).toBeNull()
  })

  test('closes on Escape', async () => {
    mockUsage.mockResolvedValue(metered())
    renderMeter()
    fireEvent.click(await screen.findByTestId('credit-meter'))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
