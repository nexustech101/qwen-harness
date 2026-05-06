import { MessageSquare, GitBranch, Plug, Settings, PanelLeft, Sun, Moon } from "lucide-react"
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
  const { activeSessionId, activeView, sidebarOpen } = useUIStore()

  return (
    <div className="flex h-screen flex-col bg-background">
      <div className="flex flex-1 overflow-hidden">
        {/* Always-visible nav rail */}
        <NavRail />

        {/* Collapsible sidebar */}
        <div
          className={cn(
            "flex flex-col shrink-0 overflow-hidden border-r border-border/30 bg-sidebar transition-[width] duration-200 ease-in-out",
            sidebarOpen ? "w-60" : "w-0",
          )}
        >
          <Sidebar />
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

