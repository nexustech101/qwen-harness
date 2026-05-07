"""
File logger — writes all trace events and orchestrator-level failures to a log file.

Subscribes to the Trace event system and also provides direct logging for
failures outside the agent loop (planner errors, dispatch failures, etc.).
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent import config


def _get_logger() -> logging.Logger:
    """Create or return the shared file logger."""
    logger = logging.getLogger("qwen-coder")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    log_path = Path(config.LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(str(log_path), encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(handler)
    return logger


_logger = _get_logger()


# ── Direct logging API (for orchestrator / dispatcher / anywhere) ─────────────

def log_info(message: str) -> None:
    _logger.info(message)


def log_error(message: str) -> None:
    _logger.error(message)


def log_warning(message: str) -> None:
    _logger.warning(message)


def log_debug(message: str) -> None:
    _logger.debug(message)


# ── Trace subscriber ─────────────────────────────────────────────────────────

def attach_to_trace(trace: "Trace") -> None:  # type: ignore # noqa: F821
    """Subscribe to all trace events and write them to the log file."""
    from agent.logging.trace import TraceEvent

    def _on_event(event: TraceEvent) -> None:
        et = event.event_type
        d = event.data

        if et == "error":
            _logger.error("[trace] %s", d.get("error", "Unknown error"))
        elif et == "tool_result" and not d.get("success"):
            _logger.warning(
                "[trace] tool_failed: %s — %s",
                d.get("name", "?"),
                d.get("error", "unknown"),
            )
        elif et == "agent_done":
            reason = d.get("reason", "done")
            level = logging.INFO if reason == "done" else logging.WARNING
            _logger.log(
                level,
                "[trace] agent_done: reason=%s turns=%s elapsed=%.1fs",
                reason,
                d.get("turns", "?"),
                d.get("elapsed", 0),
            )
        elif et == "agent_start":
            _logger.info(
                "[trace] agent_start: model=%s prompt=%.120s",
                d.get("model", "?"),
                d.get("prompt", ""),
            )
        elif et in ("model_reply", "turn_start"):
            _logger.debug("[trace] %s: %s", et, d)

    trace.subscribe_all(_on_event)
