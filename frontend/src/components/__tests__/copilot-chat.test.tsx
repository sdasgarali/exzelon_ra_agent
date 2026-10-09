import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mockChat = jest.fn()
const mockHistory = jest.fn()
const mockClear = jest.fn()

jest.mock('@/lib/api', () => ({
  copilotApi: {
    chat: (...args: any[]) => mockChat(...args),
    history: (...args: any[]) => mockHistory(...args),
    clearHistory: (...args: any[]) => mockClear(...args),
  },
  getApiError: (err: any, fallback: string) => err?.response?.data?.detail || fallback,
}))

let mockAuth: any = { user: { user_id: 1, role: 'admin', tenant_id: 7 } }
jest.mock('@/lib/store', () => ({
  useAuthStore: () => mockAuth,
}))

let mockPathname = '/dashboard'
jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}))

jest.mock('next/link', () => {
  return ({ children, href, ...props }: any) => <a href={href} {...props}>{children}</a>
})

import { CopilotChat, getPageContext } from '../copilot-chat'

const NOT_CONFIGURED = 'AI service not configured. Set an AI provider and API key in Settings.'

async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  render(<CopilotChat />)
  await user.click(screen.getByRole('button', { name: 'Open AI Copilot' }))
  return screen.getByRole('dialog', { name: 'AI Copilot' })
}

beforeEach(() => {
  jest.clearAllMocks()
  mockPathname = '/dashboard'
  mockAuth = { user: { user_id: 1, role: 'admin', tenant_id: 7 } }
  mockHistory.mockResolvedValue({ messages: [] })
})

describe('getPageContext', () => {
  it('returns the dashboard section', () => {
    expect(getPageContext('/dashboard')).toBe('dashboard')
    expect(getPageContext('/dashboard/campaigns/12')).toBe('campaigns')
    expect(getPageContext(null)).toBe('dashboard')
  })
})

