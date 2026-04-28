import { ChevronDown, ChevronRight } from "lucide-react"
import { useState } from "react"
import { RobotLogo } from "@/components/branding/RobotLogo"
import { formatStreamingContent } from "@/lib/chat-format"
import { MarkdownContent } from "./MarkdownContent"
import type { StreamingState } from "@/stores/websocket"

export function StreamingMessage({ streaming }: { streaming: StreamingState }) {
  const { content, thinking, agent } = streaming
  const [showThinking, setShowThinking] = useState(false)
  const displayContent = formatStreamingContent(content)
  const hasThinking = thinking.trim().length > 0

  return (
    <div className="flex gap-3 py-2">
      <div className="mt-0.5 shrink-0">
        <RobotLogo size={24} className="text-blue-400 animate-pulse" />
      </div>
      <div className="min-w-0 flex-1">
        {agent !== "main" && (
          <span className="mb-1 block text-[10px] font-medium text-muted-foreground/60">{agent}</span>
        )}

        {hasThinking && (
          <div className="mb-2">
            <button
              onClick={() => setShowThinking(!showThinking)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground/70 transition-colors hover:text-muted-foreground"
            >
              {showThinking ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              <span className="italic">Reasoning</span>
            </button>
            {showThinking && (
              <div className="mt-1.5 max-h-[260px] overflow-y-auto rounded-lg border border-border/30 bg-[hsl(0,0%,7%)] p-3 font-mono text-xs whitespace-pre-wrap text-muted-foreground/80">
                {thinking}
              </div>
            )}
          </div>
        )}

        {displayContent ? (
          <div className="relative">
            <MarkdownContent content={displayContent} />
            <span className="streaming-cursor ml-1 inline-block h-3 w-0.5 bg-muted-foreground/40 align-middle" />
          </div>
        ) : (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
            <span className="inline-flex gap-[2px]">
              <span className="h-1 w-1 rounded-full bg-blue-400/60 animate-[typing-dot_1.4s_ease-in-out_infinite]" />
              <span className="h-1 w-1 rounded-full bg-blue-400/60 animate-[typing-dot_1.4s_ease-in-out_0.2s_infinite]" />
              <span className="h-1 w-1 rounded-full bg-blue-400/60 animate-[typing-dot_1.4s_ease-in-out_0.4s_infinite]" />
            </span>
            <span>Generating...</span>
          </div>
        )}
      </div>
    </div>
  )
}
