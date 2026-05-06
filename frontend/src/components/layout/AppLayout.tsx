import { useRef, useState, useCallback, useEffect } from "react"
import { MessageSquare, GitBranch, Plug, Settings, PanelLeft, Sun, Moon } from "lucide-react"
import { StatusBar } from "./StatusBar"
import { Sidebar } from "@/components/sidebar/Sidebar"
import { ChatView } from "@/components/chat/ChatView"
import { WorkflowView } from "@/components/workflow/WorkflowView"
import { MCPView } from "@/components/mcp/MCPView"
import { SettingsView } from "@/components/settings/SettingsView"
import { useUIStore } from "@/stores/ui"
import { cn } from "@/lib/utils"

const SIDEBAR_MIN = 160
const SIDEBAR_MAX = 480
const SIDEBAR_DEFAULT = 220
const SIDEBAR_STORAGE_KEY = "sidebar-width"

const NAV_ITEMS = [
  { view: "chat" as const, icon: MessageSquare, label: "Chat" },
  { view: "workflows" as const, icon: GitBranch, label: "Flows" },
  { view: "mcp" as const, icon: Plug, label: "MCP" },
  { view: "settings" as const, icon: Settings, label: "Settings" },
]

function NavRail() {
  const activeView = useUIStore((s) => s.activeView)
  const setActiveView = useUIStore((s) => s.setActiveView)
  const sidebarOpen = useUIStore((s) => s.sidebarOpen)
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)
  const theme = useUIStore((s) => s.theme)
  const toggleTheme = useUIStore((s) => s.toggleTheme)

  return (
    <div className="flex w-14 shrink-0 flex-col items-center border-r border-border/30 bg-sidebar py-2 gap-1">
      {/* Logo / sidebar toggle */}
      <button
        className="mb-1 flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        onClick={toggleSidebar}
        title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
      >
        <PanelLeft className="h-4 w-4" />
      </button>

      <div className="w-8 border-t border-border/30 mb-1" />

      {/* View nav */}
      {NAV_ITEMS.map(({ view, icon: Icon, label }) => (
        <button
          key={view}
          onClick={() => setActiveView(view)}
          title={label}
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-lg transition-colors text-xs",
            activeView === view
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-accent",
          )}
        >
          <Icon className="h-4 w-4" />
        </button>
      ))}

      <div className="flex-1" />

      {/* Theme toggle */}
      <button
        className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        onClick={toggleTheme}
        title={theme === "dark" ? "Light mode" : "Dark mode"}
      >
        {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>
    </div>
  )
}

export function AppLayout() {
  const { activeSessionId, activeView, sidebarOpen } = useUIStore()

  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const stored = localStorage.getItem(SIDEBAR_STORAGE_KEY)
    return stored ? Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, parseInt(stored, 10))) : SIDEBAR_DEFAULT
  })
  const dragging = useRef(false)
  const startX = useRef(0)
  const startWidth = useRef(0)

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    dragging.current = true
    startX.current = e.clientX
    startWidth.current = sidebarWidth
    document.body.style.cursor = "col-resize"
    document.body.style.userSelect = "none"
  }, [sidebarWidth])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const delta = e.clientX - startX.current
      const next = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, startWidth.current + delta))
      setSidebarWidth(next)
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.style.cursor = ""
      document.body.style.userSelect = ""
      setSidebarWidth((w) => {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, String(w))
        return w
      })
    }
    window.addEventListener("mousemove", onMove)
    window.addEventListener("mouseup", onUp)
    return () => {
      window.removeEventListener("mousemove", onMove)
      window.removeEventListener("mouseup", onUp)
    }
  }, [])

  return (
    <div className="flex h-screen flex-col bg-background">
      <div className="flex flex-1 overflow-hidden">
        {/* Always-visible nav rail */}
        <NavRail />

        {/* Collapsible + resizable sidebar */}
        <div
          className={cn(
            "relative flex flex-col shrink-0 overflow-hidden border-r border-border/30 bg-sidebar",
            sidebarOpen ? "" : "w-0",
          )}
          style={sidebarOpen ? { width: sidebarWidth } : undefined}
        >
          <Sidebar />
          {/* Drag handle */}
          {sidebarOpen && (
            <div
              onMouseDown={onMouseDown}
              className="absolute right-0 top-0 h-full w-1 cursor-col-resize hover:bg-ring/40 active:bg-ring/60 transition-colors z-10"
            />
          )}
        </div>

        {/* Main content area */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {activeView === "chat" && <ChatView />}
          {activeView === "workflows" && <WorkflowView />}
          {activeView === "mcp" && <MCPView />}
          {activeView === "settings" && <SettingsView />}
        </div>
      </div>

      {activeView === "chat" && activeSessionId && <StatusBar />}
    </div>
  )
}

