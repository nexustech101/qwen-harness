import { useState } from "react"
import { ChevronDown, ChevronRight, Plus, Trash2, MessageSquare, GitBranch, Circle } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useSessions, useDeleteSession, useWorkflows, useDeleteWorkflow } from "@/api/queries"
import { useUIStore } from "@/stores/ui"
import { useWSStore } from "@/stores/websocket"
import { useUploadStore } from "@/stores/uploads"
import { cn } from "@/lib/utils"
import type { SessionResponse, WorkflowResponse } from "@/api/types"
import { CreateWorkflowDialog } from "@/components/workflow/CreateWorkflowDialog"
import { useAuthStore } from "@/stores/auth"
import { AuthDialog } from "@/components/account/AuthDialog"

function sessionTitle(session: SessionResponse) {
  return session.title || "Untitled"
}

// ── Chat sessions panel ───────────────────────────────────────────────────────
function ChatPanel() {
  const activeSessionId = useUIStore((s) => s.activeSessionId)
  const setActiveSession = useUIStore((s) => s.setActiveSession)
  const setActiveView = useUIStore((s) => s.setActiveView)
  const clearChat = useWSStore((s) => s.clearChat)
  const clearUploads = useUploadStore((s) => s.clearAll)
  const { data: sessions } = useSessions()
  const deleteSession = useDeleteSession()
  const [expanded, setExpanded] = useState(true)

  const handleNewChat = () => {
    setActiveSession(null)
    setActiveView("chat")
    clearChat()
    clearUploads()
  }

  const handleSelect = (id: string) => {
    setActiveSession(id)
    setActiveView("chat")
  }

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (confirm("Delete this session?")) {
      deleteSession.mutate(id)
      if (activeSessionId === id) setActiveSession(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-2 pt-3 pb-2 border-b border-border/20">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-1.5 px-2 py-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors rounded-md"
        >
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          Chats
        </button>
        {expanded && (
          <button
            onClick={handleNewChat}
            className="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>New Chat</span>
          </button>
        )}
      </div>

      {expanded && (
        <ScrollArea className="flex-1">
          <div className="space-y-0.5 p-2">
            {!sessions?.length ? (
              <div className="px-3 py-6 text-center">
                <MessageSquare className="mx-auto h-7 w-7 text-muted-foreground/30" />
                <p className="mt-2 text-xs text-muted-foreground/60">No chats yet</p>
              </div>
            ) : (
              sessions.map((session) => (
                <div
                  key={session.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleSelect(session.id)}
                  onKeyDown={(e) => e.key === "Enter" && handleSelect(session.id)}
                  className={cn(
                    "group flex w-full min-w-0 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                    activeSessionId === session.id
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                  )}
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-50" />
                  <span className="min-w-0 flex-1 truncate text-xs">{sessionTitle(session)}</span>
                  <button
                    className="opacity-0 group-hover:opacity-100 flex h-4 w-4 shrink-0 items-center justify-center rounded text-muted-foreground/60 hover:text-destructive transition-opacity"
                    onClick={(e) => handleDelete(e, session.id)}
                    title="Delete chat"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      )}
    </div>
  )
}

// ── Workflow list panel ───────────────────────────────────────────────────────
function WorkflowPanel() {
  const activeWorkflowId = useUIStore((s) => s.activeWorkflowId)
  const setActiveWorkflow = useUIStore((s) => s.setActiveWorkflow)
  const setActiveView = useUIStore((s) => s.setActiveView)
  const { data: workflows } = useWorkflows()
  const deleteWorkflow = useDeleteWorkflow()
  const [expanded, setExpanded] = useState(true)

  const handleSelect = (id: string) => {
    setActiveWorkflow(id)
    setActiveView("workflows")
  }

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (confirm("Delete this workflow?")) {
      deleteWorkflow.mutate(id)
      if (activeWorkflowId === id) setActiveWorkflow(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-2 pt-3 pb-2 border-b border-border/20">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-1.5 px-2 py-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors rounded-md"
        >
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          Workflows
        </button>
        {expanded && (
          <CreateWorkflowDialog />
        )}
      </div>

      {expanded && (
        <ScrollArea className="flex-1">
          <div className="space-y-0.5 p-2">
            {!workflows?.length ? (
              <div className="px-3 py-6 text-center">
                <GitBranch className="mx-auto h-7 w-7 text-muted-foreground/30" />
                <p className="mt-2 text-xs text-muted-foreground/60">No workflows yet</p>
              </div>
            ) : (
              workflows.map((wf) => (
                <WorkflowItem
                  key={wf.id}
                  wf={wf}
                  active={activeWorkflowId === wf.id}
                  onSelect={() => handleSelect(wf.id)}
                  onDelete={(e) => handleDelete(e, wf.id)}
                />
              ))
            )}
          </div>
        </ScrollArea>
      )}
    </div>
  )
}

function WorkflowItem({
  wf,
  active,
  onSelect,
  onDelete,
}: {
  wf: WorkflowResponse
  active: boolean
  onSelect: () => void
  onDelete: (e: React.MouseEvent) => void
}) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        "group flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
        active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
      )}
    >
      <Circle
        className={cn("h-2 w-2 shrink-0 fill-current", wf.enabled ? "text-green-400" : "text-muted-foreground/30")}
      />
      <span className="flex-1 truncate text-xs">{wf.name}</span>
      <button
        className="hidden group-hover:flex h-4 w-4 items-center justify-center rounded text-muted-foreground/60 hover:text-destructive"
        onClick={onDelete}
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </button>
  )
}

// ── MCP panel ────────────────────────────────────────────────────────────────
function MCPPanel() {
  return (
    <div className="p-4">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">MCP</div>
      <p className="text-xs text-muted-foreground/70">Tools and prompts exposed via FastMCP.</p>
    </div>
  )
}

// ── Settings panel ────────────────────────────────────────────────────────────
function SettingsPanel() {
  const user = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const logout = useAuthStore((s) => s.logout)
  const disconnect = useWSStore((s) => s.disconnect)
  const setActiveSession = useUIStore((s) => s.setActiveSession)
  const [authOpen, setAuthOpen] = useState(false)
  const [authMode, setAuthMode] = useState<"login" | "register">("login")

  return (
    <div className="p-3 space-y-2">
      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground px-1 mb-3">Account</div>
      {isAuthenticated && user ? (
        <>
          <div className="rounded-md bg-muted/30 px-3 py-2">
            <div className="text-sm font-medium truncate">{user.full_name || user.email}</div>
            <div className="text-xs text-muted-foreground truncate">{user.email}</div>
          </div>
          <button
            onClick={async () => {
              await logout()
              disconnect()
              setActiveSession(null)
            }}
            className="w-full rounded-md px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors"
          >
            Sign out
          </button>
        </>
      ) : (
        <>
          <button
            onClick={() => { setAuthMode("login"); setAuthOpen(true) }}
            className="w-full rounded-md px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors"
          >
            Sign in
          </button>
          <button
            onClick={() => { setAuthMode("register"); setAuthOpen(true) }}
            className="w-full rounded-md px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors"
          >
            Create account
          </button>
          <AuthDialog key={authMode} open={authOpen} mode={authMode} onOpenChange={setAuthOpen} />
        </>
      )}
    </div>
  )
}

// ── Root sidebar ──────────────────────────────────────────────────────────────
export function Sidebar() {
  const activeView = useUIStore((s) => s.activeView)

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground overflow-hidden">
      {activeView === "chat" && <ChatPanel />}
      {activeView === "workflows" && <WorkflowPanel />}
      {activeView === "mcp" && <MCPPanel />}
      {activeView === "settings" && <SettingsPanel />}
    </div>
  )
}
