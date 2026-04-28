"""
Streaming CLI renderer — codex-style live output.

Prints events as flowing text rather than a TUI dashboard.
Uses only Rich's low-level primitives (Console, Text, Live)
so the output looks like a tool, not a terminal application.
"""

from __future__ import annotations

import textwrap
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.style import Style
from rich.text import Text

from app.logging.trace import Trace, TraceEvent

# ── palette ────────────────────────────────────────────────────────────────────
_DIM        = Style(color="bright_black")
_CYAN       = Style(color="cyan")
_GREEN      = Style(color="green")
_YELLOW     = Style(color="yellow")
_RED        = Style(color="red")
_BOLD       = Style(bold=True)
_BOLD_CYAN  = Style(color="cyan",  bold=True)
_BOLD_GREEN = Style(color="green", bold=True)

# ── helpers ────────────────────────────────────────────────────────────────────

def _wrap(text: str, width: int = 110, indent: str = "   ") -> str:
    """Wrap long text with a hanging indent."""
    return textwrap.fill(text, width=width, subsequent_indent=indent)


def _bullet(label: str, body: str, label_style: Style = _CYAN) -> Text:
    """• label  body"""
    t = Text()
    t.append("• ", style=_BOLD)
    t.append(label, style=label_style)
    if body:
        t.append("  " + body, style=_DIM)
    return t


def _sub(body: str, style: Style = _DIM) -> Text:
    """  └ body"""
    t = Text()
    t.append("  └ ", style=_DIM)
    t.append(body, style=style)
    return t


def _short_args(args: dict[str, Any]) -> str:
    if not isinstance(args, dict) or not args:
        return "{}"
    parts: list[str] = []
    for i, (k, v) in enumerate(args.items()):
        if i >= 3:
            parts.append("...")
            break
        s = str(v)
        parts.append(f"{k}={s[:32] + '...' if len(s) > 32 else s}")
    return "{" + ", ".join(parts) + "}"


# ── renderer ───────────────────────────────────────────────────────────────────

