"""
Structured event trace — collects events for renderers and loggers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TraceEvent:
    """Single event in the trace timeline."""
    event_type: str
    timestamp: float
    data: dict[str, Any]


class Trace:
    """
    Collects structured events from the agent loop.

    Subscribers (renderers, loggers) register callbacks that are invoked
    synchronously on each event.
    """

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []
        self._subscribers: dict[str, list[Callable]] = {}
        self._start_time = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._start_time

    def subscribe(self, event_type: str, callback: Callable[[TraceEvent], None]) -> None:
        self._subscribers.setdefault(event_type, []).append(callback)

    def subscribe_all(self, callback: Callable[[TraceEvent], None]) -> None:
        """Subscribe to all event types via the wildcard '*'."""
        self._subscribers.setdefault("*", []).append(callback)

    def emit(self, event_type: str, **data: Any) -> None:
        event = TraceEvent(
            event_type=event_type,
            timestamp=time.monotonic() - self._start_time,
            data=data,
        )
        self._events.append(event)

        # Notify type-specific subscribers
        for cb in self._subscribers.get(event_type, []):
            cb(event)
        # Notify wildcard subscribers
        for cb in self._subscribers.get("*", []):
            cb(event)

    @property
    def events(self) -> list[TraceEvent]:
        return list(self._events)
