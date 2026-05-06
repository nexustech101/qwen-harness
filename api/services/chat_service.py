"""
Chat service — streaming Ollama execution loop for the frontend chat interface.

`run_session_turn` is the single entry point:
  - streams tokens from Ollama
  - broadcasts TraceEvent-style dicts to the session's WS queues
  - persists messages to the database

Note: No system-level tools (file, code, system) are exposed here. The frontend
chat is a conversational interface for automation tasks. MCP tools are handled
separately by the MCP server.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import ollama

from api.config.config import get_settings
from api.db.models import ChatMessage, ChatSession
from api.modules.session_manager import Session, manager
from api.services.response_parser import StreamingParser

settings = get_settings()

_SYSTEM_PROMPT = """\
You are a helpful automation assistant. You help users plan, discuss, and reason \
about automation tasks and workflows. You are conversational and concise.

Rules:
- Do NOT attempt to call any tools, read files, or execute code on your own initiative.
- Do NOT produce JSON tool-call objects or structured function calls.
- Respond in plain natural language.
- If a user wants you to perform an action, describe what you would do and ask them \
to trigger the appropriate automation.
""".strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── DB helpers ─────────────────────────────────────────────────────────────────

def persist_session(session: Session) -> None:
    """Upsert a ChatSession row from an in-memory Session."""
    now = _utc_now()
    if ChatSession.schema_exists():
        try:
            row = ChatSession.objects.require(id=session.id)
            row.title = session.title
            row.model = session.model
            row.status = session.status
            row.updated_at = now
            row.save()
        except Exception:
            ChatSession.objects.create(
                id=session.id,
                title=session.title,
                model=session.model,
                status=session.status,
                created_at=session.created_at,
                updated_at=now,
            )


def persist_message(session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
    if ChatMessage.schema_exists():
        ChatMessage.objects.create(
            session_id=session_id,
            role=role,
            content=content,
            metadata=json.dumps(metadata) if metadata else None,
            created_at=_utc_now(),
        )


def load_messages(session_id: str) -> list[dict[str, Any]]:
    """Return stored messages as Ollama-compatible dicts."""
    if not ChatMessage.schema_exists():
        return []
    rows = ChatMessage.objects.filter(session_id=session_id, order_by="id")
    return [{"role": row.role, "content": row.content} for row in rows]


def list_sessions() -> list[ChatSession]:
    if not ChatSession.schema_exists():
        return []
    return ChatSession.objects.filter(order_by="-created_at")


def get_session(session_id: str) -> ChatSession | None:
    if not ChatSession.schema_exists():
        return None
    try:
        return ChatSession.objects.require(id=session_id)
    except Exception:
        return None


def delete_session(session_id: str) -> bool:
    if not ChatSession.schema_exists():
        return False
    try:
        ChatMessage.objects.delete_where(session_id=session_id)
        ChatSession.objects.delete(session_id)
        return True
    except Exception:
        return False


def get_messages_for_api(session_id: str) -> list[dict[str, Any]]:
    """Return persisted messages formatted for the frontend API (with timestamps)."""
    if not ChatMessage.schema_exists():
        return []
    rows = ChatMessage.objects.filter(session_id=session_id, order_by="id")
    result = []
    for row in rows:
        if row.role not in ("user", "assistant"):
            continue
        ts: float | None = None
        try:
            ts = datetime.fromisoformat(row.created_at).timestamp()
        except Exception:
            pass
        result.append({
            "role": row.role,
            "content": row.content,
            "timestamp": ts,
            "metadata": json.loads(row.metadata) if row.metadata else None,
        })
    return result


def restore_session(session_id: str) -> Session | None:
    """Load a session from the DB into the in-memory manager if not already present."""
    existing = manager.get(session_id)
    if existing:
        return existing

    db_row = get_session(session_id)
    if db_row is None:
        return None

    # Construct a Session without calling __init__ (which generates a new UUID)
    session: Session = Session.__new__(Session)
    session.id = db_row.id
    session.title = db_row.title
    session.model = db_row.model
    session.status = "idle"
    session.created_at = db_row.created_at
    session.updated_at = db_row.updated_at
    session.history = load_messages(session_id)
    session._ws_queues = []
    session._lock = threading.Lock()
    session._task = None
    session._uploads = {}

    manager.register(session)
    return session


# ── Tool schema helpers ────────────────────────────────────────────────────────

# ── Core streaming loop ────────────────────────────────────────────────────────

async def run_session_turn(
    session: Session,
    prompt: str,
) -> AsyncIterator[dict[str, Any]]:
    """
    Run one user turn on *session*, yielding TraceEvent-style dicts.

    Callers should iterate and broadcast each event to WS queues as well
    as send them over HTTP/SSE.
    """
    client = ollama.AsyncClient(host=settings.ollama_host)

    # Build message list: system prompt + history + new user message
    # No tools are passed — the frontend chat is conversational only.
    messages: list[dict[str, Any]] = []
    if not session.history or session.history[0].get("role") != "system":
        messages.append({"role": "system", "content": _SYSTEM_PROMPT})
    messages.extend(session.history)
    user_msg: dict[str, Any] = {"role": "user", "content": prompt}
    messages.append(user_msg)
    session.history.append(user_msg)
    persist_message(session.id, "user", prompt)

    def _ev(type_: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": type_, "agent": "main", "data": data, "timestamp": time.time()}

    yield _ev("turn_start", {"session_id": session.id, "model": session.model})

    session.status = "running"

    t_start = time.monotonic()
    streaming_parser = StreamingParser()
    accumulated_content = ""

    async for chunk in await client.chat(
        model=session.model,
        messages=messages,
        stream=True,
    ):
        msg = chunk.message
        if msg.content:
            accumulated_content += msg.content
            for kind, delta in streaming_parser.feed(msg.content):
                ev_type = "thinking_delta" if kind == "thinking" else "content_delta"
                yield _ev(ev_type, {"text": delta})

    # Flush any partial lookahead buffer
    for kind, delta in streaming_parser.flush():
        ev_type = "thinking_delta" if kind == "thinking" else "content_delta"
        yield _ev(ev_type, {"text": delta})

    # Persist assistant reply
    assistant_msg: dict[str, Any] = {"role": "assistant", "content": accumulated_content}
    messages.append(assistant_msg)
    session.history.append(assistant_msg)
    persist_message(session.id, "assistant", accumulated_content)

    if accumulated_content:
        yield _ev("response_text", {"text": accumulated_content})

    elapsed = time.monotonic() - t_start
    session.status = "idle"
    session.updated_at = _utc_now()
    persist_session(session)

    yield _ev("stream_end", {"elapsed": round(elapsed, 3)})
