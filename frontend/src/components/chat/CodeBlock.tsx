import { useState, useEffect, useRef } from "react"
import { Check, Copy } from "lucide-react"
import { codeToHtml } from "shiki"
import { cn } from "@/lib/utils"

const LANG_DISPLAY: Record<string, string> = {
  js: "JavaScript",
  ts: "TypeScript",
  tsx: "TypeScript",
  jsx: "JavaScript",
  py: "Python",
  python: "Python",
  bash: "Bash",
  sh: "Shell",
  json: "JSON",
  yaml: "YAML",
  yml: "YAML",
  css: "CSS",
  html: "HTML",
  sql: "SQL",
  rust: "Rust",
  go: "Go",
  java: "Java",
  cpp: "C++",
  c: "C",
  ruby: "Ruby",
  markdown: "Markdown",
  md: "Markdown",
  toml: "TOML",
  xml: "XML",
  dockerfile: "Dockerfile",
}

export function CodeBlock({ language, children }: { language?: string; children: string }) {
  const [copied, setCopied] = useState(false)
  const [highlighted, setHighlighted] = useState<string | null>(null)
  const codeRef = useRef<HTMLDivElement>(null)

  const displayLang = language
    ? LANG_DISPLAY[language.toLowerCase()] ?? language.charAt(0).toUpperCase() + language.slice(1)
    : "Code"

  useEffect(() => {
    let active = true
    if (language) {
      codeToHtml(children, {
        lang: language,
        theme: "github-dark-default",
      })
        .then((html) => {
          if (active) setHighlighted(html)
        })
        .catch(() => {
          // Fallback to plain text if language isn't supported
        })
    }
    return () => { active = false }
  }, [children, language])

  const handleCopy = () => {
    navigator.clipboard.writeText(children)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="relative my-3 rounded-lg border border-border/50 bg-[hsl(0,0%,7%)] overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border/30 bg-[hsl(0,0%,9%)]">
        <span className="text-xs text-muted-foreground font-medium">{displayLang}</span>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            className={cn(
              "flex items-center gap-1.5 text-xs transition-colors rounded px-2 py-0.5",
              copied
                ? "text-green-400"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>

      {/* Code content */}
      {highlighted ? (
        <div
          ref={codeRef}
          className="overflow-x-auto p-4 text-sm [&_pre]:!bg-transparent [&_pre]:!m-0 [&_pre]:!p-0 [&_code]:!text-sm [&_code]:!font-mono"
          dangerouslySetInnerHTML={{ __html: highlighted }}
        />
      ) : (
        <pre className="overflow-x-auto p-4">
          <code className="text-sm font-mono text-foreground/90">{children}</code>
        </pre>
      )}
    </div>
  )
}

/** Inline code styling */
export function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-[hsl(0,0%,15%)] px-1.5 py-0.5 text-[0.85em] font-mono text-orange-300/90">
      {children}
    </code>
  )
}
