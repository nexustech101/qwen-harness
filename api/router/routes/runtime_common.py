"""Shared helpers for agent runtime routes."""

from __future__ import annotations

from pathlib import Path
import stat
from typing import Any

from fastapi import HTTPException

from app import config
from api.modules.dependencies import run_db
from api.modules.session_manager import manager
from api.schemas.agent import AgentSummary, SessionResponse, SessionStats

SKIP_DIRS = {
    "__pycache__",
    "node_modules",
    ".git",
    Path(config.WORKSPACE_DIR).name,
    ".venv",
    "venv",
}


def current_user_id(current_user: Any) -> int | None:
    if current_user is None:
        return None
    user_id = getattr(current_user, "id", None)
    return int(user_id) if user_id is not None else None


async def async_require_session(session_id: str, current_user: Any):
    session = await run_db(manager.get, session_id, user_id=current_user_id(current_user))
    if not session:
        raise HTTPException(404, "Session not found")
    return session


def session_to_response(session) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        project_root=session.project_root,
        project_name=session.project_name,
        title=getattr(session, "title", None),
        chat_only=bool(getattr(session, "chat_only", False)),
        workspace_key=session.workspace_key,
        workspace_root=session.workspace_root,
        persistence_mode=session.persistence_mode,
        owner_user_id=session.user_id,
        status=session.status,
        model=session.model,
        created_at=session.created_at,
        stats=SessionStats(**session.get_stats()),
        agents=[
            AgentSummary(
                name=agent.name,
                status=agent.status,
                model=agent.model,
                turns_used=agent.turns_used,
                max_turns=agent.max_turns,
                goal=agent.goal,
            )
            for agent in session.agents.values()
        ],
    )


def build_tree(
    path: Path,
    root: Path,
    max_depth: int = 4,
    depth: int = 0,
    max_entries: int = 1000,
    counter: dict[str, int] | None = None,
) -> list[dict]:
    if depth >= max_depth:
        return []

    if counter is None:
        counter = {"seen": 0}
    root = root.resolve()
    entries: list[dict] = []
    try:
        for item in sorted(path.iterdir(), key=lambda entry: entry.name.lower()):
            if counter["seen"] >= max_entries:
                break
            if item.is_symlink():
                continue

            try:
                item_stat = item.stat(follow_symlinks=False)
            except OSError:
                continue

            is_dir = stat.S_ISDIR(item_stat.st_mode)
            is_file = stat.S_ISREG(item_stat.st_mode)
            if item.name.startswith(".") and is_dir:
                continue
            if item.name in SKIP_DIRS:
                continue
            try:
                if not item.resolve(strict=False).is_relative_to(root):
                    continue
            except OSError:
                continue

            counter["seen"] += 1
            rel_path = item.relative_to(root).as_posix()
            entry: dict[str, Any] = {
                "name": item.name,
                "path": rel_path,
                "type": "directory" if is_dir else "file",
            }
            if is_file:
                entry["size"] = item_stat.st_size
            elif is_dir:
                entry["children"] = build_tree(item, root, max_depth, depth + 1, max_entries, counter)
            entries.append(entry)
    except PermissionError:
        pass

    return entries
