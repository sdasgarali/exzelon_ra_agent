import { render, screen } from '@testing-library/react'
import React from 'react'

const mockFetchSiteInfo = jest.fn()
jest.mock('@/lib/site-info', () => {
  const actual = jest.requireActual('@/lib/site-info')
  return { ...actual, fetchSiteInfo: () => mockFetchSiteInfo() }
})

jest.mock('@/components/marketing/ScrollReveal', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

jest.mock('next/link', () => {
  return ({ children, href, ...props }: any) => <a href={href} {...props}>{children}</a>
})

import ContactPage from '../page'

const info = {
  support_email: 'help@example.test',
  privacy_email: 'privacy@example.test',
  legal_entity_name: '',
  legal_address: '',
  legal_jurisdiction: '',
  terms_version: '',
  payments_enabled: false,
}

describe('Contact page', () => {
  beforeEach(() => mockFetchSiteInfo.mockReset())

  test('shows the support and privacy emails from site-info as mailto links', async () => {
    mockFetchSiteInfo.mockResolvedValue(info)
    render(await ContactPage({}))

    const supportLinks = screen.getAllByRole('link', { name: /help@example\.test/ })
    expect(supportLinks.length).toBeGreaterThanOrEqual(1)
    for (const l of supportLinks) expect(l.getAttribute('href')).toMatch(/^mailto:help@example\.test/)

    const privacy = screen.getByRole('link', { name: /privacy@example\.test/ })
    expect(privacy.getAttribute('href')).toMatch(/^mailto:privacy@example\.test/)

    expect(screen.queryByText(/to be published/i)).not.toBeInTheDocument()
  })

  test('has an "Email us" CTA, with a topic-specific subject', async () => {
    mockFetchSiteInfo.mockResolvedValue(info)
    render(await ContactPage({ searchParams: { topic: 'custom-plan' } }))
    const cta = screen.getByRole('link', { name: /Email us/ })
    expect(cta.getAttribute('href')).toBe(
      `mailto:help@example.test?subject=${encodeURIComponent('Custom plan enquiry')}`,
    )
  })

  test('falls back to the published address when the API is unreachable', async () => {
    mockFetchSiteInfo.mockRejectedValue(new Error('down'))
    render(await ContactPage({}))
    expect(screen.getAllByRole('link', { name: /info@neuraleads\.ai/ }).length).toBeGreaterThanOrEqual(1)
  })
})
