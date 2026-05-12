import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export interface LOB {
  lob_id: number
  tenant_id: number
  name: string
  slug: string
  lob_type: string
  description: string | null
  lead_source_config: Record<string, any> | null
  icp_config: Record<string, any> | null
  business_rules: Record<string, any> | null
  prompt_profile: Record<string, any> | null
  target_industries: string[] | null
  target_job_titles: string[] | null
  exclude_keywords: string[] | null
  is_default: boolean
  status: string
  color: string | null
  icon: string | null
  created_at: string | null
  updated_at: string | null
}

export interface LOBTypeInfo {
  lob_type: string
  label: string
  description: string
  default_color: string
  default_icon: string
}

interface LOBState {
  lobs: LOB[]
  activeLobId: number | null
  lobTypes: LOBTypeInfo[]
  setLobs: (lobs: LOB[]) => void
  setActiveLob: (lobId: number | null) => void
  setLobTypes: (types: LOBTypeInfo[]) => void
  getActiveLob: () => LOB | null
  getDefaultLob: () => LOB | null
  clearLobState: () => void
}

export const useLobStore = create<LOBState>()(
  persist(
    (set, get) => ({
      lobs: [],
      activeLobId: null,
      lobTypes: [],
      setLobs: (lobs: LOB[]) => {
        set({ lobs })
        // Auto-select default LOB if no active selection
        const current = get().activeLobId
        if (current === null && lobs.length > 0) {
          const defaultLob = lobs.find(l => l.is_default) || lobs[0]
          set({ activeLobId: defaultLob.lob_id })
        }
      },
      setActiveLob: (lobId: number | null) => set({ activeLobId: lobId }),
      setLobTypes: (types: LOBTypeInfo[]) => set({ lobTypes: types }),
      getActiveLob: () => {
        const { lobs, activeLobId } = get()
        if (activeLobId === null) return null
        return lobs.find(l => l.lob_id === activeLobId) || null
      },
      getDefaultLob: () => {
        const { lobs } = get()
        return lobs.find(l => l.is_default) || lobs[0] || null
      },
      clearLobState: () => set({ lobs: [], activeLobId: null, lobTypes: [] }),
    }),
    {
      name: 'lob-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ activeLobId: state.activeLobId }),
    }
  )
)
