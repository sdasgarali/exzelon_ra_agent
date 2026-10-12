import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SignupPage from '../page'

const mockSignup = jest.fn()
jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api')
  return {
    getApiError: actual.getApiError,
    authApi: {
      signup: (...args: any[]) => mockSignup(...args),
      resendVerification: jest.fn(),
    },
  }
})

jest.mock('@/components/brand-logo', () => ({
  __esModule: true,
  default: () => <span>NeuraLeads</span>,
}))

const STRONG = 'SecurePass123!'

async function fillBasics(user: ReturnType<typeof userEvent.setup>, password = STRONG) {
  await user.type(screen.getByLabelText('Full Name'), 'Jane Doe')
  await user.type(screen.getByLabelText('Company Name'), 'Acme Inc')
  await user.type(screen.getByLabelText('Work Email'), 'jane@acme.com')
  await user.type(screen.getByLabelText('Password'), password)
}

describe('SignupPage', () => {
  beforeEach(() => jest.clearAllMocks())

  test('shows the password rules up front, all unmet', () => {
    render(<SignupPage />)
    for (const id of ['length', 'upper', 'digit', 'special']) {
      expect(screen.getByTestId(`pw-rule-${id}`)).toHaveAttribute('data-met', 'false')
    }
    expect(screen.getByText('At least 8 characters')).toBeInTheDocument()
    expect(screen.getByText('One uppercase letter')).toBeInTheDocument()
  })

  test('checklist updates live as the password is typed', async () => {
    const user = userEvent.setup()
    render(<SignupPage />)
    await user.type(screen.getByLabelText('Password'), 'abcdefgH')
    expect(screen.getByTestId('pw-rule-length')).toHaveAttribute('data-met', 'true')
    expect(screen.getByTestId('pw-rule-upper')).toHaveAttribute('data-met', 'true')
    expect(screen.getByTestId('pw-rule-digit')).toHaveAttribute('data-met', 'false')
    expect(screen.getByTestId('pw-rule-special')).toHaveAttribute('data-met', 'false')
    await user.type(screen.getByLabelText('Password'), '1!')
    expect(screen.getByTestId('pw-rule-digit')).toHaveAttribute('data-met', 'true')
    expect(screen.getByTestId('pw-rule-special')).toHaveAttribute('data-met', 'true')
  })

  test('submit stays disabled until password rules are met AND terms are accepted', async () => {
    const user = userEvent.setup()
    render(<SignupPage />)
    const submit = screen.getByRole('button', { name: 'Create Account' })
    expect(submit).toBeDisabled()

    await fillBasics(user, 'weakpass')
    expect(submit).toBeDisabled()

    await user.click(screen.getByRole('checkbox'))
    expect(submit).toBeDisabled() // rules still unmet

    await user.clear(screen.getByLabelText('Password'))
    await user.type(screen.getByLabelText('Password'), STRONG)
    expect(submit).toBeEnabled()

    await user.click(screen.getByRole('checkbox'))
    expect(submit).toBeDisabled() // terms unticked again
  })

  test('terms checkbox links to /terms and /privacy in a new tab', () => {
    render(<SignupPage />)
    const terms = screen.getByRole('link', { name: 'Terms of Service' })
    const privacy = screen.getByRole('link', { name: 'Privacy Policy' })
    expect(terms).toHaveAttribute('href', '/terms')
    expect(terms).toHaveAttribute('target', '_blank')
    expect(privacy).toHaveAttribute('href', '/privacy')
    expect(privacy).toHaveAttribute('target', '_blank')
    expect(screen.getByRole('checkbox')).toHaveAccessibleName(/I agree to the Terms of Service and Privacy Policy/)
  })

  test('sends accept_terms: true with the form data', async () => {
    mockSignup.mockResolvedValue({ message: 'ok', user_id: 1 })
    const user = userEvent.setup()
    render(<SignupPage />)
    await fillBasics(user)
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Create Account' }))
    await waitFor(() => expect(mockSignup).toHaveBeenCalledTimes(1))
    expect(mockSignup).toHaveBeenCalledWith({
      full_name: 'Jane Doe',
      company_name: 'Acme Inc',
      email: 'jane@acme.com',
      password: STRONG,
      accept_terms: true,
    })
    expect(await screen.findByText('Check your email')).toBeInTheDocument()
  })

  test('a 422 with a list of validation objects renders readable text instead of crashing', async () => {
    mockSignup.mockRejectedValue({
      response: {
        status: 422,
        data: {
          detail: [
            { type: 'value_error', loc: ['body', 'password'], msg: 'Value error, Password must contain at least one number', input: 'x' },
            { type: 'missing', loc: ['body', 'company_name'], msg: 'Field required', input: null },
          ],
        },
      },
    })
    const user = userEvent.setup()
    render(<SignupPage />)
    await fillBasics(user)
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Create Account' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Password must contain at least one number; Company name: Field required')
  })

  test('a plain string error detail is shown as-is', async () => {
    mockSignup.mockRejectedValue({ response: { status: 400, data: { detail: 'Email already registered' } } })
    const user = userEvent.setup()
    render(<SignupPage />)
    await fillBasics(user)
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Create Account' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Email already registered')
  })
})
