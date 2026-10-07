import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const mockList = jest.fn()
const mockCreate = jest.fn()
const mockRevoke = jest.fn()

jest.mock('@/lib/api', () => ({
  integrationsApi: {
    listApiKeys: (...args: any[]) => mockList(...args),
    createApiKey: (...args: any[]) => mockCreate(...args),
    revokeApiKey: (...args: any[]) => mockRevoke(...args),
  },
  getApiError: (err: any, fallback: string) => err?.response?.data?.detail || fallback,
}))

const mockToast = jest.fn()
jest.mock('@/components/toast', () => ({
  useToast: () => ({ toast: mockToast }),
}))

let mockAuth: any = {
  user: { user_id: 1, role: 'admin', tenant_id: 7 },
  impersonation: null,
}
jest.mock('@/lib/store', () => ({
  useAuthStore: () => mockAuth,
}))

import ApiKeysMcpTab from '../api-keys-mcp-tab'
import {
  API_KEY_PLACEHOLDER,
  buildMcpSnippets,
  deriveOrigin,
  getMcpEndpoints,
} from '../mcp-snippets'

const RAW_KEY = 'exz_0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcd'

function renderTab(props: { readOnly?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ApiKeysMcpTab {...props} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  jest.clearAllMocks()
  mockAuth = { user: { user_id: 1, role: 'admin', tenant_id: 7 }, impersonation: null }
})

describe('mcp-snippets helpers', () => {
  it('derives the origin from NEXT_PUBLIC_API_URL and falls back to production', () => {
    expect(deriveOrigin('https://neuraleads.ai/api/v1')).toBe('https://neuraleads.ai')
    expect(deriveOrigin('http://localhost:8000/api/v1/')).toBe('http://localhost:8000')
    expect(deriveOrigin(undefined)).toBe('https://neuraleads.ai')
    expect(deriveOrigin('/api/v1')).toBe('https://neuraleads.ai')
    expect(getMcpEndpoints('https://staging.example.com/api/v1')).toEqual({
      mcpUrl: 'https://staging.example.com/mcp',
      apiUrl: 'https://staging.example.com/api/v1',
    })
  })

  it('builds every client snippet with the placeholder by default', () => {
    const snippets = buildMcpSnippets(getMcpEndpoints('https://neuraleads.ai/api/v1'))
    const byId = Object.fromEntries(snippets.map((s) => [s.id, s.code]))

    expect(byId.claude_code).toBe(
      `claude mcp add --transport http neuraleads https://neuraleads.ai/mcp --header "Authorization: Bearer ${API_KEY_PLACEHOLDER}"`,
    )
    expect(JSON.parse(byId.claude_desktop)).toEqual({
      mcpServers: {
        neuraleads: {
          command: 'npx',
          args: ['-y', 'mcp-remote', 'https://neuraleads.ai/mcp', '--header', `Authorization:Bearer ${API_KEY_PLACEHOLDER}`],
        },
      },
    })
    expect(JSON.parse(byId.cursor)).toEqual({
      mcpServers: {
        neuraleads: { url: 'https://neuraleads.ai/mcp', headers: { Authorization: `Bearer ${API_KEY_PLACEHOLDER}` } },
      },
    })
    expect(byId.stdio).toContain('pip install ./mcp_server')
    expect(byId.stdio).toContain('NEURALEADS_API_URL=https://neuraleads.ai/api/v1')
    expect(byId.stdio).toContain(`NEURALEADS_API_KEY=${API_KEY_PLACEHOLDER}`)
    expect(byId.stdio).toContain('neuraleads-mcp')
  })

  it('substitutes a real key when given one', () => {
    const snippets = buildMcpSnippets(getMcpEndpoints(null), RAW_KEY)
    for (const s of snippets) {
      expect(s.code).toContain(RAW_KEY)
      expect(s.code).not.toContain(API_KEY_PLACEHOLDER)
    }
  })
})

