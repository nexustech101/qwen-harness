# PROJECT_SPECS.md — qwen-coder

## 1. Purpose

**qwen-coder** is an autonomous coding agent powered by local LLMs via Ollama. It accepts natural-language tasks, plans execution, and carries them out end-to-end through tool calls that manipulate the real filesystem. It runs as both a CLI tool and a FastAPI backend that serves a React frontend over REST + WebSocket.

### Design Principles

- **Local-first**: Ollama backend; no cloud API keys required (cloud-hosted Ollama endpoints supported)
- **Tool-driven**: The LLM calls tools (`write_file`, `edit_file`, `run_command`, etc.) — it never outputs code directly to the user
- **Structured execution**: Turn-based agent loop with JSON tool calls, schema validation, deadlock detection, and automatic recovery
- **Dual interface**: Rich terminal REPL **and** FastAPI HTTP/WS server consumed by a React frontend

---

## 2. Architecture

### 2.1 High-Level Flow

```
User prompt (CLI or HTTP)
    │
    ▼
┌──────────────┐     ┌──────────────────┐
│  Orchestrator │────▶│  Planner LLM     │  (classifies: direct or decompose)
└──────┬───────┘     └──────────────────┘
       │
       ├── mode: "direct" ──▶ ExecutionEngine (single agent loop)
       │
       └── mode: "decompose" ──▶ Dispatcher → SubAgentRunner[] (isolated engines)
```

### 2.2 Complexity Gate (Orchestrator)

The Orchestrator asks a planner LLM to classify the task:

- **`"direct"` (~95%)**: Single ExecutionEngine handles everything.
- **`"decompose"` (rare)**: Only when there are genuinely independent, parallel workstreams. Produces `TaskSpec[]` dispatched to isolated sub-agents.

Decomposition has retry logic (`MAX_PARSE_RETRIES=2`). Falls back to direct mode on failure.

### 2.3 Execution Engine (Agent Loop)

Core turn-based loop:

1. **MODEL_CALL** — Stream LLM via `ollama.Client.chat(stream=True)`. Emits `content_delta` / `thinking_delta` trace events per chunk.
2. **PARSE** — Multi-strategy parser: native tool calls → structured JSON → legacy JSON → plain text. Extracts `<think>` tags.
3. **VALIDATE** — Schema validation against tool registry.
4. **DEADLOCK CHECK** — Identical consecutive calls detected at threshold of 3.
5. **EXECUTE** — Tools run via `ToolRegistry`, collect `ToolResult(success, data, metadata, error)`.
6. **INJECT** — Results appended to conversation. Budget warning at 80% turns.
7. **PRUNE** — Keeps conversation within `MAX_MESSAGES` (pins system prompt + original request + first plan message).
8. **REPEAT** — Until completion (no tools returned), max_turns, or deadlock.

Resilience:
- **Plain-text nudging**: Up to `MAX_PLAIN_NUDGES=2` before treating narrative as completion
- **Malformed JSON recovery**: Retry with error feedback (`MAX_PARSE_RETRIES=2`)
- **Deadlock detection**: `IDENTICAL_CALL_THRESHOLD=3` identical tool-call signatures → abort

### 2.4 Response Parser

Priority chain in `app/parsing/response_parser.py`:
1. **Native** — Ollama `tool_calls` on response message
2. **Structured JSON** — `{"reasoning": "...", "tools": [{name, arguments}], "response": "..."}`
3. **Legacy JSON** — `{"name": "...", "arguments": {...}}` single tool
4. **Plain text** — Narrative / final answer

Extracts `<think>...</think>` blocks (Qwen3, DeepSeek-R1 reasoning) from all modes.

### 2.5 Tool System

26 tools across 7 categories, registered via `ToolRegistry` (`app/tools/registry.py`):

