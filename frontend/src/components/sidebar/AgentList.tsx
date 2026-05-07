import { Bot } from "lucide-react"

export function AgentList() {
  return (
    <div className="p-3 text-xs text-muted-foreground flex items-center gap-2">
      <Bot className="h-3.5 w-3.5 opacity-40" />
      <span>No agents available</span>
    </div>
  )
}
