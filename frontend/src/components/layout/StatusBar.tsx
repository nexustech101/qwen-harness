import { Circle, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { useWSStore } from "@/stores/websocket"
import { useSession } from "@/api/queries"
import { useUIStore } from "@/stores/ui"

function formatNumber(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : n.toLocaleString()
}

export function StatusBar() {
  const connected = useWSStore((s) => s.connected)
  const streaming = useWSStore((s) => s.streaming)
  const tokenStats = useWSStore((s) => s.tokenStats)
  const activeSessionId = useUIStore((s) => s.activeSessionId)
  const { data: session } = useSession(activeSessionId)

  const isRunning = session?.status === "running"

  return (
    <footer className="flex h-6 items-center justify-between border-t bg-background px-3 text-xs text-muted-foreground">
      <div className="flex items-center gap-4">
        {/* Connection indicator */}
        <div className="flex items-center gap-1.5">
          <Circle
            className={cn(
              "h-2 w-2 fill-current",
              connected ? "text-green-400" : "text-red-400",
            )}
          />
          <span>{connected ? "Connected" : "Disconnected"}</span>
        </div>

        {/* Session status */}
        {session && (
          <div className="flex items-center gap-1.5">
            {isRunning && <Loader2 className="h-3 w-3 animate-spin" />}
            <span className={cn(isRunning && "text-blue-400")}>
              {session.status}
            </span>
          </div>
        )}

        {/* Streaming indicator */}
        {streaming && (
          <span className="text-blue-400 font-mono">streaming…</span>
        )}

        {/* Model */}
        {session && (
          <span className="font-mono">{session.model}</span>
        )}

        {session && (
          <span className="rounded-sm px-1.5 py-0.5 text-[10px] bg-muted text-muted-foreground">
            {session.message_count} messages
          </span>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Token stats from last stream */}
        {tokenStats && (
          <span className="font-mono">
            {formatNumber(tokenStats.evalCount)} gen · {formatNumber(tokenStats.promptEvalCount)} prompt
            {tokenStats.tokPerSec > 0 && <> · {tokenStats.tokPerSec.toFixed(1)} tok/s</>}
          </span>
        )}
      </div>
    </footer>
  )
}
