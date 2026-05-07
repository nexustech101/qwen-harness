<!-- ============================================================ -->
<!--                      agent-mcp                              -->
<!-- ============================================================ -->

<div align="center">

```
 █████╗  ██████╗ ███████╗███╗   ██╗████████╗   ███╗   ███╗ ██████╗██████╗ 
██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝   ████╗ ████║██╔════╝██╔══██╗
███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║      ██╔████╔██║██║     ██████╔╝
██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║      ██║╚██╔╝██║██║     ██╔═══╝ 
██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║      ██║ ╚═╝ ██║╚██████╗██║     
╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝      ╚═╝     ╚═╝ ╚═════╝╚═╝     
```

**A provider-agnostic AI agent harness — Ollama · OpenAI · Anthropic — with a streaming FastAPI backend, web chat UI, MCP server, and Rich interactive shell**

[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square)](https://fastapi.tiangolo.com)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.x-blueviolet?style=flat-square)](https://github.com/jlowin/fastmcp)
[![Ollama](https://img.shields.io/badge/Ollama-local%20LLM-black?style=flat-square)](https://ollama.ai)
[![OpenAI](https://img.shields.io/badge/OpenAI-compatible-412991?style=flat-square)](https://platform.openai.com)
[![Anthropic](https://img.shields.io/badge/Anthropic-compatible-c96a2e?style=flat-square)](https://www.anthropic.com)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

</div>

---

## Overview

**agent-mcp** is a self-hosted AI agent platform. It pairs a streaming FastAPI backend with a React web UI and a Rich-powered interactive shell, letting any LLM invoke tools, run commands, read and write files, and fetch URLs — all without cloud lock-in, auth services, or billing.

> **Any provider works.** Run fully local with [Ollama](https://ollama.ai) (`qwen2.5-coder:7b`, `llama3`, `codestral`, `deepseek-coder`, `mistral`, `phi3`, …) or point it at OpenAI or Anthropic by setting a single env var. Switch providers and models per-session from the web UI or shell.

```
┌──────────────────────────────────────────────────────────────┐
│                      agent-mcp stack                         │
│                                                              │
│   React Web UI  ──WSS──▶  agent-api (FastAPI / LangGraph)    │
│   NavRail layout           │                                 │
│   Chat bubbles             ├── Ollama  (local models)        │
│   Workflow canvas          ├── OpenAI  (cloud)               │
│   MCP browser              ├── Anthropic (cloud)             │
│   Settings                 ├── MCP Server (/mcp)             │
│                            └── Tool Registry (39 tools)      │
│   agent (shell) ──SSE──▶  agent-api                          │
│   Rich REPL + /commands                                      │
└──────────────────────────────────────────────────────────────┘
```

---

## Features

- **Provider-agnostic** — Ollama (local), OpenAI, or Anthropic; switch per-session via env var or shell command
- **Local-first option** — Ollama runs entirely on your machine; no API keys, no telemetry, no billing
- **Any model** — Qwen, Llama, Codestral, DeepSeek, Mistral, Phi (Ollama) · GPT-4o, o1 (OpenAI) · Claude (Anthropic)
- **React web UI** — NavRail layout with chat bubbles, n8n-style workflow canvas, MCP browser, and settings
- **Streaming shell** — Rich REPL with live Markdown rendering and real-time `<think>` block display
- **MCP server** — tools and prompts exposed via [FastMCP](https://github.com/jlowin/fastmcp) over HTTP
- **Tool registry** — typed, schema-validated tools callable by the LLM or directly via MCP
- **Centralized storage** — database, logs, traces, and workspaces in one platform directory; nothing written to CWD
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

- **Python 3.11+** — [python.org/downloads](https://www.python.org/downloads)
- **LLM provider** — one of:
  - [Ollama](https://ollama.ai) running locally (`ollama pull qwen2.5-coder:7b`)
  - An OpenAI API key
  - An Anthropic API key
- **Node.js 18+ + [pnpm](https://pnpm.io)** — for the React web UI (optional)

### Install

The install scripts handle everything: virtual environment, package install, platform data directory, and initial `.env` config.

**macOS / Linux**
```bash
git clone https://github.com/nexustech101/qwen-harness
cd agent-mcp
bash install.sh
```

**Windows (PowerShell)**
```powershell
git clone https://github.com/nexustech101/qwen-harness
cd agent-mcp
.\install.ps1
```

**Script options**

| Flag | Description |
|------|-------------|
| `--no-venv` / `-NoVenv` | Use the current Python instead of creating `.venv` |
| `--venv-dir DIR` / `-VenvDir DIR` | Custom venv path (default: `.venv`) |
| `--data-dir DIR` / `-DataDir DIR` | Override platform data directory |
| `--no-frontend` / `-NoFrontend` | Skip Node.js / pnpm check |
| `--dev` / `-Dev` | Install in editable mode (`pip install -e .`) |

**Manual install**
```bash
git clone https://github.com/nexustech101/qwen-harness
cd agent-mcp
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[graph-watch]"
```

### Configure

The install script copies `.env.example` to the platform data directory as `.env`. Edit it before starting the server:

| Platform | Config file location |
|----------|---------------------|
| Windows  | `%LOCALAPPDATA%\agent-mcp\.env` |
| macOS    | `~/Library/Application Support/agent-mcp/.env` |
| Linux    | `~/.local/share/agent-mcp/.env` |

Set your provider and model:
```bash
AGENT_API_LLM_PROVIDER=ollama          # ollama | openai | anthropic
AGENT_API_DEFAULT_MODEL=qwen2.5-coder:7b
# AGENT_API_OPENAI_API_KEY=sk-...
# AGENT_API_ANTHROPIC_API_KEY=sk-ant-...
```

### Run

```bash
# Terminal 1 — activate venv then start the API server
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
agent-api

# Terminal 2 — start the interactive shell
agent

# Terminal 3 (optional) — start the web UI dev server
cd frontend && pnpm dev
```

The API server binds to `http://0.0.0.0:8000`.  
The web UI runs at `http://localhost:5173`.  
The shell connects to `http://127.0.0.1:8000`.

---

## Configuration

All settings use the `AGENT_API_` prefix. The `.env` file is loaded from the platform data directory (see [Install](#install) above), with a CWD `.env` taking precedence for development overrides.

### Data directory

All runtime state is stored in a single platform directory — the agent never writes to your current working directory.

| Platform | Default data directory |
|----------|------------------------|
| Windows  | `%LOCALAPPDATA%\agent-mcp\` |
| macOS    | `~/Library/Application Support/agent-mcp/` |
| Linux    | `~/.local/share/agent-mcp/` |

Override with the `AGENT_DATA_DIR` environment variable.

```
agent-mcp/
├── agent.db          # SQLite — sessions, messages, workflows
├── .env              # your configuration
├── logs/             # agent.log
├── traces/           # per-turn trace events
├── workspaces/       # per-project context memory
└── checkpoints/      # LangGraph state checkpoints
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_DATA_DIR` | *(platform default)* | Override the entire data directory |
| `AGENT_API_LLM_PROVIDER` | `ollama` | LLM backend: `ollama` \| `openai` \| `anthropic` |
| `AGENT_API_DEFAULT_MODEL` | `qwen2.5-coder:7b` | Default model name for the selected provider |
| `AGENT_API_OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server URL |
| `AGENT_API_OPENAI_API_KEY` | — | OpenAI API key (required when provider=openai) |
| `AGENT_API_ANTHROPIC_API_KEY` | — | Anthropic API key (required when provider=anthropic) |
| `AGENT_API_DATABASE_URL` | `sqlite:///<data_dir>/agent.db` | Override the SQLite database path |
| `AGENT_API_MCP_SERVER_NAME` | `Local Agent` | Name shown in MCP clients |
| `AGENT_API_GLOBAL_RATE_LIMIT` | `200/minute` | API rate limit per IP |
| `AGENT_API_LOG_LEVEL` | `INFO` | Logging verbosity |
| `AGENT_API_LOG_JSON` | `false` | Emit structured JSON logs |
| `AGENT_API_BASE_URL` | `http://127.0.0.1:8000` | API base URL used by the shell |
| `AGENT_LOG_FILE` | `<data_dir>/logs/agent.log` | Shell log file path |
| `AGENT_WORKSPACE_HOME` | `<data_dir>/workspaces` | Project workspace root |
| `AGENT_TRACE_DIR` | `<data_dir>/traces` | Trace event output directory |

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
<sub>Built with FastAPI · LangGraph · FastMCP · Ollama · OpenAI · Anthropic · React · TypeScript · SQLite</sub>
</div>
