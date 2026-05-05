import { ChevronDown, ChevronRight } from "lucide-react"
import { useState } from "react"
import { formatStreamingContent } from "@/lib/chat-format"
import { MarkdownContent } from "./MarkdownContent"
import type { StreamingState } from "@/stores/websocket"

export function StreamingMessage({ streaming }: { streaming: StreamingState }) {
  const { content, thinking } = streaming
  const [showThinking, setShowThinking] = useState(false)
  const displayContent = formatStreamingContent(content)
  const hasThinking = thinking.trim().length > 0

  return (
    <div className="flex justify-start px-1 py-0.5">
      <div className="max-w-[78%]">
        {hasThinking && (
          <div className="mb-1.5">
            <button
              onClick={() => setShowThinking(!showThinking)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground/60 transition-colors hover:text-muted-foreground"
            >
              {showThinking ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              <span className="italic animate-pulse">Thinkingâ€¦</span>
            </button>
            {showThinking && (
              <div className="mt-1.5 max-h-[200px] overflow-y-auto rounded-xl border border-border/30 bg-muted/20 p-3 font-mono text-xs whitespace-pre-wrap text-muted-foreground/70">
                {thinking}
              </div>
            )}
          </div>
        )}

        <div className="rounded-2xl rounded-tl-sm bg-card border border-border/30 px-4 py-3 shadow-sm">
          {displayContent ? (
            <div className="relative">
              <MarkdownContent content={displayContent} />
              <span className="streaming-cursor ml-0.5 inline-block h-3.5 w-0.5 bg-foreground/40 align-middle animate-[streaming-cursor_1s_ease-in-out_infinite]" />
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="inline-flex gap-[3px]">
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-[typing-dot_1.4s_ease-in-out_infinite]" />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-[typing-dot_1.4s_ease-in-out_0.2s_infinite]" />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-[typing-dot_1.4s_ease-in-out_0.4s_infinite]" />
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
