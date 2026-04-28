import { create } from "zustand"
import { api } from "@/api/client"
import type { UploadMeta } from "@/api/types"

export interface StagedUpload extends UploadMeta {
  /** Local object URL for instant preview before server responds */
  localPreviewUrl?: string
  uploading?: boolean
  error?: string
}

interface UploadStore {
  staged: StagedUpload[]
  uploading: boolean
  /** Stage files via the backend upload endpoint */
  stageFiles: (sessionId: string, files: File[]) => Promise<void>
  /** Remove a single staged upload (also deletes server-side) */
  remove: (sessionId: string, uploadId: string) => void
  /** Clear all staged uploads (no server cleanup — backend cleans up after prompt) */
  clearAll: () => void
  /** Get all staged upload IDs for sending with prompt */
  getAttachmentIds: () => string[]
}

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB
const MAX_TOTAL_SIZE = 50 * 1024 * 1024 // 50 MB
const MAX_FILES = 10

const BLOCKED_EXTENSIONS = new Set([
  "exe", "dll", "bat", "cmd", "com", "msi", "scr", "pif", "vbs", "vbe",
  "js", "jse", "ws", "wsf", "wsc", "wsh", "ps1", "reg",
])

function validateFiles(files: File[], existingCount: number): string | null {
  if (existingCount + files.length > MAX_FILES) {
    return `Maximum ${MAX_FILES} attachments allowed`
  }
  let totalSize = 0
  for (const f of files) {
    if (f.size > MAX_FILE_SIZE) {
      return `"${f.name}" exceeds 10 MB limit`
    }
    totalSize += f.size
    const ext = f.name.split(".").pop()?.toLowerCase() ?? ""
    if (BLOCKED_EXTENSIONS.has(ext)) {
      return `"${f.name}" has a blocked file type`
    }
  }
  if (totalSize > MAX_TOTAL_SIZE) {
    return "Total upload size exceeds 50 MB"
  }
  return null
}

export const useUploadStore = create<UploadStore>((set, get) => ({
  staged: [],
  uploading: false,

  stageFiles: async (sessionId: string, files: File[]) => {
    const existing = get().staged
    const error = validateFiles(files, existing.length)
    if (error) {
      throw new Error(error)
    }

    // Create temporary local previews immediately
    const localPreviews: StagedUpload[] = files.map((f) => ({
      id: `pending-${crypto.randomUUID()}`,
      filename: f.name,
      mime_type: f.type,
      size: f.size,
      url: "",
      thumbnail_url: null,
      localPreviewUrl: f.type.startsWith("image/") ? URL.createObjectURL(f) : undefined,
      uploading: true,
    }))

    set((s) => ({ staged: [...s.staged, ...localPreviews], uploading: true }))

    try {
      const response = await api.uploads.stage(sessionId, files)
      // Replace pending items with server-confirmed metadata
      set((s) => {
        const withoutPending = s.staged.filter(
          (u) => !localPreviews.some((p) => p.id === u.id),
        )
        const confirmed: StagedUpload[] = response.uploads.map((u) => ({
          ...u,
          uploading: false,
        }))
        return { staged: [...withoutPending, ...confirmed], uploading: false }
      })
    } catch (err) {
      // Remove pending items on failure
      set((s) => ({
        staged: s.staged.filter((u) => !localPreviews.some((p) => p.id === u.id)),
        uploading: false,
      }))
      // Revoke object URLs
      for (const p of localPreviews) {
        if (p.localPreviewUrl) URL.revokeObjectURL(p.localPreviewUrl)
      }
      throw err
    }
  },

  remove: (sessionId: string, uploadId: string) => {
    set((s) => {
      const item = s.staged.find((u) => u.id === uploadId)
      if (item?.localPreviewUrl) URL.revokeObjectURL(item.localPreviewUrl)
      return { staged: s.staged.filter((u) => u.id !== uploadId) }
    })
    // Fire-and-forget server delete
    if (!uploadId.startsWith("pending-")) {
      api.uploads.delete(sessionId, uploadId).catch(() => {})
    }
  },

  clearAll: () => {
    const { staged } = get()
    for (const u of staged) {
      if (u.localPreviewUrl) URL.revokeObjectURL(u.localPreviewUrl)
    }
    set({ staged: [], uploading: false })
  },

  getAttachmentIds: () =>
    get()
      .staged.filter((u) => !u.uploading && !u.id.startsWith("pending-"))
      .map((u) => u.id),
}))
