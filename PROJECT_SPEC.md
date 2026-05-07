# Project Specification — Agent MCP API v3

> **Audience**: Frontend engineers, integration developers.  
> **Last updated**: 2026-05-06  
> **Base URL**: `http://localhost:8000` (configurable via `VITE_API_URL`)  
> **API prefix**: all endpoints are under `/api/`

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Configuration & Environment](#2-configuration--environment)
3. [SSE Streaming Protocol](#3-sse-streaming-protocol)
4. [WebSocket Protocol](#4-websocket-protocol)
5. [API Reference](#5-api-reference)
   - [System](#51-system)
   - [Sessions](#52-sessions)
   - [Messages](#53-messages)
   - [Prompt / Streaming](#54-prompt--streaming)
   - [Tools](#55-tools)
   - [Uploads](#56-uploads)
   - [Workflows](#57-workflows)
6. [Shared Types](#6-shared-types)
7. [LLM Provider Support](#7-llm-provider-support)
8. [Service Architecture](#8-service-architecture)
9. [Frontend Integration Notes](#9-frontend-integration-notes)
10. [Breaking Changes from v2](#10-breaking-changes-from-v2)

---

## 1. Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                       │
│   Zustand stores │ React Query │ SSE stream │ WebSocket        │
└───────────────────────────┬────────────────────────────────────┘
                            │ HTTP / WS
┌───────────────────────────▼────────────────────────────────────┐
│                      FastAPI (api/)                            │
│  /api/health  /api/config  /api/models                        │
│  /api/sessions  /api/tools  /api/uploads  /api/workflows       │
│                                                                │
│  ┌──────────────────┐   ┌───────────────────────────────────┐  │
│  │  chat_service.py │   │  api/agent/  (LangGraph loop)     │  │
│  │  Ollama direct   │   │  StateGraph + ToolNode            │  │
│  │  StreamingParser │   │  AsyncSqliteSaver checkpoint      │  │
│  └──────────────────┘   └───────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────┐   ┌───────────────────────────────────┐  │
│  │  api/llm/factory │   │  api/tools/  (39 @tool functions) │  │
│  │  Ollama / OpenAI │   │  file, system, web, code,         │  │
│  │  Anthropic       │   │  workspace, analysis, gmail,graph │  │
│  └──────────────────┘   └───────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
                            │
               ┌────────────┴────────────┐
          Ollama (local)   OpenAI API   Anthropic API
```

**Key technology choices:**

| Layer | Technology |
|---|---|
| API framework | FastAPI + Uvicorn |
| LLM orchestration | LangGraph `StateGraph` (v0.2+) |
| LLM providers | Ollama, OpenAI, Anthropic (via `langchain-*`) |
| Tool calling | LangChain `@tool` — 39 tools across 8 modules |
| Streaming | Server-Sent Events (SSE) + WebSocket |
| Persistence | SQLite via custom ORM (`api/db/models.py`) |
| Checkpointing | LangGraph `AsyncSqliteSaver` |
| Settings | Pydantic `BaseSettings` — env prefix `AGENT_API_` |

---

## 2. Configuration & Environment

### Backend env vars (`AGENT_API_` prefix)

| Variable | Default | Description |
|---|---|---|
| `AGENT_API_LLM_PROVIDER` | `ollama` | Active provider: `ollama` \| `openai` \| `anthropic` |
| `AGENT_API_OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server URL |
| `AGENT_API_DEFAULT_MODEL` | `qwen2.5-coder:7b` | Default model for new sessions |
| `AGENT_API_OPENAI_API_KEY` | — | OpenAI secret key |
| `AGENT_API_OPENAI_DEFAULT_MODEL` | `gpt-4o-mini` | Default OpenAI model |
| `AGENT_API_ANTHROPIC_API_KEY` | — | Anthropic secret key |
| `AGENT_API_ANTHROPIC_DEFAULT_MODEL` | `claude-3-5-haiku-20241022` | Default Anthropic model |
| `AGENT_API_DATABASE_URL` | `sqlite:///./agent.db` | SQLite database path |
| `AGENT_API_LOG_LEVEL` | `INFO` | Logging level |

### `GET /api/config` — current response shape

```ts
interface ConfigResponse {
  app_name: string           // "Agent MCP API"
  api_version: string        // "3.0.0"
  ollama_host: string        // used when provider = "ollama"
  default_model: string      // model name used for new sessions
  mcp_server_name: string    // display name for the MCP server
  llm_provider: "ollama" | "openai" | "anthropic"
}
```

> **⚠ Breaking change from v2**: `ConfigResponse` no longer includes `workspace_home`, `workspace_projects_dir`, `planner_model`, `coder_model`, `router_mode`, `context_mode`, `tool_scope_mode`, `max_turns`, `max_messages`, `sub_agent_max_turns`, or `max_concurrent_agents`.

---

## 3. SSE Streaming Protocol

Every event emitted by `POST /api/sessions/{id}/prompt` is a Server-Sent Event with a single `data:` field containing JSON:

```
data: {"type":"...", "agent":"main", "data":{...}, "timestamp":1234567890.123}
```

### Event types

| `type` | `data` payload | Description |
|---|---|---|
| `turn_start` | `{session_id, model, provider}` | Turn begins; model is starting |
| `content_delta` | `{text: string}` | Incremental content token |
| `thinking_delta` | `{text: string}` | Incremental reasoning / `<think>` block token |
| `tool_call` | `{tool: string, args: object}` | LLM invoked a tool |
| `tool_result` | `{tool: string, result: string}` | Tool execution result |
| `turn_done` | `{elapsed: number}` | LLM has finished generating |
| `stream_end` | `{elapsed: number}` | SSE stream is closing |
| `response_text` | `{text: string}` | Full final assistant text (after stream) |
| `error` | `{message: string}` | Error during the turn |

**Notes:**
- `thinking_delta` events are produced by Ollama `<think>` tags and Anthropic extended thinking blocks.
- `tool_call` / `tool_result` pairs only appear when the LangGraph loop is active (tools-enabled sessions).
- Always handle `stream_end` to close the EventSource — it is the terminal event.
- The `agent` field is always `"main"` in the current implementation.

---

## 4. WebSocket Protocol

`WS /api/sessions/{id}/ws`

The WebSocket mirrors the SSE events in real-time (same `{type, agent, data, timestamp}` envelope). Use it for live multi-tab or dashboard scenarios. The SSE endpoint is preferred for chat streaming.

### Server → Client events

Same event types as SSE, plus:

| `type` | payload | Notes |
|---|---|---|
| `connected` | `{session_id, status}` | Sent immediately on connect |
| `ping` | — | Keepalive every 30 s when idle |

### Client → Server messages

```json
{ "type": "cancel", "session_id": "..." }
```
Cancels the running LangGraph task for that session.

---

## 5. API Reference

All endpoints return `application/json` unless noted.

### 5.1 System

#### `GET /api/health`
```ts
// Response
{ status: "ok", version: string }
```

#### `GET /api/config`
```ts
// Response — ConfigResponse (see §2)
{
  app_name: string
  api_version: string
  ollama_host: string
  default_model: string
  mcp_server_name: string
  llm_provider: "ollama" | "openai" | "anthropic"
}
```

#### `GET /api/models`
Returns models available from the **currently configured provider**.

```ts
// Response
OllamaModel[]

interface OllamaModel {
  name: string
  size: number           // bytes
  modified_at: string
  family: string | null
  parameter_size: string | null
  quantization_level: string | null
}
```
> Currently only Ollama models are returned. Multi-provider model listing is planned (see §7).  
> Returns `502` if the configured provider is unreachable.

---

### 5.2 Sessions

#### `POST /api/sessions` — Create session
```ts
// Request
interface CreateSessionRequest {
  model?: string | null    // defaults to settings.default_model
  title?: string           // defaults to "New chat"
}

// Response — 201 SessionResponse
interface SessionResponse {
  id: string
  title: string
  model: string
  status: "idle" | "running" | "error"
  created_at: string       // ISO 8601 UTC
  updated_at: string       // ISO 8601 UTC
  message_count: number
}
```

#### `GET /api/sessions` — List sessions
```ts
// Response
SessionResponse[]
```

#### `GET /api/sessions/{id}` — Get session
```ts
// Response
SessionResponse
// 404 if not found
```

#### `DELETE /api/sessions/{id}` — Delete session
```
204 No Content
404 if not found
```

---

### 5.3 Messages

#### `GET /api/sessions/{id}/messages`
```ts
// Response
MessageResponse[]

interface MessageResponse {
  role: "user" | "assistant"
  content: string
  timestamp: number | null    // Unix epoch float
  metadata: MessageMetadata | null
}

interface MessageMetadata {
  attachments?: AttachmentRef[]
  // assistant messages may include tool call summary data in future
}

interface AttachmentRef {
  filename: string
  mime_type: string
  size: number
}
```

---

### 5.4 Prompt / Streaming

#### `POST /api/sessions/{id}/prompt`

Streams the assistant response as SSE.

```ts
// Request
interface SendPromptRequest {
  prompt: string
  attachment_ids?: string[]   // IDs from /uploads
}

// Response: text/event-stream
// See §3 for event shapes
```

**Status codes:**
- `200` — SSE stream starts
- `404` — session not found
- `409` — session is already running (debounce on client)

---

### 5.5 Tools

#### `GET /api/tools` — List all registered tools
```ts
// Response
ToolMeta[]

interface ToolMeta {
  name: string
  description: string   // first line, max 200 chars
}
```

#### `POST /api/tools/invoke` — Invoke a tool directly
```ts
// Request
interface ToolInvokeRequest {
  name: string
  args: Record<string, unknown>
}

// Response
{ result: string }

// 404 if tool not found
// 500 if tool throws
```

**Available tools (39 total):**

| Module | Tools |
|---|---|
| `file_tools` | `read_file`, `write_file`, `edit_file`, `file_exists`, `list_directory` |
| `system_tools` | `get_working_directory`, `run_command` |
| `web_tools` | `http_get` |
| `analysis_tools` | `search_in_file`, `count_lines` |
| `code_tools` | `check_syntax`, `run_tests`, `apply_patch` |
| `workspace_tools` | `grep_workspace`, `find_files`, `create_directory`, `move_file`, `delete_file`, `copy_file`, `diff_files` |
| `agent_tools` | `workspace_read`, `agent_report`, `agent_read`, `send_directive`, `request_help` |
| `gmail_tools` | `check_email`, `categorize_emails`, `reply_to_email` |
| `graph_tools` | `graph_refresh`, `graph_summary`, `graph_report`, `graph_stats`, `graph_query`, `graph_shortest_path`, `graph_neighbors`, `graph_community`, `graph_find_symbol`, `graph_symbol_details`, `graph_usages` |

---

### 5.6 Uploads

#### `POST /api/sessions/{id}/uploads` — Stage file uploads

```ts
// Request: multipart/form-data, field name "files"

// Response
interface UploadResponse {
  uploads: UploadMeta[]
}

interface UploadMeta {
  id: string
  filename: string
  mime_type: string
  size: number
  url: string
  thumbnail_url: string | null
}
```

Pass the returned `id` values in `attachment_ids` when calling `/prompt`.

#### `DELETE /api/sessions/{id}/uploads/{upload_id}`
```
204 No Content
```

---

### 5.7 Workflows

#### `POST /api/workflows` — Create workflow
```ts
// Request
interface WorkflowCreate {
  name: string
  description?: string
  definition?: WorkflowDefinition
  enabled?: boolean
}
```

#### `GET /api/workflows` — List workflows
#### `GET /api/workflows/{id}` — Get workflow
#### `PATCH /api/workflows/{id}` — Partial update
#### `DELETE /api/workflows/{id}` — Delete

```ts
// WorkflowResponse (all CRUD responses)
interface WorkflowResponse {
  id: string
  name: string
  description: string
  definition: WorkflowDefinition
  enabled: boolean
  created_at: string
  updated_at: string
}

interface WorkflowDefinition {
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
  interval_seconds?: number | null
}

interface WorkflowStep {
  id: string
  type: "prompt"
  title: string
  prompt: string
  model?: string
  x: number
  y: number
}

interface WorkflowEdge {
  id: string
  source: string
  target: string
}
```

#### `POST /api/workflows/{id}/runs` — Trigger a run
```ts
// Response
interface WorkflowRunResponse {
  id: string
  workflow_id: string
  status: "pending" | "running" | "done" | "error"
  result: Record<string, unknown> | null
  started_at: string
  finished_at: string | null
}
```

#### `GET /api/workflows/{id}/runs` — List runs for a workflow

---

## 6. Shared Types

```ts
// Used across multiple endpoints
type SessionStatus = "idle" | "running" | "error"
type LLMProvider = "ollama" | "openai" | "anthropic"

interface SessionResponse {
  id: string
  title: string
  model: string
  status: SessionStatus
  created_at: string        // ISO 8601 UTC
  updated_at: string        // ISO 8601 UTC
  message_count: number
}

interface MessageResponse {
  role: "user" | "assistant"
  content: string
  timestamp: number | null
  metadata: Record<string, unknown> | null
}

// SSE / WebSocket event envelope
interface AgentEvent {
  type: string
  agent: string             // always "main" currently
  data: Record<string, unknown>
  timestamp: number         // Unix epoch float
}
```

---

## 7. LLM Provider Support

The backend now supports three LLM providers selected by the `AGENT_API_LLM_PROVIDER` environment variable.

### Provider feature matrix

| Feature | Ollama | OpenAI | Anthropic |
|---|---|---|---|
| Chat streaming | ✅ | ✅ | ✅ |
| Tool calling | ✅ | ✅ | ✅ |
| `<think>` / reasoning tokens | ✅ native | ❌ | ✅ (extended thinking) |
| Model listing via `/api/models` | ✅ | 🔜 planned | 🔜 planned |
| Local / private | ✅ | ❌ | ❌ |

### Model name conventions by provider

| Provider | Example model names |
|---|---|
| `ollama` | `qwen2.5-coder:7b`, `llama3.2:3b`, `deepseek-r1:8b` |
| `openai` | `gpt-4o`, `gpt-4o-mini`, `o3-mini` |
| `anthropic` | `claude-opus-4-5`, `claude-3-5-haiku-20241022` |

### Per-session provider override (planned)

The `CreateSessionRequest` will accept `provider` and `model` to override the global default. Currently, the global `AGENT_API_LLM_PROVIDER` applies to all sessions.

### What the frontend needs to expose

1. A **provider selector** (ollama / openai / anthropic) — read from `/api/config` (`llm_provider` field).
2. A **model selector** — populated from `/api/models` for Ollama, or from a hardcoded / fetched list for cloud providers.
3. Pass `model` in `CreateSessionRequest` to create sessions pinned to a specific model.
4. Display the `model` field from `SessionResponse` in the session list / header.

---

## 8. Service Architecture

### `api/services/chat_service.py`

Handles the **conversational-only** chat loop:
- Uses `ollama.AsyncClient` directly (no tools; conversational mode).
- Persists sessions and messages to SQLite via `api/db/models.py`.
- Exposes DB helpers: `persist_session`, `persist_message`, `load_messages`, `list_sessions`, `get_session`, `delete_session`, `get_messages_for_api`, `restore_session`.
- `run_session_turn(session, prompt)` is the async generator streamed by `POST /prompt`.

### `api/agent/` — LangGraph agent loop

The new agent infrastructure for **tool-enabled** sessions:

| File | Responsibility |
|---|---|
| `state.py` | `AgentState(TypedDict)` — messages, session metadata, turn budget |
| `graph.py` | `StateGraph` — START → `call_model` → [`tools` → `call_model`]* → END |
| `nodes.py` | `call_model` node, `route_after_model` edge, `ToolNode` |
| `runner.py` | `run_agent_turn()` — maps `astream_events` → SSE events |
| `checkpointer.py` | `make_checkpointer()` → `AsyncSqliteSaver` for session persistence |
| `streaming.py` | Re-exports `StreamingParser` for `<think>` tag parsing |

### `api/llm/factory.py`

```python
create_llm(provider, model, *, temperature=0.0, streaming=True) -> BaseChatModel
```

Returns a LangChain-compatible LLM for `ollama`, `openai`, or `anthropic`. Used by `nodes.py`.

### `api/tools/`

All 39 tools use LangChain `@tool` decorator and return `str`. Errors are returned as `"ERROR: ..."` strings (no exceptions propagated to the graph). All are exported in `api/tools/__init__.py` as `ALL_TOOLS: list[BaseTool]`.

### `api/modules/session_manager.py`

In-memory `Session` store. Each `Session` holds:
- `history: list[dict]` — message dicts for Ollama
- `_ws_queues: list[asyncio.Queue]` — active WebSocket subscribers
- `_uploads: dict[str, UploadInfo]` — staged file uploads
- `broadcast(event)` — thread-safe push to all WS queues

---

## 9. Frontend Integration Notes

### What works unchanged
- The WebSocket store in `frontend/src/stores/websocket.ts` correctly handles `content_delta`, `thinking_delta`, `tool_call`, `tool_result`, `turn_done`, `stream_end`, `response_text`, and `error` events — the SSE protocol is unchanged.
- Session CRUD (`/api/sessions`) works as-is with the simplified `SessionResponse`.
- Upload flow (`/api/sessions/{id}/uploads`) is unchanged.
- Workflow CRUD is unchanged.

### Required changes

#### 1. `ConfigResponse` type mismatch
The frontend `ConfigResponse` type has many fields that no longer exist. Replace with:
```ts
interface ConfigResponse {
  app_name: string
  api_version: string
  ollama_host: string
  default_model: string
  mcp_server_name: string
  llm_provider: "ollama" | "openai" | "anthropic"
}
```
Update `SettingsView.tsx` to display provider-relevant config fields.

#### 2. `SessionResponse` type mismatch
The frontend expects `{project_root, project_name, workspace_key, workspace_root, persistence_mode, owner_user_id, stats, agents}`. The backend now returns a simpler shape. Update the type and remove any UI code that renders non-existent fields.

#### 3. `CreateSessionRequest` type mismatch
Remove `project_root`, `chat_only`, `planner_model`, `coder_model`, `max_turns`, `use_dispatch`, `async_dispatch`. Keep only `model?` and `title?`.

#### 4. `/api/models` — provider-aware display
Currently renders an Ollama model list. Add a label/badge showing the active provider from `/api/config`. When provider is `openai` or `anthropic`, the model list endpoint may return empty or error — handle gracefully with a fallback list or manual model name input.

#### 5. Provider switching UI
Add a provider selector (e.g. in Settings or in the session creation modal) that shows the current `llm_provider` from config. Since the provider is set server-side via env var, this is a read-only display for now; a future `/api/config` PATCH endpoint will enable runtime switching.

#### 6. Remove stub API calls
The following client methods call endpoints that **do not exist** in the current backend and will return `404`:
- `api.auth.*` — no auth system implemented
- `api.billing.*` — no billing system implemented
- `api.agents.list/get/prompt` — no `/agents` sub-resource
- `api.files.tree/read` — no `/files` sub-resource
- `api.browseFolder()` — no `/browse-folder` endpoint

For a clean integration, either: remove these calls, stub them gracefully, or guard with `try/catch` and `isLoading` states.

#### 7. New: Tools panel
The new `/api/tools` endpoint enables a **Tools** panel showing all 39 registered tools. Consider adding a tool explorer in the Settings view or as a sidebar panel.

---

## 10. Breaking Changes from v2

| Area | v2 | v3 |
|---|---|---|
| `GET /api/config` | 14 fields including workspace, routing, multi-agent | 6 fields: app, version, ollama_host, default_model, mcp_server_name, llm_provider |
| `POST /api/sessions` | `{project_root, chat_only, planner_model, coder_model, ...}` | `{model?, title?}` |
| `GET /api/sessions/{id}` | Full `SessionResponse` with `stats`, `agents`, `workspace_*` | Simple `{id, title, model, status, created_at, updated_at, message_count}` |
| Auth | `/api/auth/*` endpoints | **Not implemented** |
| Billing | `/api/billing/*` endpoints | **Not implemented** |
| Agent sub-resource | `/api/sessions/{id}/agents` | **Not implemented** |
| File tree | `/api/sessions/{id}/files` | **Not implemented** |
| Tool registry | `@registry.tool()` + `ToolResult` | LangChain `@tool` returning `str` |
| LLM integration | Ollama-only, direct API | Multi-provider via LangGraph / LangChain |
| NEW | — | `GET /api/tools`, `POST /api/tools/invoke` |
| NEW | — | `llm_provider` field in config |
