"""WebSocket route for streaming session events."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.modules.session_manager import manager

router = APIRouter()


@router.websocket("/sessions/{session_id}/ws")
async def session_websocket(websocket: WebSocket, session_id: str) -> None:
    session = manager.get(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    queue = session.subscribe()

    try:
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "status": session.status,
        })
        await asyncio.gather(
            _forward_events(websocket, queue),
            _receive_controls(websocket, session_id),
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
                await websocket.send_json({"type": "ping"})
            except Exception:
                return
        except Exception:
            return


async def _receive_controls(websocket: WebSocket, session_id: str) -> None:
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "cancel":
                session = manager.get(session_id)
                if session and session._task and not session._task.done():
                    session._task.cancel()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
