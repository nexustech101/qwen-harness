from __future__ import annotations

import logging
import time
import uuid
from typing import Callable

from fastapi import Request

from api.config.logging import set_request_id

logger = logging.getLogger("user_api.api")


def request_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host


def request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


async def observability_middleware(request: Request, call_next: Callable):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    set_request_id(request_id)
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "request_unhandled_exception",
            extra={
                "event": "request_unhandled_exception",
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
                "duration_ms": duration_ms,
                "client_ip": request_ip(request),
                "user_agent": request_user_agent(request),
            },
        )
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_complete",
        extra={
            "event": "request_complete",
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": request_ip(request),
            "user_agent": request_user_agent(request),
        },
    )
    return response

