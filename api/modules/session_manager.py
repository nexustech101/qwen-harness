"""Session lifecycle management."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from api.modules.uploads import IMAGE_MIME_TYPES, UploadInfo


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Session:
    def __init__(
        self,
        model: str,
        title: str = "New chat",
    ) -> None:
        self.id = str(uuid.uuid4())
        self.title = title
        self.model = model
        self.status = "idle"
        self.created_at = _utc_now()
        self.updated_at = self.created_at

        # In-memory message history: list of {"role", "content", "metadata"}
        self.history: list[dict[str, Any]] = []

        # WebSocket broadcast queues
        self._ws_queues: list[asyncio.Queue[dict]] = []
        self._lock = threading.Lock()

        # Running task handle
        self._task: asyncio.Task[None] | None = None

        # Staged uploads
        self._uploads: dict[str, UploadInfo] = {}

    # ── WebSocket pub/sub ──────────────────────────────────────────────────────

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

    def broadcast(self, event: dict[str, Any]) -> None:
        """Push an event to all subscribed WebSocket queues (thread-safe)."""
        loop: asyncio.AbstractEventLoop | None = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        with self._lock:
            queues = list(self._ws_queues)

        for queue in queues:
            if loop:
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, event)
                except Exception:
                    pass
            else:
                try:
                    queue.put_nowait(event)
                except Exception:
                    pass

    # ── Upload helpers ─────────────────────────────────────────────────────────

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
        """Inline text attachments into the prompt; return image paths separately."""
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
                ext = info.path.suffix.lstrip(".")
                size_kb = info.size / 1024
                text_parts.append(
                    f"\n--- Attached: {info.filename} ({size_kb:.1f} KB) ---\n"
                    f"```{ext}\n{content}\n```"
                )
            except Exception:
                text_parts.append(f"\n[Attachment: {info.filename} – could not read]")

        return "\n".join(text_parts), image_paths

    def cleanup_uploads(self, attachment_ids: list[str] | None = None) -> None:
        ids = attachment_ids or list(self._uploads.keys())
        for uid in ids:
            self.delete_upload(uid)

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "model": self.model,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.history),
        }


class SessionManager:
    """In-memory store for active sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, model: str, title: str = "New chat") -> Session:
        session = Session(model=model, title=title)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_all(self) -> list[Session]:
        with self._lock:
            return list(self._sessions.values())

    def delete(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        if session._task and not session._task.done():
            session._task.cancel()
        session.cleanup_uploads()
        return True


manager = SessionManager()
