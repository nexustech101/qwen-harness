import { Bot } from "lucide-react"

export function AgentDetail() {
  return (
    <div className="flex h-full items-center justify-center border-l text-sm text-muted-foreground">
      <div className="flex flex-col items-center gap-2">
        <Bot className="h-8 w-8 opacity-20" />
        <p>Agent details unavailable</p>
      </div>
    </div>
  )
}
