import { Bot, Circle } from "lucide-react"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { useAgents } from "@/api/queries"
import { useUIStore } from "@/stores/ui"

const STATUS_COLORS: Record<string, string> = {
  idle: "text-gray-400",
  running: "text-blue-400 animate-status-pulse",
  done: "text-green-400",
  error: "text-red-400",
  max_turns: "text-yellow-400",
  deadlock: "text-orange-400",
}

const STATUS_BADGE_VARIANT: Record<string, "secondary" | "info" | "success" | "destructive" | "warning"> = {
  idle: "secondary",
  running: "info",
  done: "success",
  error: "destructive",
  max_turns: "warning",
  deadlock: "warning",
}

export function AgentList() {
  const sessionId = useUIStore((s) => s.activeSessionId)
  const selectedAgent = useUIStore((s) => s.selectedAgent)
  const setSelectedAgent = useUIStore((s) => s.setSelectedAgent)
  const { data: agents, isLoading } = useAgents(sessionId)

  if (isLoading) {
    return <div className="p-3 text-xs text-muted-foreground">Loading agents...</div>
  }

  if (!agents?.length) {
    return <div className="p-3 text-xs text-muted-foreground">No agents yet</div>
  }

  // Sort: main first, then alphabetically
  const sorted = [...agents].sort((a, b) => {
    if (a.name === "main") return -1
    if (b.name === "main") return 1
    return a.name.localeCompare(b.name)
  })

  return (
    <div className="py-1 space-y-0.5">
      {sorted.map((agent) => (
        <button
          key={agent.name}
          className={cn(
            "flex w-full items-center gap-2 px-3 py-2 text-xs hover:bg-accent/50 transition-colors",
            selectedAgent === agent.name && "bg-accent text-accent-foreground",
          )}
          onClick={() => setSelectedAgent(agent.name === selectedAgent ? null : agent.name)}
        >
          <Bot className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <div className="flex flex-1 flex-col items-start gap-0.5 overflow-hidden">
            <div className="flex w-full items-center justify-between gap-1">
              <span className="truncate font-medium">{agent.name}</span>
              <Badge variant={STATUS_BADGE_VARIANT[agent.status] ?? "secondary"} className="text-[10px] px-1.5 py-0">
                {agent.status}
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-muted-foreground">
              <Circle className={cn("h-1.5 w-1.5 fill-current", STATUS_COLORS[agent.status])} />
              <span className="font-mono">{agent.model}</span>
              <span>{agent.turns_used}/{agent.max_turns}</span>
            </div>
          </div>
        </button>
      ))}
    </div>
  )
}
