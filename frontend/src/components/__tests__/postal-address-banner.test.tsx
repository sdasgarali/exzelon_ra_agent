import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

const mockGetProfile = jest.fn()
let mockRole = 'admin'

jest.mock('@/lib/api', () => ({
  settingsApi: { getCompanyProfile: () => mockGetProfile() },
}))

jest.mock('@/lib/store', () => ({
  useAuthStore: () => ({ user: { role: mockRole } }),
}))

jest.mock('next/link', () => {
  return ({ children, href, ...props }: any) => <a href={href} {...props}>{children}</a>
})

import { PostalAddressBanner } from '../postal-address-banner'

function renderBanner() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><PostalAddressBanner /></QueryClientProvider>)
}

beforeEach(() => {
  mockGetProfile.mockReset()
  mockRole = 'admin'
  window.sessionStorage.clear()
})

test('shows when the workspace has no postal address', async () => {
  mockGetProfile.mockResolvedValue({ name: 'Acme', company_address: null })
  renderBanner()
  expect(await screen.findByRole('alert')).toHaveTextContent(/postal address/i)
  expect(screen.getByRole('link')).toHaveAttribute('href', '/dashboard/settings?tab=business')
})

test('treats a whitespace-only address as missing', async () => {
  mockGetProfile.mockResolvedValue({ company_address: '   ' })
  renderBanner()
  expect(await screen.findByRole('alert')).toBeInTheDocument()
})

test('hidden when an address is set', async () => {
  mockGetProfile.mockResolvedValue({ company_address: '1 Main St, Springfield' })
  renderBanner()
  await waitFor(() => expect(mockGetProfile).toHaveBeenCalled())
  expect(screen.queryByRole('alert')).toBeNull()
})

test('hidden for non-admins (they cannot set it) and makes no request', async () => {
  mockRole = 'bdm'
  renderBanner()
  await new Promise((r) => setTimeout(r, 0))
  expect(mockGetProfile).not.toHaveBeenCalled()
  expect(screen.queryByRole('alert')).toBeNull()
})

test('hidden when the profile request fails', async () => {
  mockGetProfile.mockRejectedValue(new Error('400'))
  renderBanner()
  await waitFor(() => expect(mockGetProfile).toHaveBeenCalled())
  expect(screen.queryByRole('alert')).toBeNull()
})

test('dismiss hides it for the rest of the session', async () => {
  mockGetProfile.mockResolvedValue({ company_address: '' })
  const { unmount } = renderBanner()
  fireEvent.click(await screen.findByRole('button', { name: /dismiss/i }))
  expect(screen.queryByRole('alert')).toBeNull()
  unmount()
  renderBanner()
  await waitFor(() => expect(mockGetProfile).toHaveBeenCalled())
  expect(screen.queryByRole('alert')).toBeNull()
})
