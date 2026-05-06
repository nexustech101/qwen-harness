"""
Chat service — streaming Ollama execution loop with MCP tool dispatch.

`run_session_turn` is the single entry point:
  - streams tokens from Ollama
  - dispatches tool calls via the api/tools/ registry
  - broadcasts TraceEvent-style dicts to the session's WS queues
  - persists messages to the database
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import ollama

from api.config.config import get_settings
from api.db.models import ChatMessage, ChatSession
from api.modules.session_manager import Session
from api.services.response_parser import StreamingParser, parse_response
from api.tools.registry import registry

# Ensure all tool implementations are loaded
import api.tools.file_tools       # noqa: F401
import api.tools.system_tools     # noqa: F401
import api.tools.code_tools       # noqa: F401
import api.tools.analysis_tools   # noqa: F401
import api.tools.workspace_tools  # noqa: F401
import api.tools.web_tools        # noqa: F401

settings = get_settings()


class _TextFn:
    """Fake function object for tool calls emitted as JSON text."""
    __slots__ = ("name", "arguments")

    def __init__(self, name: str, arguments: dict) -> None:
        self.name = name
        self.arguments = arguments


class _TextTC:
    """Fake tool-call object for tool calls emitted as JSON text."""
    __slots__ = ("function",)

    def __init__(self, name: str, arguments: dict) -> None:
        self.function = _TextFn(name, arguments)


def _parse_text_tool_calls(content: str) -> list[_TextTC]:
    """Return mock TCs if *content* contains a JSON-formatted tool call.

    Handles two cases:
    1. Entire (stripped) content is a JSON tool call or list of tool calls.
    2. Content has preamble text (e.g. a filename) followed by a JSON object.
    """
    stripped = content.strip()
    if not stripped:
        return []

    # Fast path: entire content is JSON
    if stripped[0] in ("{", "["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(parsed, dict) and "name" in parsed and "arguments" in parsed:
                return [_TextTC(parsed["name"], parsed["arguments"])]
            if isinstance(parsed, list) and all(
                isinstance(p, dict) and "name" in p and "arguments" in p for p in parsed
            ):
                return [_TextTC(p["name"], p["arguments"]) for p in parsed]

    # Slow path: scan for ALL embedded JSON tool call objects
    decoder = json.JSONDecoder()
    results: list[_TextTC] = []
    pos = 0
    while pos < len(content):
        brace = content.find("{", pos)
        if brace == -1:
            break
        try:
            obj, end_pos = decoder.raw_decode(content, brace)
            if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                results.append(_TextTC(obj["name"], obj["arguments"]))
            pos = end_pos
        except (json.JSONDecodeError, ValueError):
            pos = brace + 1
    return results


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


# ── Tool schema helpers ────────────────────────────────────────────────────────

def _build_tools_list() -> list[dict[str, Any]]:
    """Convert the tool registry into Ollama's tools format."""
    return registry.to_ollama_format()


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
    tools_list = _build_tools_list()

    # Build message list: history + new user message
    messages = list(session.history)
    user_msg: dict[str, Any] = {"role": "user", "content": prompt}
    messages.append(user_msg)
    session.history.append(user_msg)
    persist_message(session.id, "user", prompt)

    yield {"type": "turn_start", "session_id": session.id, "model": session.model}

    session.status = "running"

    t_start = time.monotonic()
    max_tool_rounds = 10  # prevent infinite tool loops
    streaming_parser = StreamingParser()

    for _round in range(max_tool_rounds):
        # ── Stream assistant response ──────────────────────────────────────────
        accumulated_content = ""
        tool_calls_raw: list[Any] = []

        async for chunk in await client.chat(
            model=session.model,
            messages=messages,
            tools=tools_list,
            stream=True,
        ):
            msg = chunk.message

            # Accumulate streamed text and classify thinking vs. content
            if msg.content:
                accumulated_content += msg.content
                for kind, delta in streaming_parser.feed(msg.content):
                    yield {"type": "thinking" if kind == "thinking" else "token", "delta": delta}

            # Collect tool calls (may arrive in last chunk)
            if msg.tool_calls:
                tool_calls_raw.extend(msg.tool_calls)

        # Flush any partial lookahead buffer at end of each streaming round
        for kind, delta in streaming_parser.flush():
            yield {"type": "thinking" if kind == "thinking" else "token", "delta": delta}

        # --- Detect text-format tool calls (models that emit JSON as content) ---
        if not tool_calls_raw:
            text_tcs = _parse_text_tool_calls(accumulated_content)
            if text_tcs:
                tool_calls_raw = text_tcs
                accumulated_content = ""
                yield {"type": "clear_content"}

        # Add assistant message to history
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": accumulated_content}
        if tool_calls_raw:
            assistant_msg["tool_calls"] = [
                {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls_raw
            ]
        messages.append(assistant_msg)
        session.history.append(assistant_msg)
        persist_message(session.id, "assistant", accumulated_content)

        if not tool_calls_raw:
            # No tools — we're done with this turn
            break

        # ── Execute tool calls ─────────────────────────────────────────────────
        for tc in tool_calls_raw:
            tool_name: str = tc.function.name
            tool_args: dict[str, Any] = (
                tc.function.arguments
                if isinstance(tc.function.arguments, dict)
                else {}
            )

            yield {"type": "tool_call", "name": tool_name, "args": tool_args}

            try:
                result = registry.execute(tool_name, tool_args)
                output = str(result.data) if result.success else f"Error: {result.error}"
                success = result.success
            except Exception as exc:
                output = f"Tool error: {exc}"
                success = False

            yield {"type": "tool_result", "name": tool_name, "success": success, "output": output}

            tool_msg: dict[str, Any] = {"role": "tool", "content": output}
            messages.append(tool_msg)
            session.history.append(tool_msg)
            persist_message(session.id, "tool", output, metadata={"tool": tool_name, "success": success})

    elapsed = time.monotonic() - t_start
    session.status = "idle"
    session.updated_at = _utc_now()
    persist_session(session)

    # Parse the final assistant message for structured metadata
    parsed = parse_response(accumulated_content)
    yield {
        "type": "turn_done",
        "elapsed_seconds": round(elapsed, 3),
        "has_thinking": parsed.has_thinking,
        "thinking_chars": len(parsed.thinking),
    }
