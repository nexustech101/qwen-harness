import { Trash2, FolderOpen, Bot, Clock, Activity } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { useSessions, useDeleteSession } from "@/api/queries"
import { useUIStore } from "@/stores/ui"
import { formatTimestamp } from "@/lib/utils"
import { NewSessionDialog } from "./NewSessionDialog"
import type { SessionResponse } from "@/api/types"

const STATUS_VARIANT: Record<string, "secondary" | "info" | "destructive"> = {
  idle: "secondary",
  running: "info",
  error: "destructive",
}

export function SessionList() {
  const { data: sessions, isLoading } = useSessions()
  const setActiveSession = useUIStore((s) => s.setActiveSession)

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-bold">Sessions</h1>
          <p className="text-sm text-muted-foreground">Manage your coding sessions</p>
        </div>
        <NewSessionDialog />
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-[180px] rounded-lg" />
            ))}
          </div>
        ) : !sessions?.length ? (
          <div className="flex h-[400px] flex-col items-center justify-center gap-4 text-muted-foreground">
            <FolderOpen className="h-12 w-12" />
            <p>No sessions yet. Create one to get started.</p>
            <NewSessionDialog />
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sessions.map((session) => (
              <SessionCard key={session.id} session={session} onClick={() => setActiveSession(session.id)} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function SessionCard({ session, onClick }: { session: SessionResponse; onClick: () => void }) {
  const deleteSession = useDeleteSession()
  const projectName = session.chat_only
    ? session.title || session.project_name || "New chat"
    : session.project_root.split(/[/\\]/).pop() ?? session.project_root

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirm("Delete this session?")) {
      deleteSession.mutate(session.id)
    }
  }

  return (
    <Card
      className="cursor-pointer transition-all hover:border-primary/50 hover:shadow-md group"
      onClick={onClick}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex-1 overflow-hidden">
            <CardTitle className="text-base truncate">{projectName}</CardTitle>
            <CardDescription className="font-mono text-xs truncate mt-1">
              {session.chat_only ? "Conversation" : session.project_root}
            </CardDescription>
          </div>
          <Badge variant={STATUS_VARIANT[session.status] ?? "secondary"}>
            {session.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <Bot className="h-3 w-3" />
            <span>{session.agents.length} agent{session.agents.length !== 1 ? "s" : ""}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Activity className="h-3 w-3" />
            <span>{session.stats.total_turns} turns</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="h-3 w-3" />
            <span>{formatTimestamp(session.created_at)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="font-mono">{session.model}</span>
          </div>
        </div>

        <div className="flex justify-end">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
            onClick={handleDelete}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
