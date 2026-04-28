import { useState, useRef, useCallback } from "react"
import { Send, Zap, Paperclip, Upload, Clock, FileText, ImageIcon, ChevronRight, ChevronUp, Check, Cpu } from "lucide-react"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
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
  const [direct, setDirect] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [attachOpen, setAttachOpen] = useState(false)
  const [modelOpen, setModelOpen] = useState(false)
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
  const isRunning = session?.status === "running"

  const stageFiles = useUploadStore((s) => s.stageFiles)
  const clearUploads = useUploadStore((s) => s.clearAll)
  const getAttachmentIds = useUploadStore((s) => s.getAttachmentIds)
  const uploading = useUploadStore((s) => s.uploading)
  const stagedCount = useUploadStore((s) => s.staged.length)

  const handleUpload = useCallback(
    async (files: File[]) => {
      if (!activeSessionId || files.length === 0) return
      try {
        await stageFiles(activeSessionId, files)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Upload failed")
      }
    },
    [activeSessionId, stageFiles],
  )

  const handleSend = useCallback(async () => {
    const text = prompt.trim()
    if (!text || isRunning || uploading || createSession.isPending || sendPrompt.isPending) return
    const attachments = getAttachmentIds()
    const body = { prompt: text, direct, attachments: attachments.length > 0 ? attachments : undefined }

    try {
      if (activeSessionId) {
        addUserMessage(text)
        sendPrompt.mutate(body, { onSettled: () => clearUploads() })
      } else {
        clearChat()
        const session = await createSession.mutateAsync({
          chat_only: true,
          project_root: ".",
          title: text.slice(0, 60) || "New chat",
          model: selectedModel || null,
        })
        setActiveSession(session.id)
        setTimeout(() => {
          addUserMessage(text)
          api.sessions
            .sendPrompt(session.id, body)
            .catch((error) => {
              toast.error(error instanceof Error ? error.message : "Failed to send prompt")
            })
            .finally(() => clearUploads())
        }, 0)
      }
      setPrompt("")
      textareaRef.current?.focus()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to start chat")
    }
  }, [
    prompt,
    activeSessionId,
    isRunning,
    uploading,
    createSession,
    sendPrompt,
    getAttachmentIds,
    direct,
    addUserMessage,
    clearUploads,
    clearChat,
    selectedModel,
    setActiveSession,
  ])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSend()
    }
  }

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const items = e.clipboardData?.items
      if (!items) return
      const files: File[] = []
      for (const item of items) {
        if (item.kind === "file") {
          const file = item.getAsFile()
          if (file) files.push(file)
        }
      }
      if (files.length > 0) {
        e.preventDefault()
        handleUpload(files)
      }
    },
    [handleUpload],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const files = Array.from(e.dataTransfer.files)
      if (files.length > 0) handleUpload(files)
    },
    [handleUpload],
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
  }, [])

  const noSession = !activeSessionId

  return (
    <div className={cn(centered ? "w-full" : "bg-background p-3")}>
      <div className={cn(centered ? "w-full" : "mx-auto max-w-2xl")}>
        {/* Attachment thumbnails */}
        {activeSessionId && <AttachmentPreview sessionId={activeSessionId} />}

        {/* Grok-style input bar */}
        <div
          className={cn(
            "relative rounded-2xl border border-border/30 bg-card transition-all",
            "focus-within:ring-1 focus-within:ring-ring/40",
            dragOver && "ring-2 ring-blue-400/60 bg-blue-500/5",
          )}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
        >
          {dragOver && (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-blue-500/10 border-2 border-dashed border-blue-400/40 pointer-events-none">
              <span className="text-sm text-blue-400 font-medium">Drop files here</span>
            </div>
          )}

          <div className="flex items-end gap-1 px-3 pt-3 pb-2">
            {/* Attachment button with popover */}
            <Popover open={attachOpen} onOpenChange={setAttachOpen}>
              <PopoverTrigger asChild>
                <button
                  className={cn(
                    "mb-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors",
                    "text-muted-foreground hover:text-foreground hover:bg-accent",
                    stagedCount > 0 && "text-blue-400",
                  )}
                  disabled={isRunning || noSession}
                  title={noSession ? "Send a first message before attaching files" : "Attach files"}
                >
                  <Paperclip className="h-4 w-4" />
                  {stagedCount > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-blue-500 text-[9px] text-white font-bold">
                      {stagedCount}
                    </span>
                  )}
                </button>
              </PopoverTrigger>
              <PopoverContent
                side="bottom"
                align="start"
                className="w-56 max-h-[300px] overflow-y-auto p-1.5 rounded-xl"
              >
                <button
                  onClick={() => {
                    fileInputRef.current?.click()
                    setAttachOpen(false)
                  }}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm hover:bg-accent transition-colors"
                >
                  <Upload className="h-4 w-4 text-muted-foreground" />
                  <span>Upload a file</span>
                </button>
                <div className="my-1 border-t" />
                <div className="px-3 py-1.5">
                  <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    Recent
                    <ChevronRight className="h-3 w-3 ml-auto" />
                  </span>
                </div>
                {stagedCount > 0 ? (
                  useUploadStore.getState().staged.slice(0, 5).map((u) => (
                    <button
                      key={u.id}
                      className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-accent transition-colors"
                      onClick={() => setAttachOpen(false)}
                    >
                      {u.mime_type.startsWith("image/") ? (
                        <ImageIcon className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <FileText className="h-4 w-4 text-muted-foreground" />
                      )}
                      <span className="truncate">{u.filename}</span>
                    </button>
                  ))
                ) : (
                  <p className="px-3 py-2 text-xs text-muted-foreground">No recent files</p>
                )}
              </PopoverContent>
            </Popover>

            {/* Text input */}
            <textarea
              ref={textareaRef}
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value)
                // Auto-resize
                e.target.style.height = "auto"
                e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`
              }}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder="How can I help you today?"
              rows={1}
              className={cn(
                "flex-1 resize-none bg-transparent py-2 text-sm outline-none",
                "placeholder:text-muted-foreground/60",
                "max-h-[200px]",
              )}
              disabled={isRunning}
            />

            {/* Model selector */}
            <Popover open={modelOpen} onOpenChange={setModelOpen}>
              <PopoverTrigger asChild>
                <button
                  className={cn(
                    "mb-1 flex shrink-0 items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                    "border border-border/60 hover:bg-accent text-muted-foreground hover:text-foreground",
                  )}
                  title="Select model"
                >
                  <span className="max-w-[120px] truncate">
                    {_displayName(selectedModel ?? config?.model ?? "")}
                  </span>
                  <ChevronUp className={cn("h-3 w-3 transition-transform", modelOpen && "rotate-180")} />
                </button>
              </PopoverTrigger>
              <PopoverContent
                side="bottom"
                align="end"
                className="w-72 max-h-[300px] overflow-y-auto p-1.5 rounded-xl"
              >
                {models && models.length > 0 ? (
                  models.map((m) => {
                    const active = m.name === (selectedModel ?? config?.model)
                    return (
                      <button
                        key={m.name}
                        onClick={() => {
                          setSelectedModel(m.name)
                          setModelOpen(false)
                        }}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                          active ? "bg-accent" : "hover:bg-accent",
                        )}
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
            <div className="mb-1 flex items-center gap-1">
              {isRunning ? (
                <button
                  onClick={cancel}
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-muted hover:bg-accent transition-colors group"
                  title="Stop generating"
                >
                  <span className="flex items-center gap-[2px]">
                    <span className="h-1 w-1 rounded-full bg-muted-foreground group-hover:bg-foreground animate-[typing-dot_1.4s_ease-in-out_infinite]" />
                    <span className="h-1 w-1 rounded-full bg-muted-foreground group-hover:bg-foreground animate-[typing-dot_1.4s_ease-in-out_0.2s_infinite]" />
                    <span className="h-1 w-1 rounded-full bg-muted-foreground group-hover:bg-foreground animate-[typing-dot_1.4s_ease-in-out_0.4s_infinite]" />
                  </span>
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  disabled={!prompt.trim() || uploading || createSession.isPending || sendPrompt.isPending}
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-full transition-colors",
                    prompt.trim() && !uploading
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

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? [])
            if (files.length > 0) handleUpload(files)
            e.target.value = ""
          }}
        />

        {/* Options bar */}
        <div className={cn("mt-2 flex items-center gap-3", centered && "justify-center")}>
          <div className="flex items-center gap-1.5">
            <Switch id="direct" checked={direct} onCheckedChange={setDirect} />
            <Label htmlFor="direct" className="text-xs text-muted-foreground flex items-center gap-1">
              <Zap className="h-3 w-3" />
              Direct mode
            </Label>
          </div>
          <span className="text-xs text-muted-foreground">Ctrl+Enter to send</span>
        </div>
      </div>
    </div>
  )
}

/** Shorten a model name like "qwen2.5-coder:7b-instruct-q4_K_M" → "qwen2.5-coder 7b" */
function _displayName(name: string): string {
  if (!name) return "Model"
  // Split on ":" to get base and tag
  const [base, tag] = name.split(":")
  // Extract size from tag (e.g. "7b", "14b", "70b")
  const sizeMatch = tag?.match(/^(\d+\.?\d*[bBmM])/i)
  const size = sizeMatch?.[1]?.toUpperCase() ?? ""
  return size ? `${base} ${size}` : base
}
