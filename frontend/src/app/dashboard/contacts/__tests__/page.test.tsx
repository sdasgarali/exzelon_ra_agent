import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock API
const mockContactsList = jest.fn()
jest.mock('@/lib/api', () => ({
  contactsApi: {
    list: (...args: any[]) => mockContactsList(...args),
    delete: jest.fn(),
  },
  api: {
    delete: jest.fn(),
  },
}))

// Mock next/link
jest.mock('next/link', () => {
  return ({ children, href, ...props }: any) => <a href={href} {...props}>{children}</a>
})

import ContactsPage from '../page'

const mockContacts = [
  {
    contact_id: 1,
    lead_id: 10,
    lead_ids: [10],
    client_name: 'Acme Corp',
    first_name: 'John',
    last_name: 'Doe',
    title: 'VP Engineering',
    email: 'john.doe@acme.com',
    phone: '+1-555-0100',
    location_state: 'TX',
    priority_level: 'P1',
    validation_status: 'Valid',
    source: 'Apollo',
    outreach_status: 'Not Started',
    unsubscribed_at: null,
  },
  {
    contact_id: 2,
    lead_id: 20,
    lead_ids: [20],
    client_name: 'Widget Inc',
    first_name: 'Jane',
    last_name: 'Smith',
    title: 'CTO',
    email: 'jane.smith@widget.io',
    phone: '',
    location_state: 'CA',
    priority_level: 'P2',
    validation_status: 'Unknown',
    source: 'Seamless',
    outreach_status: 'Sent',
    unsubscribed_at: null,
  },
]

describe('ContactsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockContactsList.mockResolvedValue({
      items: mockContacts,
      total: 2,
    })
  })

  test('renders page heading', async () => {
    render(<ContactsPage />)
    expect(screen.getByText('Contacts')).toBeInTheDocument()
  })

  test('loads and displays contacts', async () => {
    render(<ContactsPage />)
    await waitFor(() => {
      expect(screen.getByText('john.doe@acme.com')).toBeInTheDocument()
      expect(screen.getByText('jane.smith@widget.io')).toBeInTheDocument()
    })
  })

  test('displays contact names', async () => {
    render(<ContactsPage />)
    await waitFor(() => {
      expect(screen.getByText(/John/)).toBeInTheDocument()
      expect(screen.getByText(/Jane/)).toBeInTheDocument()
    })
  })

  test('displays company names', async () => {
    render(<ContactsPage />)
    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
      expect(screen.getByText('Widget Inc')).toBeInTheDocument()
    })
  })

  test('calls contacts API on mount', async () => {
    render(<ContactsPage />)
    await waitFor(() => {
      expect(mockContactsList).toHaveBeenCalled()
    })
  })

  test('passes pagination params to API', async () => {
    render(<ContactsPage />)
    await waitFor(() => {
      expect(mockContactsList).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1, page_size: 25 })
      )
    })
  })

  test('displays source labels', async () => {
    render(<ContactsPage />)
    await waitFor(() => {
      expect(screen.getByText('Apollo')).toBeInTheDocument()
      expect(screen.getByText('Seamless')).toBeInTheDocument()
    })
  })

  test('handles API error gracefully', async () => {
    const error = new Error('Server error') as any
    error.response = { data: { detail: 'Server error' } }
    mockContactsList.mockRejectedValueOnce(error)
    render(<ContactsPage />)
    await waitFor(() => {
      expect(screen.getByText(/Failed to fetch contacts|Server error/)).toBeInTheDocument()
    })
  })
})
