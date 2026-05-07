"""
Centralized configuration for the interactive shell harness.

All settings loaded from environment variables with sensible defaults.
The shell is a thin client — it connects to the API server (uvicorn) for
all model calls and tool execution.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Platform-aware data directory (mirrors api/paths.py — kept independent so
# the CLI package does not need to import from the API package).
# ---------------------------------------------------------------------------

_APP_NAME = "agent-mcp"


def _data_dir() -> Path:
    """Return the centralized data directory for this platform."""
    override = os.environ.get("AGENT_DATA_DIR", "")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        base = Path(local_app_data) if local_app_data else (Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg).expanduser() if xdg else (Path.home() / ".local" / "share")
    return base / _APP_NAME


_DATA_DIR: Path = _data_dir()

# Load .env from the centralized data directory first (installed config), then
# allow a CWD .env to override (development workflow).
load_dotenv(_DATA_DIR / ".env", override=False)
load_dotenv(Path.cwd() / ".env", override=True)


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
WORKSPACE_HOME: str = os.getenv(
    "AGENT_WORKSPACE_HOME",
    str(_DATA_DIR / "workspaces"),
)
WORKSPACE_PROJECTS_DIR: str = os.getenv(
    "AGENT_WORKSPACE_PROJECTS_DIR",
    str(Path(WORKSPACE_HOME)),
)

# ── File I/O limits (used by api/tools/) ──────────────────────────────────────
MAX_READ_LINES: int = int(os.getenv("AGENT_MAX_READ_LINES", "500"))
MAX_READ_BYTES: int = int(os.getenv("AGENT_MAX_READ_BYTES", "50000"))
MAX_TOOL_RESULT_CHARS: int = int(os.getenv("AGENT_MAX_TOOL_RESULT_CHARS", "500000"))

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_FILE: str = os.getenv("AGENT_LOG_FILE", str(_DATA_DIR / "logs" / "agent.log"))

# ── Traces ─────────────────────────────────────────────────────────────────────
TRACE_DIR: str = os.getenv("AGENT_TRACE_DIR", str(_DATA_DIR / "traces"))

# Context memory limits
CONTEXT_SUMMARY_MAX_CHARS: int = int(os.getenv("AGENT_CONTEXT_SUMMARY_MAX_CHARS", "12000"))
CONTEXT_LOG_MAX_CHARS: int = int(os.getenv("AGENT_CONTEXT_LOG_MAX_CHARS", "40000"))