describe('CopilotChat', () => {
  it('loads and renders stored history on first open', async () => {
    const user = userEvent.setup()
    mockHistory.mockResolvedValue({
      messages: [
        { id: 1, role: 'user', content: 'Hi there', context_page: 'dashboard', created_at: '2026-10-09T10:00:00' },
        { id: 2, role: 'assistant', content: 'Hello! How can I help?', context_page: 'dashboard', created_at: '2026-10-09T10:00:01' },
      ],
    })
    await openPanel(user)
    expect(await screen.findByText('Hi there')).toBeInTheDocument()
    expect(screen.getByText('Hello! How can I help?')).toBeInTheDocument()
    expect(mockHistory).toHaveBeenCalledWith(50)
    expect(mockHistory).toHaveBeenCalledTimes(1)
  })

  it('sends only the new message with the page context and renders the reply', async () => {
    const user = userEvent.setup()
    mockPathname = '/dashboard/campaigns/5'
    mockChat.mockResolvedValue({ response: 'Here is a **plan**:\n- Step one\n- Step two' })
    await openPanel(user)
    const box = await screen.findByLabelText('Message AI Copilot')
    await waitFor(() => expect(box).not.toBeDisabled())

    await user.type(box, 'Help me{Enter}')
    expect(mockChat).toHaveBeenCalledWith('Help me', 'campaigns')
    expect(screen.getByText('Help me')).toBeInTheDocument()
    expect(await screen.findByText('plan')).toHaveProperty('tagName', 'STRONG')
    const items = screen.getAllByRole('listitem')
    expect(items.map((li) => li.textContent)).toEqual(['Step one', 'Step two'])
  })

  it('Shift+Enter inserts a newline instead of sending', async () => {
    const user = userEvent.setup()
    await openPanel(user)
    const box = await screen.findByLabelText('Message AI Copilot')
    await waitFor(() => expect(box).not.toBeDisabled())
    await user.type(box, 'line one{Shift>}{Enter}{/Shift}line two')
    expect(mockChat).not.toHaveBeenCalled()
    expect(box).toHaveValue('line one\nline two')
  })

  it('shows the backend detail and admin hint on 503, and retries', async () => {
    const user = userEvent.setup()
    mockChat.mockRejectedValueOnce({ response: { status: 503, data: { detail: NOT_CONFIGURED } } })
    mockChat.mockResolvedValueOnce({ response: 'Now it works' })
    await openPanel(user)
    const box = await screen.findByLabelText('Message AI Copilot')
    await waitFor(() => expect(box).not.toBeDisabled())
    await user.type(box, 'Hello{Enter}')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(NOT_CONFIGURED)
    expect(alert).toHaveTextContent(/ask an admin to set the ai provider/i)
    expect(within(alert).getByRole('link', { name: 'Open Settings' })).toHaveAttribute('href', '/dashboard/settings')

    await user.click(within(alert).getByRole('button', { name: 'Retry sending message' }))
    expect(await screen.findByText('Now it works')).toBeInTheDocument()
    expect(mockChat).toHaveBeenCalledTimes(2)
    expect(mockChat).toHaveBeenLastCalledWith('Hello', 'dashboard')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getAllByText('Hello')).toHaveLength(1) // no duplicate user bubble
  })

  it('hides the settings link for non-admins on 503', async () => {
    const user = userEvent.setup()
    mockAuth = { user: { user_id: 2, role: 'recruiter', tenant_id: 7 } }
    mockChat.mockRejectedValue({ response: { status: 503, data: { detail: NOT_CONFIGURED } } })
    await openPanel(user)
    const box = await screen.findByLabelText('Message AI Copilot')
    await waitFor(() => expect(box).not.toBeDisabled())
    await user.type(box, 'Hello{Enter}')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/ask an admin/i)
    expect(within(alert).queryByRole('link')).not.toBeInTheDocument()
  })

  it('sends a suggested prompt when its chip is clicked', async () => {
    const user = userEvent.setup()
    mockPathname = '/dashboard/mailboxes'
    mockChat.mockResolvedValue({ response: 'Go to Mailboxes and click Connect.' })
    await openPanel(user)
    await user.click(await screen.findByRole('button', { name: 'How do I connect a Gmail account?' }))
    expect(mockChat).toHaveBeenCalledWith('How do I connect a Gmail account?', 'mailboxes')
    expect(await screen.findByText('Go to Mailboxes and click Connect.')).toBeInTheDocument()
  })

  it('renders /dashboard routes as links and escapes HTML', async () => {
    const user = userEvent.setup()
    mockHistory.mockResolvedValue({
      messages: [
        {
          id: 3, role: 'assistant', context_page: null, created_at: '2026-10-09T10:00:00',
          content: 'Open /dashboard/mailboxes or `/dashboard/settings`. <img src=x onerror=alert(1)>',
        },
      ],
    })
    await openPanel(user)
    const link = await screen.findByRole('link', { name: '/dashboard/mailboxes' })
    expect(link).toHaveAttribute('href', '/dashboard/mailboxes')
    expect(screen.getByRole('link', { name: '/dashboard/settings' })).toHaveAttribute('href', '/dashboard/settings')
    expect(document.querySelector('img')).toBeNull()
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument()

    // Following a route link minimizes the panel.
    await user.click(link)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expand AI Copilot' })).toBeInTheDocument()
  })

  it('clears the conversation after confirmation', async () => {
    const user = userEvent.setup()
    mockHistory.mockResolvedValue({
      messages: [{ id: 1, role: 'user', content: 'Old question', context_page: null, created_at: '2026-10-09T10:00:00' }],
    })
    mockClear.mockResolvedValue({ deleted: 1 })
    const confirmSpy = jest.spyOn(window, 'confirm')

    await openPanel(user)
    await screen.findByText('Old question')

    confirmSpy.mockReturnValueOnce(false)
    await user.click(screen.getByRole('button', { name: 'Clear conversation' }))
    expect(mockClear).not.toHaveBeenCalled()

    confirmSpy.mockReturnValueOnce(true)
    await user.click(screen.getByRole('button', { name: 'Clear conversation' }))
    await waitFor(() => expect(mockClear).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.queryByText('Old question')).not.toBeInTheDocument())
    expect(screen.getByText('How can I help?')).toBeInTheDocument()
    confirmSpy.mockRestore()
  })
})
