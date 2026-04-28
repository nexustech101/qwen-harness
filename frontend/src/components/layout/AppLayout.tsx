import { useEffect } from "react"
import { PanelLeft } from "lucide-react"
import { usePanelRef } from "react-resizable-panels"
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable"
import { Button } from "@/components/ui/button"
import { TopNav } from "./Header"
import { StatusBar } from "./StatusBar"
import { Sidebar } from "@/components/sidebar/Sidebar"
import { ChatView } from "@/components/chat/ChatView"
import { FileViewer } from "@/components/file-viewer/FileViewer"
import { useUIStore } from "@/stores/ui"

export function AppLayout() {
  const { sidebarOpen, selectedFile, activeSessionId, toggleSidebar } = useUIStore()
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
      <TopNav />

      <div className="relative flex flex-1 overflow-hidden">
        {/* Sidebar toggle (visible when collapsed) */}
        {!sidebarOpen && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute left-1 top-1 z-10 h-7 w-7"
            onClick={toggleSidebar}
          >
            <PanelLeft className="h-4 w-4" />
          </Button>
        )}

        <ResizablePanelGroup orientation="horizontal">
          {/* Sidebar — always mounted, collapsible */}
          <ResizablePanel
            defaultSize="16%"
            minSize="10%"
            maxSize="25%"
            collapsible
            collapsedSize="0%"
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

          {/* Main Content */}
          <ResizablePanel defaultSize="84%" minSize="30%" id="main">
            {activeSessionId && selectedFile ? <FileViewer /> : <ChatView />}
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      {activeSessionId && <StatusBar />}
    </div>
  )
}
