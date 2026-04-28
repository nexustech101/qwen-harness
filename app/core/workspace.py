"""
Workspace manager for orchestrator/sub-agent communication and rolling context.

Workspace data is stored in a central system location (configured via
AGENT_WORKSPACE_HOME / AGENT_WORKSPACE_PROJECTS_DIR), with one workspace folder
per project root.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app import config


PROJECT_FILE = "project.md"
PLAN_FILE = "plan.md"
STATUS_FILE = "status.md"
CONTEXT_SUMMARY_FILE = "context_summary.md"
CONTEXT_LOG_FILE = "context_log.md"
WORKSPACE_META_FILE = "workspace_meta.json"

AGENT_TASK_FILE = "task.md"
AGENT_DIRECTIVES_FILE = "directives.md"
AGENT_STATUS_FILE = "status.md"
AGENT_OUTPUT_FILE = "output.md"
AGENT_CONTEXT_FILE = "context.md"
AGENT_HANDOFF_FILE = "handoff.md"


@dataclass
class WorkspaceInfo:
    """Snapshot of workspace state for context injection."""

    root: Path
    project_root: str = ""
    project_name: str = ""
    workspace_key: str = ""
    has_project: bool = False
    has_plan: bool = False
    project_content: str = ""
    plan_content: str = ""
    status_content: str = ""
    context_summary: str = ""
    context_log: str = ""
    agent_dirs: list[str] = field(default_factory=list)


class Workspace:
    """Manages a per-project workspace inside a central workspace store."""

    def __init__(self, project_root: Path | str | None = None) -> None:
        self._project_root = Path(project_root or Path.cwd()).resolve()
        self._project_name = self._project_root.name or "project"
        self._workspace_key = _workspace_key(self._project_root)

        self._home = Path(config.WORKSPACE_HOME).expanduser().resolve()
        self._projects_root = Path(config.WORKSPACE_PROJECTS_DIR).expanduser().resolve()
        self._index_file = Path(config.WORKSPACE_INDEX_FILE).expanduser().resolve()
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
        """Create central workspace directories and register this project."""
        self._home.mkdir(parents=True, exist_ok=True)
        self._projects_root.mkdir(parents=True, exist_ok=True)
        self._base.mkdir(parents=True, exist_ok=True)
        self._write_registry_entry()
        self._write_workspace_meta()
        return self._base

    def is_initialized(self) -> bool:
        return (self._base / PROJECT_FILE).exists()

    def session_upload_dir(self, session_id: str) -> Path:
        self.ensure_exists()
        path = self._base / "uploads" / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def resolve_by_project_name(cls, project_name: str) -> dict[str, str] | None:
        """Return most-recent workspace entry for a project root name."""
        normalized = project_name.strip().lower()
        if not normalized:
            return None

        index_file = Path(config.WORKSPACE_INDEX_FILE).expanduser().resolve()
        if not index_file.exists():
            return None

        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
        except Exception:
            return None

        projects = data.get("projects", {})
        if not isinstance(projects, dict):
            return None

        matches: list[dict] = [
            entry
            for entry in projects.values()
            if isinstance(entry, dict)
            and str(entry.get("project_name", "")).strip().lower() == normalized
        ]
        if not matches:
            return None

        matches.sort(key=lambda e: str(e.get("updated_at", "")), reverse=True)
        selected = matches[0]
        return {
            "project_root": str(selected.get("project_root", "")),
            "project_name": str(selected.get("project_name", "")),
            "workspace_key": str(selected.get("workspace_key", "")),
            "workspace_path": str(selected.get("workspace_path", "")),
        }

    def read_info(self) -> WorkspaceInfo:
        info = WorkspaceInfo(
            root=self._base,
            project_root=str(self._project_root),
            project_name=self._project_name,
            workspace_key=self._workspace_key,
        )

        project_path = self._base / PROJECT_FILE
        if project_path.exists():
            info.has_project = True
            info.project_content = project_path.read_text(encoding="utf-8")

        plan_path = self._base / PLAN_FILE
        if plan_path.exists():
            info.has_plan = True
            info.plan_content = plan_path.read_text(encoding="utf-8")

        status_path = self._base / STATUS_FILE
        if status_path.exists():
            info.status_content = status_path.read_text(encoding="utf-8")

        context_summary_path = self._base / CONTEXT_SUMMARY_FILE
        if context_summary_path.exists():
            info.context_summary = context_summary_path.read_text(encoding="utf-8")

        context_log_path = self._base / CONTEXT_LOG_FILE
        if context_log_path.exists():
            info.context_log = _tail_text(
                context_log_path.read_text(encoding="utf-8"),
                config.CONTEXT_LOG_MAX_CHARS,
            )

        if self._base.exists():
            info.agent_dirs = sorted(
                d.name
                for d in self._base.iterdir()
                if d.is_dir() and d.name.startswith(".qwen-agent-")
            )

        return info

    def write_project(self, content: str) -> Path:
        self.ensure_exists()
        path = self._base / PROJECT_FILE
        path.write_text(content, encoding="utf-8")
        return path

    def write_plan(self, content: str) -> Path:
        self.ensure_exists()
        path = self._base / PLAN_FILE
        path.write_text(content, encoding="utf-8")
        return path

    def write_status(self, content: str) -> Path:
        self.ensure_exists()
        path = self._base / STATUS_FILE
        path.write_text(content, encoding="utf-8")
        return path

    def read_project(self) -> str:
        path = self._base / PROJECT_FILE
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_plan(self) -> str:
        path = self._base / PLAN_FILE
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_status(self) -> str:
        path = self._base / STATUS_FILE
        return path.read_text(encoding="utf-8") if path.exists() else ""

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

    def update_context_summary(
        self,
        repo_facts: list[str] | None = None,
        decisions: list[str] | None = None,
        blockers: list[str] | None = None,
        recent_outcomes: list[str] | None = None,
        pending: list[str] | None = None,
    ) -> Path:
        lines = [
            "# Rolling Context Summary",
            "",
            _section("Repo Facts", repo_facts or []),
            _section("Decisions", decisions or []),
            _section("Open Blockers", blockers or []),
            _section("Recent Outcomes", recent_outcomes or []),
            _section("Pending Work", pending or []),
        ]
        return self.write_context_summary("\n".join(lines))

    def agent_dir(self, agent_name: str) -> Path:
        safe_name = self._sanitize_name(agent_name)
        return self._base / f".qwen-agent-{safe_name}"

    def create_agent_dir(self, agent_name: str) -> Path:
        path = self.agent_dir(agent_name)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_agent_task(self, agent_name: str, content: str) -> Path:
        d = self.create_agent_dir(agent_name)
        path = d / AGENT_TASK_FILE
        path.write_text(content, encoding="utf-8")
        return path

    def write_agent_directives(self, agent_name: str, content: str) -> Path:
        d = self.create_agent_dir(agent_name)
        path = d / AGENT_DIRECTIVES_FILE
        path.write_text(content, encoding="utf-8")
        return path

    def read_agent_task(self, agent_name: str) -> str:
        path = self.agent_dir(agent_name) / AGENT_TASK_FILE
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_agent_directives(self, agent_name: str) -> str:
        path = self.agent_dir(agent_name) / AGENT_DIRECTIVES_FILE
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_agent_status(self, agent_name: str) -> str:
        path = self.agent_dir(agent_name) / AGENT_STATUS_FILE
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_agent_output(self, agent_name: str) -> str:
        path = self.agent_dir(agent_name) / AGENT_OUTPUT_FILE
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def write_agent_status(self, agent_name: str, content: str) -> Path:
        d = self.create_agent_dir(agent_name)
        path = d / AGENT_STATUS_FILE
        path.write_text(content, encoding="utf-8")
        return path

    def write_agent_output(self, agent_name: str, content: str) -> Path:
        d = self.create_agent_dir(agent_name)
        path = d / AGENT_OUTPUT_FILE
        path.write_text(content, encoding="utf-8")
        return path

    def write_agent_handoff(self, agent_name: str, content: str) -> Path:
        d = self.create_agent_dir(agent_name)
        path = d / AGENT_HANDOFF_FILE
        path.write_text(content, encoding="utf-8")
        return path

    def inherit_context(self, new_agent: str, predecessor: str) -> Path:
        pred_output = self.read_agent_output(predecessor)
        pred_status = self.read_agent_status(predecessor)
        pred_task = self.read_agent_task(predecessor)

        lines = [f"# Inherited Context from {predecessor}", ""]
        if pred_task:
            lines.extend(["## Previous Task", pred_task, ""])
        if pred_status:
            lines.extend(["## Previous Status", pred_status, ""])
        if pred_output:
            lines.extend(["## Previous Output", pred_output, ""])

        summary = self.read_context_summary()
        if summary:
            lines.extend(["## Rolling Summary", summary, ""])

        log_tail = _tail_text(self.read_context_log(), 4000)
        if log_tail:
            lines.extend(["## Recent Context Log", log_tail, ""])

        content = "\n".join(lines)
        d = self.create_agent_dir(new_agent)
        path = d / AGENT_CONTEXT_FILE
        path.write_text(content, encoding="utf-8")
        return path

    def read_agent_context(self, agent_name: str) -> str:
        path = self.agent_dir(agent_name) / AGENT_CONTEXT_FILE
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def list_agents(self) -> list[str]:
        if not self._base.exists():
            return []
        return sorted(
            d.name.removeprefix(".qwen-agent-")
            for d in self._base.iterdir()
            if d.is_dir() and d.name.startswith(".qwen-agent-")
        )

    def agent_summary(self, agent_name: str) -> dict[str, str]:
        d = self.agent_dir(agent_name)
        summary: dict[str, str] = {"name": agent_name}

        status_path = d / AGENT_STATUS_FILE
        if status_path.exists():
            text = status_path.read_text(encoding="utf-8")
            summary["status"] = text.splitlines()[0] if text.strip() else "unknown"
        else:
            summary["status"] = "not started"

        output_path = d / AGENT_OUTPUT_FILE
        summary["completed"] = "yes" if output_path.exists() else "no"
        return summary

    @staticmethod
    def _sanitize_name(name: str) -> str:
        safe = name.lower().strip()
        safe = "".join(c if c.isalnum() or c == "-" else "-" for c in safe)
        while "--" in safe:
            safe = safe.replace("--", "-")
        return safe.strip("-") or "agent"

    def _load_index(self) -> dict:
        if not self._index_file.exists():
            return {"version": 1, "projects": {}, "updated_at": _utc_now()}
        try:
            data = json.loads(self._index_file.read_text(encoding="utf-8"))
        except Exception:
            return {"version": 1, "projects": {}, "updated_at": _utc_now()}
        if not isinstance(data, dict):
            return {"version": 1, "projects": {}, "updated_at": _utc_now()}
        if not isinstance(data.get("projects"), dict):
            data["projects"] = {}
        return data

    def _write_index(self, data: dict) -> None:
        self._index_file.parent.mkdir(parents=True, exist_ok=True)
        self._index_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    def _write_registry_entry(self) -> None:
        project_root_str = str(self._project_root)
        now = _utc_now()
        data = self._load_index()
        projects = data.setdefault("projects", {})
        existing = projects.get(project_root_str, {})

        entry = {
            "project_root": project_root_str,
            "project_name": self._project_name,
            "workspace_key": self._workspace_key,
            "workspace_path": str(self._base),
            "created_at": str(existing.get("created_at", now)),
            "updated_at": now,
        }
        projects[project_root_str] = entry
        data["updated_at"] = now
        self._write_index(data)

    def _write_workspace_meta(self) -> None:
        meta = {
            "project_root": str(self._project_root),
            "project_name": self._project_name,
            "workspace_key": self._workspace_key,
            "workspace_path": str(self._base),
            "updated_at": _utc_now(),
        }
        path = self._base / WORKSPACE_META_FILE
        path.write_text(json.dumps(meta, indent=2, ensure_ascii=True), encoding="utf-8")


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


def _section(title: str, items: list[str]) -> str:
    lines = [f"## {title}"]
    if not items:
        lines.append("- (none)")
    else:
        lines.extend(f"- {item}" for item in items)
    return "\n".join(lines) + "\n"
