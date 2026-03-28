import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface Tenant {
  tenant_id: number
  name: string
  slug: string
  plan: string
}

interface User {
  user_id: number
  email: string
  full_name: string | null
  role: 'super_admin' | 'admin' | 'operator' | 'viewer'
  is_active: boolean
  tenant_id: number | null
  tenant: Tenant | null
  is_verified: boolean
}

interface Impersonation {
  tenantId: number
  tenantName: string
  tenantPlan: string
}

interface AuthState {
  token: string | null
  user: User | null
  impersonation: Impersonation | null
  setAuth: (token: string, user: User) => void
  logout: () => void
  isAuthenticated: () => boolean
  isSuperAdmin: () => boolean
  isAdmin: () => boolean
  startImpersonation: (tenantId: number, tenantName: string, tenantPlan: string) => void
  stopImpersonation: () => void
  isImpersonating: () => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      impersonation: null,
      setAuth: (token: string, user: User) => set({
        token,
        user,
        impersonation: null,
      }),
      logout: () => set({
        token: null,
        user: null,
        impersonation: null,
      }),
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
      name: 'auth-storage',
    }
  )
)