| Category      | Tools                                                                 |
|--------------|-----------------------------------------------------------------------|
| **File**      | `read_file`, `write_file`, `edit_file`, `file_exists`, `list_directory` |
| **System**    | `get_working_directory`, `run_command`, `log_message`                  |
| **Analysis**  | `search_in_file`, `count_lines`                                       |
| **Code**      | `check_syntax`, `run_tests`, `apply_patch`                            |
| **Workspace** | `grep_workspace`, `find_files`, `create_directory`, `move_file`, `delete_file`, `copy_file`, `diff_files` |
| **Agent**     | `workspace_read`, `agent_report`, `agent_read`, `send_directive`, `request_help` |
| **Web**       | `http_get`                                                            |

`safe_resolve()` in `app/tools/path_utils.py` sandboxes all file paths to the working directory. JSON schemas for all parameters live in `app/tools/schemas.py`.

### 2.6 Prompt System

Three Markdown templates in `app/prompts/`, rendered by `system_prompts.py`:

- **`main.md`** — Single-agent prompt (Plan → Build → Verify workflow, JSON format rules)
- **`orchestrator.md`** — Planner prompt (direct vs. decompose criteria)
- **`sub_agent.md`** — Sub-agent prompt (task spec, directives, inherited context)

### 2.7 Observability (Trace System)

`app/observability/trace.py` provides a structured event bus. Components emit typed events; subscribers receive them synchronously.

**Event types**: `agent_start`, `model_call`, `model_reply`, `content_delta`, `thinking_delta`, `stream_end`, `reasoning`, `tool_dispatch`, `tool_result`, `error`, `recovery`, `turn_start`, `response_text`, `agent_done`, `max_turns`

**Subscribers**:
- `ConsoleRenderer` — Rich terminal output (tool names, success/failure, latency, reasoning)
- `FileLogger` — All events written to `agent.log`
- `Session._bridge_event()` — Forwards events to WebSocket queues (API mode)

### 2.8 Dispatcher (Sub-Agent Mode)

`app/core/dispatcher.py`:
- **Sequential**: Topological sort by `depends_on`
- **Async**: Concurrent execution behind semaphore (`MAX_CONCURRENT_AGENTS=3`)
- Dependency validation detects cycles
- Each sub-agent gets an isolated `ExecutionEngine` + `Trace`; events relay to parent trace tagged with agent name

### 2.9 Workspace (`.qwen-coder/`)

Filesystem protocol for orchestrator↔sub-agent communication:

```
.qwen-coder/
├── project.md                  # Project overview
├── plan.md                     # Execution plan (written in Phase 1)
├── status.md                   # Overall progress
├── uploads/{session_id}/       # Staged file uploads (API mode)
└── .qwen-agent-<name>/         # Per-sub-agent directory
    ├── task.md, directives.md, context.md, status.md, output.md
```

---

## 3. FastAPI Backend

### 3.1 Server

`app/account_api/api/__init__.py` — `create_app()` factory. CORS open (all origins). Includes REST routers + WS router.

Run: `uvicorn app.account_api.api:create_app --factory --port 8100`

### 3.2 REST Endpoints (`app/account_api/api/routes/*.py`)

All prefixed `/api`.

| Method   | Path                                        | Purpose                              |
|----------|---------------------------------------------|--------------------------------------|
| `GET`    | `/health`                                   | Health check + Ollama connectivity   |
| `GET`    | `/config`                                   | Current server config                |
| `GET`    | `/models`                                   | List Ollama models                   |
| `GET`    | `/browse-folder`                            | OS native folder picker (tkinter)    |
| `POST`   | `/sessions`                                 | Create session (project_root + opts) |
| `GET`    | `/sessions`                                 | List all sessions                    |
| `GET`    | `/sessions/{id}`                            | Get session detail                   |
| `DELETE` | `/sessions/{id}`                            | Delete session + cleanup uploads     |
| `POST`   | `/sessions/{id}/messages`                   | Send prompt (with optional attachments) |
| `GET`    | `/sessions/{id}/messages`                   | Get message history                  |
| `GET`    | `/sessions/{id}/agents`                     | List agents in session               |
| `GET`    | `/sessions/{id}/agents/{name}`              | Agent detail (messages, tools, files)|
| `POST`   | `/sessions/{id}/agents/{name}/prompt`       | Send prompt to specific agent        |
| `POST`   | `/sessions/{id}/uploads`                    | Stage file uploads (multipart)       |
| `GET`    | `/sessions/{id}/uploads/{uid}`              | Serve uploaded file                  |
| `GET`    | `/sessions/{id}/uploads/{uid}/thumbnail`    | On-demand PIL thumbnail (200×200)    |
| `DELETE` | `/sessions/{id}/uploads/{uid}`              | Delete staged upload                 |
| `GET`    | `/sessions/{id}/files`                      | File tree of project_root            |
| `GET`    | `/sessions/{id}/files/{path}`               | Read file content                    |

