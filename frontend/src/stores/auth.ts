import { create } from "zustand"
import { api, clearAuthToken, getAuthToken, getRefreshToken, setTokens } from "@/api/client"
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
    const { accessToken, refreshToken } = storageTokens()
    set({ accessToken, refreshToken, loading: true })

    if (!accessToken && !refreshToken) {
      set({ user: null, isAuthenticated: false, loading: false, initialized: true })
      return
    }

    try {
      const user = await api.auth.me()
      const tokens = storageTokens()
      set({
        user,
        ...tokens,
        isAuthenticated: true,
        loading: false,
        initialized: true,
      })
    } catch {
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

  register: async (body) => {
    set({ loading: true })
    try {
      await api.auth.register(body)
      const tokens = await api.auth.login({ email: body.email, password: body.password })
      setTokens(tokens)
      const user = await api.auth.me()
      set({
        user,
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        isAuthenticated: true,
        loading: false,
        initialized: true,
      })
    } catch (error) {
      set({ loading: false, initialized: true })
      throw error
    }
  },

  login: async (body) => {
    set({ loading: true })
    try {
      const tokens = await api.auth.login(body)
      setTokens(tokens)
      const user = await api.auth.me()
      set({
        user,
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        isAuthenticated: true,
        loading: false,
        initialized: true,
      })
    } catch (error) {
      set({ loading: false, initialized: true })
      throw error
    }
  },

  logout: async () => {
    const refreshToken = get().refreshToken ?? getRefreshToken()
    set({ loading: true })
    try {
      await api.auth.logout(refreshToken)
    } catch {
      // Local logout should still happen if the server session is already gone.
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
    const refreshToken = get().refreshToken ?? getRefreshToken()
    if (!refreshToken) {
      clearAuthToken()
      throw new Error("Missing refresh token")
    }
    const tokens = await api.auth.refresh(refreshToken)
    setTokens(tokens)
    set({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      isAuthenticated: !!get().user,
    })
    return tokens
  },

  fetchMe: async () => {
    const user = await api.auth.me()
    const tokens = storageTokens()
    set({ user, ...tokens, isAuthenticated: true, initialized: true })
    return user
  },

  changePassword: async (body) => {
    await api.auth.changePassword(body)
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
