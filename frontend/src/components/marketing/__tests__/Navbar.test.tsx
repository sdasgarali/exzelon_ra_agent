import { render, screen } from '@testing-library/react'
import Navbar from '../Navbar'

let mockToken: string | null = null

jest.mock('@/lib/store', () => ({
  useAuthStore: (selector: (s: { token: string | null }) => unknown) =>
    selector({ token: mockToken }),
}))

describe('Marketing Navbar', () => {
  beforeEach(() => {
    mockToken = null
  })

  it('shows Log in and Get Started when logged out', () => {
    render(<Navbar />)
    expect(screen.getByRole('link', { name: 'Log in' })).toHaveAttribute('href', '/login')
    expect(screen.getByRole('link', { name: 'Get Started' })).toHaveAttribute('href', '/signup')
    expect(screen.queryByRole('link', { name: 'Go to Dashboard' })).not.toBeInTheDocument()
  })

  it('shows Go to Dashboard instead of auth CTAs when logged in', () => {
    mockToken = 'access-token'
    render(<Navbar />)
    expect(screen.getByRole('link', { name: 'Go to Dashboard' })).toHaveAttribute('href', '/dashboard')
    expect(screen.queryByRole('link', { name: 'Log in' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Get Started' })).not.toBeInTheDocument()
  })
})
