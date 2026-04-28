# Qwen Coder — Frontend Specification

> Auto-generated project overview for agent consumption.
> Describes the frontend architecture, component tree, state management,
> backend integration layer, and styling conventions.

---

## 1. Technology Stack

| Layer            | Technology                          | Version  |
| ---------------- | ----------------------------------- | -------- |
| Runtime          | React                               | 19.2.4   |
| Language         | TypeScript (strict)                 | —        |
| Build tool       | Vite                                | —        |
| CSS              | Tailwind CSS v4                     | 4.2.2    |
| State management | Zustand                             | 5.0.12   |
| Server state     | TanStack React Query                | 5.96.2   |
| Markdown         | react-markdown + remark-gfm        | 10.1.0   |
| Syntax highlight | Shiki (`github-dark-default` theme) | 4.0.2    |
| UI primitives    | Radix UI (Dialog, Popover, Switch, Tooltip, ScrollArea, etc.) | — |
| Panels           | react-resizable-panels              | 4.9.0    |
| Icons            | lucide-react                        | 1.7.0    |
| Toasts           | sonner                              | 2.0.7    |
| Routing          | react-router-dom                    | 7.14.0   |

### Dev Server

```
frontend/vite.config.ts
- Dev port: 3000
- Path alias: `@` → `./src`
- Proxy: `/api/*` → `http://localhost:8100` (backend)
- WebSocket proxy included in the same `/api` rule
```

---

## 2. Project Structure

```
frontend/
├── index.html               # SPA entry point
├── vite.config.ts            # Build config, proxy, aliases
├── package.json              # Dependencies & scripts
├── tsconfig.json             # TypeScript config
│
└── src/
    ├── main.tsx              # React root, renders <App />
    ├── App.tsx               # QueryClient, TooltipProvider, Toaster, hooks, <AppLayout />
    ├── index.css             # Tailwind v4 import, CSS variables, prose-chat, animations
    │
    ├── api/                  # Backend integration layer
    │   ├── types.ts          # TypeScript interfaces mirroring backend API shapes
    │   ├── client.ts         # Typed fetch wrapper (`api.*` namespace)
    │   └── queries.ts        # TanStack Query hooks wrapping client calls
    │
    ├── stores/               # Zustand state stores
    │   ├── ui.ts             # UI state (theme, sidebar, panels, active session, model)
    │   ├── websocket.ts      # WebSocket connection, streaming buffer, chat items
    │   └── uploads.ts        # File upload staging, validation, preview
    │
    ├── hooks/
    │   ├── useWebSocket.ts   # Connects/disconnects WS on active session change
    │   └── useKeyboardShortcuts.ts  # Global keyboard shortcuts
    │
    ├── lib/
    │   └── utils.ts          # `cn()` (clsx+twMerge), formatTime, formatTimestamp, etc.
    │
    └── components/
        ├── ui/               # Radix-based primitives (button, input, dialog, popover, etc.)
        ├── branding/
        │   └── RobotLogo.tsx            # SVG robot head logo
        ├── layout/
        │   ├── AppLayout.tsx            # Root layout: TopNav + Sidebar + Main + StatusBar
        │   ├── Header.tsx               # TopNav: theme toggle + user avatar
        │   └── StatusBar.tsx            # Bottom bar: connection, session, token stats
        ├── sidebar/
        │   ├── Sidebar.tsx              # Logo, projects list, file tree
        │   ├── SessionList.tsx          # (Unused — sessions rendered inline in Sidebar)
        │   ├── FileTree.tsx             # Recursive file explorer with VS Code-style icons
        │   └── AgentList.tsx            # Sub-agent list with status badges
        ├── session/
        │   ├── NewSessionDialog.tsx     # Modal: create session (folder picker, model dropdown)
        │   └── SessionList.tsx          # Sidebar session history
        ├── chat/
        │   ├── ChatView.tsx             # Main chat area: welcome screen or messages + prompt
        │   ├── ChatMessage.tsx          # Message dispatcher + user/assistant/tool/error cards
        │   ├── StreamingMessage.tsx      # Live streaming indicator with collapsible raw output
        │   ├── CodeBlock.tsx            # Shiki-highlighted code with copy button
        │   ├── PromptInput.tsx          # Message input bar: text, attachments, model picker
        │   └── AttachmentPreview.tsx    # Thumbnail strip for staged file uploads
        ├── detail/
        │   └── AgentDetail.tsx          # Agent detail panel (currently not rendered in layout)
        └── file-viewer/
            └── FileViewer.tsx           # Full-file Shiki viewer with line numbers
```

---

## 3. Application Initialization

```
main.tsx → <App />
  └── QueryClientProvider (staleTime: 5s, retry: 1, no refetchOnWindowFocus)
      └── TooltipProvider
          ├── <AppInner />
          │   ├── useKeyboardShortcuts()  ← Global hotkeys
          │   ├── useWebSocket()          ← Auto-connect WS on session change
          │   └── <AppLayout />           ← Root visual layout
          └── <Toaster position="bottom-right" />
```

---

## 4. Layout Architecture

`AppLayout` is the root layout component. It renders:

```
┌──────────────────────────────────────────────────┐
│ TopNav (h-11) — theme toggle, user avatar        │
├──────────┬───────────────────────────────────────┤
│ Sidebar  │  Main Content                         │
│ (16%)    │  ChatView or FileViewer               │
│          │                                       │
│ - Logo   │  (if no file selected → ChatView)     │
│ - New    │  (if file selected → FileViewer)      │
│ - List   │                                       │
│ - Files  │                                       │
├──────────┴───────────────────────────────────────┤
│ StatusBar (h-6) — connection, model, stats       │
│ (only visible when a session is active)          │
└──────────────────────────────────────────────────┘
```

- **Sidebar**: Collapsible via `react-resizable-panels`. Stores collapsed state in `useUIStore.sidebarOpen`.
- **Main Content**: Shows `ChatView` by default. Switches to `FileViewer` when a file is selected in the sidebar file tree.
- **StatusBar**: Only rendered when `activeSessionId` is set. Shows connection status, session status, model, token stats, turn/tool/file counts.

---

## 5. State Management

### 5.1 `useUIStore` (Zustand)

Global UI state, persisted in memory only.

| Field             | Type                  | Purpose                                      |
| ----------------- | --------------------- | -------------------------------------------- |
| `theme`           | `"light" \| "dark"`   | Color scheme (applied via `.dark` class)     |
| `sidebarOpen`     | `boolean`             | Sidebar panel collapsed state                |
| `rightPanelOpen`  | `boolean`             | (Legacy — not rendered in layout)            |
| `selectedAgent`   | `string \| null`      | Currently selected agent name                |
| `selectedFile`    | `string \| null`      | File path open in FileViewer                 |
| `activeSessionId` | `string \| null`      | Current session ID — drives WS + all queries |
| `selectedModel`   | `string \| null`      | Model selected in the model picker popover   |

### 5.2 `useWSStore` (Zustand)

WebSocket connection + real-time chat state.

| Field              | Type                          | Purpose                                          |
| ------------------ | ----------------------------- | ------------------------------------------------ |
| `connected`        | `boolean`                     | WebSocket open state                             |
| `sessionId`        | `string \| null`              | Which session the WS is connected to             |
| `chatItems`        | `ChatItem[]`                  | All rendered messages/events in the chat          |
| `pendingToolCalls` | `Map<string, number>`         | Tracks tool calls awaiting results (key → index) |
| `streaming`        | `StreamingState \| null`      | Current streaming buffer state                   |
| `tokenStats`       | `TokenStats \| null`          | Token counts from last stream_end event          |

**Key methods:**
- `connect(sessionId)` — Opens WebSocket to `/api/sessions/{id}/ws`
- `disconnect()` — Closes WS, clears reconnect timers
- `cancel()` — Sends `{ type: "cancel" }` over WS
- `addUserMessage(content)` — Optimistically adds user message to chatItems
- `clearChat()` — Resets all chat state

**Streaming buffer:** Content deltas are accumulated in module-level `contentBuf`/`thinkingBuf` strings and flushed to React state via `requestAnimationFrame` loop for performance (avoids re-renders per token).

**Reconnection:** Exponential backoff up to 30s, max 5 attempts. If the WS never opens (`openedOnce = false`), clears the active session instead of retrying (indicates stale/deleted session).

### 5.3 `useUploadStore` (Zustand)

File upload staging for message attachments.

| Field      | Type              | Purpose                                    |
| ---------- | ----------------- | ------------------------------------------ |
| `staged`   | `StagedUpload[]`  | Uploads awaiting send (with local preview) |
| `uploading`| `boolean`         | Whether an upload is in progress           |

**Validation rules:** Max 10 files, max 10MB per file, max 50MB total, blocked executable extensions.

---

## 6. Backend Integration

### 6.1 API Client (`api/client.ts`)

Typed fetch wrapper. All calls go through `request<T>(path, options)` which:
- Prepends `VITE_API_URL` (defaults to same-origin)
- Sets `Content-Type: application/json`
- Throws `ApiError(status, body)` on non-2xx
- Returns parsed JSON typed as `T`

**Namespace structure:**

```typescript
api.health()                              // GET /api/health
api.config()                              // GET /api/config  
api.models()                              // GET /api/models
api.browseFolder()                        // GET /api/browse-folder

api.sessions.list()                       // GET /api/sessions
api.sessions.get(id)                      // GET /api/sessions/{id}
api.sessions.create(body)                 // POST /api/sessions
api.sessions.delete(id)                   // DELETE /api/sessions/{id}
api.sessions.messages(id)                 // GET /api/sessions/{id}/messages
api.sessions.sendPrompt(id, body)         // POST /api/sessions/{id}/messages

api.agents.list(sessionId)                // GET /api/sessions/{id}/agents
api.agents.get(sessionId, name)           // GET /api/sessions/{id}/agents/{name}
api.agents.prompt(sessionId, name, body)  // POST /api/sessions/{id}/agents/{name}/prompt

api.files.tree(sessionId)                 // GET /api/sessions/{id}/files
api.files.read(sessionId, filePath)       // GET /api/sessions/{id}/files/{path}

api.uploads.stage(sessionId, files)       // POST /api/sessions/{id}/uploads (FormData)
api.uploads.delete(sessionId, uploadId)   // DELETE /api/sessions/{id}/uploads/{uploadId}
api.uploads.thumbnailUrl(sessionId, id)   // URL string (for <img src>)
api.uploads.fileUrl(sessionId, id)        // URL string (for <img src>)
```

### 6.2 React Query Hooks (`api/queries.ts`)

| Hook                   | Key                             | Options                                                                 |
| ---------------------- | ------------------------------- | ----------------------------------------------------------------------- |
| `useHealth()`          | `["health"]`                    | Refetch every 30s, retry 1                                              |
| `useConfig()`          | `["config"]`                    | staleTime 5 min                                                         |
| `useModels()`          | `["models"]`                    | staleTime 1 min                                                         |
| `useSessions()`        | `["sessions"]`                  | Default                                                                 |
| `useSession(id)`       | `["session", id]`               | Enabled when `id` truthy. No retry on 404. Refetch 3s when `"running"`. |
| `useCreateSession()`   | mutation                        | Invalidates `["sessions"]` on success                                   |
| `useDeleteSession()`   | mutation                        | Invalidates `["sessions"]` on success                                   |
| `useMessages(id)`      | `["messages", id]`              | Enabled when `id` truthy                                                |
| `useSendPrompt(id)`    | mutation                        | Invalidates `["session", id]` on success                                |
| `useAgents(id)`        | `["agents", id]`                | Refetch every 5s                                                        |
| `useAgentDetail(s, n)` | `["agent", sessionId, name]`    | Refetch 2s when agent is "running"                                      |
| `useAgentPrompt(s, n)` | mutation                        | Direct mutationFn                                                       |
| `useFileTree(id)`      | `["files", id]`                 | Enabled when `id` truthy                                                |
| `useFileContent(s, p)` | `["file", sessionId, filePath]` | Enabled when both truthy                                                |

### 6.3 WebSocket Protocol

**Connection:** `ws://host/api/sessions/{sessionId}/ws`

**Inbound events** (server → client), all shaped as `WSEvent`:

```typescript
{ type: string, agent: string, data: Record<string, unknown>, timestamp: number }
```

| Event Type       | Data Fields                                                      | Handling                                                      |
| ---------------- | ---------------------------------------------------------------- | ------------------------------------------------------------- |
| `connected`      | —                                                                | Ignored                                                       |
| `ping`           | —                                                                | Ignored                                                       |
| `model_call`     | —                                                                | Ignored                                                       |
| `content_delta`  | `{ text: string }`                                               | Appended to streaming content buffer                          |
| `thinking_delta` | `{ text: string }`                                               | Appended to streaming thinking buffer                         |
| `stream_end`     | `{ eval_count, prompt_eval_count, eval_duration }`               | Clears streaming, captures token stats                        |
| `model_reply`    | —                                                                | Clears streaming if still present                             |
| `agent_start`    | `{ model: string, prompt: string }`                              | Adds agent_start ChatItem                                     |
| `turn_start`     | —                                                                | Suppressed                                                    |
| `reasoning`      | `{ text: string }`                                               | Adds reasoning ChatItem                                       |
| `tool_dispatch`  | `{ name: string, args: object }`                                 | Adds tool_call ChatItem, tracks in pendingToolCalls           |
| `tool_result`    | `{ name: string, data?: string, success: bool, error?: string }` | Updates matching tool_call ChatItem with result               |
| `response_text`  | `{ text: string }`                                               | Adds assistant ChatItem (final parsed response)               |
| `error`          | `{ error: string }`                                              | Adds error ChatItem                                           |
| `recovery`       | —                                                                | Suppressed                                                    |
| `agent_done`     | `{ reason: string, turns: number, elapsed: number }`             | Adds agent_done ChatItem                                      |
| `max_turns`      | `{ limit: number }`                                              | Adds error ChatItem with turn limit message                   |

**Outbound events** (client → server):

| Event          | Payload                                  |
| -------------- | ---------------------------------------- |
| `cancel`       | `{ type: "cancel", session_id: string }` |

**File tree refresh:** After any `tool_result` where the tool name is a file-modifying operation (`write_file`, `edit_file`, `delete_file`, `move_file`, `copy_file`, `create_directory`), a `file-tree-changed` custom DOM event is dispatched. The `FileTree` component listens for this to invalidate its query cache.

---

## 7. Key TypeScript Interfaces

### API Response Types

```typescript
interface SessionResponse {
  id: string; project_root: string; status: "idle" | "running" | "error"
  model: string; created_at: number; stats: SessionStats; agents: AgentSummary[]
}

interface SessionStats {
  total_turns: number; total_tool_calls: number; elapsed_seconds: number
  files_modified: string[]; message_count: number
}

interface OllamaModel {
  name: string; size: number; modified_at: string
  family: string | null; parameter_size: string | null; quantization_level: string | null
}

interface CreateSessionRequest {
  project_root: string; model?: string | null; planner_model?: string | null
  coder_model?: string | null; max_turns?: number | null
  use_dispatch?: boolean; async_dispatch?: boolean
}

interface PromptRequest { prompt: string; direct?: boolean; attachments?: string[] }
```

### Chat Item Types

```typescript
type ChatItem =
  | { type: "user"; content: string; timestamp: number }
  | { type: "assistant"; content: string; timestamp: number; metadata?: ResultMetadata }
  | { type: "reasoning"; content: string; agent: string; timestamp: number }
  | { type: "tool_call"; name: string; args: object; result?: string; success?: boolean; error?: string; agent: string; id: string; timestamp: number }
  | { type: "error"; content: string; agent: string; timestamp: number }
  | { type: "agent_start"; agent: string; model: string; goal: string; timestamp: number }
  | { type: "agent_done"; agent: string; reason: string; turns: number; elapsed: number; timestamp: number }
```

---

## 8. Component Details

### 8.1 ChatView

The main chat area. Two modes:
- **Empty state**: Centered welcome screen with RobotLogo, title, and centered PromptInput.
- **Active chat**: Scrollable message list + bottom-pinned PromptInput.

Messages are grouped by `groupChatItems()`:
- `"user"`, `"assistant"`, `"reasoning"`, `"error"` → rendered individually as `ChatMessage`
- `"tool_call"`, `"agent_start"`, `"agent_done"` → grouped into collapsible `ActivityGroup` sections

Auto-scroll tracks whether the user is within 100px of the bottom.

### 8.2 ChatMessage

Dispatcher component that renders the correct card based on `item.type`:

- **UserMessage**: Avatar circle ("U") + plain text content
- **AssistantMessage**: RobotLogo + Markdown rendered via `react-markdown` with custom code components → `CodeBlock` for fenced blocks, `InlineCode` for inline. Has copy button and metadata footer (turns, tools, time, files).
- **ReasoningBlock**: Collapsible "Thinking..." with monospace content
- **ToolCallCard**: Collapsible tool call showing name, file path hint, pending/success/error state, expandable args + result JSON
- **ErrorCard**: Red alert with error text
- **AgentStartCard / AgentDoneCard**: Subtle banners showing agent lifecycle

### 8.3 StreamingMessage

Shown during active model generation. All raw model output (content deltas + thinking deltas) are treated as internal process and collapsed into a single "Thinking..." collapsible section. Only the typing dots animation is visible by default. The final response arrives as a `response_text` event which creates a proper assistant ChatMessage.

### 8.4 PromptInput

Grok-style input bar with:
- **Attachment popover** (Paperclip icon): Upload files, shows recent staged files
- **Auto-resizing textarea**: Grows to max 200px
- **Model selector popover**: Lists Ollama models with name, parameter size, family, checkmark on active
- **Send/Cancel button**: Send icon when idle, typing dots animation when running (click to cancel)
- **Direct mode toggle**: Switch to bypass orchestrator
- **Drag-and-drop**: Files can be dropped on the input area
- **Paste support**: Images pasted from clipboard are auto-uploaded

### 8.5 NewSessionDialog

Modal dialog for creating new sessions:
- **Project Root**: Text input + folder browse button (calls `GET /api/browse-folder` which opens native OS tkinter dialog)
- **Model selector**: Popover dropdown listing all Ollama models (same style as PromptInput)
- **Max Turns**: Number input
- **Orchestrator toggle**: Switch to enable dispatch mode
- On submit: calls `api.sessions.create()`, sets active session, closes dialog

### 8.6 CodeBlock

Syntax-highlighted code block using Shiki:
- Header bar with language label + copy button
- Async Shiki highlight with `github-dark-default` theme
- Fallback to plain `<pre>` if language not supported
- `InlineCode` export for inline code spans (orange-tinted monospace)

### 8.7 FileViewer

Full-file viewer opened when a file is selected from the sidebar `FileTree`:
- Header: filename, line count badge, size badge, refresh + close buttons
- Shiki-highlighted content with line numbers (gutter)
- Listens for `file-tree-changed` events to indicate files may have changed

### 8.8 Sidebar

Left panel containing:
1. **Logo + collapse button** (Qwen Coder branding)
2. **Projects section**: `NewSessionDialog` trigger + session list
3. **Session list**: Clickable sessions with project name, model, status dot, delete button. Shows first 15 with "Show all" expand. Active session highlighted.
4. **File tree**: Recursive `FileTree` component shown when a session is active. VS Code-style file/folder icons colored by extension. Refreshes on `file-tree-changed` events.

---

## 9. Styling Conventions

### CSS Variables (Dark Theme)

```css
--background: 0 0% 5%        /* Near-black app background */
--foreground: 0 0% 95%       /* White text */
--card: 0 0% 7%              /* Slightly lighter card surfaces */
--muted: 0 0% 12%            /* Subtle backgrounds */
--muted-foreground: 0 0% 55% /* Dimmed text */
--accent: 0 0% 14%           /* Hover/active backgrounds */
--border: 0 0% 14%           /* Subtle borders */
--sidebar: 0 0% 4%           /* Darker sidebar background */
```

### Key CSS Classes

- `.prose-chat` — Custom typography ruleset for markdown in assistant messages (paragraphs, headings, lists, blockquotes, tables, code, links, horizontal rules).
- `.streaming-cursor` — Blinking caret animation for streaming indicators.
- `typing-dot` keyframe — Bouncing dots animation for the stop button and generating indicator.
- `status-pulse` keyframe — Pulsing opacity for running status indicators.

### Tailwind Patterns

- Borders use `border-border/30` for subtle dividers
- Text hierarchy: `text-foreground` → `text-muted-foreground` → `text-muted-foreground/60`
- Code surfaces: `bg-[hsl(0,0%,7%)]` for code blocks, `bg-[hsl(0,0%,9%)]` for code headers
- Rounded corners: `rounded-2xl` for input bar, `rounded-lg` for code blocks and cards
- All Radix popovers use `side="bottom"` with `max-h-[300px] overflow-y-auto`

---

## 10. Keyboard Shortcuts

| Shortcut         | Action                        |
| ---------------- | ----------------------------- |
| `Ctrl+B`         | Toggle sidebar                |
| `Ctrl+Shift+B`   | Toggle right panel (legacy)   |
| `Escape`         | Cancel running prompt          |
| `Ctrl+K`         | Focus prompt input            |
| `Ctrl+Shift+L`   | Toggle theme                  |
| `Ctrl+Enter`     | Send message (in prompt input)|

---

## 11. Data Flow Summary

```
User types message → PromptInput
  → addUserMessage() (optimistic, into chatItems)
  → api.sessions.sendPrompt() (POST /api/sessions/{id}/messages)
  → Backend processes prompt, model generates response

WebSocket receives events:
  content_delta → streaming buffer (RAF flush loop)
  thinking_delta → streaming buffer  
  tool_dispatch → tool_call ChatItem
  tool_result → updates matching tool_call
  stream_end → clears streaming, captures token stats
  response_text → assistant ChatItem (final clean response)
  agent_start/agent_done → lifecycle ChatItems

ChatView renders chatItems:
  groupChatItems() → content items + activity groups
  ChatMessage dispatches to correct renderer
  StreamingMessage shows while streaming is active
```

---

## 12. File Upload Flow

```
User drops/pastes/selects files → PromptInput
  → useUploadStore.stageFiles(sessionId, files)
    → Validates (count, size, extension)
    → Creates local preview URLs
    → POSTs FormData to /api/sessions/{id}/uploads
    → Replaces pending items with server-returned UploadMeta
  → AttachmentPreview renders thumbnails
  → On send: getAttachmentIds() returns upload IDs
  → Included in PromptRequest.attachments[]
  → clearAll() after send
```
