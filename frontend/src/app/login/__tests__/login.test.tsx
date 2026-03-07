import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LoginPage from '../page'

// Mock the API
const mockLogin = jest.fn()
const mockRegister = jest.fn()
jest.mock('@/lib/api', () => ({
  authApi: {
    login: (...args: any[]) => mockLogin(...args),
    register: (...args: any[]) => mockRegister(...args),
  },
}))

// Mock the store
const mockSetAuth = jest.fn()
jest.mock('@/lib/store', () => ({
  useAuthStore: () => ({
    setAuth: mockSetAuth,
  }),
}))

// Mock next/navigation
const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    back: jest.fn(),
    prefetch: jest.fn(),
    refresh: jest.fn(),
  }),
}))

describe('LoginPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  test('renders login form with email and password fields', () => {
    render(<LoginPage />)
    expect(screen.getByPlaceholderText('you@example.com')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Enter password')).toBeInTheDocument()
    expect(screen.getByText('Sign In')).toBeInTheDocument()
  })

  test('renders app title', () => {
    render(<LoginPage />)
    expect(screen.getByText('Exzelon RA')).toBeInTheDocument()
  })

  test('has required attribute on email field', () => {
    render(<LoginPage />)
    const emailInput = screen.getByPlaceholderText('you@example.com')
    expect(emailInput).toHaveAttribute('required')
  })

  test('has required attribute on password field', () => {
    render(<LoginPage />)
    const passwordInput = screen.getByPlaceholderText('Enter password')
    expect(passwordInput).toHaveAttribute('required')
  })

  test('shows sign up link', () => {
    render(<LoginPage />)
    expect(screen.getByText("Don't have an account? Sign up")).toBeInTheDocument()
  })

  test('toggles to registration form when clicking sign up link', async () => {
    render(<LoginPage />)
    const signUpLink = screen.getByText("Don't have an account? Sign up")
    await userEvent.click(signUpLink)
    expect(screen.getByText('Create Account')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('John Doe')).toBeInTheDocument()
  })

  test('successful login redirects to dashboard', async () => {
    mockLogin.mockResolvedValueOnce({
      access_token: 'test-token',
      user: { user_id: 1, email: 'test@test.com', role: 'admin' },
    })

    render(<LoginPage />)
    await userEvent.type(screen.getByPlaceholderText('you@example.com'), 'test@test.com')
    await userEvent.type(screen.getByPlaceholderText('Enter password'), 'password123')
    await userEvent.click(screen.getByText('Sign In'))

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('test@test.com', 'password123')
      expect(mockSetAuth).toHaveBeenCalledWith('test-token', expect.any(Object))
      expect(mockPush).toHaveBeenCalledWith('/dashboard')
    })
  })

  test('shows error message on login failure', async () => {
    mockLogin.mockRejectedValueOnce({
      response: { data: { detail: 'Invalid credentials' } },
    })

    render(<LoginPage />)
    await userEvent.type(screen.getByPlaceholderText('you@example.com'), 'bad@test.com')
    await userEvent.type(screen.getByPlaceholderText('Enter password'), 'wrong')
    await userEvent.click(screen.getByText('Sign In'))

    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument()
    })
  })

  test('disables submit button while loading', async () => {
    mockLogin.mockImplementation(() => new Promise(() => {})) // never resolves

    render(<LoginPage />)
    await userEvent.type(screen.getByPlaceholderText('you@example.com'), 'test@test.com')
    await userEvent.type(screen.getByPlaceholderText('Enter password'), 'password123')

    const submitButton = screen.getByRole('button', { name: /sign in/i })
    await userEvent.click(submitButton)

    await waitFor(() => {
      expect(submitButton).toBeDisabled()
    })
  })
})
