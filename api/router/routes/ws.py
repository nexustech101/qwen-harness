"""WebSocket routes for streaming runtime events from agent sessions."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.modules.session_manager import manager
from api.config.config import get_settings
from api.config.security import decode_token
from api.services.user_service import get_user_by_id

router = APIRouter()


class WebSocketAuthError(Exception):
    pass


@router.websocket("/api/sessions/{session_id}/ws")
async def session_websocket(websocket: WebSocket, session_id: str):
    try:
        user_id = await _resolve_user_id(websocket)
    except WebSocketAuthError:
        await websocket.close(code=4401, reason="Invalid access token")
        return

    session = await asyncio.to_thread(manager.get, session_id, user_id=user_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    queue = session.subscribe()

    try:
        await websocket.send_json(
            {
                "type": "connected",
                "agent": "system",
                "data": {
                    "session_id": session_id,
                    "status": session.status,
                    "agents": list(session.agents.keys()),
                },
                "timestamp": 0,
            }
        )
        await asyncio.gather(
            _forward_events(websocket, queue),
            _receive_messages(websocket, user_id),
        )
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        session.unsubscribe(queue)


async def _forward_events(websocket: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=30.0)
            await websocket.send_json(event)
        except asyncio.TimeoutError:
            try:
                await websocket.send_json({"type": "ping", "agent": "system", "data": {}, "timestamp": 0})
            except Exception:
                return
        except Exception:
            return


async def _receive_messages(websocket: WebSocket, user_id: int | None) -> None:
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "cancel":
                session_id = data.get("session_id")
                if session_id:
                    session = await asyncio.to_thread(manager.get, str(session_id), user_id=user_id)
                    if session and session._task and not session._task.done():
                        session._task.cancel()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


async def _resolve_user_id(websocket: WebSocket) -> int | None:
    token = _extract_token(websocket)
    if not token:
        return None

    try:
        settings = get_settings()
        payload = decode_token(token, expected_type="access", settings=settings)
        subject = payload.get("sub")
        if not subject:
            raise WebSocketAuthError
        user_id = int(subject)
        user = await asyncio.to_thread(get_user_by_id, user_id)
        if not user.is_active:
            raise WebSocketAuthError
        return user_id
    except WebSocketAuthError:
        raise
    except Exception as exc:
        raise WebSocketAuthError from exc


def _extract_token(websocket: WebSocket) -> str:
    auth_header = websocket.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return (websocket.query_params.get("token") or "").strip()
