import { render } from '@testing-library/react'
import React from 'react'

const mockFetchSiteInfo = jest.fn()

jest.mock('@/lib/site-info', () => {
  const actual = jest.requireActual('@/lib/site-info')
  return { ...actual, fetchSiteInfo: () => mockFetchSiteInfo() }
})

jest.mock('@/lib/marketing-fonts', () => ({
  marketingFontVars: '',
  plexMono: { variable: '' },
  sourceSerif: { variable: '' },
}))

jest.mock('next/link', () => {
  return ({ children, href, ...props }: any) => <a href={href} {...props}>{children}</a>
})

// jsdom has no IntersectionObserver; the contents rail uses it.
beforeAll(() => {
  ;(global as any).IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})

import PrivacyPage from '../page'
import TermsPage from '../../terms/page'

const EMPTY = {
  support_email: 'info@neuraleads.ai',
  privacy_email: 'info@neuraleads.ai',
  legal_entity_name: '',
  legal_address: '',
  legal_jurisdiction: '',
  terms_version: '2026-09-10',
  payments_enabled: false,
}

const FILLED = {
  ...EMPTY,
  privacy_email: 'privacy@neuraleads.ai',
  legal_entity_name: 'Neuraforz Ltd',
  legal_address: '1 Main Street, Springfield',
  legal_jurisdiction: 'England and Wales',
}

// \b so ordinary words like "depending" don't count.
const FORBIDDEN = [/\bpending\b/i,/legal entity name/i, /registered address/i, /privacy address/i,
  /support address/i, /<jurisdiction>/i, /123 Business St/i]

async function renderPage(Page: () => Promise<JSX.Element>) {
  const el = await Page()
  return render(el)
}

describe.each([
  ['privacy', PrivacyPage],
  ['terms', TermsPage],
])('%s page', (_name, Page) => {
  beforeEach(() => mockFetchSiteInfo.mockReset())

  test('no placeholder text when nothing is configured', async () => {
    mockFetchSiteInfo.mockResolvedValue(EMPTY)
    const { container } = await renderPage(Page as any)
    const text = container.textContent || ''
    for (const re of FORBIDDEN) expect(text).not.toMatch(re)
    expect(text).toContain('NeuraLeads')
    expect(text).not.toMatch(/registered at/i)
    expect(text).not.toMatch(/governed by the laws of|governing jurisdiction/i)
  })

  test('falls back gracefully when site-info is unreachable', async () => {
    mockFetchSiteInfo.mockRejectedValue(new Error('down'))
    const { container } = await renderPage(Page as any)
    const text = container.textContent || ''
    for (const re of FORBIDDEN) expect(text).not.toMatch(re)
    expect(container.querySelector('a[href="mailto:info@neuraleads.ai"]')).not.toBeNull()
  })

  test('renders entity, address and jurisdiction when configured', async () => {
    mockFetchSiteInfo.mockResolvedValue(FILLED)
    const { container } = await renderPage(Page as any)
    const text = container.textContent || ''
    for (const re of FORBIDDEN) expect(text).not.toMatch(re)
    expect(text).toContain('Neuraforz Ltd')
    expect(text).toContain('1 Main Street, Springfield')
    expect(text).toContain('England and Wales')
  })
})

test('privacy page links the privacy email', async () => {
  mockFetchSiteInfo.mockResolvedValue(FILLED)
  const { container } = await renderPage(PrivacyPage as any)
  expect(container.querySelectorAll('a[href="mailto:privacy@neuraleads.ai"]').length).toBeGreaterThan(0)
})

test('terms page links the support email', async () => {
  mockFetchSiteInfo.mockResolvedValue(FILLED)
  const { container } = await renderPage(TermsPage as any)
  expect(container.querySelector('a[href="mailto:info@neuraleads.ai"]')).not.toBeNull()
})
