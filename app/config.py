"""
Centralized configuration for the interactive shell harness.

All settings loaded from environment variables with sensible defaults.
The shell is a thin client — it connects to the API server (uvicorn) for
all model calls and tool execution.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _resolve_ollama_host() -> str:
    raw = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    raw = raw.replace("0.0.0.0", "127.0.0.1")
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    return raw


# ── API server the shell connects to ──────────────────────────────────────────
API_BASE_URL: str = os.getenv("AGENT_API_BASE_URL", "http://127.0.0.1:8000")

# ── Ollama (used only for model listing in the shell when API is unreachable) ──
OLLAMA_HOST: str = _resolve_ollama_host()

# ── Model defaults ─────────────────────────────────────────────────────────────
DEFAULT_MODEL: str = os.getenv("AGENT_DEFAULT_MODEL", "qwen2.5-coder:7b")
MODEL: str = os.getenv("AGENT_MODEL", DEFAULT_MODEL)

# ── Workspace ─────────────────────────────────────────────────────────────────
_WORKSPACE_DIR: str = os.getenv("AGENT_WORKSPACE_DIR", ".agent")
WORKSPACE_HOME: str = os.getenv(
    "AGENT_WORKSPACE_HOME",
    str((Path.home() / _WORKSPACE_DIR).resolve()),
)
WORKSPACE_PROJECTS_DIR: str = os.getenv(
    "AGENT_WORKSPACE_PROJECTS_DIR",
    str((Path(WORKSPACE_HOME) / "workspaces").resolve()),
)

# ── File I/O limits (used by api/tools/) ──────────────────────────────────────
MAX_READ_LINES: int = int(os.getenv("AGENT_MAX_READ_LINES", "500"))
MAX_READ_BYTES: int = int(os.getenv("AGENT_MAX_READ_BYTES", "50000"))
MAX_TOOL_RESULT_CHARS: int = int(os.getenv("AGENT_MAX_TOOL_RESULT_CHARS", "500000"))

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_FILE: str = os.getenv("AGENT_LOG_FILE", "agent.log")

# Context memory limits
CONTEXT_SUMMARY_MAX_CHARS: int = int(os.getenv("AGENT_CONTEXT_SUMMARY_MAX_CHARS", "12000"))
CONTEXT_LOG_MAX_CHARS: int = int(os.getenv("AGENT_CONTEXT_LOG_MAX_CHARS", "40000"))
