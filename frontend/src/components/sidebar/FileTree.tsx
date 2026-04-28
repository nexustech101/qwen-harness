import { useState, useEffect, useCallback } from "react"
import { ChevronRight, ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { useFileTree } from "@/api/queries"
import { useUIStore } from "@/stores/ui"
import { useQueryClient } from "@tanstack/react-query"
import type { FileEntry } from "@/api/types"

// ── Icon colors by extension (VS Code palette) ────────────────────────────────

const ICON_STYLES: Record<string, { color: string; label: string }> = {
  py:     { color: "#3572A5", label: "PY" },
  js:     { color: "#f1e05a", label: "JS" },
  jsx:    { color: "#61dafb", label: "JX" },
  ts:     { color: "#3178c6", label: "TS" },
  tsx:    { color: "#3178c6", label: "TX" },
  json:   { color: "#a8a800", label: "{}" },
  css:    { color: "#563d7c", label: "CS" },
  scss:   { color: "#c6538c", label: "SC" },
  html:   { color: "#e34c26", label: "<>" },
  md:     { color: "#519aba", label: "MD" },
  txt:    { color: "#8b8b8b", label: "TX" },
  yaml:   { color: "#cb171e", label: "YM" },
  yml:    { color: "#cb171e", label: "YM" },
  toml:   { color: "#9c4121", label: "TM" },
  sh:     { color: "#89e051", label: "SH" },
  bash:   { color: "#89e051", label: "SH" },
  rs:     { color: "#dea584", label: "RS" },
  go:     { color: "#00ADD8", label: "GO" },
  java:   { color: "#b07219", label: "JA" },
  rb:     { color: "#701516", label: "RB" },
  c:      { color: "#555555", label: "C" },
  cpp:    { color: "#f34b7d", label: "C+" },
  h:      { color: "#555555", label: "H" },
  sql:    { color: "#e38c00", label: "SQ" },
  xml:    { color: "#e34c26", label: "XM" },
  svg:    { color: "#ff9900", label: "SV" },
  png:    { color: "#a074c4", label: "IM" },
  jpg:    { color: "#a074c4", label: "IM" },
  gif:    { color: "#a074c4", label: "IM" },
  lock:   { color: "#8b8b8b", label: "LK" },
  cfg:    { color: "#8b8b8b", label: "CF" },
  ini:    { color: "#8b8b8b", label: "IN" },
  env:    { color: "#8b8b8b", label: "EN" },
}

function getExtension(name: string): string {
  const parts = name.split(".")
  if (parts.length < 2) return ""
  return parts.pop()!.toLowerCase()
}

function FileIcon({ name, isDir, isOpen }: { name: string; isDir: boolean; isOpen?: boolean }) {
  if (isDir) {
    return (
      <svg className="h-4 w-4 shrink-0" viewBox="0 0 16 16" fill="none">
        <path
          d={isOpen
            ? "M1.5 3C1.5 2.44772 1.94772 2 2.5 2H6.29289C6.4255 2 6.55268 2.05268 6.64645 2.14645L7.85355 3.35355C7.94732 3.44732 8.0745 3.5 8.20711 3.5H13.5C14.0523 3.5 14.5 3.94772 14.5 4.5V5H2.5C1.94772 5 1.5 5.44772 1.5 6V3Z"
            : "M1.5 3C1.5 2.44772 1.94772 2 2.5 2H6.29289C6.4255 2 6.55268 2.05268 6.64645 2.14645L7.85355 3.35355C7.94732 3.44732 8.0745 3.5 8.20711 3.5H13.5C14.0523 3.5 14.5 3.94772 14.5 4.5V12C14.5 12.5523 14.0523 13 13.5 13H2.5C1.94772 13 1.5 12.5523 1.5 12V3Z"
          }
          fill={isOpen ? "#dcb67a" : "#c09553"}
        />
        {isOpen && (
          <path
            d="M1.5 6C1.5 5.44772 1.94772 5 2.5 5H14.5L13.5 13H2.5C1.94772 13 1.5 12.5523 1.5 12V6Z"
            fill="#dcb67a"
          />
        )}
      </svg>
    )
  }

  const ext = getExtension(name)
  const style = ICON_STYLES[ext]

  if (style) {
    return (
      <span
        className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-[2px] text-[7px] font-bold leading-none"
        style={{ backgroundColor: style.color + "22", color: style.color }}
      >
        {style.label}
      </span>
    )
  }

  // Default file icon
  return (
    <svg className="h-4 w-4 shrink-0 text-muted-foreground" viewBox="0 0 16 16" fill="none">
      <path
        d="M3 1.5C2.44772 1.5 2 1.94772 2 2.5V13.5C2 14.0523 2.44772 14.5 3 14.5H13C13.5523 14.5 14 14.0523 14 13.5V5.20711C14 4.94189 13.8946 4.6875 13.7071 4.5L10.5 1.29289C10.3125 1.10536 10.0581 1 9.79289 1H3.5C3 1 3 1.5 3 1.5Z"
        fill="currentColor"
        opacity="0.3"
      />
      <path d="M10 1V4.5C10 5.05228 10.4477 5.5 11 5.5H14" stroke="currentColor" strokeWidth="0.5" opacity="0.5" />
    </svg>
  )
}

// ── Sort: directories first, then alphabetical ────────────────────────────────

function sortEntries(entries: FileEntry[]): FileEntry[] {
  return [...entries].sort((a, b) => {
    if (a.type !== b.type) return a.type === "directory" ? -1 : 1
    return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" })
  })
}

// ── Indent guide ──────────────────────────────────────────────────────────────

const INDENT_SIZE = 16

function IndentGuides({ depth }: { depth: number }) {
  if (depth === 0) return null
  return (
    <>
      {Array.from({ length: depth }, (_, i) => (
        <span
          key={i}
          className="absolute top-0 bottom-0 w-px bg-border/50"
          style={{ left: `${i * INDENT_SIZE + 12}px` }}
        />
      ))}
    </>
  )
}

// ── Tree root ─────────────────────────────────────────────────────────────────

export function FileTree() {
  const sessionId = useUIStore((s) => s.activeSessionId)
  const { data: tree, isLoading } = useFileTree(sessionId)
  const qc = useQueryClient()

  const refreshTree = useCallback(() => {
    if (sessionId) {
      qc.invalidateQueries({ queryKey: ["files", sessionId] })
    }
  }, [sessionId, qc])

  useEffect(() => {
    window.addEventListener("file-tree-changed", refreshTree)
    return () => window.removeEventListener("file-tree-changed", refreshTree)
  }, [refreshTree])

  if (isLoading) {
    return (
      <div className="flex flex-col gap-1.5 p-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="flex items-center gap-2 px-2">
            <div className="h-3 w-3 rounded bg-muted animate-pulse" />
            <div className="h-3 rounded bg-muted animate-pulse" style={{ width: `${40 + i * 15}px` }} />
          </div>
        ))}
      </div>
    )
  }

  if (!tree?.length) {
    return (
      <div className="p-3 text-xs text-muted-foreground">No files</div>
    )
  }

  return (
    <div className="py-0.5 text-[13px]">
      {sortEntries(tree).map((entry) => (
        <FileTreeNode key={entry.path} entry={entry} depth={0} />
      ))}
    </div>
  )
}

