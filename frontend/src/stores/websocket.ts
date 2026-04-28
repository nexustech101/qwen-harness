import { create } from "zustand"
import type { ChatItem, MessageResponse, WSEvent } from "@/api/types"
import { getAuthToken } from "@/api/client"
import { useUIStore } from "@/stores/ui"
import { formatAssistantContent } from "@/lib/chat-format"
import { toast } from "sonner"

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempts = 0
const MAX_RECONNECT = 5

// ── Streaming buffer (mutated in-place, flushed via RAF) ──────────────────────
let contentBuf = ""
let thinkingBuf = ""
let bufDirty = false
let rafId: number | null = null

export interface StreamingState {
  content: string
  thinking: string
  agent: string
  timestamp: number
}

export interface TokenStats {
  evalCount: number
  promptEvalCount: number
  tokPerSec: number
}

interface WSStore {
  connected: boolean
  sessionId: string | null
  chatItems: ChatItem[]
  pendingToolCalls: Map<string, number>
  streaming: StreamingState | null
  tokenStats: TokenStats | null
  connect: (sessionId: string) => void
  disconnect: () => void
  cancel: () => void
  addUserMessage: (content: string) => void
  hydrateMessages: (sessionId: string, messages: MessageResponse[]) => void
  clearChat: () => void
}

function makeToolId(agent: string, name: string, ts: number): string {
  return `${agent}-${name}-${ts}`
}

function startFlushLoop(set: (fn: (s: WSStore) => Partial<WSStore>) => void, get: () => WSStore) {
  if (rafId !== null) return
  function flush() {
    if (bufDirty) {
      const cur = get().streaming
      if (cur) {
        set(() => ({
          streaming: { ...cur, content: contentBuf, thinking: thinkingBuf },
        }))
      }
      bufDirty = false
    }
    rafId = requestAnimationFrame(flush)
  }
  rafId = requestAnimationFrame(flush)
}

function stopFlushLoop() {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

export const useWSStore = create<WSStore>((set, get) => ({
  connected: false,
  sessionId: null,
  chatItems: [],
  pendingToolCalls: new Map(),
  streaming: null,
  tokenStats: null,

  connect: (sessionId: string) => {
    const state = get()
    if (state.sessionId === sessionId && ws?.readyState === WebSocket.OPEN) return

    get().disconnect()

    const baseUrl = import.meta.env.VITE_API_URL ?? window.location.origin
    const wsUrl = baseUrl.replace(/^http/, "ws")
    const token = getAuthToken()
    const qs = token ? `?token=${encodeURIComponent(token)}` : ""
    const socket = new WebSocket(`${wsUrl}/api/sessions/${sessionId}/ws${qs}`)
    ws = socket

    set({ sessionId })
    reconnectAttempts = 0

    let openedOnce = false

    socket.onopen = () => {
      openedOnce = true
      set({ connected: true })
      reconnectAttempts = 0
    }

    socket.onclose = (event) => {
      set({ connected: false })
      if (event.code === 4004) {
        useUIStore.getState().setActiveSession(null)
        toast.error("Session unavailable or no longer accessible")
        window.dispatchEvent(new CustomEvent("session-access-lost"))
        return
      }
      // If we never successfully connected, the session likely doesn't exist — stop retrying
      if (!openedOnce) {
        useUIStore.getState().setActiveSession(null)
        return
      }
      if (get().sessionId === sessionId && reconnectAttempts < MAX_RECONNECT) {
        const delay = Math.min(1000 * 2 ** reconnectAttempts, 30000)
        reconnectAttempts++
        reconnectTimer = setTimeout(() => get().connect(sessionId), delay)
      }
    }

    socket.onerror = () => {
      socket.close()
    }

    socket.onmessage = (e) => {
      try {
        const event: WSEvent = JSON.parse(e.data)
        processEvent(event, set, get)
      } catch {
        // ignore malformed messages
      }
    }
  },

  disconnect: () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.onclose = null
      ws.close()
      ws = null
    }
    set({ connected: false, sessionId: null })
  },

  cancel: () => {
    const { sessionId } = get()
    if (ws?.readyState === WebSocket.OPEN && sessionId) {
      ws.send(JSON.stringify({ type: "cancel", session_id: sessionId }))
    }
  },

  addUserMessage: (content: string) => {
    set((s) => ({
      chatItems: [
        ...s.chatItems,
        { type: "user" as const, content, timestamp: Date.now() / 1000 },
      ],
    }))
  },

  hydrateMessages: (sessionId, messages) => {
    const state = get()
    if (state.sessionId === sessionId && state.streaming) return
    const items = messages
      .map((message): ChatItem | null => {
        const timestamp = message.timestamp ?? Date.now() / 1000
        if (message.role === "user") {
          return { type: "user", content: message.content, timestamp }
        }
        if (message.role === "assistant" || message.role === "system") {
          return {
            type: "assistant",
            content: formatAssistantContent(message.content) || message.content,
            timestamp,
            metadata: message.metadata ?? undefined,
          }
        }
        if (message.role === "error") {
          return { type: "error", content: message.content, agent: "main", timestamp }
        }
        return null
      })
      .filter((item): item is ChatItem => item !== null)
    stopFlushLoop()
    contentBuf = ""
    thinkingBuf = ""
    bufDirty = false
    set({ chatItems: items, pendingToolCalls: new Map(), streaming: null, tokenStats: null })
  },

  clearChat: () => {
    stopFlushLoop()
    set({ chatItems: [], pendingToolCalls: new Map(), streaming: null, tokenStats: null })
  },
}))