### 3.3 WebSocket (`app/account_api/api/ws.py`)

`WS /api/sessions/{id}/ws` — Streams real-time trace events to the frontend.

- On connect: sends `connected` event with session status + agent list
- Event forwarding: `Session._bridge_event()` enqueues events → `_forward_events()` sends JSON to client
- Keepalive: `ping` every 30s on idle
- Client → server: supports `cancel` command to abort running task
- Reconnect: client handles reconnection; server cleans up queue on disconnect

### 3.4 Session Manager (`app/account_api/api/session_manager.py`)

In-memory session store. Key classes:

**`Session`**:
- Wraps `Orchestrator` for a project directory
- Constructor: `(project_root, model?, planner_model?, coder_model?, max_turns?, use_dispatch?, async_dispatch?)`
- State: `id` (UUID), `status` (idle/running/error), `history[]`, `agents{}`, `uploads{}`
- `run_prompt(prompt, direct, images)` — Acquires `_execution_lock`, runs agent in thread via `asyncio.to_thread`, appends user/assistant/error messages to history
- WS pub/sub: `subscribe()` / `unsubscribe(queue)` manage `_ws_queues[]`
- `_bridge_event(event, trace)` — Thread-safe forwarding from agent thread to async WS queues

**`SessionManager`** (singleton `manager`):
- `create(**kwargs) → Session`
- `get(id) → Session | None`
- `list_all() → list[Session]`
- `delete(id)` — Cancels running task, cleans up uploads, removes from store

**Upload handling**:
- Files staged to `.qwen-coder/uploads/{session_id}/{upload_id}/`
- MIME validation via magic bytes + extension blocklist
- Limits: 10 MB/file, 50 MB/request, 10 files max
- Blocked extensions: `.exe`, `.dll`, `.so`, `.bat`, `.ps1`, etc.
- When prompt sent with `attachments[]`: images passed as file paths to `ExecutionEngine.run(images=)`, text files injected into prompt content
- Thumbnails generated on-demand via Pillow, cached as `{id}_thumb.png`

### 3.5 Pydantic Models (`app/account_api/schemas/agent.py`)

**Request models**:
- `CreateSessionRequest(project_root, model?, planner_model?, coder_model?, max_turns?, use_dispatch, async_dispatch)`
- `SendPromptRequest(prompt, direct=False, attachments=[])`

**Response models**:
- `HealthResponse(status, ollama_connected)`
- `ConfigResponse(ollama_host, model, planner_model, coder_model, max_turns, max_messages, sub_agent_max_turns, max_concurrent_agents)`
- `OllamaModel(name, size, modified_at, family?, parameter_size?, quantization_level?)`
- `SessionResponse(id, project_root, status, model, created_at, stats, agents)`
- `SessionStats(total_turns, total_tool_calls, elapsed_seconds, files_modified, message_count)`
- `AgentSummary(name, status, model, turns_used, max_turns, goal)`
- `AgentDetailResponse(AgentSummary + messages, tool_calls, files_modified)`
- `MessageResponse(role, content, timestamp?, metadata?)`
- `PromptAccepted(status, session_id)`
- `UploadMeta(id, filename, mime_type, size, url, thumbnail_url?)`
- `UploadResponse(uploads[])`
- `FileTreeEntry(name, path, type, size?, children?)`
- `FileContentResponse(path, content, size, lines)`

