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
    get_messages_for_api,
    get_session,
    list_sessions,
    persist_session,
    restore_session,
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
    tool_profile: str = "default"


class SendPromptRequest(BaseModel):
    prompt: str
    attachment_ids: list[str] = []


# ── Session endpoints ──────────────────────────────────────────────────────────

@router.post("/sessions", status_code=201)
async def create_session(req: CreateSessionRequest) -> dict[str, Any]:
    model = req.model or settings.default_model
    session = manager.create(model=model, title=req.title, tool_profile=req.tool_profile)
    persist_session(session)
    return session.to_dict()


@router.get("/sessions")
async def list_sessions_endpoint() -> list[dict[str, Any]]:
    db_sessions = list_sessions()
    result = []
    for db_s in db_sessions:
        mem = manager.get(db_s.id)
        if mem:
            result.append(mem.to_dict())
        else:
            result.append({
                "id": db_s.id,
                "title": db_s.title,
                "model": db_s.model,
                "status": db_s.status,
                "created_at": db_s.created_at,
                "updated_at": db_s.updated_at,
                "message_count": 0,
            })
    return result


@router.get("/sessions/{session_id}")
async def get_session_endpoint(session_id: str) -> dict[str, Any]:
    session = restore_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session.to_dict()


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session_endpoint(session_id: str) -> None:
    # Remove from memory if loaded; don't 404 if not in memory — it may only be in DB.
    manager.delete(session_id)
    if not delete_session(session_id):
        raise HTTPException(404, "Session not found")


# ── Message endpoints ──────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str) -> list[dict[str, Any]]:
    # Verify session exists in memory or DB
    if not manager.get(session_id) and not get_session(session_id):
        raise HTTPException(404, "Session not found")
    return get_messages_for_api(session_id)


# ── Prompt / streaming ─────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/prompt")
async def send_prompt(session_id: str, req: SendPromptRequest) -> StreamingResponse:
    """Stream a session turn as Server-Sent Events."""
    session = restore_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status == "running":
        raise HTTPException(409, "Session is already running")

    original_prompt = req.prompt
    inlined_prompt = req.prompt
    if req.attachment_ids:
        inlined_prompt, _images = session.resolve_attachments(inlined_prompt, req.attachment_ids)

    import json as _json

    async def _stream():
        async for event in run_session_turn(
            session,
            inlined_prompt,
            original_prompt=original_prompt,
            attachment_ids=req.attachment_ids,
        ):
            session.broadcast(event)
            yield f"data: {_json.dumps(event)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
