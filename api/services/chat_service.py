"""
Chat service — LangGraph-backed streaming execution loop.

`run_session_turn` is the single entry point:
  - delegates to api.agent.runner.run_agent_turn (LangGraph + tools)
  - broadcasts TraceEvent-style dicts to the session's WS queues
  - persists messages to the database
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from api.agent.runner import run_agent_turn
from api.config.config import get_settings
from api.db.models import ChatMessage, ChatSession
from api.modules.session_manager import Session, manager

settings = get_settings()

_SYSTEM_PROMPT = """\
You are a powerful AI coding and automation agent. You have access to tools for \
reading and writing files, running shell commands, searching the workspace, \
fetching URLs, and analysing code.

Use your tools proactively when a task requires it — do not ask the user to perform \
actions you can do yourself. When using tools, briefly state what you are doing, \
execute the tool, then report the result concisely.
""".strip()

_WEB_RESEARCH_SYSTEM_PROMPT = """\
You are a web research assistant with access to real-time internet search and \
browsing tools. You can search the web, fetch and read pages, extract links, \
and conduct multi-source research.

When answering questions:
1. Use web_search to find relevant sources.
2. Use fetch_page to read the full content of important results.
3. Use research_topic for questions that require synthesising multiple sources.
4. Always cite your sources using inline numbers [1], [2], etc. and list them at the end.
5. Distinguish clearly between what you know and what you found in the search results.

You do NOT have access to the local filesystem or shell commands. If asked to \
read or write files, explain that this capability is not available in this context.
""".strip()


def _system_prompt_for_profile(profile: str) -> str:
    """Return the appropriate system prompt for the given tool profile."""
    if profile == "web_research":
        return _WEB_RESEARCH_SYSTEM_PROMPT
    return _SYSTEM_PROMPT


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
    session.tool_profile = getattr(db_row, "tool_profile", "default") or "default"
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
    *,
    original_prompt: str | None = None,
    attachment_ids: list[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Run one agent turn via the LangGraph loop, yielding SSE-compatible event dicts.

    Delegates to api.agent.runner.run_agent_turn so all 39 registered tools are
    available to the model. Events are the same protocol used by runner.py:
    turn_start, content_delta, thinking_delta, tool_call, tool_result,
    response_text, turn_done, stream_end, error.
    """
    # Collect attachment metadata for DB storage (filename/mime/size only)
    attachment_refs: list[dict[str, Any]] = []
    if attachment_ids:
        for uid in attachment_ids:
            info = session.get_upload(uid)
            if info is not None:
                attachment_refs.append({
                    "filename": info.filename,
                    "mime_type": info.mime_type,
                    "size": info.size,
                })

    user_metadata: dict[str, Any] | None = (
        {"attachments": attachment_refs} if attachment_refs else None
    )
    persist_message(
        session.id,
        "user",
        original_prompt if original_prompt is not None else prompt,
        metadata=user_metadata,
    )

    # Build conversation history excluding any system entries
    # (system prompt is passed separately to run_agent_turn)
    history = [m for m in session.history if m.get("role") != "system"]
    user_msg: dict[str, Any] = {"role": "user", "content": prompt}
    all_messages = history + [user_msg]
    session.history.append(user_msg)
    session.status = "running"

    accumulated_content = ""

    async for event in run_agent_turn(
        session_id=session.id,
        provider=settings.llm_provider,
        model=session.model,
        messages=all_messages,
        system_prompt=_system_prompt_for_profile(session.tool_profile),
        tool_profile=session.tool_profile,
        max_turns=10,
    ):
        etype = event.get("type", "")

        if etype == "response_text":
            accumulated_content = event["data"].get("text", "")

        elif etype == "stream_end":
            if accumulated_content:
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": accumulated_content}
                session.history.append(assistant_msg)
                persist_message(session.id, "assistant", accumulated_content)
            session.status = "idle"
            session.updated_at = _utc_now()
            persist_session(session)

        yield event
