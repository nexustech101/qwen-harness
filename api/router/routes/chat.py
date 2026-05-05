"""Chat routes — session CRUD, message history, and prompt submission."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.config.config import get_settings
from api.modules.session_manager import manager
from api.services.chat_service import (
    delete_session,
    list_sessions,
    load_messages,
    persist_session,
    run_session_turn,
)

router = APIRouter(tags=["chat"])
settings = get_settings()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Request / Response schemas ─────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    model: str | None = None
    title: str = "New chat"


class SendPromptRequest(BaseModel):
    prompt: str
    attachment_ids: list[str] = []


# ── Session endpoints ──────────────────────────────────────────────────────────

@router.post("/sessions", status_code=201)
async def create_session(req: CreateSessionRequest) -> dict[str, Any]:
    model = req.model or settings.default_model
    session = manager.create(model=model, title=req.title)
    persist_session(session)
    return session.to_dict()


@router.get("/sessions")
async def list_sessions_endpoint() -> list[dict[str, Any]]:
    return [s.to_dict() for s in manager.list_all()]


@router.get("/sessions/{session_id}")
async def get_session_endpoint(session_id: str) -> dict[str, Any]:
    session = manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session.to_dict()


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session_endpoint(session_id: str) -> None:
    if not manager.delete(session_id):
        raise HTTPException(404, "Session not found")
    delete_session(session_id)


# ── Message endpoints ──────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str) -> list[dict[str, Any]]:
    session = manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    # Return in-memory history (may include tool messages); filter to user/assistant for API consumers
    return [m for m in session.history if m.get("role") in ("user", "assistant")]


# ── Prompt / streaming ─────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/prompt")
async def send_prompt(session_id: str, req: SendPromptRequest) -> StreamingResponse:
    """Stream a session turn as Server-Sent Events."""
    session = manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status == "running":
        raise HTTPException(409, "Session is already running")

    prompt = req.prompt
    if req.attachment_ids:
        prompt, _images = session.resolve_attachments(prompt, req.attachment_ids)

    import json as _json

    async def _stream():
        async for event in run_session_turn(session, prompt):
            session.broadcast(event)
            yield f"data: {_json.dumps(event)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
