import { useState, useCallback, useEffect } from "react"
import { Play, Clock, Save, ChevronDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Separator } from "@/components/ui/separator"
import { WorkflowCanvas } from "./WorkflowCanvas"
import { useWorkflow, useUpdateWorkflow, useExecuteWorkflow, useModels, useConfig } from "@/api/queries"
import { useUIStore } from "@/stores/ui"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import type { WorkflowDefinition, WorkflowStep, WorkflowEdge } from "@/api/types"

const INTERVAL_OPTIONS = [
  { label: "None", value: 0 },
  { label: "Every 15 min", value: 900 },
  { label: "Every 30 min", value: 1800 },
  { label: "Every hour", value: 3600 },
  { label: "Every 6 hours", value: 21600 },
  { label: "Every 24 hours", value: 86400 },
]

export function WorkflowView() {
  const activeWorkflowId = useUIStore((s) => s.activeWorkflowId)
  const setActiveSession = useUIStore((s) => s.setActiveSession)
  const setActiveView = useUIStore((s) => s.setActiveView)

  if (!activeWorkflowId) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <div className="text-center">
          <p className="text-sm">Select a workflow or create one</p>
          <p className="text-xs mt-1 opacity-60">Use the sidebar to manage workflows</p>
        </div>
      </div>
    )
  }

  return (
    <WorkflowEditor
      workflowId={activeWorkflowId}
      onExecuteSuccess={(sessionId) => {
        setActiveSession(sessionId)
        setActiveView("chat")
      }}
    />
  )
}

