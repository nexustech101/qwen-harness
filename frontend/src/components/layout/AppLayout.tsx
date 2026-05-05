import { useEffect } from "react"
import { MessageSquare, GitBranch, Plug, Settings, PanelLeft, Sun, Moon } from "lucide-react"
import { usePanelRef } from "react-resizable-panels"
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable"
import { Button } from "@/components/ui/button"
import { StatusBar } from "./StatusBar"
import { Sidebar } from "@/components/sidebar/Sidebar"
import { ChatView } from "@/components/chat/ChatView"
import { WorkflowView } from "@/components/workflow/WorkflowView"
import { MCPView } from "@/components/mcp/MCPView"
import { SettingsView } from "@/components/settings/SettingsView"
import { useUIStore } from "@/stores/ui"
import { cn } from "@/lib/utils"

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
  const { sidebarOpen, activeSessionId, activeView } = useUIStore()
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen)

  const sidebarRef = usePanelRef()

  // Sync store → panel
  useEffect(() => {
    const panel = sidebarRef.current
    if (!panel) return
    if (sidebarOpen && panel.isCollapsed()) panel.expand()
    if (!sidebarOpen && !panel.isCollapsed()) panel.collapse()
  }, [sidebarOpen, sidebarRef])

  return (
    <div className="flex h-screen flex-col bg-background">
      <div className="flex flex-1 overflow-hidden">
        {/* Always-visible nav rail */}
        <NavRail />

        {/* Sidebar content + main */}
        <ResizablePanelGroup orientation="horizontal" className="flex-1">
          <ResizablePanel
            defaultSize={18}
            minSize={12}
            maxSize={30}
            collapsible
            collapsedSize={0}
            panelRef={sidebarRef}
            id="sidebar"
            onResize={(size) => {
              const collapsed = size.asPercentage < 1
              if (collapsed && sidebarOpen) setSidebarOpen(false)
              if (!collapsed && !sidebarOpen) setSidebarOpen(true)
            }}
          >
            <Sidebar />
          </ResizablePanel>

          <ResizableHandle />

          {/* Main content area */}
          <ResizablePanel defaultSize={82} minSize={40} id="main">
            {activeView === "chat" && <ChatView />}
            {activeView === "workflows" && <WorkflowView />}
            {activeView === "mcp" && <MCPView />}
            {activeView === "settings" && <SettingsView />}
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      {activeView === "chat" && activeSessionId && <StatusBar />}
    </div>
  )
}