### 3.6 Token Streaming Flow

```
ExecutionEngine._stream_chat()
  → ollama.Client.chat(stream=True)
  → per chunk: trace.emit("content_delta" | "thinking_delta")
  → Session._bridge_event() → loop.call_soon_threadsafe(queue.put_nowait)
  → ws._forward_events() → websocket.send_json()
  → Frontend renders tokens in real-time
```

At stream end: emits `stream_end` with `eval_count`, `prompt_eval_count`, `eval_duration` for token stats.

---

## 4. Project Structure

```
coding-agent/
├── pyproject.toml              # Package config (name: qwen-coder, entry: app.main:main)
├── requirements.txt            # Dependencies
│
├── app/
│   ├── __init__.py
│   ├── __main__.py             # python -m app entry
│   ├── main.py                 # CLI argparse (single-prompt or interactive)
│   ├── interactive.py          # Rich-powered REPL loop
│   ├── config.py               # Env-var config with defaults
│   ├── .env                    # Local overrides
│   │
│   ├── api/                    # FastAPI backend
│   │   ├── server.py           # create_app() factory, CORS, router mounting
│   │   ├── routes.py           # 19 REST endpoints under /api
│   │   ├── models.py           # Pydantic request/response schemas
│   │   ├── session_manager.py  # In-memory Session store, upload handling, WS pub/sub
│   │   └── ws.py               # WebSocket handler (event streaming, cancel, keepalive)
│   │
│   ├── core/                   # Agent orchestration
│   │   ├── orchestrator.py     # Direct vs. dispatch routing, planner LLM call
│   │   ├── execution.py        # Agent loop (_stream_chat, turn cycle, nudge/recovery)
│   │   ├── dispatcher.py       # Sequential + async sub-agent dispatch
│   │   ├── sub_agent.py        # Isolated sub-agent runner
│   │   ├── workspace.py        # .qwen-coder/ directory protocol manager
│   │   └── state.py            # Dataclasses: ToolResult, AgentState, TaskSpec, etc.
│   │
│   ├── tools/                  # 26 tools, 7 categories
│   │   ├── registry.py         # ToolRegistry (register, validate, execute, format)
│   │   ├── schemas.py          # JSON schemas for all tool parameters
│   │   ├── path_utils.py       # safe_resolve() path sandboxing
│   │   ├── file_tools.py       # read_file, write_file, edit_file, file_exists, list_directory
│   │   ├── system_tools.py     # get_working_directory, run_command, log_message
│   │   ├── analysis_tools.py   # search_in_file, count_lines
│   │   ├── code_tools.py       # check_syntax, run_tests, apply_patch
│   │   ├── workspace_tools.py  # grep_workspace, find_files, create_directory, move_file, etc.
│   │   ├── agent_tools.py      # workspace_read, agent_report, agent_read, send_directive, request_help
│   │   └── web_tools.py        # http_get (URL validation, SSRF protection)
│   │
│   ├── parsing/
│   │   ├── response_parser.py  # Multi-strategy parser (native → JSON → legacy → plain)
│   │   └── schema_validator.py # Validates tool calls against registered schemas
│   │
│   ├── prompts/
│   │   ├── system_prompts.py   # Template renderer (loads .md, fills variables)
│   │   ├── main.md             # Single-agent system prompt
│   │   ├── orchestrator.md     # Planner system prompt
│   │   └── sub_agent.md        # Sub-agent system prompt
│   │
│   └── observability/
│       ├── trace.py            # Structured event bus (emit + subscribe)
│       ├── console_renderer.py # Rich terminal output
│       └── file_logger.py      # File logging + trace subscriber
│
└── data/                       # Training data artifacts (separate concern)
```

---

## 5. Configuration (`app/config.py`)

All from environment variables with defaults:

