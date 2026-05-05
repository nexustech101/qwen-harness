import { useCallback, useRef, useState } from "react"
import { Plus, X } from "lucide-react"
import { cn } from "@/lib/utils"
import type { WorkflowStep, WorkflowEdge } from "@/api/types"

const NODE_W = 220
const NODE_H = 84
const GRID_SIZE = 24

interface CanvasProps {
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
  onStepsChange: (steps: WorkflowStep[]) => void
  onEdgesChange: (edges: WorkflowEdge[]) => void
  onSelectStep: (id: string | null) => void
  selectedStepId: string | null
}

type DragState =
  | { kind: "none" }
  | { kind: "node"; stepId: string; startMouseX: number; startMouseY: number; startNodeX: number; startNodeY: number }
  | { kind: "pan"; startX: number; startY: number; startOffsetX: number; startOffsetY: number }
  | { kind: "connecting"; fromStepId: string; fromSide: "output" }

function snapToGrid(val: number) {
  return Math.round(val / GRID_SIZE) * GRID_SIZE
}

function newStepId() {
  return `step_${Date.now().toString(36)}`
}

function bezierPath(x1: number, y1: number, x2: number, y2: number): string {
  const cx = (x1 + x2) / 2
  return `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`
}

export function WorkflowCanvas({
  steps,
  edges,
  onStepsChange,
  onEdgesChange,
  onSelectStep,
  selectedStepId,
}: CanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [offset, setOffset] = useState({ x: 60, y: 60 })
  const [drag, setDrag] = useState<DragState>({ kind: "none" })
  const [connectingMousePos, setConnectingMousePos] = useState({ x: 0, y: 0 })

  // ── Pointer events ──────────────────────────────────────────────────────────
  const onMouseDownNode = useCallback(
    (e: React.MouseEvent, stepId: string) => {
      if (e.button !== 0) return
      e.stopPropagation()
      const step = steps.find((s) => s.id === stepId)
      if (!step) return
      onSelectStep(stepId)
      setDrag({
        kind: "node",
        stepId,
        startMouseX: e.clientX,
        startMouseY: e.clientY,
        startNodeX: step.x,
        startNodeY: step.y,
      })
    },
    [steps, onSelectStep],
  )

  const onMouseDownOutput = useCallback(
    (e: React.MouseEvent, stepId: string) => {
      e.stopPropagation()
      const rect = containerRef.current?.getBoundingClientRect()
      if (rect) setConnectingMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
      setDrag({ kind: "connecting", fromStepId: stepId, fromSide: "output" })
    },
    [],
  )

  const onMouseDownBackground = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return
      onSelectStep(null)
      setDrag({ kind: "pan", startX: e.clientX, startY: e.clientY, startOffsetX: offset.x, startOffsetY: offset.y })
    },
    [offset, onSelectStep],
  )

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (drag.kind === "node") {
        const dx = e.clientX - drag.startMouseX
        const dy = e.clientY - drag.startMouseY
        onStepsChange(
          steps.map((s) =>
            s.id === drag.stepId
              ? { ...s, x: snapToGrid(drag.startNodeX + dx), y: snapToGrid(drag.startNodeY + dy) }
              : s,
          ),
        )
      } else if (drag.kind === "pan") {
        setOffset({ x: drag.startOffsetX + e.clientX - drag.startX, y: drag.startOffsetY + e.clientY - drag.startY })
      } else if (drag.kind === "connecting") {
        const rect = containerRef.current?.getBoundingClientRect()
        if (rect) setConnectingMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
      }
    },
    [drag, steps, onStepsChange],
  )

  const onMouseUpNode = useCallback(
    (e: React.MouseEvent, targetId: string) => {
      if (drag.kind === "connecting") {
        e.stopPropagation()
        const from = drag.fromStepId
        if (from !== targetId) {
          // Avoid duplicate
          const exists = edges.some((ed) => ed.source === from && ed.target === targetId)
          if (!exists) {
            onEdgesChange([
              ...edges,
              { id: `e_${from}_${targetId}`, source: from, target: targetId },
            ])
          }
        }
      }
      setDrag({ kind: "none" })
    },
    [drag, edges, onEdgesChange],
  )

  const onMouseUp = useCallback(() => {
    setDrag({ kind: "none" })
  }, [])

  // ── Add step ────────────────────────────────────────────────────────────────
  const addStep = useCallback(() => {
    const id = newStepId()
    const x = snapToGrid(80 + steps.length * (NODE_W + 48))
    const y = snapToGrid(120)
    onStepsChange([
      ...steps,
      { id, type: "prompt", title: `Step ${steps.length + 1}`, prompt: "", x, y },
    ])
    onSelectStep(id)
  }, [steps, onStepsChange, onSelectStep])

  // ── Delete edge ─────────────────────────────────────────────────────────────
  const deleteEdge = useCallback(
    (id: string) => onEdgesChange(edges.filter((e) => e.id !== id)),
    [edges, onEdgesChange],
  )

  // ── Render helpers ───────────────────────────────────────────────────────────
  // Compute port positions in SVG (canvas) space
  const portPos = useCallback(
    (stepId: string, side: "input" | "output") => {
      const s = steps.find((st) => st.id === stepId)
      if (!s) return { x: 0, y: 0 }
      const sx = s.x + offset.x
      const sy = s.y + offset.y
      return side === "output"
        ? { x: sx + NODE_W, y: sy + NODE_H / 2 }
        : { x: sx, y: sy + NODE_H / 2 }
    },
    [steps, offset],
  )

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full overflow-hidden cursor-default"
      style={{
        background: `radial-gradient(circle, hsl(var(--border)/0.6) 1px, transparent 1px)`,
        backgroundSize: `${GRID_SIZE}px ${GRID_SIZE}px`,
        backgroundPosition: `${offset.x % GRID_SIZE}px ${offset.y % GRID_SIZE}px`,
      }}
      onMouseDown={onMouseDownBackground}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
    >
      {/* SVG overlay for edges */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 1 }}>
        {edges.map((edge) => {
          const from = portPos(edge.source, "output")
          const to = portPos(edge.target, "input")
          const midX = (from.x + to.x) / 2
          const midY = (from.y + to.y) / 2
          return (
            <g key={edge.id}>
              <path
                d={bezierPath(from.x, from.y, to.x, to.y)}
                fill="none"
                stroke="hsl(var(--border))"
                strokeWidth={2}
              />
              {/* Invisible thicker hit area */}
              <path
                d={bezierPath(from.x, from.y, to.x, to.y)}
                fill="none"
                stroke="transparent"
                strokeWidth={14}
                className="pointer-events-auto cursor-pointer"
                onClick={(e) => { e.stopPropagation(); deleteEdge(edge.id) }}
              />
              {/* Delete dot at midpoint */}
              <circle
                cx={midX}
                cy={midY}
                r={6}
                fill="hsl(var(--destructive))"
                className="pointer-events-auto cursor-pointer opacity-0 hover:opacity-100 transition-opacity"
                onClick={(e) => { e.stopPropagation(); deleteEdge(edge.id) }}
              />
            </g>
          )
        })}

        {/* Live connecting line */}
        {drag.kind === "connecting" && (() => {
          const from = portPos(drag.fromStepId, "output")
          return (
            <path
              d={bezierPath(from.x, from.y, connectingMousePos.x, connectingMousePos.y)}
              fill="none"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              strokeDasharray="6 4"
            />
          )
        })()}
      </svg>

      {/* Nodes */}
      {steps.map((step) => {
        const sx = step.x + offset.x
        const sy = step.y + offset.y
        const isSelected = step.id === selectedStepId
        return (
          <div
            key={step.id}
            style={{
              position: "absolute",
              left: sx,
              top: sy,
              width: NODE_W,
              height: NODE_H,
              zIndex: 2,
            }}
            className={cn(
              "rounded-xl border bg-card shadow-sm select-none",
              isSelected ? "border-primary ring-1 ring-primary/30" : "border-border/50 hover:border-border",
              drag.kind === "node" && drag.stepId === step.id && "shadow-lg",
            )}
            onMouseDown={(e) => onMouseDownNode(e, step.id)}
            onMouseUp={(e) => onMouseUpNode(e, step.id)}
          >
            {/* Input port */}
            <div
              className="absolute -left-2.5 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full border-2 border-border bg-background hover:border-primary transition-colors z-10 cursor-crosshair"
              onMouseDown={(e) => e.stopPropagation()}
              onMouseUp={(e) => onMouseUpNode(e, step.id)}
            />

            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-border/30 cursor-grab active:cursor-grabbing">
              <span className="text-xs font-medium truncate flex-1 pr-2">{step.title || "Step"}</span>
              <button
                className="h-4 w-4 shrink-0 flex items-center justify-center rounded text-muted-foreground/50 hover:text-destructive transition-colors"
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation()
                  onStepsChange(steps.filter((s) => s.id !== step.id))
                  onEdgesChange(edges.filter((ed) => ed.source !== step.id && ed.target !== step.id))
                  if (selectedStepId === step.id) onSelectStep(null)
                }}
              >
                <X className="h-3 w-3" />
              </button>
            </div>

            {/* Body: prompt preview */}
            <div className="px-3 py-2 text-xs text-muted-foreground/70 truncate leading-tight">
              {step.prompt ? step.prompt.slice(0, 60) + (step.prompt.length > 60 ? "…" : "") : (
                <span className="italic opacity-50">No prompt defined</span>
              )}
            </div>

            {/* Output port */}
            <div
              className="absolute -right-2.5 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full border-2 border-border bg-background hover:border-primary transition-colors z-10 cursor-crosshair"
              onMouseDown={(e) => { e.stopPropagation(); onMouseDownOutput(e, step.id) }}
            />
          </div>
        )
      })}

      {/* Add node button */}
      <button
        className="absolute bottom-5 right-5 z-10 flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-md hover:bg-primary/90 transition-colors"
        onClick={(e) => { e.stopPropagation(); addStep() }}
      >
        <Plus className="h-4 w-4" />
        Add Step
      </button>
    </div>
  )
}