function WorkflowEditor({
  workflowId,
  onExecuteSuccess,
}: {
  workflowId: string
  onExecuteSuccess: (sessionId: string) => void
}) {
  const { data: wf, isLoading } = useWorkflow(workflowId)
  const updateWorkflow = useUpdateWorkflow()
  const executeWorkflow = useExecuteWorkflow()
  const { data: models } = useModels()
  const { data: config } = useConfig()

  const [name, setName] = useState("")
  const [steps, setSteps] = useState<WorkflowStep[]>([])
  const [edges, setEdges] = useState<WorkflowEdge[]>([])
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [intervalSeconds, setIntervalSeconds] = useState(0)
  const [isDirty, setIsDirty] = useState(false)
  const [scheduleOpen, setScheduleOpen] = useState(false)

  // Hydrate from loaded workflow
  useEffect(() => {
    if (!wf) return
    setName(wf.name)
    setSteps(wf.definition.steps ?? [])
    setEdges(wf.definition.edges ?? [])
    setIntervalSeconds(wf.definition.interval_seconds ?? 0)
    setIsDirty(false)
  }, [wf])

  const markDirty = useCallback(() => setIsDirty(true), [])

  const handleStepsChange = useCallback((s: WorkflowStep[]) => { setSteps(s); markDirty() }, [markDirty])
  const handleEdgesChange = useCallback((e: WorkflowEdge[]) => { setEdges(e); markDirty() }, [markDirty])

  const handleSave = useCallback(async () => {
    if (!wf) return
    const definition: WorkflowDefinition = {
      steps,
      edges,
      interval_seconds: intervalSeconds || null,
    }
    try {
      await updateWorkflow.mutateAsync({ id: workflowId, name, description: wf.description, definition, enabled: wf.enabled })
      setIsDirty(false)
      toast.success("Workflow saved")
    } catch {
      toast.error("Failed to save workflow")
    }
  }, [wf, workflowId, name, steps, edges, intervalSeconds, updateWorkflow])

  const handleExecute = useCallback(async () => {
    // Auto-save first
    if (isDirty) await handleSave()
    try {
      const result = await executeWorkflow.mutateAsync(workflowId)
      toast.success("Workflow started")
      onExecuteSuccess(result.session_id)
    } catch {
      toast.error("Failed to execute workflow")
    }
  }, [isDirty, handleSave, executeWorkflow, workflowId, onExecuteSuccess])

  const selectedStep = steps.find((s) => s.id === selectedStepId) ?? null

  const updateSelectedStep = useCallback(
    (patch: Partial<WorkflowStep>) => {
      if (!selectedStep) return
      setSteps((prev) => prev.map((s) => (s.id === selectedStep.id ? { ...s, ...patch } : s)))
      markDirty()
    },
    [selectedStep, markDirty],
  )

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
        Loading workflow…
      </div>
    )
  }

  const currentIntervalLabel =
    INTERVAL_OPTIONS.find((o) => o.value === intervalSeconds)?.label ?? "Schedule"

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-3 border-b border-border/30 px-4 py-2.5">
        <input
          className="flex-1 bg-transparent text-sm font-medium outline-none placeholder:text-muted-foreground/50 min-w-0"
          value={name}
          onChange={(e) => { setName(e.target.value); markDirty() }}
          placeholder="Workflow name"
        />

        {/* Schedule dropdown */}
        <div className="relative">
          <button
            onClick={() => setScheduleOpen(!scheduleOpen)}
            className="flex items-center gap-1.5 rounded-md border border-border/50 px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent transition-colors"
          >
            <Clock className="h-3.5 w-3.5" />
            {currentIntervalLabel}
            <ChevronDown className={cn("h-3 w-3 transition-transform", scheduleOpen && "rotate-180")} />
          </button>
          {scheduleOpen && (
            <div className="absolute right-0 top-full z-20 mt-1 w-48 rounded-xl border border-border bg-card shadow-lg py-1">
              {INTERVAL_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => {
                    setIntervalSeconds(opt.value)
                    setScheduleOpen(false)
                    markDirty()
                  }}
                  className={cn(
                    "flex w-full items-center px-3 py-2 text-sm transition-colors hover:bg-accent",
                    intervalSeconds === opt.value && "text-primary",
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={handleSave}
          disabled={!isDirty || updateWorkflow.isPending}
          className="gap-1.5"
        >
          <Save className="h-3.5 w-3.5" />
          {updateWorkflow.isPending ? "Saving…" : "Save"}
        </Button>

        <Button
          size="sm"
          onClick={() => void handleExecute()}
          disabled={executeWorkflow.isPending}
          className="gap-1.5"
        >
          <Play className="h-3.5 w-3.5" />
          {executeWorkflow.isPending ? "Starting…" : "Execute"}
        </Button>
      </div>

      {/* Canvas + step editor */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-hidden">
          <WorkflowCanvas
            steps={steps}
            edges={edges}
            onStepsChange={handleStepsChange}
            onEdgesChange={handleEdgesChange}
            onSelectStep={setSelectedStepId}
            selectedStepId={selectedStepId}
          />
        </div>

        {/* Step editor panel */}
        {selectedStep && (
          <div className="w-72 shrink-0 border-l border-border/30 overflow-y-auto bg-card/30 p-4 space-y-4">
            <div>
              <h3 className="text-sm font-semibold mb-3">Edit Step</h3>
              <Separator className="mb-4" />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="step-title">Title</Label>
              <Input
                id="step-title"
                value={selectedStep.title}
                onChange={(e) => updateSelectedStep({ title: e.target.value })}
                placeholder="Step title"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="step-prompt">Prompt</Label>
              <Textarea
                id="step-prompt"
                value={selectedStep.prompt}
                onChange={(e) => updateSelectedStep({ prompt: e.target.value })}
                placeholder="Define the prompt for this step…"
                rows={8}
                className="resize-none text-sm"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="step-model">Model (optional)</Label>
              <select
                id="step-model"
                value={selectedStep.model ?? ""}
                onChange={(e) => updateSelectedStep({ model: e.target.value || undefined })}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="">Default ({config?.model ?? "—"})</option>
                {models?.map((m) => (
                  <option key={m.name} value={m.name}>{m.name}</option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