describe('ApiKeysMcpTab', () => {
  it('shows the empty state when there are no keys', async () => {
    mockList.mockResolvedValue([])
    renderTab()
    expect(await screen.findByText('No API keys yet')).toBeInTheDocument()
  })

  it('lists keys with prefix, scopes and expiry', async () => {
    mockList.mockResolvedValue([
      {
        key_id: 3, name: 'Claude Desktop', key_prefix: 'exz_abcd1234', scopes: ['write'], is_active: true,
        last_used_at: null, created_at: '2026-10-01T10:00:00', expires_at: null,
      },
    ])
    renderTab()
    const row = (await screen.findByRole('cell', { name: 'Claude Desktop' })).closest('tr') as HTMLElement
    expect(within(row).getByText('exz_abcd1234…')).toBeInTheDocument()
    expect(within(row).getByText('write')).toBeInTheDocument()
    expect(within(row).getAllByText('Never')).toHaveLength(2) // last used + expires
  })

  it('creates a key, shows it exactly once, and can fill it into the snippets', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([])
    mockCreate.mockResolvedValue({
      key_id: 9, name: 'Cursor', key: RAW_KEY, key_prefix: RAW_KEY.slice(0, 12), scopes: ['read'],
      expires_at: null, message: 'Save this key',
    })
    renderTab()
    await screen.findByText('No API keys yet')

    await user.click(screen.getByRole('button', { name: /create api key/i }))
    const dialog = await screen.findByRole('dialog')

    // Read is the default scope; admin shows a warning.
    expect(within(dialog).getByRole('radio', { name: /^read/i })).toBeChecked()
    await user.click(within(dialog).getByRole('radio', { name: /^admin/i }))
    expect(within(dialog).getByText(/an admin key can do everything/i)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('radio', { name: /^read/i }))

    await user.type(within(dialog).getByLabelText('Name'), '  Cursor  ')
    await user.selectOptions(within(dialog).getByLabelText('Expires'), '90')
    await user.click(within(dialog).getByRole('button', { name: /^create key$/i }))

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith({ name: 'Cursor', scopes: ['read'], expires_in_days: 90 }),
    )
    const secret = await within(dialog).findByTestId('new-api-key')
    expect(secret).toHaveValue(RAW_KEY)
    expect(secret).toHaveAttribute('readonly')
    expect(within(dialog).getByText(/you won't see it again/i)).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Copy API key' }))
    await expect(navigator.clipboard.readText()).resolves.toBe(RAW_KEY)

    await user.click(within(dialog).getByRole('button', { name: /fill into setup snippets/i }))
    await user.click(within(dialog).getByRole('button', { name: /i've saved my key/i }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    // The key is gone from the dialog but embedded in the snippets on request.
    expect(screen.queryByTestId('new-api-key')).not.toBeInTheDocument()
    expect(screen.getByTestId('snippet-claude_code')).toHaveTextContent(RAW_KEY)

    // Reopening the dialog starts a fresh form, never the old key.
    await user.click(screen.getByRole('button', { name: /create api key/i }))
    const reopened = await screen.findByRole('dialog')
    expect(within(reopened).queryByTestId('new-api-key')).not.toBeInTheDocument()
    expect(within(reopened).getByLabelText('Name')).toHaveValue('')

    // The raw key never touches web storage.
    expect(JSON.stringify({ ...window.localStorage })).not.toContain(RAW_KEY)
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain(RAW_KEY)
  })

  it('sends expires_in_days null for "Never" and validates the name', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([])
    mockCreate.mockResolvedValue({ key_id: 1, name: 'x', key: RAW_KEY, key_prefix: 'exz_', scopes: ['read'] })
    renderTab()
    await screen.findByText('No API keys yet')
    await user.click(screen.getByRole('button', { name: /create api key/i }))
    const dialog = await screen.findByRole('dialog')

    await user.click(within(dialog).getByRole('button', { name: /^create key$/i }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent(/give the key a name/i)
    expect(mockCreate).not.toHaveBeenCalled()

    await user.type(within(dialog).getByLabelText('Name'), 'Claude')
    await user.click(within(dialog).getByRole('button', { name: /^create key$/i }))
    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith({ name: 'Claude', scopes: ['read'], expires_in_days: null }),
    )
  })

  it('shows a clear message when the user is not allowed (403)', async () => {
    mockList.mockRejectedValue({ response: { status: 403, data: { detail: 'Access denied' } } })
    renderTab()
    expect(await screen.findByText(/do not have permission to manage api keys/i)).toBeInTheDocument()
  })

  it('surfaces the backend message on a 400 when creating', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([])
    mockCreate.mockRejectedValue({ response: { status: 400, data: { detail: 'Invalid scope: owner' } } })
    renderTab()
    await screen.findByText('No API keys yet')
    await user.click(screen.getByRole('button', { name: /create api key/i }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Name'), 'Bad')
    await user.click(within(dialog).getByRole('button', { name: /^create key$/i }))
    expect(await within(dialog).findByText('Invalid scope: owner')).toBeInTheDocument()
  })

  it('revokes a key after confirmation', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([
      { key_id: 5, name: 'Old key', key_prefix: 'exz_deadbeef', scopes: ['read'], is_active: true, last_used_at: null, created_at: null, expires_at: null },
    ])
    mockRevoke.mockResolvedValue(undefined)
    renderTab()
    await user.click(await screen.findByRole('button', { name: 'Revoke API key Old key' }))
    const dialog = await screen.findByRole('dialog')
    expect(mockRevoke).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole('button', { name: /^revoke key$/i }))
    await waitFor(() => expect(mockRevoke).toHaveBeenCalledWith(5))
    expect(mockToast).toHaveBeenCalledWith('success', 'API key revoked', expect.any(String))
  })

  it('asks a super admin to pick a tenant before loading keys', async () => {
    mockAuth = { user: { user_id: 1, role: 'super_admin', tenant_id: null }, impersonation: null }
    renderTab()
    expect(screen.getByText(/api keys belong to a tenant/i)).toBeInTheDocument()
    expect(mockList).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /create api key/i })).not.toBeInTheDocument()
  })

  it('copies a setup snippet', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([])
    renderTab()
    await user.click(screen.getByRole('tab', { name: 'Cursor' }))
    await user.click(screen.getByRole('button', { name: 'Copy Cursor snippet' }))
    const copied = await navigator.clipboard.readText()
    expect(JSON.parse(copied).mcpServers.neuraleads.headers.Authorization).toBe(`Bearer ${API_KEY_PLACEHOLDER}`)
  })
})