| Variable                    | Default                         | Purpose                              |
|----------------------------|---------------------------------|--------------------------------------|
| `OLLAMA_HOST`              | `http://127.0.0.1:11434`       | Ollama server URL                    |
| `AGENT_MODEL`              | `qwen3-coder:480b-cloud`       | Default model for all roles          |
| `AGENT_PLANNER_MODEL`      | (falls back to MODEL)           | Planner/classifier model             |
| `AGENT_CODER_MODEL`        | (falls back to MODEL)           | Code generation model                |
| `AGENT_MAX_TURNS`          | `30`                            | Max turns per agent run              |
| `AGENT_MAX_MESSAGES`       | `30`                            | Max messages before pruning          |
| `AGENT_MAX_PARSE_RETRIES`  | `2`                             | Malformed JSON retries               |
| `AGENT_MAX_PLAIN_NUDGES`   | `2`                             | Plain-text nudges before completion  |
| `IDENTICAL_CALL_THRESHOLD` | `3`                             | Deadlock detection threshold         |
| `AGENT_SUB_MAX_TURNS`      | `10`                            | Max turns per sub-agent              |
| `AGENT_MAX_CONCURRENT`     | `3`                             | Max concurrent sub-agents            |
| `MAX_READ_LINES`           | `500`                           | Max lines returned by read_file      |
| `MAX_READ_BYTES`           | `50000`                         | Max bytes returned by read_file      |
| `MAX_TOOL_RESULT_CHARS`    | `10000`                         | Truncation limit for tool results    |
| `AGENT_LOG_FILE`           | `agent.log`                     | Log output path                      |
| `WORKSPACE_DIR`            | `.qwen-coder`                   | Agent workspace directory name       |

---

## 6. Dependencies (`requirements.txt`)

```
ollama>=0.4.0              # Ollama client (streaming chat)
rich>=13.0                 # Terminal UI
fastapi>=0.115.0           # REST + WebSocket framework
python-multipart>=0.0.9    # Multipart form parsing (uploads)
uvicorn[standard]>=0.30.0  # ASGI server
python-dotenv>=1.0.0       # .env file support
Pillow>=10.0.0             # Image thumbnailing
```

---

## 7. Usage

### CLI

```bash
pip install -e .

# Interactive REPL
qwen-coder

# Single prompt (direct mode)
qwen-coder --direct "fix the import error in app.py"

# Override models
qwen-coder --planner-model qwen3:32b --coder-model qwen2.5-coder:7b "task"

# Set max turns
qwen-coder --max-turns 50 "build a complex project"
```

### API Server

```bash
uvicorn app.account_api.api:create_app --factory --host 0.0.0.0 --port 8100
```

---

## 8. Key Implementation Details

### Image Support

The `ExecutionEngine.run()` method accepts `images: list[str] | None`. When provided, images are included in the Ollama chat message for vision-capable models. Images flow through: `Session.run_prompt() → Session._execute() → Orchestrator.run() → ExecutionEngine.run()`.

### Thread Safety

Agent execution runs in a worker thread (`asyncio.to_thread`). The `Session._bridge_event()` method uses `loop.call_soon_threadsafe()` to forward trace events from the agent thread to the async event loop's WS queues. A global `_execution_lock` serializes prompt execution within a session.

### Message Pruning Strategy

When conversation exceeds `MAX_MESSAGES`, the engine prunes middle messages while preserving:
1. System prompt (index 0)
2. Original user request (index 1)
3. First plan message (if present)
4. Most recent messages

### WebSocket Event Schema

All events follow: `{type: string, agent: string, data: {}, timestamp: number}`

Key event types streamed to frontend:
- `connected`, `ping` — Connection lifecycle
- `content_delta`, `thinking_delta`, `stream_end` — Token streaming
- `agent_start`, `agent_done` — Agent lifecycle
- `turn_start` — Turn boundaries
- `tool_dispatch`, `tool_result` — Tool execution
- `reasoning`, `response_text` — Model output
- `error`, `recovery`, `max_turns` — Error handling
