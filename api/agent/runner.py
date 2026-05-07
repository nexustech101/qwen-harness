"""
agent_runner.py — SSE-compatible LangGraph streaming runner.

Maps LangGraph astream_events() onto the existing SSE protocol:
  turn_start, content_delta, thinking_delta, tool_call,
  tool_result, turn_done, stream_end, response_text, error

This is the single async generator that API routes and the chat service
should iterate over.
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from api.agent.graph import get_compiled_graph
from api.agent.state import AgentState
from api.agent.streaming import StreamingParser


def _ev(type_: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": type_, "agent": "main", "data": data, "timestamp": time.time()}


async def run_agent_turn(
    *,
    session_id: str,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    system_prompt: str | None = None,
    tool_profile: str = "default",
    max_turns: int = 10,
    checkpointer=None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Run one agent turn with LangGraph, yielding SSE-compatible event dicts.

    Args:
        session_id:    Unique session identifier (used as LangGraph thread_id).
        provider:      LLM provider — "ollama", "openai", or "anthropic".
        model:         Model name for the provider.
        messages:      Conversation history as list of {"role": ..., "content": ...} dicts.
        system_prompt: Optional system message to prepend if not already present.
        tool_profile:  Named tool set — "default" (full) or "web_research" (web + read-only).
        max_turns:     Maximum tool-call rounds before forcing a final response.
        checkpointer:  Optional AsyncSqliteSaver for stateful runs.
    """
    graph = get_compiled_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": session_id}}

    # Convert dict messages to LangChain message objects
    lc_messages: list = []
    if system_prompt:
        lc_messages.append(SystemMessage(content=system_prompt))
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))

    initial_state: AgentState = {
        "messages": lc_messages,
        "session_id": session_id,
        "provider": provider,
        "model": model,
        "tool_profile": tool_profile,
        "tool_calls_made": 0,
        "max_turns": max_turns,
        "status": "running",
    }

    yield _ev("turn_start", {"session_id": session_id, "model": model, "provider": provider})

    t_start = time.monotonic()
    streaming_parser = StreamingParser()
    accumulated_content = ""

    try:
        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            kind = event.get("event", "")
            name = event.get("name", "")
            data = event.get("data", {})

            # ── LLM streaming tokens ──────────────────────────────────────────
            if kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                if chunk and hasattr(chunk, "content"):
                    raw = chunk.content
                    if isinstance(raw, str) and raw:
                        accumulated_content += raw
                        for seg_kind, delta in streaming_parser.feed(raw):
                            ev_type = "thinking_delta" if seg_kind == "thinking" else "content_delta"
                            yield _ev(ev_type, {"text": delta})
                    elif isinstance(raw, list):
                        # Anthropic streaming chunks may be block lists
                        for block in raw:
                            if isinstance(block, dict):
                                if block.get("type") == "text":
                                    text = block.get("text", "")
                                    if text:
                                        accumulated_content += text
                                        for seg_kind, delta in streaming_parser.feed(text):
                                            ev_type = "thinking_delta" if seg_kind == "thinking" else "content_delta"
                                            yield _ev(ev_type, {"text": delta})
                                elif block.get("type") == "thinking":
                                    thinking_text = block.get("thinking", "")
                                    if thinking_text:
                                        yield _ev("thinking_delta", {"text": thinking_text})

            # ── Tool call started ─────────────────────────────────────────────
            elif kind == "on_tool_start":
                tool_input = data.get("input", {})
                # If the model emitted JSON text as a pseudo-tool-call, that text
                # was streamed as content_delta.  Clear it — it's not the response.
                if accumulated_content.strip().startswith("{"):
                    accumulated_content = ""
                    streaming_parser = StreamingParser()  # reset parser state too
                    yield _ev("clear_content", {})
                yield _ev("tool_call", {"tool": name, "args": tool_input})

            # ── Tool call finished ────────────────────────────────────────────
            elif kind == "on_tool_end":
                tool_output = data.get("output", "")
                yield _ev("tool_result", {"tool": name, "result": str(tool_output)})

        # Flush streaming parser lookahead
        for seg_kind, delta in streaming_parser.flush():
            ev_type = "thinking_delta" if seg_kind == "thinking" else "content_delta"
            yield _ev(ev_type, {"text": delta})

        if accumulated_content:
            yield _ev("response_text", {"text": accumulated_content})

        elapsed = time.monotonic() - t_start
        yield _ev("turn_done", {"elapsed": round(elapsed, 3)})
        yield _ev("stream_end", {"elapsed": round(elapsed, 3)})

    except Exception as exc:
        yield _ev("error", {"message": str(exc)})
        yield _ev("stream_end", {"elapsed": round(time.monotonic() - t_start, 3)})
