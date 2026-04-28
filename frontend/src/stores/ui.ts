import { create } from "zustand"

interface UIStore {
  theme: "light" | "dark"
  sidebarOpen: boolean
  rightPanelOpen: boolean
  selectedAgent: string | null
  selectedFile: string | null
  activeSessionId: string | null
  selectedModel: string | null
  toggleTheme: () => void
  toggleSidebar: () => void
  toggleRightPanel: () => void
  setSidebarOpen: (open: boolean) => void
  setRightPanelOpen: (open: boolean) => void
  setSelectedAgent: (name: string | null) => void
  setSelectedFile: (path: string | null) => void
  setActiveSession: (id: string | null) => void
  setSelectedModel: (model: string | null) => void
}

export const useUIStore = create<UIStore>((set) => ({
  theme: "dark",
  sidebarOpen: true,
  rightPanelOpen: false,
  selectedAgent: null,
  selectedFile: null,
  activeSessionId: null,
  selectedModel: null,

  toggleTheme: () =>
    set((s) => {
      const next = s.theme === "dark" ? "light" : "dark"
      document.documentElement.classList.toggle("dark", next === "dark")
      return { theme: next }
    }),

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
  setSelectedAgent: (name) => set({ selectedAgent: name, rightPanelOpen: !!name }),
  setSelectedFile: (path) => set({ selectedFile: path }),
  setActiveSession: (id) => set({ activeSessionId: id, selectedAgent: null, selectedFile: null }),
  setSelectedModel: (model) => set({ selectedModel: model }),
}))
