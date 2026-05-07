"""
Workspace manager for orchestrator/sub-agent communication and rolling context.

Workspace data is stored in a central system location (configured via
AGENT_WORKSPACE_HOME / AGENT_WORKSPACE_PROJECTS_DIR), with one workspace folder
per project root.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent import config


CONTEXT_SUMMARY_FILE = "context_summary.md"
CONTEXT_LOG_FILE = "context_log.md"


@dataclass
class WorkspaceInfo:
    """Snapshot of workspace state for context injection."""

    root: Path
    project_root: str = ""
    project_name: str = ""
    workspace_key: str = ""
    context_summary: str = ""
    context_log: str = ""


class Workspace:
    """Manages a per-project workspace inside a central workspace store."""

    def __init__(self, project_root: Path | str | None = None) -> None:
        self._project_root = Path(project_root or Path.cwd()).resolve()
        self._project_name = self._project_root.name or "project"
        self._workspace_key = _workspace_key(self._project_root)

        self._home = Path(config.WORKSPACE_HOME).expanduser().resolve()
        self._projects_root = Path(config.WORKSPACE_PROJECTS_DIR).expanduser().resolve()
        self._base = self._projects_root / self._workspace_key

    @property
    def root(self) -> Path:
        return self._base

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def project_name(self) -> str:
        return self._project_name

    @property
    def workspace_key(self) -> str:
        return self._workspace_key

    @property
    def workspace_home(self) -> Path:
        return self._home

    def ensure_exists(self) -> Path:
        """Create workspace directories."""
        self._home.mkdir(parents=True, exist_ok=True)
        self._projects_root.mkdir(parents=True, exist_ok=True)
        self._base.mkdir(parents=True, exist_ok=True)
        return self._base

    def is_initialized(self) -> bool:
        return self._base.exists()

    def read_info(self) -> WorkspaceInfo:
        info = WorkspaceInfo(
            root=self._base,
            project_root=str(self._project_root),
            project_name=self._project_name,
            workspace_key=self._workspace_key,
        )

        context_summary_path = self._base / CONTEXT_SUMMARY_FILE
        if context_summary_path.exists():
            info.context_summary = context_summary_path.read_text(encoding="utf-8")

        context_log_path = self._base / CONTEXT_LOG_FILE
        if context_log_path.exists():
            info.context_log = _tail_text(
                context_log_path.read_text(encoding="utf-8"),
                config.CONTEXT_LOG_MAX_CHARS,
            )

        return info

    def write_context_summary(self, content: str) -> Path:
        self.ensure_exists()
        path = self._base / CONTEXT_SUMMARY_FILE
        content = _tail_text(content, config.CONTEXT_SUMMARY_MAX_CHARS)
        path.write_text(content, encoding="utf-8")
        return path

    def read_context_summary(self) -> str:
        path = self._base / CONTEXT_SUMMARY_FILE
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def append_context_log(self, title: str, body: str) -> Path:
        self.ensure_exists()
        path = self._base / CONTEXT_LOG_FILE
        timestamp = _utc_now()
        entry = f"## {timestamp} - {title}\n{body.strip()}\n\n"
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        merged = _tail_text(existing + entry, config.CONTEXT_LOG_MAX_CHARS)
        path.write_text(merged, encoding="utf-8")
        return path

    def read_context_log(self) -> str:
        path = self._base / CONTEXT_LOG_FILE
        return path.read_text(encoding="utf-8") if path.exists() else ""

def _workspace_key(project_root: Path) -> str:
    name = project_root.name or "project"
    slug = _slugify(name)
    digest = hashlib.sha1(str(project_root).encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}"


def _slugify(text: str) -> str:
    safe = "".join(c.lower() if c.isalnum() else "-" for c in text.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "project"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tail_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]
