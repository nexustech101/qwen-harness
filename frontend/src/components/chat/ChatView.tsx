import { useRef, useEffect, useState, useMemo } from "react"
import { ChatMessage, ActivityGroup } from "./ChatMessage"
import { StreamingMessage } from "./StreamingMessage"
import { PromptInput } from "./PromptInput"
import { RobotLogo } from "@/components/branding/RobotLogo"
import { NewSessionDialog } from "@/components/session/NewSessionDialog"
import { useMessages, useSession } from "@/api/queries"
import { useWSStore } from "@/stores/websocket"
import { useUIStore } from "@/stores/ui"
import { useAuthStore } from "@/stores/auth"
import { useUploadStore } from "@/stores/uploads"
import type { ChatItem } from "@/api/types"

// ── Group consecutive internal items into collapsible activity sections ───────
const ACTIVITY_TYPES = new Set(["tool_call", "agent_start", "agent_done"])

type RenderGroup =
  | { kind: "content"; item: ChatItem }
  | { kind: "activity"; items: ChatItem[] }

function groupChatItems(items: ChatItem[]): RenderGroup[] {
  const groups: RenderGroup[] = []
  let buf: ChatItem[] = []
  const flush = () => {
    if (buf.length > 0) {
      groups.push({ kind: "activity", items: [...buf] })
      buf = []
    }
  }
  for (const item of items) {
    if (ACTIVITY_TYPES.has(item.type)) {
      buf.push(item)
    } else {
      flush()
      groups.push({ kind: "content", item })
    }
  }
  flush()
  return groups
}

export function ChatView() {
  const chatItems = useWSStore((s) => s.chatItems)
  const streaming = useWSStore((s) => s.streaming)
  const clearChat = useWSStore((s) => s.clearChat)
  const hydrateMessages = useWSStore((s) => s.hydrateMessages)
  const activeSessionId = useUIStore((s) => s.activeSessionId)
  const { data: session } = useSession(activeSessionId)
  const { data: messages } = useMessages(activeSessionId)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const clearUploads = useUploadStore((s) => s.clearAll)
  const bottomRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const hydratedSessionRef = useRef<string | null>(null)

  // Auto-scroll on new messages or streaming updates
  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }
  }, [chatItems, streaming, autoScroll])

  useEffect(() => {
    clearChat()
    clearUploads()
    hydratedSessionRef.current = null
  }, [activeSessionId, clearChat, clearUploads])

  useEffect(() => {
    if (!activeSessionId || !messages || session?.status === "running") return
    if (hydratedSessionRef.current === activeSessionId) return
    hydrateMessages(activeSessionId, messages)
    hydratedSessionRef.current = activeSessionId
  }, [activeSessionId, hydrateMessages, messages, session?.status])

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget
    const isNearBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 100
    setAutoScroll(isNearBottom)
  }

  const isEmpty = chatItems.length === 0 && !streaming
  const groups = useMemo(() => groupChatItems(chatItems), [chatItems])
  const showGuestNotice = isAuthenticated && session?.persistence_mode === "guest"

  return (
    <div className="flex h-full flex-col">
      {isEmpty ? (
        /* ── Welcome screen (Grok-style centered) ────────────────────── */
        <div className="flex flex-1 flex-col items-center justify-center px-4">
          <RobotLogo size={72} className="text-blue-400 mb-6" />
          <h1 className="text-2xl font-semibold mb-1">Qwen Coder</h1>
          <p className="text-muted-foreground text-sm mb-10">How can I help you today?</p>
          {showGuestNotice && (
            <div className="mb-4 flex items-center gap-3 rounded-lg border border-border/50 bg-card/60 px-3 py-2 text-xs text-muted-foreground">
              <span>This chat is temporary.</span>
              <NewSessionDialog label="Start new saved chat" />
            </div>
          )}
          <div className="w-full max-w-2xl">
            <PromptInput centered />
          </div>
        </div>
      ) : (
        /* ── Chat messages ───────────────────────────────────────────── */
        <>
          <div className="flex-1 overflow-y-auto" onScroll={handleScroll}>
            <div className="mx-auto max-w-3xl space-y-3 px-4 py-4">
              {showGuestNotice && (
                <div className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-card/60 px-3 py-2 text-xs text-muted-foreground">
                  <span>This chat is temporary.</span>
                  <NewSessionDialog label="Start new saved chat" />
                </div>
              )}
              {groups.map((g, i) =>
                g.kind === "content" ? (
                  <ChatMessage key={i} item={g.item} />
                ) : (
                  <ActivityGroup key={i} items={g.items} />
                ),
              )}
              {streaming && <StreamingMessage streaming={streaming} />}
              <div ref={bottomRef} />
            </div>
          </div>
          <PromptInput />
        </>
      )}
    </div>
  )
}
