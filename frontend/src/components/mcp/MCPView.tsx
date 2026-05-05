import { Plug, Wrench, MessageSquare } from "lucide-react"
import { Separator } from "@/components/ui/separator"

const MCP_TOOLS = [
  { name: "read_file", description: "Read the contents of a file at a given path" },
  { name: "write_file", description: "Write content to a file, creating it if needed" },
  { name: "edit_file", description: "Apply a targeted patch to a file" },
  { name: "list_directory", description: "List files in a directory" },
  { name: "run_command", description: "Execute a shell command in the workspace" },
  { name: "search_text", description: "Grep for a pattern across the workspace" },
  { name: "read_url", description: "Fetch and return the text content of a URL" },
  { name: "python_repl", description: "Execute a Python snippet and return output" },
]

const MCP_PROMPTS = [
  { name: "code_review", description: "Review code for quality, bugs, and style issues" },
  { name: "refactor", description: "Refactor a code block with given objectives" },
  { name: "write_tests", description: "Generate tests for a given function or module" },
  { name: "explain_code", description: "Explain what a code snippet does in plain language" },
]

export function MCPView() {
  return (
    <div className="h-full overflow-y-auto p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
          <Plug className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-lg font-semibold">MCP Server</h1>
          <p className="text-sm text-muted-foreground">Model Context Protocol — tools and prompts</p>
        </div>
      </div>

      <Separator className="mb-6" />

      {/* Tools */}
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <Wrench className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Tools</h2>
          <span className="ml-auto text-xs text-muted-foreground">{MCP_TOOLS.length} registered</span>
        </div>
        <div className="space-y-2">
          {MCP_TOOLS.map((tool) => (
            <div
              key={tool.name}
              className="flex items-start gap-3 rounded-lg border border-border/30 bg-card/40 px-4 py-3"
            >
              <code className="text-xs font-mono text-blue-400/80 pt-0.5 shrink-0">{tool.name}</code>
              <span className="text-xs text-muted-foreground">{tool.description}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Prompts */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <MessageSquare className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Prompts</h2>
          <span className="ml-auto text-xs text-muted-foreground">{MCP_PROMPTS.length} registered</span>
        </div>
        <div className="space-y-2">
          {MCP_PROMPTS.map((prompt) => (
            <div
              key={prompt.name}
              className="flex items-start gap-3 rounded-lg border border-border/30 bg-card/40 px-4 py-3"
            >
              <code className="text-xs font-mono text-purple-400/80 pt-0.5 shrink-0">{prompt.name}</code>
              <span className="text-xs text-muted-foreground">{prompt.description}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