class ConsoleRenderer:
    """
    Renders agent events as streaming CLI text.

    Completed lines are printed permanently; only the *current* streaming
    block (reasoning + response) is held in a Live region so it refreshes
    in-place without flickering the rest of the output.
    """

    def __init__(self, trace: Trace, console: Console | None = None) -> None:
        self._console = console or Console(highlight=False, markup=False)
        self._trace   = trace

        # transient streaming state
        self._reasoning_buf  = ""
        self._response_buf   = ""
        self._live: Live | None = None
        self._last_parse_mode = ""
        self._activity: list[str] = []

        self._register()

    # ── event subscription ────────────────────────────────────────────────────

    def _register(self) -> None:
        handlers = {
            "agent_start":    self._on_agent_start,
            "turn_start":     self._on_turn_start,
            "model_call":     self._on_model_call,
            "thinking_delta": self._on_thinking_delta,
            "content_delta":  self._on_content_delta,
            "stream_end":     self._on_stream_end,
            "model_reply":    self._on_model_reply,
            "reasoning":      self._on_reasoning,
            "response_text":  self._on_response_text,
            "tool_dispatch":  self._on_tool_dispatch,
            "tool_result":    self._on_tool_result,
            "agent_done":     self._on_agent_done,
            "error":          self._on_error,
            "recovery":       self._on_recovery,
        }
        for event_type, handler in handlers.items():
            self._trace.subscribe(event_type, handler)

    # ── low-level print helpers ───────────────────────────────────────────────

    def _print(self, renderable: Any) -> None:
        """Print a line *outside* the live region (permanent output)."""
        if self._live is not None and hasattr(self._live, "console"):
            # Temporarily steal the console to print above the live block.
            self._live.console.print(renderable)
        else:
            self._console.print(renderable)

    def _start_live(self) -> None:
        if self._live is not None:
            return
        self._live = Live(
            self._stream_renderable(),
            console=self._console,
            refresh_per_second=16,
            transient=True,   # erased on stop — raw streamed JSON never persists
        )
        self._live.start()

    def _stop_live(self) -> None:
        if self._live is None:
            return
        # Blank the renderable before stopping so Rich erases it cleanly.
        self._live.update(Text())
        self._live.stop()
        self._live = None
        self._reasoning_buf = ""
        self._response_buf  = ""

    def _refresh_live(self) -> None:
        if self._live is not None:
            self._live.update(self._stream_renderable())

    def _stream_renderable(self) -> Text:
        """Build the in-place streaming block shown while the model runs."""
        t = Text()
        if self._reasoning_buf:
            t.append("  Thinking  ", style=_BOLD_CYAN)
            t.append("\n")
            for line in self._reasoning_buf.splitlines()[-6:]:  # last 6 lines
                t.append("  " + line[:120] + "\n", style=_DIM)
        if self._response_buf:
            t.append("  Responding  ", style=_BOLD_GREEN)
            t.append("\n")
            for line in self._response_buf.splitlines()[-4:]:
                t.append("  " + line[:120] + "\n", style=Style(color="white"))
        return t

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_agent_start(self, event: TraceEvent) -> None:
        d            = event.data
        model        = d.get("model", "?")
        prompt       = d.get("prompt", "")
        self._reasoning_buf = ""
        self._response_buf  = ""

        header = Text()
        header.append(f"\n›_ ", style=_BOLD_CYAN)
        header.append(model, style=_BOLD)
        self._print(header)

        prompt_line = Text()
        prompt_line.append("  ", style=_DIM)
        prompt_line.append(_wrap(prompt, indent="    "), style=Style(color="white"))
        self._print(prompt_line)
        self._print("")

    def _on_turn_start(self, event: TraceEvent) -> None:
        turn  = event.data.get("turn", "?")
        phase = event.data.get("phase", "")
        self._print("")
        t = Text()
        t.append("  turn ", style=_DIM)
        t.append(str(turn), style=_CYAN)
        if phase:
            t.append(f"  {phase}", style=_DIM)
        self._print(t)

    def _on_model_call(self, event: TraceEvent) -> None:
        cats = event.data.get("tool_categories")
        cat_txt = ", ".join(cats) if isinstance(cats, list) else "all"
        self._reasoning_buf = ""
        self._response_buf  = ""
        self._print(_bullet("thinking", f"tools: {cat_txt}"))
        self._start_live()

    def _on_thinking_delta(self, event: TraceEvent) -> None:
        self._reasoning_buf += event.data.get("text", "")
        self._refresh_live()

    def _on_content_delta(self, event: TraceEvent) -> None:
        self._response_buf += event.data.get("text", "")
        self._refresh_live()

    def _on_stream_end(self, event: TraceEvent) -> None:
        tok     = event.data.get("eval_count") or 0
        ptok    = event.data.get("prompt_eval_count") or 0
        dur_ms  = int((event.data.get("eval_duration") or 0) / 1_000_000)
        if tok:
            self._stop_live()
            self._print(_sub(f"tok={tok}  prompt_tok={ptok}  {dur_ms}ms", _DIM))

    def _on_model_reply(self, event: TraceEvent) -> None:
        d       = event.data
        mode    = d.get("parse_mode", "?")
        repair  = d.get("repair_applied", False)
        lat     = float(d.get("elapsed_ms", 0)) / 1000.0
        self._last_parse_mode = str(mode)
        body    = f"mode={mode}"
        if repair:
            body += "  repair=yes"
        body += f"  {lat:.2f}s"
        self._print(_sub(body, _DIM))

    def _on_reasoning(self, event: TraceEvent) -> None:
        text = (event.data.get("text") or "").strip()
        if not text:
            return
        self._stop_live()
        lines = text.splitlines()
        preview = lines[0][:100] + ("…" if len(lines[0]) > 100 else "")
        if len(lines) > 1:
            preview += f"  [{len(lines)} lines]"
        self._print(_sub(preview, _DIM))

    def _on_response_text(self, event: TraceEvent) -> None:
        text = (event.data.get("text") or "").strip()
        if not text:
            return
        self._stop_live()
        self._reasoning_buf = ""
        self._response_buf  = ""

        t = Text()
        t.append("\n")
        for line in text.splitlines():
            wrapped = _wrap(line, indent="  ")
            t.append("  " + wrapped + "\n", style=Style(color="white"))
        self._print(t)

    def _on_tool_dispatch(self, event: TraceEvent) -> None:
        name    = event.data.get("name", "?")
        args    = event.data.get("args", {})
        call_id = event.data.get("call_id", "")
        suffix  = f"#{call_id}" if call_id else ""
        self._activity.append(f"tool -> {name}{suffix}")
        self._stop_live()
        self._print("")
        self._print(_bullet(f"{name}{suffix}", _short_args(args)))

    def _on_tool_result(self, event: TraceEvent) -> None:
        name    = event.data.get("name", "?")
        ok      = bool(event.data.get("success", False))
        summary = str(event.data.get("summary") or event.data.get("error") or "")

        marker      = "✔" if ok else "✗"
        marker_style = _GREEN if ok else _RED
        t = Text()
        t.append("  └ ", style=_DIM)
        t.append(marker, style=marker_style)
        t.append(f" {name}", style=_BOLD if not ok else _DIM)
        if summary:
            t.append("  " + summary[:120], style=_DIM)
        self._print(t)

    def _on_agent_done(self, event: TraceEvent) -> None:
        self._stop_live()
        reason  = event.data.get("reason", "done")
        turns   = event.data.get("turns", 0)
        elapsed = float(event.data.get("elapsed", 0.0))

        t = Text()
        t.append("\n✔ ", style=_BOLD_GREEN)
        t.append(f"done", style=_BOLD)
        t.append(f"  reason={reason}  turns={turns}  {elapsed:.1f}s", style=_DIM)
        t.append("\n")
        self._print(t)

    def _on_error(self, event: TraceEvent) -> None:
        self._stop_live()
        err = str(event.data.get("error", "unknown error"))
        t = Text()
        t.append("✗ ", style=_RED + _BOLD)
        t.append(err[:160], style=_RED)
        self._print(t)

    def _on_recovery(self, event: TraceEvent) -> None:
        attempt = event.data.get("attempt", 0)
        reason  = event.data.get("reason", "")
        self._print("")
        t = Text()
        t.append("  ↻ ", style=_YELLOW)
        t.append(f"recovery #{attempt}", style=_YELLOW)
        if reason:
            t.append(f"  {reason[:100]}", style=_DIM)
        self._print(t)
