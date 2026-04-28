import { useState } from "react"
import {
  PanelLeftClose,
  ChevronDown,
  ChevronRight,
  Plus,
  Trash2,
  MessageSquare,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { RobotLogo } from "@/components/branding/RobotLogo"
import { NewSessionDialog } from "@/components/session/NewSessionDialog"
import { FileTree } from "@/components/sidebar/FileTree"
import { useSessions, useDeleteSession } from "@/api/queries"
import { useUIStore } from "@/stores/ui"
import { useWSStore } from "@/stores/websocket"
import { useUploadStore } from "@/stores/uploads"
import { cn } from "@/lib/utils"
import type { SessionResponse } from "@/api/types"

function sessionTitle(session: SessionResponse) {
  if (session.chat_only) return session.title || session.project_name || "New chat"
  return session.project_root.split(/[/\\]/).pop() ?? session.project_root
}

export function Sidebar() {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)
  const activeSessionId = useUIStore((s) => s.activeSessionId)
  const setActiveSession = useUIStore((s) => s.setActiveSession)
  const clearChat = useWSStore((s) => s.clearChat)
  const clearUploads = useUploadStore((s) => s.clearAll)
  const { data: sessions } = useSessions()
  const deleteSession = useDeleteSession()

  const [projectsOpen, setProjectsOpen] = useState(true)
  const [historyExpanded, setHistoryExpanded] = useState(false)
  const [filesOpen, setFilesOpen] = useState(true)

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (confirm("Delete this session?")) {
      deleteSession.mutate(id)
      if (activeSessionId === id) setActiveSession(null)
    }
  }

  const visibleSessions = historyExpanded ? sessions : sessions?.slice(0, 15)

  const handleNewChat = () => {
    setActiveSession(null)
    clearChat()
    clearUploads()
  }

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      {/* Logo + collapse */}
      <div className="flex h-12 items-center justify-between px-3">
        <div className="flex items-center gap-2">
          <RobotLogo size={24} className="text-blue-400" />
          <span className="text-sm font-semibold tracking-tight">Qwen Coder</span>
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={toggleSidebar}>
          <PanelLeftClose className="h-4 w-4" />
        </Button>
      </div>

      {/* Chats header */}
      <div className="px-2 pt-2 pb-1">
        <button
          onClick={() => setProjectsOpen(!projectsOpen)}
          className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
        >
          {projectsOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          Chats
        </button>
        {projectsOpen && (
          <div className="mt-1 space-y-1 px-1">
            <button
              onClick={handleNewChat}
              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>New Chat</span>
            </button>
            <NewSessionDialog variant="sidebar" label="Open Project" />
          </div>
        )}
      </div>

      {/* Session history list */}
      <ScrollArea className="flex-1 px-2">
        {projectsOpen && (
          <div className="space-y-0.5 pb-2">
            {!sessions?.length ? (
              <div className="px-3 py-6 text-center">
                <MessageSquare className="mx-auto h-8 w-8 text-muted-foreground/40" />
                <p className="mt-2 text-xs text-muted-foreground">No chats yet</p>
              </div>
            ) : (
              <>
                {visibleSessions?.map((session) => (
                  <button
                    key={session.id}
                    onClick={() => setActiveSession(session.id)}
                    className={cn(
                      "group flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                      activeSessionId === session.id
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                    )}
                  >
                    <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-60" />
                    <span className="flex-1 truncate">{sessionTitle(session)}</span>
                    <Badge
                      variant={session.chat_only ? "info" : session.persistence_mode === "persistent" ? "success" : "secondary"}
                      className="px-1.5 py-0 text-[10px] opacity-80"
                    >
                      {session.chat_only ? "Chat" : session.persistence_mode === "persistent" ? "Saved" : "Project"}
                    </Badge>
                    <Trash2
                      className="h-3 w-3 shrink-0 opacity-0 group-hover:opacity-60 hover:!opacity-100 hover:text-destructive transition-opacity"
                      onClick={(e) => handleDelete(e, session.id)}
                    />
                  </button>
                ))}
                {sessions.length > 15 && (
                  <button
                    onClick={() => setHistoryExpanded(!historyExpanded)}
                    className="w-full px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {historyExpanded ? "Show less" : "See all"}
                  </button>
                )}
              </>
            )}
          </div>
        )}

        {/* File tree — shown when a project is selected */}
        {activeSessionId && sessions?.find((session) => session.id === activeSessionId)?.chat_only !== true && (
          <div className="border-t border-border/50 pt-1">
            <button
              onClick={() => setFilesOpen(!filesOpen)}
              className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
            >
              {filesOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              Files
            </button>
            {filesOpen && <FileTree />}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
