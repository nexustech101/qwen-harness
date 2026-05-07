import { useState } from "react"
import { Plus, ChevronDown, Check, Cpu } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { useCreateSession, useConfig, useModels } from "@/api/queries"
import { useUIStore } from "@/stores/ui"
import { useAuthStore } from "@/stores/auth"
import { cn } from "@/lib/utils"

export function NewSessionDialog({
  variant = "default",
  label,
}: {
  variant?: "default" | "sidebar"
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const [model, setModel] = useState("")
  const [modelOpen, setModelOpen] = useState(false)

  const { data: config } = useConfig()
  const { data: models } = useModels()
  const createSession = useCreateSession()
  const setActiveSession = useUIStore((s) => s.setActiveSession)
  const selectedModel = useUIStore((s) => s.selectedModel)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  const effectiveModel = model || selectedModel || config?.default_model || ""

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    try {
      const session = await createSession.mutateAsync({
        model: model.trim() || selectedModel || null,
      })
      setActiveSession(session.id)
      setOpen(false)
      resetForm()
    } catch {
      // error handled by mutation
    }
  }

  const resetForm = () => {
    setModel("")
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {variant === "sidebar" ? (
          <button className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors">
            <Plus className="h-3.5 w-3.5" />
            <span>{label ?? "New Project"}</span>
          </button>
        ) : (
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            {label ?? "New Session"}
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md gap-0 p-0 overflow-hidden">
        <div className="px-6 pt-6 pb-4">
          <DialogHeader className="space-y-1">
            <DialogTitle className="text-lg font-semibold">New Session</DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground/80">
              Configure a workspace for the agent.
            </DialogDescription>
          </DialogHeader>
          <p className="mt-3 text-xs text-muted-foreground">
            {isAuthenticated ? "This session will be saved to your account." : "Guest sessions are temporary."}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="px-6 pb-6 space-y-5">
          {/* Model Selector */}
          <div className="space-y-1.5">
            <Popover open={modelOpen} onOpenChange={setModelOpen}>
              <PopoverTrigger asChild>
                <button
                  type="button"
                  className={cn(
                    "flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 text-sm transition-colors",
                    "hover:bg-accent/50 focus:outline-none focus:ring-1 focus:ring-ring/40",
                    !effectiveModel && "text-muted-foreground/60",
                  )}
                >
                  <span className="truncate">
                    {effectiveModel ? _displayName(effectiveModel) : "Select model..."}
                  </span>
                  <ChevronDown className={cn("h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform", modelOpen && "rotate-180")} />
                </button>
              </PopoverTrigger>
              <PopoverContent
                side="bottom"
                align="start"
                className="w-[var(--radix-popover-trigger-width)] max-h-[280px] overflow-y-auto p-1 rounded-lg"
              >
                {models && models.length > 0 ? (
                  models.map((m) => {
                    const active = m.name === effectiveModel
                    return (
                      <button
                        key={m.name}
                        type="button"
                        onClick={() => {
                          setModel(m.name)
                          setModelOpen(false)
                        }}
                        className={cn(
                          "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
                          active ? "bg-accent" : "hover:bg-accent/50",
                        )}
                      >
                        <Cpu className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        <div className="flex-1 text-left min-w-0">
                          <div className="font-medium truncate text-[13px]">{_displayName(m.name)}</div>
                          <div className="text-[11px] text-muted-foreground/70 truncate">
                            {[m.parameter_size, m.family, m.quantization_level].filter(Boolean).join(" · ") || m.name}
                          </div>
                        </div>
                        {active && <Check className="h-3.5 w-3.5 shrink-0 text-foreground" />}
                      </button>
                    )
                  })
                ) : (
                  <p className="px-3 py-2 text-xs text-muted-foreground">No models found</p>
                )}
              </PopoverContent>
            </Popover>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={createSession.isPending}
              className="px-5"
            >
              {createSession.isPending ? "Creating..." : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Shorten a model name like "qwen2.5-coder:7b-instruct-q4_K_M" → "qwen2.5-coder 7b" */
function _displayName(name: string): string {
  if (!name) return "Model"
  const [base, tag] = name.split(":")
  const sizeMatch = tag?.match(/^(\d+\.?\d*[bBmM])/i)
  const size = sizeMatch?.[1]?.toUpperCase() ?? ""
  return size ? `${base} ${size}` : base
}
