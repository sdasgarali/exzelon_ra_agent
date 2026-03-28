import { render, screen, waitFor, act } from '@testing-library/react'
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

  test('shows user email initial in avatar', async () => {
    await act(async () => {
      render(<DashboardLayout><div>Content</div></DashboardLayout>)
    })
    await waitFor(() => {
      expect(screen.getByText('A')).toBeInTheDocument()
    })
  })

  test('shows user display name', async () => {
    await act(async () => {
      render(<DashboardLayout><div>Content</div></DashboardLayout>)
    })
    await waitFor(() => {
      expect(screen.getByText('Admin User')).toBeInTheDocument()
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
        expect(screen.getByText(link)).toBeInTheDocument()
      }
    })
  })

  test('renders sign out button', async () => {
    await act(async () => {
      render(<DashboardLayout><div>Content</div></DashboardLayout>)
    })
    await waitFor(() => {
      expect(screen.getByText('Sign out')).toBeInTheDocument()
    })
  })
})
