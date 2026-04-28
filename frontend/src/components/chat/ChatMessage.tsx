import { useCallback, useState } from "react"
import { AlertCircle, Check, CheckCircle2, ChevronDown, ChevronRight, Copy, Loader2 } from "lucide-react"
import { cn, formatTime } from "@/lib/utils"
import { formatAssistantContent, formatToolResult } from "@/lib/chat-format"
import { MarkdownContent } from "./MarkdownContent"
import { RobotLogo } from "@/components/branding/RobotLogo"
import type { ChatItem } from "@/api/types"

export function ChatMessage({ item }: { item: ChatItem }) {
  switch (item.type) {
    case "user":
      return <UserMessage content={item.content} />
    case "assistant":
      return <AssistantMessage content={item.content} metadata={item.metadata} />
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

function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex gap-3 py-2">
      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/80">
        <span className="text-[10px] font-bold text-primary-foreground">U</span>
      </div>
      <div className="min-w-0 flex-1">
        <p className="whitespace-pre-wrap text-sm font-medium leading-relaxed">{content}</p>
      </div>
    </div>
  )
}

function AssistantMessage({
  content,
  metadata,
}: {
  content: string
  metadata?: import("@/api/types").ResultMetadata
}) {
  const [copied, setCopied] = useState(false)
  const displayContent = formatAssistantContent(content) || content

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(displayContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [displayContent])

  return (
    <div className="flex gap-3 py-2">
      <div className="mt-0.5 shrink-0">
        <RobotLogo size={24} className="text-blue-400" />
      </div>
      <div className="min-w-0 flex-1">
        <MarkdownContent content={displayContent} />

        <div className="mt-3 flex items-center gap-4">
          {metadata && (
            <span className="text-xs text-muted-foreground">
              {metadata.turns} turns - {metadata.tool_calls_made} tools - {formatTime(metadata.elapsed_seconds)}
              {metadata.files_modified.length > 0 && ` - ${metadata.files_modified.length} files`}
            </span>
          )}
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              title="Copy message"
            >
              {copied ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function ReasoningBlock({ content, agent }: { content: string; agent: string }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="ml-9">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground/70 transition-colors hover:text-muted-foreground"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <span className="italic">Reasoning{agent !== "main" ? ` (${agent})` : ""}</span>
      </button>
      {open && (
        <div className="mt-1.5 max-h-[300px] overflow-y-auto rounded-lg border border-border/30 bg-[hsl(0,0%,7%)] p-3 font-mono text-xs whitespace-pre-wrap text-muted-foreground/80">
          {content}
        </div>
      )}
    </div>
  )
}

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
    <div className="ml-9">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs transition-colors hover:bg-accent/30"
      >
        {expanded ? <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />}
        <span className="font-mono text-blue-400/80">{name}</span>
        {filePath && <span className="truncate text-[11px] text-muted-foreground/60">{filePath}</span>}
        <span className="ml-auto">
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
        <div className="mt-1 ml-5 space-y-2 rounded-lg border border-border/30 bg-[hsl(0,0%,7%)] p-3">
          <div>
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">Args</span>
            <pre className="mt-1 max-h-[200px] overflow-auto rounded-md bg-[hsl(0,0%,5%)] p-2 font-mono text-xs text-muted-foreground">
              {JSON.stringify(args, null, 2)}
            </pre>
          </div>
          {displayResult && (
            <div>
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">Result</span>
              <pre
                className={cn(
                  "mt-1 max-h-[200px] overflow-auto rounded-md p-2 font-mono text-xs",
                  error ? "bg-red-500/5 text-red-400/80" : "bg-[hsl(0,0%,5%)] text-muted-foreground",
                )}
              >
                {displayResult}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ErrorCard({ content }: { content: string }) {
  return (
    <div className="ml-9 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-sm text-red-400/90">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{content}</span>
    </div>
  )
}

function AgentStartCard({ agent, model }: { agent: string; model: string }) {
  return (
    <div className="ml-9 flex items-center gap-2 py-0.5 text-xs text-muted-foreground/60">
      <Loader2 className="h-3 w-3 animate-spin text-blue-400/50" />
      <span>
        <span className="text-blue-400/70">{agent}</span> working - {model}
      </span>
    </div>
  )
}

function AgentDoneCard({ agent, reason, turns, elapsed }: { agent: string; reason: string; turns: number; elapsed: number }) {
  const ok = reason === "done"
  return (
    <div className="ml-9 flex items-center gap-2 py-0.5 text-xs text-muted-foreground/60">
      <CheckCircle2 className={cn("h-3 w-3", ok ? "text-green-400/60" : "text-yellow-400/60")} />
      <span>
        <span className={ok ? "text-green-400/70" : "text-yellow-400/70"}>{agent}</span> finished - {turns} turns - {formatTime(elapsed)}
      </span>
    </div>
  )
}

export function ActivityGroup({ items }: { items: ChatItem[] }) {
  const [expanded, setExpanded] = useState(false)
  const toolCalls = items.filter(
    (i): i is Extract<ChatItem, { type: "tool_call" }> => i.type === "tool_call",
  )
  const pending = toolCalls.filter((t) => t.success === undefined).length
  const failed = toolCalls.some((t) => t.success === false)
  const allDone = pending === 0 && toolCalls.length > 0

  if (toolCalls.length === 0 && items.every((i) => i.type === "agent_start" || i.type === "agent_done")) {
    const start = items.find((i): i is Extract<ChatItem, { type: "agent_start" }> => i.type === "agent_start")
    const done = items.find((i): i is Extract<ChatItem, { type: "agent_done" }> => i.type === "agent_done")
    if (start && !done) {
      return <AgentStartCard agent={start.agent} model={start.model} />
    }
    if (done) {
      return <AgentDoneCard agent={done.agent} reason={done.reason} turns={done.turns} elapsed={done.elapsed} />
    }
    return null
  }

  const uniqueNames = [...new Set(toolCalls.map((t) => t.name))]
  const label = uniqueNames.length <= 3 ? uniqueNames.join(", ") : `${toolCalls.length} tool calls`

  return (
    <div className="ml-9 my-0.5">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 rounded-md px-2 py-1 text-xs text-muted-foreground/60 transition-colors hover:bg-accent/30 hover:text-muted-foreground"
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <span className="font-mono">{label}</span>
        {pending > 0 && <Loader2 className="h-3 w-3 animate-spin text-blue-400/50" />}
        {allDone && !failed && <CheckCircle2 className="h-3 w-3 text-green-400/60" />}
        {failed && <AlertCircle className="h-3 w-3 text-red-400/60" />}
      </button>
      {expanded && (
        <div className="mt-1 ml-2 space-y-px border-l border-border/20 pl-3">
          {toolCalls.map((toolCall, i) => {
            const filePath = (toolCall.args?.path as string) ?? (toolCall.args?.file_path as string) ?? null
            return (
              <div key={i} className="flex items-center gap-2 py-0.5 text-xs text-muted-foreground/70">
                <span className="font-mono text-blue-400/70">{toolCall.name}</span>
                {filePath && (
                  <span className="max-w-[250px] truncate text-muted-foreground/50">{filePath}</span>
                )}
                <span className="ml-auto">
                  {toolCall.success === undefined ? (
                    <Loader2 className="h-3 w-3 animate-spin text-muted-foreground/40" />
                  ) : toolCall.success ? (
                    <CheckCircle2 className="h-3 w-3 text-green-400/60" />
                  ) : (
                    <AlertCircle className="h-3 w-3 text-red-400/60" />
                  )}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
