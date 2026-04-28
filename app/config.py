"""
Centralized configuration for the coding agent.

All settings loaded from environment variables with sensible defaults.
Trust model
-----------
The LLM is treated as a **semi-trusted actor**: it may hallucinate paths,
generate wrong code, or misuse tools, but is NOT assumed to be adversarial.
Guardrails (path sandboxing, command allowlist) exist to prevent accidental
damage, not to resist deliberate exploitation.  Users accept that run_command
can execute arbitrary logic within the allowed command set.  For untrusted
model scenarios, run the entire agent inside a container."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the app/ directory (next to this file)
load_dotenv(Path(__file__).parent / ".env")


def _resolve_ollama_host() -> str:
    """Resolve the Ollama host URL, normalizing bind addresses like 0.0.0.0."""
    raw = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    raw = raw.replace("0.0.0.0", "127.0.0.1")
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    return raw


# ── Model & API ────────────────────────────────────────────────────────────────
OLLAMA_HOST: str = _resolve_ollama_host()

# Universal fallback model (used when role-specific models are not set).
# AGENT_DEFAULT_MODEL allows a stable baseline while AGENT_MODEL can override.
DEFAULT_MODEL: str = os.getenv("AGENT_DEFAULT_MODEL", "qwen2.5-coder:7b")
MODEL: str = os.getenv("AGENT_MODEL", DEFAULT_MODEL)

# Role-specific models — fall back to MODEL if not set
PLANNER_MODEL: str = os.getenv("AGENT_PLANNER_MODEL", "") or MODEL
CODER_MODEL: str = os.getenv("AGENT_CODER_MODEL", "") or MODEL

# Router / context / tool exposure policies
ROUTER_MODE: str = os.getenv("AGENT_ROUTER_MODE", "rule_first").strip().lower()
if ROUTER_MODE not in {"rule_first", "hybrid", "planner_first"}:
    ROUTER_MODE = "rule_first"

CONTEXT_MODE: str = os.getenv("AGENT_CONTEXT_MODE", "session_rolling").strip().lower()
if CONTEXT_MODE not in {"session_rolling", "session_only", "persistent"}:
    CONTEXT_MODE = "session_rolling"

TOOL_SCOPE_MODE: str = os.getenv("AGENT_TOOL_SCOPE_MODE", "dynamic").strip().lower()
if TOOL_SCOPE_MODE not in {"dynamic", "all"}:
    TOOL_SCOPE_MODE = "dynamic"

# ── Agent Loop ─────────────────────────────────────────────────────────────────
MAX_TURNS: int = int(os.getenv("AGENT_MAX_TURNS", "30"))
MAX_PARSE_RETRIES: int = 2
MAX_PLAIN_NUDGES: int = 2  # plain-text nudges before treating as "done"
MAX_MESSAGES: int = int(os.getenv("AGENT_MAX_MESSAGES", "30"))
IDENTICAL_CALL_THRESHOLD: int = 3

# ── Sub-Agent / Dispatch ───────────────────────────────────────────────────────
SUB_AGENT_MAX_TURNS: int = int(os.getenv("AGENT_SUB_MAX_TURNS", "10"))
MAX_CONCURRENT_AGENTS: int = int(os.getenv("AGENT_MAX_CONCURRENT", "3"))
WORKSPACE_DIR: str = os.getenv("AGENT_WORKSPACE_DIR", ".qwen-coder")
WORKSPACE_HOME: str = os.getenv(
    "AGENT_WORKSPACE_HOME",
    str((Path.home() / WORKSPACE_DIR).resolve()),
)
WORKSPACE_PROJECTS_DIR: str = os.getenv(
    "AGENT_WORKSPACE_PROJECTS_DIR",
    str((Path(WORKSPACE_HOME) / "workspaces").resolve()),
)
WORKSPACE_INDEX_FILE: str = os.getenv(
    "AGENT_WORKSPACE_INDEX_FILE",
    str((Path(WORKSPACE_HOME) / "workspace_index.json").resolve()),
)
MAX_DECOMPOSE_AGENTS: int = int(os.getenv("AGENT_MAX_DECOMPOSE_AGENTS", "3"))

# ── File I/O ───────────────────────────────────────────────────────────────────
MAX_READ_LINES: int = int(os.getenv("AGENT_MAX_READ_LINES", "500"))
MAX_READ_BYTES: int = int(os.getenv("AGENT_MAX_READ_BYTES", "50000"))
MAX_TOOL_RESULT_CHARS: int = 500_000
LOG_FILE: str = os.getenv("AGENT_LOG_FILE", "agent.log")

# Context memory limits
CONTEXT_SUMMARY_MAX_CHARS: int = int(os.getenv("AGENT_CONTEXT_SUMMARY_MAX_CHARS", "12000"))
CONTEXT_LOG_MAX_CHARS: int = int(os.getenv("AGENT_CONTEXT_LOG_MAX_CHARS", "40000"))
