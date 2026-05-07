import { FileCode } from "lucide-react"
import { useUIStore } from "@/stores/ui"

export function FileViewer() {
  const selectedFile = useUIStore((s) => s.selectedFile)

  if (!selectedFile) return null

  return (
    <div className="flex h-full items-center justify-center border-l text-sm text-muted-foreground">
      <div className="flex flex-col items-center gap-2">
        <FileCode className="h-8 w-8 opacity-20" />
        <p>File viewer unavailable</p>
      </div>
    </div>
  )
}
