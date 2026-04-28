"""Health endpoint for the unified runtime API."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import config
from api.modules.middleware import request_ip
from api.config.logging import get_request_id
from api.config.security import utc_now_iso
from api.schemas.agent import HealthResponse

router = APIRouter(tags=["agent-runtime"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    ollama_ok = False
    try:
        import ollama

        client = ollama.Client(host=config.OLLAMA_HOST)
        client.list()
        ollama_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        service="Qwen Coder API",
        time=utc_now_iso(),
        ip=request_ip(request),
        request_id=getattr(request.state, "request_id", get_request_id()),
        ollama_connected=ollama_ok,
    )

