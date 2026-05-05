const BASE_URL = import.meta.env.VITE_API_URL ?? ""
const AUTH_TOKEN_KEY = "qwen_coder_access_token"
const REFRESH_TOKEN_KEY = "qwen_coder_refresh_token"

let refreshInFlight: Promise<import("./types").TokenPair> | null = null

export function getAuthToken(): string | null {
  try {
    return window.localStorage.getItem(AUTH_TOKEN_KEY)
  } catch {
    return null
  }
}

export function getRefreshToken(): string | null {
  try {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY)
  } catch {
    return null
  }
}

export function setAuthToken(token: string): void {
  try {
    window.localStorage.setItem(AUTH_TOKEN_KEY, token)
  } catch {
    // ignore storage failures
  }
}

export function setRefreshToken(token: string): void {
  try {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, token)
  } catch {
    // ignore storage failures
  }
}

export function setTokens(tokens: import("./types").TokenPair): void {
  setAuthToken(tokens.access_token)
  setRefreshToken(tokens.refresh_token)
  window.dispatchEvent(new CustomEvent("auth-tokens-changed"))
}

export function clearAuthToken(): void {
  try {
    window.localStorage.removeItem(AUTH_TOKEN_KEY)
    window.localStorage.removeItem(REFRESH_TOKEN_KEY)
    window.dispatchEvent(new CustomEvent("auth-tokens-cleared"))
    window.dispatchEvent(new CustomEvent("auth-tokens-changed"))
  } catch {
    // ignore storage failures
  }
}

async function refreshAccessToken(): Promise<import("./types").TokenPair> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    throw new ApiError(401, "Missing refresh token")
  }

  if (!refreshInFlight) {
    refreshInFlight = fetch(`${BASE_URL}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.text().catch(() => "")
          throw new ApiError(res.status, body || res.statusText)
        }
        return res.json() as Promise<import("./types").TokenPair>
      })
      .then((tokens) => {
        setTokens(tokens)
        return tokens
      })
      .finally(() => {
        refreshInFlight = null
      })
  }

  return refreshInFlight
}

async function request<T>(path: string, options?: RequestInit, retrying = false): Promise<T> {
  const token = getAuthToken()
  const headers = new Headers(options?.headers ?? {})
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`)
  }
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!res.ok) {
    if (res.status === 401 && !retrying && getRefreshToken() && path !== "/api/auth/refresh") {
      try {
        await refreshAccessToken()
        return request<T>(path, options, true)
      } catch {
        clearAuthToken()
        window.dispatchEvent(new CustomEvent("auth-refresh-failed"))
      }
    }
    const body = await res.text().catch(() => "")
    throw new ApiError(res.status, body || res.statusText)
  }

  if (res.status === 204) {
    return undefined as T
  }

  return res.json() as Promise<T>
}

export class ApiError extends Error {
  status: number
  body: string

  constructor(status: number, body: string) {
    super(`API ${status}: ${body}`)
    this.name = "ApiError"
    this.status = status
    this.body = body
  }
}

