import { useState } from "react"
import { PanelRightClose, Bot, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import { useAgentDetail, useAgentPrompt } from "@/api/queries"
import { useUIStore } from "@/stores/ui"
import { cn } from "@/lib/utils"

export function AgentDetail() {
  const { activeSessionId, selectedAgent, toggleRightPanel, setSelectedFile } = useUIStore()
  const { data: agent, isLoading } = useAgentDetail(activeSessionId, selectedAgent)

  if (!selectedAgent) {
    return (
      <div className="flex h-full items-center justify-center border-l text-sm text-muted-foreground">
        <p>Select an agent to view details</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center border-l text-sm text-muted-foreground">
        Loading...
      </div>
    )
  }

  if (!agent) return null

  const turnsPercent = agent.max_turns > 0 ? (agent.turns_used / agent.max_turns) * 100 : 0

  return (
    <div className="flex h-full flex-col border-l">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-blue-400" />
          <span className="text-sm font-semibold">{agent.name}</span>
          <Badge variant={agent.status === "running" ? "info" : agent.status === "done" ? "success" : "secondary"}>
            {agent.status}
          </Badge>
        </div>
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={toggleRightPanel}>
          <PanelRightClose className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Meta info */}
      <div className="border-b px-3 py-2 text-xs text-muted-foreground space-y-1">
        <div className="flex justify-between">
          <span>Model</span>
          <span className="font-mono">{agent.model}</span>
        </div>
        <div className="flex justify-between items-center">
          <span>Turns</span>
          <span>{agent.turns_used} / {agent.max_turns}</span>
        </div>
        <div className="h-1 rounded-full bg-muted overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              turnsPercent > 80 ? "bg-yellow-400" : "bg-blue-400",
            )}
            style={{ width: `${Math.min(turnsPercent, 100)}%` }}
          />
        </div>
        {agent.goal && (
          <p className="pt-1 text-foreground/70 line-clamp-2">{agent.goal}</p>
        )}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="context" className="flex flex-1 flex-col overflow-hidden">
        <TabsList className="mx-2 mt-2 h-8">
          <TabsTrigger value="context" className="text-xs">Context</TabsTrigger>
          <TabsTrigger value="tools" className="text-xs">Tools ({agent.tool_calls.length})</TabsTrigger>
          <TabsTrigger value="files" className="text-xs">Files ({agent.files_modified.length})</TabsTrigger>
        </TabsList>

        {/* Context Window */}
        <TabsContent value="context" className="flex-1 overflow-hidden m-0">
          <ScrollArea className="h-full">
            <div className="space-y-2 p-2">
              {agent.messages.map((msg, i) => (
                <ContextMessage key={i} message={msg} defaultCollapsed={msg.role === "system"} />
              ))}
            </div>
          </ScrollArea>
        </TabsContent>

        {/* Tool Calls */}
        <TabsContent value="tools" className="flex-1 overflow-hidden m-0">
          <ScrollArea className="h-full">
            <div className="space-y-1 p-2">
              {agent.tool_calls.length === 0 ? (
                <p className="p-3 text-xs text-muted-foreground">No tool calls</p>
              ) : (
                agent.tool_calls.map((tc, i) => (
                  <ToolCallRow key={i} name={tc.name} args={tc.args} />
                ))
              )}
            </div>
          </ScrollArea>
        </TabsContent>

        {/* Files Modified */}
        <TabsContent value="files" className="flex-1 overflow-hidden m-0">
          <ScrollArea className="h-full">
            <div className="space-y-0.5 p-2">
              {agent.files_modified.length === 0 ? (
                <p className="p-3 text-xs text-muted-foreground">No files modified</p>
              ) : (
                agent.files_modified.map((f) => (
                  <button
                    key={f}
                    onClick={() => setSelectedFile(f)}
                    className="flex w-full items-center gap-2 rounded px-2 py-1 text-xs font-mono hover:bg-accent/50 transition-colors"
                  >
                    {f}
                  </button>
                ))
              )}
            </div>
          </ScrollArea>
        </TabsContent>
      </Tabs>

      {/* Agent hop input */}
      <AgentHopInput />
    </div>
  )
}

function ContextMessage({
  message,
  defaultCollapsed,
}: {
  message: import("@/api/types").MessageResponse
  defaultCollapsed: boolean
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)

  const roleColor = {
    system: "text-muted-foreground",
    user: "text-green-400",
    assistant: "text-blue-400",
    error: "text-red-400",
  }[message.role] ?? "text-foreground"

  return (
    <div className="rounded border bg-muted/30 text-xs">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex w-full items-center gap-2 px-2 py-1.5 hover:bg-accent/30 transition-colors"
      >
        <Badge variant="outline" className={cn("text-[10px] px-1 py-0", roleColor)}>
          {message.role}
        </Badge>
        {collapsed && (
          <span className="truncate text-muted-foreground">
            {message.content.substring(0, 80)}...
          </span>
        )}
      </button>
      {!collapsed && (
        <pre className="whitespace-pre-wrap break-words border-t p-2 font-mono text-[11px] max-h-[300px] overflow-auto">
          {message.content}
        </pre>
      )}
    </div>
  )
}

function ToolCallRow({ name, args }: { name: string; args: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="rounded border bg-muted/30 text-xs">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-2 py-1.5 hover:bg-accent/30 transition-colors"
      >
        <span className="font-mono font-medium text-blue-400">{name}</span>
        {!expanded && (
          <span className="truncate text-muted-foreground">
            {JSON.stringify(args).substring(0, 60)}
          </span>
        )}
      </button>
      {expanded && (
        <pre className="border-t p-2 font-mono text-[11px] max-h-[200px] overflow-auto">
          {JSON.stringify(args, null, 2)}
        </pre>
      )}
    </div>
  )
}

function AgentHopInput() {
  const [prompt, setPrompt] = useState("")
  const { activeSessionId, selectedAgent } = useUIStore()
  const agentPrompt = useAgentPrompt(activeSessionId ?? "", selectedAgent ?? "")

  const handleSend = () => {
    const text = prompt.trim()
    if (!text) return
    agentPrompt.mutate(text)
    setPrompt("")
  }

  return (
    <div className="border-t p-2">
      <div className="flex gap-1">
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder="Prompt this agent..."
          className="min-h-[36px] max-h-[80px] resize-none text-xs"
        />
        <Button size="icon" className="h-9 w-9 shrink-0" onClick={handleSend} disabled={!prompt.trim()}>
          <Send className="h-3 w-3" />
        </Button>
      </div>
    </div>
  )
}
