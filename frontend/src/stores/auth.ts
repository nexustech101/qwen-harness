import { create } from "zustand"
import { api, clearAuthToken, getAuthToken, getRefreshToken } from "@/api/client"
import type { ChangePasswordRequest, LoginRequest, RegisterRequest, TokenPair, UserPublic } from "@/api/types"

interface AuthStore {
  user: UserPublic | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  loading: boolean
  initialized: boolean
  bootstrap: () => Promise<void>
  register: (body: RegisterRequest) => Promise<void>
  login: (body: LoginRequest) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<TokenPair>
  fetchMe: () => Promise<UserPublic>
  changePassword: (body: ChangePasswordRequest) => Promise<void>
  clearAuth: () => void
  syncTokensFromStorage: () => void
}

function storageTokens() {
  return {
    accessToken: getAuthToken(),
    refreshToken: getRefreshToken(),
  }
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  ...storageTokens(),
  isAuthenticated: !!getAuthToken(),
  loading: false,
  initialized: false,

  syncTokensFromStorage: () => {
    const tokens = storageTokens()
    set({
      ...tokens,
      isAuthenticated: !!tokens.accessToken && !!get().user,
    })
  },

  bootstrap: async () => {
    set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false, loading: false, initialized: true })
  },

  register: async (body) => {
    set({ loading: true })
    try {
      await api.auth.register(body)
    } catch {
      // no-op — auth not implemented
    } finally {
      set({ loading: false, initialized: true })
    }
  },

  login: async (body) => {
    set({ loading: true })
    try {
      await api.auth.login(body)
    } catch {
      // no-op — auth not implemented
    } finally {
      set({ loading: false, initialized: true })
    }
  },

  logout: async () => {
    const refreshToken = get().refreshToken ?? getRefreshToken()
    set({ loading: true })
    try {
      await api.auth.logout(refreshToken)
    } catch {
      // no-op
    } finally {
      clearAuthToken()
      set({
        user: null,
        accessToken: null,
        refreshToken: null,
        isAuthenticated: false,
        loading: false,
        initialized: true,
      })
    }
  },

  refresh: async () => {
    return {} as TokenPair
  },

  fetchMe: async () => {
    return api.auth.me()
  },

  changePassword: async (_body) => {
    // no-op — auth not implemented
  },

  clearAuth: () => {
    clearAuthToken()
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      loading: false,
      initialized: true,
    })
  },
}))