export const api = {
  health: () => request<import("./types").HealthResponse>("/api/health"),

  config: () => request<import("./types").ConfigResponse>("/api/config"),

  models: () => request<import("./types").OllamaModel[]>("/api/models"),

  browseFolder: () => request<{ path: string | null }>("/api/browse-folder"),

  auth: {
    register: (body: import("./types").RegisterRequest) =>
      request<import("./types").UserPublic>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    login: (body: import("./types").LoginRequest) =>
      request<import("./types").TokenPair>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    refresh: (refreshToken: string) =>
      request<import("./types").TokenPair>("/api/auth/refresh", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken }),
      }),
    logout: (refreshToken?: string | null) =>
      request<void>("/api/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken ?? null }),
      }),
    me: () => request<import("./types").UserPublic>("/api/auth/me"),
    changePassword: (body: import("./types").ChangePasswordRequest) =>
      request<void>("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },

  billing: {
    subscription: () =>
      request<import("./types").BillingSubscriptionPublic>("/api/billing/subscription"),
    checkoutSession: (body: { price_id?: string | null } = {}) =>
      request<import("./types").BillingCheckoutResponse>("/api/billing/checkout-session", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    portalSession: () =>
      request<import("./types").BillingPortalResponse>("/api/billing/portal-session", {
        method: "POST",
      }),
  },

  sessions: {
    list: () => request<import("./types").SessionResponse[]>("/api/sessions"),

    get: (id: string) => request<import("./types").SessionResponse>(`/api/sessions/${encodeURIComponent(id)}`),

    create: (body: import("./types").CreateSessionRequest) =>
      request<import("./types").SessionResponse>("/api/sessions", {
        method: "POST",
        body: JSON.stringify(body),
      }),

    delete: (id: string) =>
      request<{ status: string }>(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE" }),

    messages: (id: string) =>
      request<import("./types").MessageResponse[]>(`/api/sessions/${encodeURIComponent(id)}/messages`),

    sendPrompt: (id: string, body: import("./types").PromptRequest) =>
      request<import("./types").PromptAccepted>(`/api/sessions/${encodeURIComponent(id)}/messages`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },

  agents: {
    list: (sessionId: string) =>
      request<import("./types").AgentSummary[]>(`/api/sessions/${encodeURIComponent(sessionId)}/agents`),

    get: (sessionId: string, name: string) =>
      request<import("./types").AgentDetailResponse>(
        `/api/sessions/${encodeURIComponent(sessionId)}/agents/${encodeURIComponent(name)}`,
      ),

    prompt: (sessionId: string, name: string, body: { prompt: string }) =>
      request<import("./types").PromptAccepted>(
        `/api/sessions/${encodeURIComponent(sessionId)}/agents/${encodeURIComponent(name)}/prompt`,
        { method: "POST", body: JSON.stringify(body) },
      ),
  },

  files: {
    tree: (sessionId: string) =>
      request<import("./types").FileEntry[]>(`/api/sessions/${encodeURIComponent(sessionId)}/files`),

    read: (sessionId: string, filePath: string) =>
      request<import("./types").FileContent>(
        `/api/sessions/${encodeURIComponent(sessionId)}/files/${filePath}`,
      ),
  },

  workflows: {
    list: () => request<import("./types").WorkflowResponse[]>("/api/workflows"),

    get: (id: string) =>
      request<import("./types").WorkflowResponse>(`/api/workflows/${encodeURIComponent(id)}`),

    create: (body: {
      name: string
      description?: string
      definition?: import("./types").WorkflowDefinition
      enabled?: boolean
    }) =>
      request<import("./types").WorkflowResponse>("/api/workflows", {
        method: "POST",
        body: JSON.stringify(body),
      }),

    update: (
      id: string,
      body: Partial<{
        name: string
        description: string
        definition: import("./types").WorkflowDefinition
        enabled: boolean
      }>,
    ) =>
      request<import("./types").WorkflowResponse>(`/api/workflows/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),

    delete: (id: string) =>
      request<void>(`/api/workflows/${encodeURIComponent(id)}`, { method: "DELETE" }),

    execute: (id: string) =>
      request<import("./types").WorkflowExecuteResponse>(
        `/api/workflows/${encodeURIComponent(id)}/execute`,
        { method: "POST" },
      ),

    runs: (id: string) =>
      request<import("./types").WorkflowRunResponse[]>(`/api/workflows/${encodeURIComponent(id)}/runs`),
  },

  uploads: {
    stage: async (sessionId: string, files: File[]): Promise<import("./types").UploadResponse> => {
      const form = new FormData()
      for (const f of files) form.append("files", f)
      const send = () => {
        const token = getAuthToken()
        return fetch(`${BASE_URL}/api/sessions/${encodeURIComponent(sessionId)}/uploads`, {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          body: form,
        })
      }
      let res = await send()
      if (res.status === 401 && getRefreshToken()) {
        try {
          await refreshAccessToken()
          res = await send()
        } catch {
          clearAuthToken()
          window.dispatchEvent(new CustomEvent("auth-refresh-failed"))
        }
      }
      if (!res.ok) {
        const body = await res.text().catch(() => "")
        throw new ApiError(res.status, body || res.statusText)
      }
      return res.json() as Promise<import("./types").UploadResponse>
    },

    delete: (sessionId: string, uploadId: string) =>
      request<{ status: string }>(
        `/api/sessions/${encodeURIComponent(sessionId)}/uploads/${encodeURIComponent(uploadId)}`,
        { method: "DELETE" },
      ),

    thumbnailUrl: (sessionId: string, uploadId: string) =>
      `${BASE_URL}/api/sessions/${encodeURIComponent(sessionId)}/uploads/${encodeURIComponent(uploadId)}/thumbnail`,

    fileUrl: (sessionId: string, uploadId: string) =>
      `${BASE_URL}/api/sessions/${encodeURIComponent(sessionId)}/uploads/${encodeURIComponent(uploadId)}`,
  },
}
