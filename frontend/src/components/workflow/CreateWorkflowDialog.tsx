import { useState } from "react"
import { Plus } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useCreateWorkflow } from "@/api/queries"
import { useUIStore } from "@/stores/ui"
import { toast } from "sonner"

export function CreateWorkflowDialog() {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")

  const createWorkflow = useCreateWorkflow()
  const setActiveWorkflow = useUIStore((s) => s.setActiveWorkflow)
  const setActiveView = useUIStore((s) => s.setActiveView)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    try {
      const wf = await createWorkflow.mutateAsync({
        name: name.trim(),
        description: description.trim(),
        definition: { steps: [], edges: [] },
        enabled: true,
      })
      setActiveWorkflow(wf.id)
      setActiveView("workflows")
      setOpen(false)
      setName("")
      setDescription("")
    } catch {
      toast.error("Failed to create workflow")
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button className="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors">
          <Plus className="h-3.5 w-3.5" />
          <span>New Workflow</span>
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>New Workflow</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label htmlFor="wf-name">Name</Label>
            <Input
              id="wf-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My workflow"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="wf-desc">Description</Label>
            <Input
              id="wf-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What does this workflow do?"
            />
          </div>
          <Button type="submit" className="w-full" disabled={!name.trim() || createWorkflow.isPending}>
            {createWorkflow.isPending ? "Creating..." : "Create"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
