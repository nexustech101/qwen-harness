import { useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api, ApiError } from "./client"
import type { CreateSessionRequest, PromptRequest } from "./types"
import { useAuthStore } from "@/stores/auth"
import { useUIStore } from "@/stores/ui"
import { toast } from "sonner"

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: 1,
  })
}

export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: api.config,
    staleTime: 5 * 60_000,
  })
}

export function useModels() {
  return useQuery({
    queryKey: ["models"],
    queryFn: api.models,
    staleTime: 60_000,
  })
}

export function useSessions() {
  const userId = useAuthStore((s) => s.user?.id)
  const initialized = useAuthStore((s) => s.initialized)
  return useQuery({
    queryKey: ["sessions", userId ?? "guest"],
    queryFn: api.sessions.list,
    enabled: initialized,
  })
}

export function useSession(id: string | null) {
  const setActiveSession = useUIStore((s) => s.setActiveSession)
  const query = useQuery({
    queryKey: ["session", id],
    queryFn: () => api.sessions.get(id!),
    enabled: !!id,
    retry: (failureCount, error) => {
      // Don't retry on 404 — session doesn't exist
      if (error instanceof ApiError && error.status === 404) return false
      return failureCount < 2
    },
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.status === "running" ? 3000 : false
    },
  })

  useEffect(() => {
    if (query.error instanceof ApiError && query.error.status === 404) {
      setActiveSession(null)
      toast.error("Session unavailable or no longer accessible")
    }
  }, [query.error, setActiveSession])

  return query
}

export function useCreateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (req: CreateSessionRequest) => api.sessions.create(req),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  })
}

export function useDeleteSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.sessions.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  })
}

export function useMessages(sessionId: string | null) {
  return useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () => api.sessions.messages(sessionId!),
    enabled: !!sessionId,
  })
}

export function useSendPrompt(sessionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (req: PromptRequest) => api.sessions.sendPrompt(sessionId, req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["session", sessionId] })
    },
  })
}

export function useAgents(sessionId: string | null) {
  return useQuery({
    queryKey: ["agents", sessionId],
    queryFn: () => api.agents.list(sessionId!),
    enabled: !!sessionId,
    refetchInterval: 5000,
  })
}

export function useAgentDetail(sessionId: string | null, agentName: string | null) {
  return useQuery({
    queryKey: ["agent", sessionId, agentName],
    queryFn: () => api.agents.get(sessionId!, agentName!),
    enabled: !!sessionId && !!agentName,
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.status === "running" ? 2000 : false
    },
  })
}

export function useAgentPrompt(sessionId: string, agentName: string) {
  return useMutation({
    mutationFn: (prompt: string) => api.agents.prompt(sessionId, agentName, { prompt }),
  })
}

export function useFileTree(sessionId: string | null) {
  return useQuery({
    queryKey: ["files", sessionId],
    queryFn: () => api.files.tree(sessionId!),
    enabled: !!sessionId,
  })
}

export function useFileContent(sessionId: string | null, filePath: string | null) {
  return useQuery({
    queryKey: ["file", sessionId, filePath],
    queryFn: () => api.files.read(sessionId!, filePath!),
    enabled: !!sessionId && !!filePath,
  })
}

export function useBillingSubscription(enabled: boolean) {
  return useQuery({
    queryKey: ["billing", "subscription"],
    queryFn: api.billing.subscription,
    enabled,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && [404, 502, 503].includes(error.status)) return false
      return failureCount < 1
    },
  })
}

export function useCheckoutSession() {
  return useMutation({
    mutationFn: (priceId?: string | null) => api.billing.checkoutSession({ price_id: priceId ?? null }),
  })
}

export function usePortalSession() {
  return useMutation({
    mutationFn: api.billing.portalSession,
  })
}

// ── Workflow queries ──────────────────────────────────────────────────────────

export function useWorkflows() {
  return useQuery({
    queryKey: ["workflows"],
    queryFn: api.workflows.list,
    staleTime: 10_000,
  })
}

export function useWorkflow(id: string | null) {
  return useQuery({
    queryKey: ["workflow", id],
    queryFn: () => api.workflows.get(id!),
    enabled: !!id,
    staleTime: 5_000,
  })
}

export function useCreateWorkflow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Parameters<typeof api.workflows.create>[0]) => api.workflows.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  })
}

export function useUpdateWorkflow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & Parameters<typeof api.workflows.update>[1]) =>
      api.workflows.update(id, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["workflows"] })
      qc.invalidateQueries({ queryKey: ["workflow", vars.id] })
    },
  })
}

export function useDeleteWorkflow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.workflows.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  })
}

export function useExecuteWorkflow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.workflows.execute(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["workflow-runs", id] })
    },
  })
}

export function useWorkflowRuns(workflowId: string | null) {
  return useQuery({
    queryKey: ["workflow-runs", workflowId],
    queryFn: () => api.workflows.runs(workflowId!),
    enabled: !!workflowId,
    refetchInterval: 5_000,
  })
}
