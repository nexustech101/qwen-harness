"""
Platform-aware data-directory resolution for agent-mcp.

The resolved directory is used for:
  - SQLite database         → <data_dir>/agent.db
  - API / CLI log files     → <data_dir>/logs/
  - LangGraph checkpoints   → <data_dir>/checkpoints/
  - Project workspaces      → <data_dir>/workspaces/
  - Trace event files       → <data_dir>/traces/

Platform defaults
-----------------
Windows  : %LOCALAPPDATA%\\agent-mcp\\
macOS    : ~/Library/Application Support/agent-mcp/
Linux    : $XDG_DATA_HOME/agent-mcp/   (fallback: ~/.local/share/agent-mcp/)

Override with the AGENT_DATA_DIR environment variable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_NAME = "agent-mcp"

_SUBDIRS = ("logs", "traces", "workspaces", "checkpoints")


def data_dir() -> Path:
    """Return the platform-appropriate writable data directory (not created)."""
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


def ensure_data_dir() -> Path:
    """Create the data directory and standard subdirectories if absent.

    Safe to call multiple times (idempotent).  Returns the data dir path.
    """
    d = data_dir()
    for sub in ("",) + _SUBDIRS:
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d
