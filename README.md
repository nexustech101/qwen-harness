<!-- ============================================================ -->
<!--                       QWEN MCP                              -->
<!-- ============================================================ -->

<div align="center">

```
 ██████╗ ██╗    ██╗███████╗███╗   ██╗    ███╗   ███╗ ██████╗ ██████╗ 
██╔═══██╗██║    ██║██╔════╝████╗  ██║    ████╗ ████║██╔════╝ ██╔══██╗
██║   ██║██║ █╗ ██║█████╗  ██╔██╗ ██║    ██╔████╔██║██║      ██████╔╝
██║▄▄ ██║██║███╗██║██╔══╝  ██║╚██╗██║    ██║╚██╔╝██║██║      ██╔═══╝ 
╚██████╔╝╚███╔███╔╝███████╗██║ ╚████║    ██║ ╚═╝ ██║╚██████╗ ██║     
 ╚══▀▀═╝  ╚══╝╚══╝ ╚══════╝╚═╝  ╚═══╝    ╚═╝     ╚═╝ ╚═════╝ ╚═╝     
```

**A local-first AI agent harness with a web chat UI, MCP server, and FastAPI backend — powered by any Ollama model**

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square)](https://fastapi.tiangolo.com)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.x-blueviolet?style=flat-square)](https://github.com/jlowin/fastmcp)
[![Ollama](https://img.shields.io/badge/Ollama-local%20LLM-black?style=flat-square)](https://ollama.ai)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

</div>

---

## Overview

**qwen-mcp** is a self-hosted AI agent platform. It pairs a streaming FastAPI backend with a React web UI and a Rich-powered interactive shell, letting any local Ollama model invoke tools, run commands, read and write files, and fetch URLs — all without cloud dependencies, auth services, or billing.

> **Any locally hosted Ollama model works.** The name "QWEN MCP" reflects a popular default (`qwen2.5-coder:7b`), but you can use `llama3`, `codestral`, `deepseek-coder`, `mistral`, `phi3`, or any other model you have pulled. Switch models per-session from the web UI or set `AGENT_API_DEFAULT_MODEL` in your `.env`.

```
┌──────────────────────────────────────────────────────────────┐
│                       qwen-mcp stack                         │
│                                                              │
│   React Web UI  ──WSS──▶  agent-api (FastAPI)                │
│   NavRail layout           │                                 │
│   Chat bubbles             ├── Ollama (any local model)       │
│   Workflow canvas          ├── MCP Server (/mcp)             │
│   MCP browser              └── Tool Registry                 │
│                                                              │
│   agent (shell) ──SSE──▶  agent-api                          │
│   Rich REPL                                                  │
└──────────────────────────────────────────────────────────────┘
```

---

## Features

- **Local-first** — runs entirely on your machine; no API keys, no telemetry
- **Any Ollama model** — use Qwen, Llama, Codestral, DeepSeek, Mistral, Phi, or any other pulled model
- **React web UI** — NavRail layout with chat bubbles, n8n-style workflow canvas, MCP browser, and settings
- **Streaming shell** — Rich REPL with live Markdown rendering and real-time `<think>` block display
- **MCP server** — tools and prompts exposed via [FastMCP](https://github.com/jlowin/fastmcp) over HTTP
- **Tool registry** — typed, schema-validated tools callable by the LLM or directly via MCP
- **Session persistence** — chat history stored in SQLite; resume any session with `/sessions`
- **Workflow CRUD** — storable, runnable workflows via REST
- **SSE + WebSocket** — dual streaming transports for prompt responses
- **Rate limiting** — per-IP slowapi guards on all API routes
- **Open source** — MIT licensed, zero proprietary dependencies

---

## Web Interface

The frontend is a React + TypeScript single-page app served from `frontend/`. Start it alongside the API server for a full-featured chat experience.

**Views (NavRail sidebar)**

| Icon | View | Description |
|------|------|-------------|
| 💬 | **Chat** | Bubble-layout chat with streaming responses, `<think>` blocks, and tool call cards. Session list in sidebar. |
| ⚙ | **Workflows** | Create and edit n8n-style step graphs. Visual canvas with drag-to-move nodes, Bezier edges, and a step editor panel. Execute a workflow to open it as a chat session. |
| 🔌 | **MCP** | Browse all registered MCP tools and prompts with descriptions. |
| ⚙ | **Settings** | Inspect live configuration: model, Ollama host, execution limits, routing mode. |

**Key UX details**

- User messages appear on the right (primary colour); AI responses on the left
- Reasoning (`<think>` content) shown in a collapsible block
- Tool calls and results shown as expandable cards
- Paste long multi-line content (code, logs, error traces) into the prompt bar — a compact preview card shows the line/char count while the full text is sent to the model
- Model selector popover in the prompt bar; switch per-session without restarting

```bash
# Start the frontend dev server
cd frontend
pnpm install
pnpm dev          # http://localhost:5173

# Or build for production
pnpm build        # outputs to frontend/dist/
```

---

## Shell Demo

```
╭──────────────────────────────────────────────────────╮
│  agent-shell                                         │
│  Model  : qwen2.5-coder:7b                           │
│  Server : http://127.0.0.1:8000                      │
│  Session: 5c5b1f0b-7219-46ed-8ccd-a496f9702e33       │
╰──────────────────────────────────────────────────────╯

> What files are in the current directory?

  ⚙ list_directory(path='.')
  ✓ list_directory: api/, app/, frontend/, graph/, tests/, pyproject.toml, ...

  Here are the top-level contents of the current directory:

  - **api/** — FastAPI server, MCP server, tool registry
  - **app/** — interactive shell and REST client
  - **frontend/** — Vite + TypeScript web UI
  - **graph/** — optional code graph analysis utilities
  - **tests/** — unit and integration test suite
  - **pyproject.toml** — project configuration and entry points

> /help

  ┌────────────┬──────────────────────────────────┐
  │ /new       │ Start a new chat session         │
  │ /sessions  │ List and switch between sessions │
  │ /session   │ Show current session ID          │
  │ /models    │ List available models            │
  │ /workflows │ List workflows                   │
  │ /clear     │ Clear the terminal               │
  │ /help      │ Show this help                   │
  │ quit       │ Exit the shell                   │
  └────────────┴──────────────────────────────────┘

> /sessions

  ┌───┬───┬────────────┬──────────┬────────┐
  │ # │   │ Title      │ ID       │ Status │
  ├───┼───┼────────────┼──────────┼────────┤
  │ 1 │ ▶ │ New chat   │ 5c5b1f0b │ idle   │
  │ 2 │   │ New chat   │ 924c1810 │ idle   │
  └───┴───┴────────────┴──────────┴────────┘
```

---

## Architecture

```
coding-agent/
├── api/                    # FastAPI server
│   ├── config/             # Settings (pydantic-settings)
│   ├── db/                 # SQLite models (registers.db)
│   ├── integrations/       # Third-party adapters
│   ├── mcp/                # FastMCP server + tool/prompt wrappers
│   │   ├── server.py       # mcp = FastMCP(...)
│   │   ├── tools.py        # @mcp.tool registrations
│   │   └── prompts.py      # @mcp.prompt registrations
│   ├── modules/            # Middleware, rate limiting, session manager
│   ├── router/             # FastAPI routers
│   │   └── routes/         # chat, system, workflows, websocket
│   ├── services/           # Business logic
│   │   ├── chat_service.py # Ollama streaming loop + tool dispatch
│   │   └── response_parser.py  # <think> tag + JSON streaming parser
│   └── tools/              # Tool implementations
│       ├── registry.py     # ToolRegistry with schema validation
│       ├── file_tools.py   # read, write, edit, list, exists
│       ├── system_tools.py # run_command, get_working_directory
│       └── web_tools.py    # http_get / fetch_url
│
├── app/                    # Interactive shell (thin API client)
│   ├── core/
│   │   ├── client.py       # MCPAgentClient (SSE + WebSocket)
│   │   └── orchestrator.py # Session lifecycle wrapper
│   └── interactive.py      # Rich REPL
│
├── frontend/               # Vite + TypeScript web UI
└── pyproject.toml          # Entry points: agent / agent-api
```

---

## Registered Tools

| Category | Tool | Description |
|----------|------|-------------|
| `file` | `read_file` | Read file content with optional line range |
| `file` | `write_file` | Write or append content to a file |
| `file` | `edit_file` | Replace a specific string in a file |
| `file` | `list_directory` | List directory contents |
| `file` | `file_exists` | Check whether a path exists |
| `system` | `get_working_directory` | Return the current working directory |
| `system` | `run_command` | Execute a shell command (allowlist-gated) |
| `web` | `http_get` | Fetch a URL and return the response body |

MCP prompts: `code_review`, `explain_error`, `generate_tests`, `refactor_code`

---

## Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) running locally with at least one pulled model
- A pulled model — e.g. `ollama pull qwen2.5-coder:7b` (or any other model you prefer)
- Node.js 18+ and [pnpm](https://pnpm.io) (for the web UI)

### Install

```bash
git clone https://github.com/your-org/agent-mcp
cd agent-mcp
pip install -e .
```

### Run

```bash
# Terminal 1 — start the API server
agent-api

# Terminal 2 — start the web UI (optional)
cd frontend && pnpm dev

# Terminal 3 — start the interactive shell (optional)
agent
```

The API server binds to `http://0.0.0.0:8000` by default.  
The web UI runs at `http://localhost:5173`.  
The shell connects to `http://127.0.0.1:8000`.

---

## Configuration

All settings use the `AGENT_API_` prefix or can be placed in a `.env` file at the project root.

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_API_OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server URL |
| `AGENT_API_DEFAULT_MODEL` | `qwen2.5-coder:7b` | Default chat model — **any pulled Ollama model works** |
| `AGENT_API_DATABASE_URL` | `sqlite:///./agent.db` | Session/workflow database |
| `AGENT_API_MCP_SERVER_NAME` | `Local Agent` | Name shown in MCP clients |
| `AGENT_API_GLOBAL_RATE_LIMIT` | `200/minute` | API rate limit per IP |
| `AGENT_API_LOG_LEVEL` | `INFO` | Logging verbosity |
| `AGENT_API_LOG_JSON` | `false` | Emit structured JSON logs |

Override the shell's server URL with `AGENT_API_BASE_URL` (default: `http://127.0.0.1:8000`).

---

## API Reference

### Sessions

```
POST   /api/sessions                    Create a session
GET    /api/sessions                    List all sessions
GET    /api/sessions/{id}               Get session details
DELETE /api/sessions/{id}               Delete session + messages
GET    /api/sessions/{id}/messages      Fetch message history
POST   /api/sessions/{id}/prompt        Stream a prompt (SSE)
WS     /api/sessions/{id}/ws            WebSocket stream
```

### Workflows

```
POST   /api/workflows                   Create a workflow
GET    /api/workflows                   List workflows
GET    /api/workflows/{id}              Get workflow
PUT    /api/workflows/{id}              Update workflow
DELETE /api/workflows/{id}              Delete workflow
GET    /api/workflows/{id}/runs         Run history
```

### System

```
GET    /api/health                      Health check
GET    /api/config                      Active configuration
GET    /api/models                      Available Ollama models
```

### MCP

```
*      /mcp                             FastMCP HTTP transport (SSE + streamable)
```

---

## Response Streaming

Prompt responses are streamed as [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events). Each event is a JSON object:

```jsonc
{ "type": "turn_start",  "session_id": "...", "model": "..." }
{ "type": "thinking",    "delta": "..." }          // <think> content
{ "type": "token",       "delta": "..." }          // visible response
{ "type": "tool_call",   "name": "...", "args": {} }
{ "type": "tool_result", "name": "...", "success": true, "output": "..." }
{ "type": "turn_done",   "elapsed_seconds": 1.23 }
{ "type": "error",       "detail": "..." }
```

---

## Development

```bash
# Install with dev extras
pip install -e ".[graph-all]"

# Run tests
pytest tests/

# Lint
ruff check .
```

---

## License

MIT — free to use, modify, and distribute.

---

<div align="center">
<sub>Built with FastAPI · FastMCP · Ollama · React · TypeScript · SQLite</sub>
</div>
