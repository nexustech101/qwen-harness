import { X, FileText, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { api } from "@/api/client"
import { useUploadStore, type StagedUpload } from "@/stores/uploads"

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function isImage(mime: string): boolean {
  return mime.startsWith("image/")
}

function Thumbnail({ upload, sessionId }: { upload: StagedUpload; sessionId: string }) {
  if (upload.uploading) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-muted">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (isImage(upload.mime_type)) {
    const src =
      upload.localPreviewUrl ??
      (upload.thumbnail_url
        ? api.uploads.thumbnailUrl(sessionId, upload.id)
        : api.uploads.fileUrl(sessionId, upload.id))
    return (
      <img
        src={src}
        alt={upload.filename}
        className="h-full w-full object-cover"
        draggable={false}
      />
    )
  }

  // Non-image file icon
  const ext = upload.filename.split(".").pop()?.toUpperCase() ?? ""
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-0.5 bg-muted">
      <FileText className="h-5 w-5 text-muted-foreground" />
      {ext && <span className="text-[9px] font-bold text-muted-foreground">{ext}</span>}
    </div>
  )
}

export function AttachmentPreview({ sessionId }: { sessionId: string }) {
  const staged = useUploadStore((s) => s.staged)
  const remove = useUploadStore((s) => s.remove)

  if (staged.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2 px-1 pb-2">
      {staged.map((upload) => (
        <div
          key={upload.id}
          className={cn(
            "group relative h-16 w-16 rounded-lg border overflow-hidden",
            "transition-colors hover:border-foreground/30",
            upload.error && "border-red-500/50",
          )}
          title={`${upload.filename} (${formatSize(upload.size)})`}
        >
          <Thumbnail upload={upload} sessionId={sessionId} />

          {/* Remove button */}
          <button
            onClick={() => remove(sessionId, upload.id)}
            className={cn(
              "absolute -right-1 -top-1 z-10 flex h-5 w-5 items-center justify-center",
              "rounded-full bg-background border shadow-sm",
              "opacity-0 group-hover:opacity-100 transition-opacity",
              "hover:bg-destructive hover:text-destructive-foreground",
            )}
            aria-label={`Remove ${upload.filename}`}
          >
            <X className="h-3 w-3" />
          </button>

          {/* Filename label */}
          <div className="absolute inset-x-0 bottom-0 bg-black/60 px-1 py-0.5 text-center">
            <span className="block truncate text-[9px] text-white leading-tight">
              {upload.filename}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
