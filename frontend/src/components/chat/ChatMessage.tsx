import { useCallback, useState } from "react"
import { AlertCircle, Check, CheckCircle2, ChevronDown, ChevronRight, Copy, Loader2 } from "lucide-react"
import { cn, formatTime } from "@/lib/utils"
import { formatAssistantContent, formatToolResult } from "@/lib/chat-format"
import { MarkdownContent } from "./MarkdownContent"
import type { ChatItem } from "@/api/types"

export function ChatMessage({ item }: { item: ChatItem }) {
  switch (item.type) {
    case "user":
      return <UserBubble content={item.content} />
    case "assistant":
      return <AssistantBubble content={item.content} metadata={item.metadata} />
    case "reasoning":
      return <ReasoningBlock content={item.content} agent={item.agent} />
    case "tool_call":
      return (
        <ToolCallCard
          name={item.name}
          args={item.args}
          result={item.result}
          success={item.success}
          error={item.error}
        />
      )
    case "error":
      return <ErrorCard content={item.content} />
    case "turn_divider":
      return null
    case "agent_start":
      return <AgentStartCard agent={item.agent} model={item.model} />
    case "agent_done":
      return <AgentDoneCard agent={item.agent} reason={item.reason} turns={item.turns} elapsed={item.elapsed} />
    default:
      return null
  }
}

// â”€â”€ User bubble (right-aligned) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end px-1 py-0.5">
      <div className="max-w-[75%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm">
        <p className="whitespace-pre-wrap leading-relaxed">{content}</p>
      </div>
    </div>
  )
}

