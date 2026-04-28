import { useState, useEffect } from "react"
import { X, FileCode, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { useFileContent } from "@/api/queries"
import { useUIStore } from "@/stores/ui"
import { useQueryClient } from "@tanstack/react-query"
import { codeToHtml } from "shiki"

const EXT_TO_LANG: Record<string, string> = {
  py: "python",
  js: "javascript",
  jsx: "jsx",
  ts: "typescript",
  tsx: "tsx",
  rs: "rust",
  go: "go",
  rb: "ruby",
  java: "java",
  c: "c",
  cpp: "cpp",
  h: "c",
  hpp: "cpp",
  cs: "csharp",
  css: "css",
  html: "html",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  md: "markdown",
  sh: "bash",
  bash: "bash",
  sql: "sql",
  xml: "xml",
  dockerfile: "dockerfile",
}

function getLang(filePath: string): string {
  const name = filePath.split(/[/\\]/).pop()?.toLowerCase() ?? ""
  if (name === "dockerfile") return "dockerfile"
  const ext = name.split(".").pop() ?? ""
  return EXT_TO_LANG[ext] ?? "text"
}

export function FileViewer() {
  const { activeSessionId, selectedFile, setSelectedFile } = useUIStore()
  const { data: file, isLoading, isError } = useFileContent(activeSessionId, selectedFile)
  const qc = useQueryClient()
  const [highlightedHtml, setHighlightedHtml] = useState<string>("")

  useEffect(() => {
    if (!file?.content || !selectedFile) {
      queueMicrotask(() => setHighlightedHtml(""))
      return
    }

    let cancelled = false
    const lang = getLang(selectedFile)

    codeToHtml(file.content, {
      lang,
      theme: "github-dark-default",
    })
      .then((html) => {
        if (!cancelled) setHighlightedHtml(html)
      })
      .catch(() => {
        // Fallback: if language isn't supported, try plaintext
        if (!cancelled) setHighlightedHtml("")
      })

    return () => { cancelled = true }
  }, [file?.content, selectedFile])

  if (!selectedFile) return null

  const refresh = () => {
    if (activeSessionId && selectedFile) {
      qc.invalidateQueries({ queryKey: ["file", activeSessionId, selectedFile] })
    }
  }

  const lines = file?.content.split("\n") ?? []

  return (
    <div className="flex h-full flex-col">
      {/* File header */}
      <div className="flex h-10 items-center justify-between border-b px-3">
        <div className="flex items-center gap-2 text-sm">
          <FileCode className="h-4 w-4 text-muted-foreground" />
          <span className="font-mono text-xs">{selectedFile}</span>
          {file && (
            <>
              <Badge variant="secondary" className="text-[10px]">{file.lines} lines</Badge>
              <Badge variant="secondary" className="text-[10px]">{(file.size / 1024).toFixed(1)} KB</Badge>
            </>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={refresh}>
            <RefreshCw className="h-3 w-3" />
          </Button>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setSelectedFile(null)}>
            <X className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* File content */}
      <ScrollArea className="flex-1">
        {isLoading ? (
          <div className="p-4 text-sm text-muted-foreground">Loading...</div>
        ) : isError ? (
          <div className="p-4 text-sm text-red-400">Error loading file</div>
        ) : file ? (
          <div className="flex text-xs font-mono">
            {/* Line numbers */}
            <div className="sticky left-0 shrink-0 select-none border-r bg-background px-3 py-3 text-right text-muted-foreground/50" style={{ lineHeight: "20px" }}>
              {lines.map((_, i) => (
                <div key={i}>{i + 1}</div>
              ))}
            </div>

            {/* Code content */}
            <div className="min-w-0 flex-1 overflow-x-auto py-3 pl-4 pr-4">
              {highlightedHtml ? (
                <div
                  dangerouslySetInnerHTML={{ __html: highlightedHtml }}
                  style={{ lineHeight: "20px" }}
                  className="[&_pre]:!m-0 [&_pre]:!p-0 [&_pre]:!bg-transparent [&_pre]:!leading-[20px] [&_code]:!bg-transparent [&_code]:!leading-[20px] [&_.line]:!leading-[20px]"
                />
              ) : (
                <pre className="whitespace-pre !m-0 !p-0" style={{ lineHeight: "20px" }}>
                  <code>{file.content}</code>
                </pre>
              )}
            </div>
          </div>
        ) : null}
      </ScrollArea>
    </div>
  )
}
