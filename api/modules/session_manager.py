"""Session lifecycle management that bridges API routes to the core agent."""

from __future__ import annotations

import asyncio
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app import config
from api.modules.runtime_executor import RuntimeExecutor
from api.router.runtime_persistence import (
    load_message_history,
    load_session_record,
    persist_message,
    persist_session,
    persist_status,
    persist_usage_event,
)
from api.modules.uploads import IMAGE_MIME_TYPES, UploadInfo
from app.core.state import AgentResult
from app.core.workspace import Workspace
from app.logging.trace import TraceEvent


class AgentInfo:
    __slots__ = (
        "name",
        "model",
        "goal",
        "max_turns",
        "status",
        "turns_used",
        "messages",
        "tool_calls",
        "files_modified",
    )

    def __init__(self, name: str, model: str, goal: str, max_turns: int) -> None:
        self.name = name
        self.model = model
        self.goal = goal
        self.max_turns = max_turns
        self.status = "idle"
        self.turns_used = 0
        self.messages: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []
        self.files_modified: list[str] = []


class Session:
    def __init__(
        self,
        project_root: str,
        user_id: int | None = None,
        persistence_mode: str = "guest",
        model: str | None = None,
        planner_model: str | None = None,
        coder_model: str | None = None,
        max_turns: int | None = None,
        use_dispatch: bool = False,
        async_dispatch: bool = False,
        title: str | None = None,
        chat_only: bool = False,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.project_root = str(Path(project_root).resolve())
        self.user_id = user_id
        self.persistence_mode = persistence_mode if persistence_mode in {"guest", "persistent"} else "guest"
        self.title = title
        self.chat_only = chat_only
        self.status = "idle"
        self.created_at = time.time()
        self.model = model or config.MODEL
        self.workspace = Workspace(project_root=self.project_root)
        self.workspace.ensure_exists()
        self.project_name = title or self.workspace.project_name
        self.workspace_key = self.workspace.workspace_key
        self.workspace_root = str(self.workspace.root)

        self._config = {
            "model": model,
            "planner_model": planner_model,
            "coder_model": coder_model,
            "max_turns": max_turns,
            "use_dispatch": use_dispatch,
            "async_dispatch": async_dispatch,
        }

        self.agents: dict[str, AgentInfo] = {}
        self.history: list[dict[str, Any]] = []
        self.last_result: AgentResult | None = None

        self._ws_queues: list[asyncio.Queue[dict]] = []
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

        self._task: asyncio.Task[AgentResult] | None = None
        self._executor: RuntimeExecutor | None = None

        self._uploads: dict[str, UploadInfo] = {}

    @property
    def is_persistent(self) -> bool:
        return self.persistence_mode == "persistent" and self.user_id is not None

    @property
    def uploads_dir(self) -> Path:
        return self.workspace.session_upload_dir(self.id)

    def add_upload(self, info: UploadInfo) -> UploadInfo:
        if info.session_id != self.id:
            raise ValueError("Upload belongs to a different session")
        self._uploads[info.id] = info
        return info

    def get_upload(self, upload_id: str) -> UploadInfo | None:
        return self._uploads.get(upload_id)

    def delete_upload(self, upload_id: str) -> bool:
        info = self._uploads.pop(upload_id, None)
        if info and info.path.exists():
            info.path.unlink(missing_ok=True)
        return True

    def resolve_attachments(self, prompt: str, attachment_ids: list[str]) -> tuple[str, list[str]]:
        text_parts: list[str] = [prompt]
        image_paths: list[str] = []

        for attachment_id in attachment_ids:
            info = self._uploads.get(attachment_id)
            if not info or not info.path.exists():
                continue

            if info.mime_type in IMAGE_MIME_TYPES:
                image_paths.append(str(info.path.resolve()))
                continue

            try:
                content = info.path.read_text(encoding="utf-8", errors="replace")
                size_kb = info.size / 1024
                ext = info.path.suffix.lstrip(".")
                text_parts.append(
                    f"\n--- Attached file: {info.filename} ({size_kb:.1f} KB) ---\n"
                    f"```{ext}\n{content}\n```"
                )
            except Exception:
                text_parts.append(f"\n[Attachment: {info.filename} - could not read]")

        return "\n".join(text_parts), image_paths

    def cleanup_uploads(self, attachment_ids: list[str] | None = None) -> None:
        ids = attachment_ids or list(self._uploads.keys())
        for attachment_id in ids:
            self.delete_upload(attachment_id)

    def cleanup_all_uploads(self) -> None:
        upload_dir = self.workspace.root / "uploads" / self.id
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
        self._uploads.clear()

    async def _persist_message(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        agent_name: str | None = None,
    ) -> None:
        if not self.is_persistent:
            return
        await asyncio.to_thread(
            persist_message,
            session_id=self.id,
            user_id=int(self.user_id),  # type: ignore[arg-type]
            role=role,
            content=content,
            metadata=metadata,
            agent_name=agent_name,
        )

    async def _persist_status(self, status: str) -> None:
        if not self.is_persistent:
            return
        await asyncio.to_thread(
            persist_status,
            session_id=self.id,
            user_id=int(self.user_id),  # type: ignore[arg-type]
            status=status,
        )

    async def _persist_usage_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        if not self.is_persistent:
            return
        await asyncio.to_thread(
            persist_usage_event,
            event_type=event_type,
            session_id=self.id,
            user_id=int(self.user_id),  # type: ignore[arg-type]
            payload=payload,
        )

    def subscribe(self) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        with self._lock:
            self._ws_queues.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        with self._lock:
            try:
                self._ws_queues.remove(queue)
            except ValueError:
                pass

    def _bridge_event(self, event: TraceEvent) -> None:
        agent_name = "main"
        event_type = event.event_type

        if event_type.startswith("sub_"):
            agent_name = event.data.get("agent_name", "unknown")
            event_type = event_type[4:]

        ws_event: dict[str, Any] = {
            "type": event_type,
            "agent": agent_name,
            "data": _safe_serialize(event.data),
            "timestamp": event.timestamp,
        }

        self._update_agent_from_event(event_type, agent_name, event.data)

        loop = self._loop
        if loop:
            with self._lock:
                for queue in self._ws_queues:
                    try:
                        loop.call_soon_threadsafe(queue.put_nowait, ws_event)
                    except Exception:
                        pass

    def _update_agent_from_event(self, event_type: str, agent_name: str, data: dict[str, Any]) -> None:
        if event_type == "agent_start":
            info = AgentInfo(
                name=agent_name,
                model=data.get("model", self.model),
                goal=data.get("prompt", ""),
                max_turns=data.get("max_turns", config.MAX_TURNS),
            )
            info.status = "running"
            self.agents[agent_name] = info
            return

        if event_type == "agent_done":
            agent = self.agents.get(agent_name)
            if agent:
                reason = data.get("reason", "done")
                agent.status = "done" if reason == "done" else reason
                agent.turns_used = data.get("turns", 0)
            return

        if event_type == "tool_dispatch":
            agent = self.agents.get(agent_name)
            if agent:
                agent.tool_calls.append(
                    {
                        "name": data.get("name"),
                        "args": data.get("args", {}),
                    }
                )
            return

        if event_type == "tool_result":
            agent = self.agents.get(agent_name)
            if agent and data.get("success"):
                tool_name = data.get("name", "")
                if tool_name in {"write_file", "edit_file"}:
                    path = data.get("args", {}).get("path", "")
                    if path:
                        agent.files_modified.append(path)

    async def run_prompt(self, prompt: str, direct: bool = False, images: list[str] | None = None) -> AgentResult:
        self.status = "running"
        await self._persist_status("running")
        await self._persist_usage_event(
            "conversation.run_started",
            {
                "direct": direct,
                "image_count": len(images or []),
                "prompt_length": len(prompt),
                "model": self.model,
            },
        )
        self._loop = asyncio.get_running_loop()

        self.history.append({"role": "user", "content": prompt, "timestamp": time.time()})
        await self._persist_message("user", prompt)

        self._executor = RuntimeExecutor(
            project_root=self.project_root,
            config_values=self._config,
            event_callback=self._bridge_event,
        )
        try:
            execution = await self._executor.run(prompt=prompt, direct=direct, images=images)
            result = execution.result
            for name, messages in execution.agent_messages.items():
                agent = self.agents.get(name)
                if agent:
                    agent.messages = messages
            self.last_result = result
            assistant_metadata = {
                "turns": result.turns,
                "reason": result.reason,
                "tool_calls_made": result.tool_calls_made,
                "files_modified": result.files_modified,
                "elapsed_seconds": result.elapsed_seconds,
            }
            self.history.append(
                {
                    "role": "assistant",
                    "content": result.result or "",
                    "timestamp": time.time(),
                    "metadata": assistant_metadata,
                }
            )
            await self._persist_message("assistant", result.result or "", metadata=assistant_metadata)
            await self._persist_usage_event("conversation.run_completed", assistant_metadata)
            self.status = "idle"
            await self._persist_status("idle")
            return result
        except asyncio.CancelledError:
            self.status = "cancelled"
            await self._persist_usage_event("conversation.run_cancelled", {"reason": "cancelled"})
            await self._persist_status("cancelled")
            raise
        except Exception as exc:
            self.status = "error"
            self.history.append({"role": "error", "content": str(exc), "timestamp": time.time()})
            await self._persist_message("error", str(exc))
            await self._persist_usage_event(
                "conversation.run_failed",
                {"error_type": type(exc).__name__, "error": str(exc)},
            )
            await self._persist_status("error")
            raise
        finally:
            self._executor = None

    def get_stats(self) -> dict[str, Any]:
        total_turns = sum(agent.turns_used for agent in self.agents.values())
        total_tool_calls = sum(len(agent.tool_calls) for agent in self.agents.values())
        files_modified: list[str] = []
        elapsed_seconds = self.last_result.elapsed_seconds if self.last_result else 0.0
        for agent in self.agents.values():
            files_modified.extend(agent.files_modified)
        return {
            "total_turns": total_turns,
            "total_tool_calls": total_tool_calls,
            "elapsed_seconds": elapsed_seconds,
            "files_modified": list(set(files_modified)),
            "message_count": len(self.history),
        }

    def get_live_messages(self, agent_name: str) -> list[dict]:
        agent = self.agents.get(agent_name)
        return agent.messages if agent else []


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, **kwargs: Any) -> Session:
        session = Session(**kwargs)
        persist_session(session)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str, user_id: int | None = None) -> Session | None:
        with self._lock:
            session = self._sessions.get(session_id)
        if session:
            if session.user_id is None and user_id is not None:
                return None
            if session.user_id is not None and session.user_id != user_id:
                return None
            return session

        if user_id is None:
            return None
        return self._hydrate_persistent_session(session_id, user_id)

    def list_all(self, user_id: int | None = None) -> list[Session]:
        with self._lock:
            sessions = list(self._sessions.values())
        if user_id is None:
            return [session for session in sessions if session.user_id is None]
        return [session for session in sessions if session.user_id == user_id]

    def delete(self, session_id: str, user_id: int | None = None) -> bool:
        session = self.get(session_id, user_id=user_id)
        if session is None:
            return False

        with self._lock:
            self._sessions.pop(session_id, None)
        if session._task and not session._task.done():
            session._task.cancel()
        session.cleanup_all_uploads()

        return True

    def forget(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.pop(session_id, None)

    def _hydrate_persistent_session(self, session_id: str, user_id: int) -> Session | None:
        try:
            stored = load_session_record(session_id, user_id)
        except Exception:
            return None

        session = Session(
            project_root=stored.project_root,
            user_id=user_id,
            persistence_mode="persistent",
            model=stored.model,
            use_dispatch=False,
            async_dispatch=False,
            title=stored.project_name,
            chat_only=Path(stored.project_root).name == "chat-sessions",
        )
        session.id = stored.id
        session.status = stored.status
        session.created_at = _iso_to_unix(stored.created_at) or time.time()
        session.project_name = stored.project_name or session.project_name
        session.workspace_key = stored.workspace_key or session.workspace_key
        session.workspace_root = stored.workspace_root or session.workspace_root

        try:
            rows = load_message_history(session_id, user_id)
            session.history = [
                {
                    "role": row.role,
                    "content": row.content,
                    "timestamp": _iso_to_unix(row.created_at) or time.time(),
                    "metadata": row.metadata,
                }
                for row in rows
            ]
        except Exception:
            session.history = []

        with self._lock:
            self._sessions[session.id] = session
        return session


manager = SessionManager()


def _safe_serialize(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_serialize(v) for k, v in value.items()}
    return str(value)


def _iso_to_unix(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None
