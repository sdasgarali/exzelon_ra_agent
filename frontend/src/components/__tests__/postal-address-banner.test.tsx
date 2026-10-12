import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

const mockGetProfile = jest.fn()
const mockUpdateProfile = jest.fn()
let mockRole = 'admin'

jest.mock('@/lib/api', () => ({
  settingsApi: {
    getCompanyProfile: () => mockGetProfile(),
    updateCompanyProfile: (d: any) => mockUpdateProfile(d),
  },
  getApiError: (e: any) => e?.message || 'error',
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
  mockUpdateProfile.mockReset()
  mockRole = 'admin'
  window.sessionStorage.clear()
})

test('shows when the workspace has no postal address', async () => {
  mockGetProfile.mockResolvedValue({ name: 'Acme', company_address: null })
  renderBanner()
  expect(await screen.findByRole('alert')).toHaveTextContent(/postal address/i)
  expect(screen.getByRole('button', { name: 'Add address' })).toBeInTheDocument()
})

test('saves the address inline (works even when the Business Rules tab is hidden)', async () => {
  mockGetProfile.mockResolvedValueOnce({ company_address: null })
    .mockResolvedValue({ company_address: '12 High St, Leeds LS1 1AA, UK' })
  mockUpdateProfile.mockResolvedValue({})
  renderBanner()
  fireEvent.click(await screen.findByRole('button', { name: 'Add address' }))
  fireEvent.change(screen.getByLabelText('Company postal address'), {
    target: { value: '  12 High St, Leeds LS1 1AA, UK  ' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save address' }))
  await waitFor(() => expect(mockUpdateProfile).toHaveBeenCalledWith({ company_address: '12 High St, Leeds LS1 1AA, UK' }))
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
})

test('rejects an obviously incomplete address without calling the API', async () => {
  mockGetProfile.mockResolvedValue({ company_address: null })
  renderBanner()
  fireEvent.click(await screen.findByRole('button', { name: 'Add address' }))
  fireEvent.change(screen.getByLabelText('Company postal address'), { target: { value: 'Leeds' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save address' }))
  expect(await screen.findByText(/full postal address/i)).toBeInTheDocument()
  expect(mockUpdateProfile).not.toHaveBeenCalled()
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
