"""
Execution engine — the turn-by-turn agent loop.
"""

from __future__ import annotations

import json
import time

import ollama

from app import config
from app.core.state import AgentResult, AgentState, ToolCall, TurnState
from app.logging.trace import Trace
from app.response.response_parser import ResponseParser
from app.response.schema_validator import SchemaValidator
from app.tools.registry import ToolRegistry


class ExecutionEngine:
    """Runs the agent loop: model call -> parse -> validate -> execute tools -> repeat."""

    def __init__(
        self,
        registry: ToolRegistry,
        trace: Trace,
        system_prompt: str,
        model: str | None = None,
        max_turns: int | None = None,
    ) -> None:
        self._registry = registry
        self._trace = trace
        self._system_prompt = system_prompt
        self._model = model or config.MODEL
        self._max_turns = max_turns or config.MAX_TURNS
        self._parser = ResponseParser(
            known_tools={t.name for t in registry.list_tools()}
        )
        self._validator = SchemaValidator(registry)
        self._client = ollama.Client(host=config.OLLAMA_HOST)
        self._files_modified: list[str] = []
        self._graph_dirty_paths: list[str] = []
        self._graph_preflight_done = False
        self._graph_service = None
        self._messages: list[dict] = []  # live message buffer (exposed for API)

    def run(
        self, user_message: str, images: list[str] | None = None,
    ) -> AgentResult:
        """Execute the agent loop until completion or limit."""
        start_time = time.monotonic()
        state = AgentState(max_turns=self._max_turns)

        user_msg: dict = {"role": "user", "content": user_message}
        if images:
            user_msg["images"] = images

        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt},
            user_msg,
        ]
        self._messages = messages

        self._trace.emit(
            "agent_start",
            model=self._model,
            prompt=user_message,
            max_turns=self._max_turns,
        )

        last_tool_sig = ""
        identical_count = 0
        consecutive_plain = 0

        while state.total_turns < state.max_turns:
            state.total_turns += 1
            turn = TurnState(turn_number=state.total_turns)
            self._trace.emit("turn_start", turn=state.total_turns, phase=state.phase)

            tool_categories = self._select_tool_categories(state)
            tools_for_turn = self._registry.to_ollama_format(categories=tool_categories)
            self._ensure_graph_ready()

            self._trace.emit(
                "model_call",
                message_count=len(messages),
                phase=state.phase,
                tool_categories=tool_categories,
            )
            t0 = time.monotonic()

            try:
                content, native_calls, stream_thinking, _stream_stats = self._stream_chat(
                    messages,
                    tools_for_turn,
                )
            except KeyboardInterrupt:
                raise
            except Exception as e:
                self._trace.emit("error", error=f"Model call failed: {e}")
                return self._finish(state, start_time, "model_error", str(e))

            elapsed_ms = (time.monotonic() - t0) * 1000

            parsed = self._parser.parse(content, native_calls, stream_thinking=stream_thinking)
            turn.model_response = content
            turn.parsed_reasoning = parsed.reasoning
            turn.parsed_response = parsed.response
            turn.parsed_tools = parsed.tool_calls

            diagnostics = dict(parsed.diagnostics)
            parse_mode = diagnostics.pop("parse_mode", parsed.mode)
            self._trace.emit(
                "model_reply",
                parse_mode=parse_mode,
                elapsed_ms=elapsed_ms,
                status=parsed.status,
                **diagnostics,
            )

            if parsed.reasoning:
                self._trace.emit("reasoning", text=parsed.reasoning)

            if not parsed.tool_calls:
                final = parsed.response or parsed.reasoning or content.strip()

                if (
                    final
                    and parsed.mode == "plain"
                    and turn.retry_count < config.MAX_PARSE_RETRIES
                    and _looks_like_tool_json(final, self._registry)
                ):
                    turn.retry_count += 1
                    self._trace.emit(
                        "recovery",
                        attempt=turn.retry_count,
                        reason="Response looked like tool JSON but was not parsed",
                    )
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Respond with valid JSON only. Expected: "
                            '{"reasoning":"...","tools":[{"name":"...","arguments":{...}}],'
                            '"status":"in-progress|completed|blocked","response":"..."}'
                        ),
                    })
                    continue

                # Structured/native payloads with empty tools are treated as completion/block.
                if parsed.mode in ("structured", "native", "legacy", "array"):
                    if parsed.status == "blocked":
                        self._trace.emit("response_text", text=final or "Agent is blocked")
                        return self._finish(state, start_time, "blocked", final or "Agent is blocked")
                    if final:
                        consecutive_plain = 0
                        self._trace.emit("response_text", text=final)
                        return self._finish(state, start_time, "done", final)

                if parsed.mode == "plain" and final:
                    if consecutive_plain < config.MAX_PLAIN_NUDGES:
                        consecutive_plain += 1
                        self._trace.emit(
                            "recovery",
                            attempt=consecutive_plain,
                            reason="Plain text response — nudging to continue",
                        )
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                "Use tools to continue. Respond ONLY with JSON in this shape: "
                                '{"reasoning":"...","tools":[{"name":"...","arguments":{...}}],'
                                '"status":"in-progress","response":""}'
                            ),
                        })
                        continue

                    self._trace.emit("response_text", text=final)
                    return self._finish(state, start_time, "done", final)

                turn.retry_count += 1
                if turn.retry_count <= config.MAX_PARSE_RETRIES:
                    self._trace.emit("recovery", attempt=turn.retry_count, reason="Empty response")
                    messages.append({
                        "role": "user",
                        "content": "Response was empty. Return JSON format with tools/response.",
                    })
                    continue

                return self._finish(state, start_time, "empty_response", "Agent returned empty response")

            validation = self._validator.validate(parsed.tool_calls)
            if not validation.valid:
                error_text = "; ".join(validation.errors)
                self._trace.emit(
                    "error",
                    error=f"Validation: {error_text}",
                    schema_mismatch=validation.schema_mismatch,
                )
                available = [t.name for t in self._registry.list_tools()]
                messages.append({
                    "role": "assistant",
                    "content": content,
                })
                messages.append({
                    "role": "user",
                    "content": (
                        "Tool call validation failed. Correct it and retry.\n"
                        f"errors={error_text}\n"
                        f"available={available}"
                    ),
                })
                continue

            sig = _tool_signature(parsed.tool_calls)
            if sig == last_tool_sig:
                identical_count += 1
            else:
                identical_count = 1
                last_tool_sig = sig

            if identical_count >= config.IDENTICAL_CALL_THRESHOLD:
                self._trace.emit("error", error="Deadlock detected")
                return self._finish(state, start_time, "deadlock", "Agent stuck in loop — aborting.")

            consecutive_plain = 0
            self._trace.emit(
                "tool_calls_parsed",
                calls=[{"name": c.name, "arguments": c.arguments, "call_id": c.call_id} for c in parsed.tool_calls],
            )

            result_envelopes: list[dict] = []
            for call in parsed.tool_calls:
                call.ensure_call_id()
                call.name = self._registry.normalize_name(call.name)

                self._trace.emit(
                    "tool_dispatch",
                    name=call.name,
                    args=call.arguments,
                    call_id=call.call_id,
                )

                result = self._registry.execute(call.name, call.arguments)
                result.summary = _summarize_tool_result(call.name, result)
                turn.tool_results.append(result)
                state.tool_call_history.append(call)

                self._trace.emit(
                    "tool_result",
                    name=call.name,
                    args=call.arguments,
                    call_id=call.call_id,
                    success=result.success,
                    data=result.data,
                    error=result.error,
                    summary=result.summary,
                    metadata=result.metadata,
                )

                self._track_modified_paths(call)
                envelope = result.as_envelope(call)
                envelope["metadata"] = {
                    **(envelope.get("metadata") or {}),
                    **_retrievable_metadata(call.name, call.arguments),
                }
                result_envelopes.append(envelope)

            messages.append({"role": "assistant", "content": content})

            all_ok = all(r.success for r in turn.tool_results)
            state.phase = self._advance_phase(state.phase, parsed.tool_calls)

            budget = {
                "turn": state.total_turns,
                "max_turns": state.max_turns,
                "remaining": max(state.max_turns - state.total_turns, 0),
            }
            if state.total_turns >= int(state.max_turns * 0.8):
                budget["warning"] = "near_limit"

            payload = {
                "phase": state.phase,
                "tool_results": result_envelopes,
                "all_ok": all_ok,
                "budget": budget,
                "next": "complete_or_continue",
                "instruction": (
                    "If task is complete, return JSON with tools=[] and short response. "
                    "Otherwise return the next batch of tool calls."
                ),
            }
            messages.append({
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            })
            messages = _prune_messages(messages)
            self._messages = messages

        self._trace.emit("max_turns", limit=self._max_turns)
        return self._finish(state, start_time, "max_turns", "Reached maximum number of turns")

    def _finish(
        self,
        state: AgentState,
        start_time: float,
        reason: str,
        result: str,
    ) -> AgentResult:
        elapsed = time.monotonic() - start_time
        agent_result = AgentResult(
            result=result,
            turns=state.total_turns,
            reason=reason,
            tool_calls_made=len(state.tool_call_history),
            files_modified=list(self._files_modified),
            elapsed_seconds=round(elapsed, 2),
        )
        self._trace.emit(
            "agent_done",
            result=result[:300],
            turns=state.total_turns,
            reason=reason,
            elapsed=elapsed,
        )
        return agent_result

    def _stream_chat(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> tuple[str, list | None, str, dict]:
        """Call the model with streaming, emitting token deltas via trace."""
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        native_calls = None
        eval_count: int | None = None
        prompt_eval_count: int | None = None
        eval_duration: float | None = None

        for chunk in self._client.chat(
            model=self._model,
            messages=messages,
            tools=tools,
            stream=True,
        ):
            delta = chunk.message.content or ""
            thinking = getattr(chunk.message, "thinking", None) or ""

            if delta:
                content_parts.append(delta)
                self._trace.emit("content_delta", text=delta)

            if thinking:
                thinking_parts.append(thinking)
                self._trace.emit("thinking_delta", text=thinking)

            chunk_calls = getattr(chunk.message, "tool_calls", None)
            if chunk_calls and native_calls is None:
                native_calls = chunk_calls

            if chunk.done:
                native_calls = native_calls or getattr(chunk.message, "tool_calls", None)
                eval_count = getattr(chunk, "eval_count", None)
                prompt_eval_count = getattr(chunk, "prompt_eval_count", None)
                eval_duration = getattr(chunk, "eval_duration", None)

        self._trace.emit(
            "stream_end",
            eval_count=eval_count,
            prompt_eval_count=prompt_eval_count,
            eval_duration=eval_duration,
        )
        return (
            "".join(content_parts),
            native_calls,
            "".join(thinking_parts),
            {
                "eval_count": eval_count,
                "prompt_eval_count": prompt_eval_count,
                "eval_duration": eval_duration,
            },
        )

    def _select_tool_categories(self, state: AgentState) -> list[str] | None:
        if config.TOOL_SCOPE_MODE != "dynamic":
            return None

        if state.phase == "discover":
            return ["file", "analysis", "workspace", "graph"]
        if state.phase == "verify":
            return ["code", "system", "file", "analysis", "workspace", "graph"]
        return ["file", "analysis", "workspace", "graph", "code", "system", "web", "agent"]

    def _advance_phase(self, phase: str, calls: list[ToolCall]) -> str:
        write_tools = {
            "write_file",
            "edit_file",
            "delete_file",
            "move_file",
            "copy_file",
            "create_directory",
            "apply_patch",
            "run_command",
        }
        call_names = {c.name for c in calls}

        if phase == "discover":
            if call_names & write_tools:
                return "verify"
            return "modify"
        if phase == "modify" and (call_names & write_tools):
            return "verify"
        return phase

    def _track_modified_paths(self, call: ToolCall) -> None:
        name = call.name
        args = call.arguments
        path_keys = {
            "write_file": ["path"],
            "edit_file": ["path"],
            "apply_patch": ["path"],
            "delete_file": ["path"],
            "create_directory": ["path"],
            "move_file": ["source", "destination"],
            "copy_file": ["source", "destination"],
        }
        keys = path_keys.get(name, [])
        for key in keys:
            p = args.get(key)
            if isinstance(p, str) and p and p not in self._files_modified:
                self._files_modified.append(p)
                if _is_graph_relevant_change(p):
                    self._graph_dirty_paths.append(p)

    def _ensure_graph_ready(self) -> None:
        policy = getattr(config, "GRAPH_AUTO_REFRESH", "auto")
        if policy == "off":
            return
        if self._graph_preflight_done and not self._graph_dirty_paths:
            return
        if self._graph_preflight_done and policy != "auto":
            return

        reason = "preflight" if not self._graph_preflight_done else "dirty"
        try:
            service = self._get_graph_service()
            if self._graph_dirty_paths:
                service.mark_dirty(self._graph_dirty_paths)
            result = service.ensure_fresh(reason=reason)
            self._trace.emit(
                "graph_refresh",
                reason=reason,
                refreshed=result.refreshed,
                file_count=result.file_count,
                symbol_count=result.symbol_count,
                edge_count=result.edge_count,
            )
            self._graph_dirty_paths = []
            self._graph_preflight_done = True
        except Exception as exc:
            self._trace.emit("graph_refresh_skipped", reason=reason, error=str(exc))
            self._graph_preflight_done = True

    def _get_graph_service(self):
        if self._graph_service is None:
            from pathlib import Path

            from app.core.workspace import Workspace
            from graph.service import GraphService
            from graph.store import GraphStore

            ws = Workspace(project_root=Path.cwd())
            self._graph_service = GraphService(GraphStore(ws.project_root, ws.graph_path(), ws.graph_context_path()))
        return self._graph_service


def _summarize_tool_result(name: str, result) -> str:
    if result.success:
        if result.data:
            first = result.data.strip().splitlines()[0] if result.data.strip() else "ok"
            return first[:180]
        return "ok"
    return (result.error or "failed")[:180]


def _retrievable_metadata(name: str, arguments: dict) -> dict:
    if name.startswith("graph_"):
        return {
            "retrievable": True,
            "retrieval_tool": name,
            "retrieval_args": arguments,
        }
    if name in {"read_file", "grep_workspace", "search_in_file", "list_directory", "find_files"}:
        return {
            "retrievable": True,
            "retrieval_tool": name,
            "retrieval_args": arguments,
        }
    return {}


def _is_graph_relevant_change(path: str) -> bool:
    suffix = path.rsplit(".", 1)
    if len(suffix) != 2:
        return False
    return f".{suffix[-1].lower()}" in {
        ".py", ".ts", ".js", ".jsx", ".tsx", ".mjs", ".go", ".rs", ".java",
        ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".rb", ".swift", ".kt",
        ".kts", ".cs", ".scala", ".php", ".lua", ".toc", ".zig", ".ps1",
        ".ex", ".exs", ".m", ".mm", ".jl", ".vue", ".svelte", ".dart",
        ".v", ".sv",
    }


def _tool_signature(calls: list[ToolCall]) -> str:
    parts = []
    for call in calls:
        args = str(sorted(call.arguments.items()))
        parts.append(f"{call.name}:{args}")
    return "|".join(parts)


def _prune_messages(messages: list[dict]) -> list[dict]:
    """Prune messages while keeping critical context pinned."""
    messages = _compact_retrievable_messages(messages)
    if len(messages) <= config.MAX_MESSAGES:
        return messages

    pinned_indices = {0, 1}

    for i, msg in enumerate(messages[2:], start=2):
        if msg.get("role") == "assistant":
            text = (msg.get("content") or "").lower()
            if "plan" in text and ("phase" in text or "step" in text or ".md" in text):
                pinned_indices.add(i)
                break

    budget = config.MAX_MESSAGES
    pinned = [messages[i] for i in sorted(pinned_indices) if i < len(messages)]
    remaining_budget = budget - len(pinned)

    unpinned = [msg for i, msg in enumerate(messages) if i not in pinned_indices]
    kept_tail = unpinned[-remaining_budget:] if remaining_budget > 0 else []

    return pinned + kept_tail


def _compact_retrievable_messages(messages: list[dict], keep_tail: int = 4) -> list[dict]:
    compacted: list[dict] = []
    cutoff = max(len(messages) - keep_tail, 0)
    for index, msg in enumerate(messages):
        if index >= cutoff or msg.get("role") != "user":
            compacted.append(msg)
            continue

        content = msg.get("content")
        if not isinstance(content, str) or '"tool_results"' not in content:
            compacted.append(msg)
            continue

        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            compacted.append(msg)
            continue

        changed = False
        for result in payload.get("tool_results", []):
            if not isinstance(result, dict):
                continue
            metadata = result.get("metadata") or {}
            if metadata.get("retrievable") and result.get("data"):
                tool = metadata.get("retrieval_tool") or result.get("name")
                result["data"] = (
                    "[compacted: retrievable project context; "
                    f"use {tool} with metadata.retrieval_args to reload]"
                )
                changed = True
        if changed:
            msg = {**msg, "content": json.dumps(payload, ensure_ascii=False)}
        compacted.append(msg)
    return compacted


def _looks_like_tool_json(text: str, registry: ToolRegistry) -> bool:
    """Heuristic: does the text look like a failed tool call JSON response?"""
    lowered = text.lower()
    if "{" not in lowered and "[" not in lowered:
        return False
    if '"name"' not in lowered and '"tools"' not in lowered and '"arguments"' not in lowered:
        return False
    known = {t.name for t in registry.list_tools()}
    return any(name.lower() in lowered for name in known)
