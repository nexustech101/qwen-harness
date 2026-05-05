"""Response parser for LLM output.

Provides two interfaces:

  StreamingParser   — stateful, token-by-token. Feed raw Ollama deltas and
                      receive back typed (kind, text) pairs so callers can
                      emit distinct SSE events for thinking vs. content.

  parse_response()  — full-text post-processor. Given a complete assistant
                      message, returns a ParsedResponse with typed Segment
                      objects (thinking, code, json, text).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum


# ── Segment types ──────────────────────────────────────────────────────────────


class SegmentKind(str, Enum):
    THINKING = "thinking"  # inside <think>…</think>
    CODE = "code"          # fenced code block
    JSON = "json"          # JSON object or array (bare or inside ```json)
    TEXT = "text"          # plain prose / markdown


@dataclass
class Segment:
    kind: SegmentKind
    content: str
    language: str | None = None  # set for CODE segments: "python", "js", …


@dataclass
class ParsedResponse:
    raw: str
    segments: list[Segment] = field(default_factory=list)

    @property
    def thinking(self) -> str:
        """Concatenated content of all THINKING segments."""
        return "\n".join(s.content for s in self.segments if s.kind == SegmentKind.THINKING)

    @property
    def visible(self) -> str:
        """All non-thinking content rebuilt as clean Markdown text."""
        parts: list[str] = []
        for s in self.segments:
            if s.kind == SegmentKind.THINKING:
                continue
            if s.kind == SegmentKind.CODE:
                parts.append(f"```{s.language or ''}\n{s.content}\n```")
            elif s.kind == SegmentKind.JSON:
                # Pretty-print JSON inside a fenced block
                try:
                    pretty = json.dumps(json.loads(s.content), indent=2)
                except json.JSONDecodeError:
                    pretty = s.content
                parts.append(f"```json\n{pretty}\n```")
            else:
                parts.append(s.content)
        return "\n\n".join(p for p in parts if p.strip())

    @property
    def has_thinking(self) -> bool:
        return any(s.kind == SegmentKind.THINKING for s in self.segments)


# ── Regex patterns ─────────────────────────────────────────────────────────────

# <think> … </think>  (case-insensitive, DOTALL)
_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)

# ``` [lang] \n … ```
_FENCE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


# ── Full-text parser ───────────────────────────────────────────────────────────


def parse_response(text: str) -> ParsedResponse:
    """Parse a complete assistant response into typed Segment objects."""
    result = ParsedResponse(raw=text)
    _split_think(text, result.segments)
    return result


def _split_think(text: str, out: list[Segment]) -> None:
    last = 0
    for m in _THINK_RE.finditer(text):
        before = text[last : m.start()]
        if before.strip():
            _split_fences(before, out)
        content = m.group(1).strip()
        if content:
            out.append(Segment(kind=SegmentKind.THINKING, content=content))
        last = m.end()
    tail = text[last:]
    if tail.strip():
        _split_fences(tail, out)


def _split_fences(text: str, out: list[Segment]) -> None:
    last = 0
    for m in _FENCE_RE.finditer(text):
        before = text[last : m.start()]
        if before.strip():
            _classify_bare(before.strip(), out)
        lang = m.group(1).strip() or None
        code = m.group(2).rstrip()
        if _is_json(code) and lang in (None, "", "json"):
            out.append(Segment(kind=SegmentKind.JSON, content=code, language="json"))
        else:
            out.append(Segment(kind=SegmentKind.CODE, content=code, language=lang or "text"))
        last = m.end()
    tail = text[last:]
    if tail.strip():
        _classify_bare(tail.strip(), out)


def _classify_bare(text: str, out: list[Segment]) -> None:
    """Emit a JSON segment or plain TEXT segment for non-fenced content."""
    if _is_json(text):
        out.append(Segment(kind=SegmentKind.JSON, content=text.strip(), language="json"))
    else:
        out.append(Segment(kind=SegmentKind.TEXT, content=text))


def _is_json(text: str) -> bool:
    stripped = text.strip()
    if not stripped or stripped[0] not in ("{", "["):
        return False
    try:
        json.loads(stripped)
        return True
    except json.JSONDecodeError:
        return False


# ── Streaming parser ───────────────────────────────────────────────────────────


class StreamingParser:
    """Stateful per-token classifier for streaming Ollama output.

    Feed raw text deltas one at a time; receive back a list of
    ``(kind, text)`` pairs where kind is ``"thinking"`` or ``"content"``.

    Handles tag boundaries that may arrive split across multiple tokens.
    Currently recognised tag pairs:

    * ``<think>`` / ``</think>``           → emitted as ``"thinking"``
    * ``<tool_response>`` / ``</tool_response>``  → suppressed entirely

    Usage::

        parser = StreamingParser()
        async for chunk in ollama_stream:
            for kind, delta in parser.feed(chunk.message.content or ""):
                yield {"type": kind, "delta": delta}
        for kind, delta in parser.flush():
            yield {"type": kind, "delta": delta}
    """

    # (open_tag, close_tag, emit_kind)  — emit_kind=None means suppress
    _TAG_PAIRS: list[tuple[str, str, str | None]] = [
        ("<think>",         "</think>",          "thinking"),
        ("<tool_response>", "</tool_response>",   None),
    ]

    def __init__(self) -> None:
        self._close_tag: str | None = None   # None = currently in content mode
        self._emit_kind: str | None = None   # kind to emit inside special block
        self._buf = ""

    def feed(self, text: str) -> list[tuple[str, str]]:
        """Process a raw delta. Returns ``[(kind, text), …]``."""
        self._buf += text
        out: list[tuple[str, str]] = []
        while self._buf:
            if self._close_tag is not None:
                # Inside a special block — look for closing tag
                tag = self._close_tag
                idx = self._buf.find(tag)
                if idx == -1:
                    safe, held = _safe_split(self._buf, tag)
                    if safe and self._emit_kind is not None:
                        out.append((self._emit_kind, safe))
                    self._buf = held
                    break
                else:
                    if idx > 0 and self._emit_kind is not None:
                        out.append((self._emit_kind, self._buf[:idx]))
                    self._buf = self._buf[idx + len(tag):]
                    self._close_tag = None
                    self._emit_kind = None
            else:
                # Content mode — find the earliest opening tag
                open_tags = [p[0] for p in self._TAG_PAIRS]
                best_idx = -1
                best_pair: tuple[str, str, str | None] | None = None
                for open_tag, close_tag, emit_kind in self._TAG_PAIRS:
                    idx = self._buf.find(open_tag)
                    if idx != -1 and (best_idx == -1 or idx < best_idx):
                        best_idx = idx
                        best_pair = (open_tag, close_tag, emit_kind)

                if best_pair is None:
                    safe, held = _safe_split_any(self._buf, open_tags)
                    if safe:
                        out.append(("content", safe))
                    self._buf = held
                    break
                else:
                    open_tag, close_tag, emit_kind = best_pair
                    if best_idx > 0:
                        out.append(("content", self._buf[:best_idx]))
                    self._buf = self._buf[best_idx + len(open_tag):]
                    self._close_tag = close_tag
                    self._emit_kind = emit_kind
        return out

    def flush(self) -> list[tuple[str, str]]:
        """Flush remaining lookahead buffer (call after stream ends)."""
        if not self._buf:
            return []
        if self._close_tag is not None:
            # Stream ended mid-special-block
            result = [(self._emit_kind, self._buf)] if self._emit_kind is not None else []
        else:
            result = [("content", self._buf)]
        self._buf = ""
        self._close_tag = None
        self._emit_kind = None
        return result


def _safe_split(text: str, tag: str) -> tuple[str, str]:
    """Split ``text`` into ``(safe_to_emit, tail_to_hold)``.

    We hold back up to ``len(tag) - 1`` chars from the end in case the
    opening of ``tag`` starts there.
    """
    max_hold = len(tag) - 1
    for size in range(min(max_hold, len(text)), 0, -1):
        if tag.startswith(text[-size:]):
            return text[:-size], text[-size:]
    return text, ""


def _safe_split_any(text: str, tags: list[str]) -> tuple[str, str]:
    """Like ``_safe_split`` but holds back enough for *any* of the given tags."""
    for size in range(min(max(len(t) - 1 for t in tags), len(text)), 0, -1):
        suffix = text[-size:]
        if any(t.startswith(suffix) for t in tags):
            return text[:-size], text[-size:]
    return text, ""
