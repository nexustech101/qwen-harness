"""
Dual-mode response parser — handles native tool calls, JSON, and think tags.
"""

from __future__ import annotations

import json
import re
import uuid

from app.core.state import ParseResult, ToolCall

# Pattern for <think>...</think> blocks (qwen3, deepseek-r1, etc.)
_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)
_FENCED_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


class ResponseParser:
    """
    Parse LLM responses into structured ParseResult.

    Priority chain:
      1. Native tool calls (from response.message.tool_calls)
      2. Structured JSON  {"reasoning": ..., "tools": [...], "response": ..., "status": ...}
      3. Legacy JSON       {"name": ..., "arguments": {...}}
      4. Top-level array   [{"name": ..., "arguments": {...}}, ...]
      5. Plain text        (treat entire response as final answer)

    Think tags (<think>...</think>) and stream-level thinking are merged.
    """

    def __init__(self, known_tools: set[str] | None = None) -> None:
        self._known_tools = known_tools or set()

    def parse(
        self,
        content: str | None,
        native_tool_calls: list | None = None,
        stream_thinking: str = "",
    ) -> ParseResult:
        """Parse a model response into a structured result."""

        thinking = (stream_thinking or "").strip()
        clean_content = content or ""
        if clean_content:
            think_tags, clean_content = self._extract_thinking(clean_content)
            if think_tags:
                thinking = "\n".join([p for p in (thinking, think_tags) if p]).strip()

        # 1) Native tool calls from Ollama response object.
        if native_tool_calls:
            tools: list[ToolCall] = []
            for call in native_tool_calls:
                if hasattr(call, "function"):
                    args = getattr(call.function, "arguments", {}) or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    tools.append(
                        ToolCall(
                            name=self._normalize_name(call.function.name),
                            arguments=args if isinstance(args, dict) else {},
                            call_id=getattr(call, "id", "") or uuid.uuid4().hex[:12],
                        )
                    )
                elif isinstance(call, dict):
                    args = call.get("arguments", {})
                    tools.append(
                        ToolCall(
                            name=self._normalize_name(call.get("name", "")),
                            arguments=args if isinstance(args, dict) else {},
                            call_id=str(call.get("call_id") or call.get("id") or uuid.uuid4().hex[:12]),
                        )
                    )

            return ParseResult(
                mode="native",
                tool_calls=tools,
                reasoning=thinking,
                diagnostics={
                    "parse_mode": "native",
                    "repair_applied": False,
                    "normalize_variant": "native_tool_calls",
                    "schema_mismatch": False,
                },
                raw_content=content or "",
            )

        if not clean_content.strip():
            return ParseResult(
                mode="plain",
                reasoning=thinking,
                diagnostics={
                    "parse_mode": "plain",
                    "repair_applied": False,
                    "normalize_variant": "empty",
                    "schema_mismatch": False,
                },
                raw_content=content or "",
            )

        decoded, repaired, variant = self._decode_json_payload(clean_content)
        if decoded is not None:
            parsed = self._normalize_payload(decoded, clean_content)
            parsed.diagnostics = {
                **parsed.diagnostics,
                "parse_mode": parsed.mode,
                "repair_applied": repaired,
                "normalize_variant": variant,
            }
            if thinking and parsed.reasoning:
                parsed.reasoning = f"{thinking}\n{parsed.reasoning}"
            elif thinking:
                parsed.reasoning = thinking
            return parsed

        return ParseResult(
            mode="plain",
            reasoning=thinking,
            response=clean_content.strip(),
            diagnostics={
                "parse_mode": "plain",
                "repair_applied": False,
                "normalize_variant": "plain_text",
                "schema_mismatch": False,
            },
            raw_content=content or "",
        )

    def _normalize_payload(self, payload: object, raw_text: str) -> ParseResult:
        if isinstance(payload, list):
            calls, mismatch = self._normalize_tool_list(payload)
            return ParseResult(
                mode="array",
                tool_calls=calls,
                diagnostics={"schema_mismatch": mismatch},
                raw_content=raw_text,
            )

        if not isinstance(payload, dict):
            return ParseResult(mode="plain", response=raw_text.strip(), raw_content=raw_text)

        lower = {str(k).lower(): v for k, v in payload.items()}

        # Structured payload with explicit sections.
        if any(k in lower for k in ("reasoning", "tools", "response", "status")):
            tools_raw = lower.get("tools", [])
            if isinstance(tools_raw, dict):
                tools_raw = [tools_raw]
            if isinstance(tools_raw, str):
                tools_raw = [tools_raw]
            if not isinstance(tools_raw, list):
                tools_raw = []

            calls, mismatch = self._normalize_tool_list(tools_raw)
            return ParseResult(
                mode="structured",
                tool_calls=calls,
                reasoning=str(lower.get("reasoning", "")).strip(),
                response=str(lower.get("response", "")).strip(),
                status=str(lower.get("status", "")).strip(),
                diagnostics={"schema_mismatch": mismatch},
                raw_content=raw_text,
            )

        # Legacy single-tool object.
        name = lower.get("name") or lower.get("tool") or lower.get("function")
        if name:
            args = (
                lower.get("arguments")
                or lower.get("parameters")
                or lower.get("args")
                or {}
            )
            if not isinstance(args, dict):
                args = {}
            call = ToolCall(
                name=self._normalize_name(str(name)),
                arguments=args,
                call_id=str(lower.get("call_id") or lower.get("id") or uuid.uuid4().hex[:12]),
            )
            if self._known_tools and call.name not in self._known_tools:
                return ParseResult(
                    mode="plain",
                    response=raw_text.strip(),
                    diagnostics={"schema_mismatch": True},
                    raw_content=raw_text,
                )
            return ParseResult(
                mode="legacy",
                tool_calls=[call],
                diagnostics={"schema_mismatch": False},
                raw_content=raw_text,
            )

        return ParseResult(
            mode="plain",
            response=raw_text.strip(),
            diagnostics={"schema_mismatch": True},
            raw_content=raw_text,
        )

    def _normalize_tool_list(self, tools_raw: list) -> tuple[list[ToolCall], bool]:
        out: list[ToolCall] = []
        mismatch = False
        for item in tools_raw:
            if isinstance(item, str):
                out.append(
                    ToolCall(
                        name=self._normalize_name(item),
                        arguments={},
                        call_id=uuid.uuid4().hex[:12],
                    )
                )
                continue

            if not isinstance(item, dict):
                mismatch = True
                continue

            name = item.get("name") or item.get("function") or item.get("tool")
            if not name:
                mismatch = True
                continue

            args = item.get("arguments") or item.get("parameters") or item.get("args") or {}
            if not isinstance(args, dict):
                args = {}
                mismatch = True

            out.append(
                ToolCall(
                    name=self._normalize_name(str(name)),
                    arguments=args,
                    call_id=str(item.get("call_id") or item.get("id") or uuid.uuid4().hex[:12]),
                )
            )

        return out, mismatch

    def _decode_json_payload(self, text: str) -> tuple[object | None, bool, str]:
        candidates: list[tuple[str, str]] = []

        for m in _FENCED_BLOCK_RE.finditer(text):
            candidate = m.group(1).strip()
            if candidate.startswith("{") or candidate.startswith("["):
                candidates.append(("fenced", candidate))

        if not candidates:
            balanced = _extract_balanced_json(text)
            if balanced:
                candidates.append(("balanced", balanced))

        for variant, candidate in candidates:
            loaded, repaired = _loads_with_repair(candidate)
            if loaded is not None:
                return loaded, repaired, variant

        return None, False, "none"

    @staticmethod
    def _extract_thinking(text: str) -> tuple[str, str]:
        """Extract <think>...</think> blocks, return (thinking, remaining_text)."""
        parts = []
        for m in _THINK_RE.finditer(text):
            parts.append(m.group(1).strip())
        cleaned = _THINK_RE.sub("", text).strip()
        return "\n".join(parts), cleaned

    def _normalize_name(self, name: str) -> str:
        aliases = {
            "read_file_content": "read_file",
            "write_to_file": "write_file",
            "get_curr_working_dir": "get_working_directory",
            "get_files_in_dir": "list_directory",
            "search_files": "grep_workspace",
            "workspace_search": "grep_workspace",
            "run_shell_command": "run_command",
        }
        n = str(name or "").strip()
        return aliases.get(n, n)


def _loads_with_repair(candidate: str) -> tuple[object | None, bool]:
    try:
        return json.loads(candidate), False
    except json.JSONDecodeError:
        repaired = re.sub(r",\s*([}\]])", r"\1", candidate).strip()
        if '"' not in repaired and "'" in repaired:
            repaired = repaired.replace("'", '"')
        try:
            return json.loads(repaired), repaired != candidate
        except json.JSONDecodeError:
            return None, False


def _extract_balanced_json(text: str) -> str | None:
    start = -1
    opening = ""
    for i, ch in enumerate(text):
        if ch in "[{":
            start = i
            opening = ch
            break
    if start < 0:
        return None

    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == opening:
            depth += 1
            continue
        if ch == closing:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return None