function processEvent(event: WSEvent, set: (fn: (s: WSStore) => Partial<WSStore>) => void, get: () => WSStore) {
  const { type, agent, data, timestamp } = event

  switch (type) {
    case "connected":
    case "ping":
    case "model_call":
      break

    // ── Streaming deltas (buffer, no state update per token) ──────────
    case "content_delta": {
      const text = (data.text as string) ?? ""
      if (!text) break
      const cur = get().streaming
      if (!cur) {
        // First delta — init buffer and streaming state
        contentBuf = text
        thinkingBuf = ""
        bufDirty = true
        set(() => ({
          streaming: { content: text, thinking: "", agent, timestamp },
        }))
        startFlushLoop(set, get)
      } else {
        contentBuf += text
        bufDirty = true
      }
      break
    }

    case "thinking_delta": {
      const text = (data.text as string) ?? ""
      if (!text) break
      const cur = get().streaming
      if (!cur) {
        contentBuf = ""
        thinkingBuf = text
        bufDirty = true
        set(() => ({
          streaming: { content: "", thinking: text, agent, timestamp },
        }))
        startFlushLoop(set, get)
      } else {
        thinkingBuf += text
        bufDirty = true
      }
      break
    }

    case "stream_end": {
      stopFlushLoop()
      // Capture token stats
      const evalCount = (data.eval_count as number) ?? 0
      const promptEvalCount = (data.prompt_eval_count as number) ?? 0
      const elapsed = (data.eval_duration as number) ?? (data.elapsed as number) ?? 0
      const tokPerSec = elapsed > 0 ? evalCount / elapsed : 0
      set(() => ({
        streaming: null,
        tokenStats: evalCount > 0 ? { evalCount, promptEvalCount, tokPerSec } : get().tokenStats,
      }))
      contentBuf = ""
      thinkingBuf = ""
      bufDirty = false
      break
    }

    // ── Structured events (standard array push) ──────────────────────
    default:
        processStructuredEvent(event, set)
      break
  }

  // Trigger file tree refresh on file operations
  if (type === "tool_result") {
    const toolName = (data.name as string) ?? ""
    if (["write_file", "edit_file", "delete_file", "move_file", "copy_file", "create_directory"].includes(toolName)) {
      window.dispatchEvent(new CustomEvent("file-tree-changed"))
    }
  }
}

function processStructuredEvent(event: WSEvent, set: (fn: (s: WSStore) => Partial<WSStore>) => void) {
  const { type, agent, data, timestamp } = event

  set((s) => {
    const items = [...s.chatItems]
    const pending = new Map(s.pendingToolCalls)

    switch (type) {
      case "model_reply":
        // model_reply just signals parsing will follow — clear streaming if still present
        if (s.streaming) {
          stopFlushLoop()
          return { streaming: null, chatItems: items, pendingToolCalls: pending }
        }
        break

      case "agent_start":
        items.push({
          type: "agent_start",
          agent,
          model: (data.model as string) ?? "",
          goal: (data.prompt as string) ?? "",
          timestamp,
        })
        break

      case "turn_start":
        break  // suppressed — internal agent loop detail

      case "reasoning":
        items.push({
          type: "reasoning",
          content: (data.text as string) ?? "",
          agent,
          timestamp,
        })
        break

      case "tool_dispatch": {
        const toolName = (data.name as string) ?? ""
        const args = (data.args as Record<string, unknown>) ?? {}
        const id = makeToolId(agent, toolName, timestamp)
        items.push({
          type: "tool_call",
          name: toolName,
          args,
          agent,
          id,
          timestamp,
        })
        pending.set(`${agent}-${toolName}`, items.length - 1)
        break
      }

      case "tool_result": {
        const toolName = (data.name as string) ?? ""
        const key = `${agent}-${toolName}`
        const idx = pending.get(key)
        if (idx !== undefined && items[idx]?.type === "tool_call") {
          const item = items[idx] as ChatItem & { type: "tool_call" }
          items[idx] = {
            ...item,
            result: (data.data as string) ?? (data.error as string) ?? "",
            success: (data.success as boolean) ?? false,
            error: (data.error as string) ?? undefined,
          }
          pending.delete(key)
        }
        break
      }

      case "response_text":
        items.push({
          type: "assistant",
          content: formatAssistantContent((data.text as string) ?? ""),
          timestamp,
        })
        break

      case "error":
        items.push({
          type: "error",
          content: (data.error as string) ?? "Unknown error",
          agent,
          timestamp,
        })
        break

      case "recovery":
        break  // suppressed — internal agent loop detail

      case "agent_done":
        items.push({
          type: "agent_done",
          agent,
          reason: (data.reason as string) ?? "",
          turns: (data.turns as number) ?? 0,
          elapsed: (data.elapsed as number) ?? 0,
          timestamp,
        })
        break

      case "max_turns":
        items.push({
          type: "error",
          content: `Turn limit reached (${data.limit})`,
          agent,
          timestamp,
        })
        break
    }

    return { chatItems: items, pendingToolCalls: pending }
  })
}
