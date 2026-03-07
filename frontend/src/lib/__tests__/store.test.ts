import { useAuthStore } from '@/lib/store'

describe('Auth Store', () => {
  beforeEach(() => {
    // Reset store state before each test
    useAuthStore.setState({
      token: null,
      user: null,
    })
    window.localStorage.clear()
  })

  const mockUser = {
    user_id: 1,
    email: 'test@example.com',
    full_name: 'Test User',
    role: 'admin' as const,
    is_active: true,
  }

  test('initial state has no token or user', () => {
    const state = useAuthStore.getState()
    expect(state.token).toBeNull()
    expect(state.user).toBeNull()
  })

  test('setAuth stores token and user', () => {
    useAuthStore.getState().setAuth('test-token', mockUser)

    const state = useAuthStore.getState()
    expect(state.token).toBe('test-token')
    expect(state.user).toEqual(mockUser)
  })

  test('logout clears token and user', () => {
    useAuthStore.getState().setAuth('test-token', mockUser)
    useAuthStore.getState().logout()

    const state = useAuthStore.getState()
    expect(state.token).toBeNull()
    expect(state.user).toBeNull()
  })

  test('isAuthenticated returns true when token exists', () => {
    useAuthStore.getState().setAuth('test-token', mockUser)
    expect(useAuthStore.getState().isAuthenticated()).toBe(true)
  })

  test('isAuthenticated returns false when no token', () => {
    expect(useAuthStore.getState().isAuthenticated()).toBe(false)
  })

  test('isSuperAdmin returns true for super_admin role', () => {
    const superAdmin = { ...mockUser, role: 'super_admin' as const }
    useAuthStore.getState().setAuth('test-token', superAdmin)
    expect(useAuthStore.getState().isSuperAdmin()).toBe(true)
  })

  test('isSuperAdmin returns false for admin role', () => {
    useAuthStore.getState().setAuth('test-token', mockUser)
    expect(useAuthStore.getState().isSuperAdmin()).toBe(false)
  })

  test('isAdmin returns true for admin role', () => {
    useAuthStore.getState().setAuth('test-token', mockUser)
    expect(useAuthStore.getState().isAdmin()).toBe(true)
  })

  test('isAdmin returns true for super_admin role', () => {
    const superAdmin = { ...mockUser, role: 'super_admin' as const }
    useAuthStore.getState().setAuth('test-token', superAdmin)
    expect(useAuthStore.getState().isAdmin()).toBe(true)
  })

  test('isAdmin returns false for viewer role', () => {
    const viewer = { ...mockUser, role: 'viewer' as const }
    useAuthStore.getState().setAuth('test-token', viewer)
    expect(useAuthStore.getState().isAdmin()).toBe(false)
  })

  test('isAdmin returns false for operator role', () => {
    const operator = { ...mockUser, role: 'operator' as const }
    useAuthStore.getState().setAuth('test-token', operator)
    expect(useAuthStore.getState().isAdmin()).toBe(false)
  })
})
