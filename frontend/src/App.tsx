import { useEffect } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Toaster } from "sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppLayout } from "@/components/layout/AppLayout"
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts"
import { useWebSocket } from "@/hooks/useWebSocket"
import { useAuthStore } from "@/stores/auth"
import { useWSStore } from "@/stores/websocket"
import { useUIStore } from "@/stores/ui"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

function AppInner() {
  useKeyboardShortcuts()
  useWebSocket()
  const bootstrap = useAuthStore((s) => s.bootstrap)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const syncTokensFromStorage = useAuthStore((s) => s.syncTokensFromStorage)
  const userId = useAuthStore((s) => s.user?.id)
  const disconnect = useWSStore((s) => s.disconnect)
  const setActiveSession = useUIStore((s) => s.setActiveSession)

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  useEffect(() => {
    queryClient.invalidateQueries({ queryKey: ["sessions"] })
    queryClient.invalidateQueries({ queryKey: ["messages"] })
  }, [userId])

  useEffect(() => {
    const handleRefreshFailed = () => {
      clearAuth()
      disconnect()
      setActiveSession(null)
      queryClient.removeQueries({ queryKey: ["billing"] })
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
    }
    const handleTokensChanged = () => {
      syncTokensFromStorage()
    }
    const handleSessionAccessLost = () => {
      setActiveSession(null)
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
    }
    window.addEventListener("auth-refresh-failed", handleRefreshFailed)
    window.addEventListener("auth-tokens-changed", handleTokensChanged)
    window.addEventListener("session-access-lost", handleSessionAccessLost)
    return () => {
      window.removeEventListener("auth-refresh-failed", handleRefreshFailed)
      window.removeEventListener("auth-tokens-changed", handleTokensChanged)
      window.removeEventListener("session-access-lost", handleSessionAccessLost)
    }
  }, [clearAuth, disconnect, setActiveSession, syncTokensFromStorage])

  return <AppLayout />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <AppInner />
        <Toaster
          position="bottom-right"
          toastOptions={{
            className: "bg-card text-card-foreground border",
          }}
        />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