// ── Tree node ─────────────────────────────────────────────────────────────────

function FileTreeNode({ entry, depth }: { entry: FileEntry; depth: number }) {
  const [expanded, setExpanded] = useState(depth < 1)
  const { selectedFile, setSelectedFile } = useUIStore()
  const isDir = entry.type === "directory"
  const isActive = selectedFile === entry.path

  const paddingLeft = depth * INDENT_SIZE + 4

  return (
    <div>
      <button
        className={cn(
          "relative flex w-full items-center gap-1.5 h-[22px] pr-2 text-[13px] transition-colors",
          "hover:bg-[hsl(var(--accent)/0.5)]",
          "focus-visible:outline-none focus-visible:bg-accent",
          isActive && "bg-accent text-accent-foreground",
          !isActive && !isDir && "text-foreground/80",
        )}
        style={{ paddingLeft: `${paddingLeft}px` }}
        onClick={() => {
          if (isDir) {
            setExpanded(!expanded)
          } else {
            setSelectedFile(entry.path)
          }
        }}
      >
        <IndentGuides depth={depth} />

        {/* Chevron */}
        {isDir ? (
          expanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )
        ) : (
          <span className="w-3.5 shrink-0" />
        )}

        {/* Icon */}
        <FileIcon name={entry.name} isDir={isDir} isOpen={expanded} />

        {/* Name */}
        <span className="truncate">{entry.name}</span>
      </button>

      {/* Children */}
      {isDir && expanded && entry.children && sortEntries(entry.children).map((child) => (
        <FileTreeNode key={child.path} entry={child} depth={depth + 1} />
      ))}
    </div>
  )
}
