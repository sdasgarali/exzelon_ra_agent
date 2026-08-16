import { create } from 'zustand'
import { persist, createJSONStorage, type StateStorage } from 'zustand/middleware'

interface Tenant {
  tenant_id: number
  name: string
  slug: string
  plan: string
  industry: string | null
  website: string | null
  company_address: string | null
  logo_url: string | null
}

interface User {
  user_id: number
  email: string
  full_name: string | null
  role: string
  base_role?: string | null  // built-in role a custom role resolves to (for UI gating)
  is_active: boolean
  tenant_id: number | null
  tenant: Tenant | null
  is_verified: boolean
  notify_inapp_enabled?: boolean
  notify_email_enabled?: boolean
}

interface Impersonation {
  tenantId: number
  tenantName: string
  tenantPlan: string
}

interface AuthState {
  token: string | null
  refreshToken: string | null
  user: User | null
  impersonation: Impersonation | null
  rememberMe: boolean
  setAuth: (token: string, user: User, refreshToken?: string, rememberMe?: boolean) => void
  setUser: (user: User) => void
  setTokens: (token: string, refreshToken: string) => void
  logout: () => void
  isAuthenticated: () => boolean
  isSuperAdmin: () => boolean
  isAdmin: () => boolean
  startImpersonation: (tenantId: number, tenantName: string, tenantPlan: string) => void
  stopImpersonation: () => void
  isImpersonating: () => boolean
}

const STORAGE_KEY = 'auth-storage'

/**
 * Custom storage that writes to localStorage when "Remember Me" is checked,
 * and sessionStorage otherwise. On read, checks both (localStorage first)
 * so tokens are found regardless of where they were stored.
 */
const dualStorage: StateStorage = {
  getItem: (name: string): string | null => {
    if (typeof window === 'undefined') return null
    // Check localStorage first (remember me), then sessionStorage
    return localStorage.getItem(name) ?? sessionStorage.getItem(name)
  },
  setItem: (name: string, value: string): void => {
    if (typeof window === 'undefined') return
    // Determine current rememberMe preference from the state being persisted
    try {
      const parsed = JSON.parse(value)
      const rememberMe = parsed?.state?.rememberMe ?? true
      if (rememberMe) {
        localStorage.setItem(name, value)
        sessionStorage.removeItem(name)
      } else {
        sessionStorage.setItem(name, value)
        localStorage.removeItem(name)
      }
    } catch {
      localStorage.setItem(name, value)
    }
  },
  removeItem: (name: string): void => {
    if (typeof window === 'undefined') return
    localStorage.removeItem(name)
    sessionStorage.removeItem(name)
  },
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      refreshToken: null,
      user: null,
      impersonation: null,
      rememberMe: true,
      setAuth: (token: string, user: User, refreshToken?: string, rememberMe?: boolean) => set({
        token,
        refreshToken: refreshToken || null,
        user,
        impersonation: null,
        rememberMe: rememberMe ?? get().rememberMe,
      }),
      setUser: (user: User) => set({ user }),
      setTokens: (token: string, refreshToken: string) => set({
        token,
        refreshToken,
      }),
      logout: () => {
        // Clear both storages on logout
        localStorage.removeItem(STORAGE_KEY)
        sessionStorage.removeItem(STORAGE_KEY)
        set({
          token: null,
          refreshToken: null,
          user: null,
          impersonation: null,
        })
      },
      isAuthenticated: () => !!get().token,
      isSuperAdmin: () => {
        const role = get().user?.role
        return role === 'super_admin'
      },
      isAdmin: () => {
        const role = get().user?.role
        return role === 'admin' || role === 'super_admin'
      },
      startImpersonation: (tenantId: number, tenantName: string, tenantPlan: string) => set({
        impersonation: { tenantId, tenantName, tenantPlan },
      }),
      stopImpersonation: () => set({
        impersonation: null,
      }),
      isImpersonating: () => !!get().impersonation,
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => dualStorage),
    }
  )
)
