from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from .config import Settings

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(request_id: str) -> None:
    _request_id_ctx.set(request_id)


def get_request_id() -> str:
    return _request_id_ctx.get()


def _as_json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _as_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_json_safe(v) for v in value]
    return str(value)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", get_request_id()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        extra_keys = (
            "event",
            "method",
            "path",
            "query",
            "status_code",
            "duration_ms",
            "client_ip",
            "user_agent",
            "user_id",
            "email",
            "action",
            "success",
            "details",
        )
        for key in extra_keys:
            if hasattr(record, key):
                payload[key] = _as_json_safe(getattr(record, key))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


def configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)

    handler = logging.StreamHandler()
    if settings.log_json:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root.handlers.clear()
    root.addHandler(handler)

