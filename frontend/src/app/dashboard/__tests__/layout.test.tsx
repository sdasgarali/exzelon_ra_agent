import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import React from 'react'

// Mock the store
const mockUser = {
  user_id: 1,
  email: 'admin@test.com',
  full_name: 'Admin User',
  role: 'super_admin',
  is_active: true,
}

jest.mock('@/lib/store', () => ({
  useAuthStore: () => ({
    user: mockUser,
    logout: jest.fn(),
    isAuthenticated: () => true,
  }),
}))

jest.mock('@/lib/api', () => ({
  warmupApi: {
    getUnreadCount: jest.fn().mockResolvedValue({ unread_count: 0 }),
  },
  tenantsApi: {
    list: jest.fn().mockResolvedValue({ items: [] }),
    impersonate: jest.fn().mockResolvedValue({}),
  },
}))

jest.mock('@/components/error-boundary', () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

jest.mock('@/components/offline-banner', () => ({
  OfflineBanner: () => null,
}))

jest.mock('@/components/theme-provider', () => ({
  useTheme: () => ({ theme: 'light', toggleTheme: jest.fn() }),
}))

jest.mock('@/hooks/use-keyboard-shortcuts', () => ({
  useKeyboardShortcuts: () => ({
    helpOpen: false,
    setHelpOpen: jest.fn(),
    shortcuts: [],
  }),
}))

// Mock next/link to avoid app router dependency
jest.mock('next/link', () => {
  return ({ children, href, ...props }: any) => <a href={href} {...props}>{children}</a>
})

import DashboardLayout from '../layout'

describe('DashboardLayout', () => {
  afterEach(() => {
    jest.clearAllTimers()
  })

  test('renders sidebar with app name', async () => {
    await act(async () => {
      render(<DashboardLayout><div>Test Content</div></DashboardLayout>)
    })
    await waitFor(() => {
      expect(screen.getAllByText('NeuraLeads').length).toBeGreaterThanOrEqual(1)
    })
  })

  test('renders children content', async () => {
    await act(async () => {
      render(<DashboardLayout><div>Test Content</div></DashboardLayout>)
    })
    await waitFor(() => {
      expect(screen.getByText('Test Content')).toBeInTheDocument()
    })
  })

  // The sidebar render is shared by the desktop + mobile-drawer layouts, so
  // user/avatar/nav elements legitimately appear more than once — assert with
  // *AllBy* rather than the single-match getByText.
  test('shows user email initial in avatar', async () => {
    await act(async () => {
      render(<DashboardLayout><div>Content</div></DashboardLayout>)
    })
    await waitFor(() => {
      expect(screen.getAllByText('A').length).toBeGreaterThanOrEqual(1)
    })
  })

  test('shows user display name', async () => {
    await act(async () => {
      render(<DashboardLayout><div>Content</div></DashboardLayout>)
    })
    await waitFor(() => {
      expect(screen.getAllByText('Admin User').length).toBeGreaterThanOrEqual(1)
    })
  })

  test('renders navigation links for super_admin', async () => {
    await act(async () => {
      render(<DashboardLayout><div>Content</div></DashboardLayout>)
    })

    const navLinks = [
      'Dashboard', 'Leads', 'Clients', 'Contacts', 'Validation',
      'Outreach', 'Email Templates', 'Mailboxes', 'Warmup Engine',
      'Pipelines', 'User Management', 'Roles & Permissions',
      'Data Backups', 'Settings'
    ]

    await waitFor(() => {
      for (const link of navLinks) {
        expect(screen.getAllByText(link).length).toBeGreaterThanOrEqual(1)
      }
    })
  })

  test('renders sign out button', async () => {
    await act(async () => {
      render(<DashboardLayout><div>Content</div></DashboardLayout>)
    })
    // Sign out lives inside the profile dropdown — open it via the profile
    // trigger (the user's name), then assert the item is present.
    const profileTrigger = screen.getAllByText('Admin User')[0]
    await act(async () => {
      fireEvent.click(profileTrigger)
    })
    await waitFor(() => {
      expect(screen.getAllByText('Sign out').length).toBeGreaterThanOrEqual(1)
    })
  })
})
