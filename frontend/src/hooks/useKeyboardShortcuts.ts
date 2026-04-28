import { useEffect } from "react"
import { useUIStore } from "@/stores/ui"
import { useWSStore } from "@/stores/websocket"

export function useKeyboardShortcuts() {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)
  const toggleRightPanel = useUIStore((s) => s.toggleRightPanel)
  const toggleTheme = useUIStore((s) => s.toggleTheme)
  const cancel = useWSStore((s) => s.cancel)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+B — toggle sidebar
      if (e.ctrlKey && e.key === "b" && !e.shiftKey) {
        e.preventDefault()
        toggleSidebar()
      }

      // Ctrl+Shift+B — toggle right panel
      if (e.ctrlKey && e.shiftKey && e.key === "B") {
        e.preventDefault()
        toggleRightPanel()
      }

      // Escape — cancel running prompt
      if (e.key === "Escape") {
        cancel()
      }

      // Ctrl+K — focus prompt input
      if (e.ctrlKey && e.key === "k") {
        e.preventDefault()
        const textarea = document.querySelector<HTMLTextAreaElement>("textarea[placeholder*='prompt']")
        textarea?.focus()
      }

      // Ctrl+Shift+L — toggle theme
      if (e.ctrlKey && e.shiftKey && e.key === "L") {
        e.preventDefault()
        toggleTheme()
      }
    }

    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [toggleSidebar, toggleRightPanel, toggleTheme, cancel])
}