// â”€â”€ Assistant bubble (left-aligned) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function AssistantBubble({
  content,
  metadata,
}: {
  content: string
  metadata?: import("@/api/types").ResultMetadata
}) {
  const [copied, setCopied] = useState(false)
  const displayContent = formatAssistantContent(content) || content

  const handleCopy = useCallback(() => {
    void navigator.clipboard.writeText(displayContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [displayContent])

  return (
    <div className="flex justify-start px-1 py-0.5">
      <div className="max-w-[78%]">
        <div className="rounded-2xl rounded-tl-sm bg-card border border-border/30 px-4 py-3 shadow-sm">
          <MarkdownContent content={displayContent} />
        </div>
        <div className="mt-1 flex items-center gap-3 px-1">
          {metadata && (
            <span className="text-[11px] text-muted-foreground/60">
              {metadata.turns} turns Â· {metadata.tool_calls_made} tools Â· {formatTime(metadata.elapsed_seconds)}
              {metadata.files_modified.length > 0 && ` Â· ${metadata.files_modified.length} files`}
            </span>
          )}
          <button
            onClick={handleCopy}
            className="ml-auto flex items-center gap-1 rounded-md px-2 py-0.5 text-xs text-muted-foreground/60 transition-colors hover:bg-accent hover:text-foreground"
            title="Copy"
          >
            {copied ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
          </button>
        </div>
      </div>
    </div>
  )
}

// â”€â”€ Reasoning block â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ReasoningBlock({ content, agent }: { content: string; agent: string }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="flex justify-start px-1 py-0.5">
      <div className="max-w-[78%]">
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground/60 transition-colors hover:text-muted-foreground"
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          <span className="italic">Thinking{agent !== "main" ? ` (${agent})` : ""}</span>
        </button>
        {open && (
          <div className="mt-1.5 max-h-[260px] overflow-y-auto rounded-xl border border-border/30 bg-muted/20 p-3 font-mono text-xs whitespace-pre-wrap text-muted-foreground/70">
            {content}
          </div>
        )}
      </div>
    </div>
  )
}

// â”€â”€ Tool call card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ToolCallCard({
  name,
  args,
  result,
  success,
  error,
}: {
  name: string
  args: Record<string, unknown>
  result?: string
  success?: boolean
  error?: string
}) {
  const [expanded, setExpanded] = useState(false)
  const isPending = success === undefined
  const isFileOp = ["write_file", "edit_file", "read_file", "delete_file"].includes(name)
  const filePath = isFileOp ? (args.path as string) ?? (args.file_path as string) : null
  const displayResult = formatToolResult(result, error)

  return (
    <div className="flex justify-start px-1 py-0.5">
      <div className="max-w-[78%]">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-left text-xs bg-muted/30 border border-border/20 hover:bg-muted/50 transition-colors"
        >
          {expanded
            ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
            : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
          <span className="font-mono text-blue-400/80">{name}</span>
          {filePath && <span className="truncate max-w-[160px] text-muted-foreground/50">{filePath}</span>}
          <span className="ml-2">
            {isPending ? (
              <Loader2 className="h-3 w-3 animate-spin text-blue-400/60" />
            ) : success ? (
              <CheckCircle2 className="h-3 w-3 text-green-400/70" />
            ) : (
              <AlertCircle className="h-3 w-3 text-red-400/70" />
            )}
          </span>
        </button>

        {expanded && (
          <div className="mt-1 space-y-2 rounded-xl border border-border/20 bg-muted/10 p-3">
            <div>
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/50">Args</span>
              <pre className="mt-1 max-h-[160px] overflow-auto rounded-md bg-background p-2 font-mono text-xs text-muted-foreground">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
            {displayResult && (
              <div>
                <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/50">Result</span>
                <pre
                  className={cn(
                    "mt-1 max-h-[160px] overflow-auto rounded-md p-2 font-mono text-xs",
                    error ? "bg-red-500/5 text-red-400/80" : "bg-background text-muted-foreground",
                  )}
                >
                  {displayResult}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// â”€â”€ Error card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ErrorCard({ content }: { content: string }) {
  return (
    <div className="flex justify-start px-1 py-0.5">
      <div className="flex items-start gap-2 rounded-2xl rounded-tl-sm border border-red-500/20 bg-red-500/5 px-4 py-2.5 text-sm text-red-400/90">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{content}</span>
      </div>
    </div>
  )
}

// â”€â”€ Activity group (tool calls grouped) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function ActivityGroup({ items }: { items: ChatItem[] }) {
  const [open, setOpen] = useState(false)
  const toolCalls = items.filter((i) => i.type === "tool_call")
  const pending = toolCalls.some((i) => i.type === "tool_call" && i.success === undefined)
  const label = toolCalls.length === 1
    ? (toolCalls[0] as Extract<ChatItem, { type: "tool_call" }>).name
    : `${toolCalls.length} tool calls`

  return (
    <div className="flex justify-start px-1 py-0.5">
      <div>
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs bg-muted/20 border border-border/20 text-muted-foreground hover:bg-muted/40 transition-colors"
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          {pending ? <Loader2 className="h-3 w-3 animate-spin text-blue-400/60" /> : <CheckCircle2 className="h-3 w-3 text-green-400/60" />}
          <span className="font-mono">{label}</span>
        </button>
        {open && (
          <div className="mt-1 space-y-1 pl-1">
            {items.map((item, i) => (
              <ChatMessage key={i} item={item} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// â”€â”€ Agent status pills â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function AgentStartCard({ agent, model }: { agent: string; model: string }) {
  return (
    <div className="flex justify-start px-1 py-0.5">
      <div className="flex items-center gap-2 rounded-full bg-muted/30 border border-border/20 px-3 py-1 text-xs text-muted-foreground/70">
        <Loader2 className="h-3 w-3 animate-spin text-blue-400/60" />
        <span className="text-blue-400/70">{agent}</span>
        <span>Â·</span>
        <span>{model}</span>
      </div>
    </div>
  )
}

function AgentDoneCard({ agent, reason, turns, elapsed }: { agent: string; reason: string; turns: number; elapsed: number }) {
  return (
    <div className="flex justify-start px-1 py-0.5">
      <div className="flex items-center gap-2 rounded-full bg-muted/20 border border-border/20 px-3 py-1 text-xs text-muted-foreground/50">
        <CheckCircle2 className="h-3 w-3 text-green-400/60" />
        <span className="text-blue-400/60">{agent}</span>
        <span>Â·</span>
        <span>{turns} turns Â· {formatTime(elapsed)}</span>
        {reason && <><span>Â·</span><span className="italic">{reason}</span></>}
      </div>
    </div>
  )
}

