import { useState, useRef, useCallback } from "react"
import type { DragEvent } from "react"
import { Send, ChevronUp, Check, Cpu, Paperclip } from "lucide-react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useCreateSession, useSendPrompt, useSession, useModels, useConfig } from "@/api/queries"
import { api } from "@/api/client"
import { useUIStore } from "@/stores/ui"
import { useWSStore } from "@/stores/websocket"
import { useUploadStore } from "@/stores/uploads"
import { AttachmentPreview } from "./AttachmentPreview"
import { cn } from "@/lib/utils"
import { toast } from "sonner"

export function PromptInput({ centered }: { centered?: boolean }) {
  const [prompt, setPrompt] = useState("")
  const [modelOpen, setModelOpen] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const activeSessionId = useUIStore((s) => s.activeSessionId)
  const selectedModel = useUIStore((s) => s.selectedModel)
  const setSelectedModel = useUIStore((s) => s.setSelectedModel)
  const setActiveSession = useUIStore((s) => s.setActiveSession)
  const { data: session } = useSession(activeSessionId)
  const { data: config } = useConfig()
  const { data: models } = useModels()
  const sendPrompt = useSendPrompt(activeSessionId ?? "")
  const createSession = useCreateSession()
  const addUserMessage = useWSStore((s) => s.addUserMessage)
  const clearChat = useWSStore((s) => s.clearChat)
  const cancel = useWSStore((s) => s.cancel)
  const stageFiles = useUploadStore((s) => s.stageFiles)
  const staged = useUploadStore((s) => s.staged)
  const getAttachmentIds = useUploadStore((s) => s.getAttachmentIds)
  const clearAll = useUploadStore((s) => s.clearAll)
  const isRunning = session?.status === "running"

  /** Ensure a session exists (creates one if needed) and returns its id. */
  const ensureSession = useCallback(async (): Promise<string | null> => {
    if (activeSessionId) return activeSessionId
    try {
      const sess = await createSession.mutateAsync({
        chat_only: true,
        project_root: ".",
        title: "New chat",
        model: selectedModel || null,
      })
      setActiveSession(sess.id)
      return sess.id
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create session")
      return null
    }
  }, [activeSessionId, createSession, selectedModel, setActiveSession])

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const fileArr = Array.from(files)
    if (!fileArr.length) return
    const sessionId = await ensureSession()
    if (!sessionId) return
    try {
      await stageFiles(sessionId, fileArr)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed")
    }
  }, [ensureSession, stageFiles])

  const handleSend = useCallback(async () => {
    const text = prompt.trim()
    if (!text || isRunning || createSession.isPending || sendPrompt.isPending) return

    const attachmentIds = getAttachmentIds()
    // Snapshot attachment refs for the user bubble before clearing
    const attachmentRefs = staged
      .filter((u) => !u.uploading && !u.id.startsWith("pending-"))
      .map((u) => ({ filename: u.filename, mime_type: u.mime_type, size: u.size }))

    const body = { prompt: text, attachment_ids: attachmentIds }

    try {
      if (activeSessionId) {
        addUserMessage(text, attachmentRefs.length ? attachmentRefs : undefined)
        sendPrompt.mutate(body)
        clearAll()
      } else {
        clearChat()
        clearAll()
        const sess = await createSession.mutateAsync({
          chat_only: true,
          project_root: ".",
          title: text.slice(0, 60) || "New chat",
          model: selectedModel || null,
        })
        setActiveSession(sess.id)
        setTimeout(() => {
          addUserMessage(text)
          api.sessions.sendPrompt(sess.id, { prompt: text }).catch((err) => {
            toast.error(err instanceof Error ? err.message : "Failed to send prompt")
          })
        }, 0)
      }
      setPrompt("")
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto"
        textareaRef.current.focus()
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to start chat")
    }
  }, [prompt, activeSessionId, isRunning, createSession, sendPrompt, addUserMessage, clearChat, selectedModel, setActiveSession, getAttachmentIds, staged, clearAll])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      void handleSend()
    }
  }

  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = Array.from(e.clipboardData.items)
    const imageItems = items.filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    if (!imageItems.length) return
    e.preventDefault()
    const files = imageItems
      .map((item) => item.getAsFile())
      .filter((f): f is File => f !== null)
    if (files.length) void handleFiles(files)
  }, [handleFiles])

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    if (e.dataTransfer.types.includes("Files")) {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(true)
    }
  }

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    // Only clear when leaving the outer container (not crossing child elements)
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragging(false)
    }
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    void handleFiles(e.dataTransfer.files)
  }

  return (
    <div className={cn(centered ? "w-full" : "bg-background p-3")}>
      <div className={cn(centered ? "w-full" : "mx-auto max-w-2xl")}>
        <div
          className={cn(
            "relative rounded-2xl border bg-card transition-all",
            isDragging
              ? "border-ring/60 ring-2 ring-ring/30"
              : "border-border/30 focus-within:ring-1 focus-within:ring-ring/40",
          )}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Drag overlay */}
          {isDragging && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-card/80 backdrop-blur-sm">
              <div className="flex flex-col items-center gap-1.5 text-muted-foreground">
                <Paperclip className="h-6 w-6" />
                <span className="text-sm font-medium">Drop files to attach</span>
              </div>
            </div>
          )}

          {/* Attachment thumbnails (shown above textarea) */}
          {activeSessionId && staged.length > 0 && (
            <div className="px-3 pt-3">
              <AttachmentPreview sessionId={activeSessionId} />
            </div>
          )}

          <div className="flex items-end gap-1 px-3 pt-3 pb-2">
            {/* Attach button */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="mb-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-muted-foreground/60 transition-colors hover:bg-accent hover:text-muted-foreground"
              title="Attach files"
              disabled={isRunning}
            >
              <Paperclip className="h-4 w-4" />
            </button>

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="sr-only"
              onChange={(e) => {
                if (e.target.files?.length) void handleFiles(e.target.files)
                e.target.value = ""
              }}
            />

            {/* Text input */}
            <textarea
              ref={textareaRef}
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value)
                e.target.style.height = "auto"
                e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`
              }}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder="How can I help you today?"
              rows={1}
              className="flex-1 resize-none bg-transparent py-2 text-sm outline-none placeholder:text-muted-foreground/60 max-h-[200px]"
              disabled={isRunning}
            />

            {/* Model selector */}
            <Popover open={modelOpen} onOpenChange={setModelOpen}>
              <PopoverTrigger asChild>
                <button
                  className="mb-1 flex shrink-0 items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium border border-border/60 hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                  title="Select model"
                >
                  <span className="max-w-[120px] truncate">
                    {_displayName(selectedModel ?? config?.model ?? "")}
                  </span>
                  <ChevronUp className={cn("h-3 w-3 transition-transform", modelOpen && "rotate-180")} />
                </button>
              </PopoverTrigger>
              <PopoverContent side="bottom" align="end" className="w-72 max-h-[300px] overflow-y-auto p-1.5 rounded-xl">
                {models && models.length > 0 ? (
                  models.map((m) => {
                    const active = m.name === (selectedModel ?? config?.model)
                    return (
                      <button
                        key={m.name}
                        onClick={() => { setSelectedModel(m.name); setModelOpen(false) }}
                        className={cn("flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors", active ? "bg-accent" : "hover:bg-accent")}
                      >
                        <Cpu className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <div className="flex-1 text-left min-w-0">
                          <div className="font-medium truncate">{_displayName(m.name)}</div>
                          <div className="text-xs text-muted-foreground">
                            {[m.parameter_size, m.family, m.quantization_level].filter(Boolean).join(" · ") || m.name}
                          </div>
                        </div>
                        {active && <Check className="h-4 w-4 shrink-0 text-foreground" />}
                      </button>
                    )
                  })
                ) : (
                  <p className="px-3 py-2 text-xs text-muted-foreground">No models available</p>
                )}
              </PopoverContent>
            </Popover>

            {/* Send / Cancel */}
            <div className="mb-1">
              {isRunning ? (
                <button
                  onClick={cancel}
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-muted hover:bg-accent transition-colors"
                  title="Stop generating"
                >
                  <span className="h-3 w-3 rounded-sm bg-foreground/70" />
                </button>
              ) : (
                <button
                  onClick={() => void handleSend()}
                  disabled={!prompt.trim() || createSession.isPending || sendPrompt.isPending}
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-full transition-colors",
                    prompt.trim()
                      ? "bg-foreground text-background hover:bg-foreground/90"
                      : "bg-muted text-muted-foreground cursor-not-allowed",
                  )}
                  title="Send (Ctrl+Enter)"
                >
                  <Send className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>

        <div className={cn("mt-1.5 flex items-center", centered ? "justify-center" : "justify-end")}>
          <span className="text-[11px] text-muted-foreground/40">Ctrl+Enter to send</span>
        </div>
      </div>
    </div>
  )
}

function _displayName(name: string): string {
  if (!name) return "Model"
  const [base, tag] = name.split(":")
  const sizeMatch = tag?.match(/^(\d+\.?\d*[bBmM])/i)
  const size = sizeMatch?.[1]?.toUpperCase() ?? ""
  return size ? `${base} ${size}` : base
}
