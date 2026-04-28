import { useEffect } from "react"
import { useWSStore } from "@/stores/websocket"
import { useUIStore } from "@/stores/ui"
import { useAuthStore } from "@/stores/auth"

export function useWebSocket() {
  const connect = useWSStore((s) => s.connect)
  const disconnect = useWSStore((s) => s.disconnect)
  const activeSessionId = useUIStore((s) => s.activeSessionId)
  const accessToken = useAuthStore((s) => s.accessToken)

  useEffect(() => {
    if (activeSessionId) {
      connect(activeSessionId)
    }
    return () => {
      disconnect()
    }
  }, [activeSessionId, accessToken, connect, disconnect])
}
