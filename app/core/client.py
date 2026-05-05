"""
MCPAgentClient — thin async HTTP/WebSocket client for the Agent API server.

All calls go to the REST API (api/) running at API_BASE_URL.
Streaming chat uses a WebSocket subscription that listens for events while
the REST prompt POST drives the turn.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import websockets

from app import config


class MCPAgentClient:
    """Async client wrapping the Agent API REST + WebSocket interface."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base = (base_url or config.API_BASE_URL).rstrip("/")
        self._http = httpx.AsyncClient(base_url=self._base, timeout=60.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "MCPAgentClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ── Health ────────────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        r = await self._http.get("/api/health")
        r.raise_for_status()
        return r.json()

    # ── Models ────────────────────────────────────────────────────────────────

    async def list_models(self) -> list[str]:
        r = await self._http.get("/api/models")
        r.raise_for_status()
        data = r.json()
        return [m.get("name", "") for m in data.get("models", [])]

    # ── Sessions ─────────────────────────────────────────────────────────────

    async def create_session(self, model: str, title: str = "New chat") -> dict[str, Any]:
        r = await self._http.post("/api/sessions", json={"model": model, "title": title})
        r.raise_for_status()
        return r.json()

    async def list_sessions(self) -> list[dict[str, Any]]:
        r = await self._http.get("/api/sessions")
        r.raise_for_status()
        return r.json()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/api/sessions/{session_id}")
        r.raise_for_status()
        return r.json()

    async def delete_session(self, session_id: str) -> None:
        r = await self._http.delete(f"/api/sessions/{session_id}")
        r.raise_for_status()

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        r = await self._http.get(f"/api/sessions/{session_id}/messages")
        r.raise_for_status()
        return r.json()

    # ── Prompt streaming ─────────────────────────────────────────────────────

    async def stream_prompt(
        self,
        session_id: str,
        prompt: str,
        attachment_ids: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Send a prompt and stream SSE events from the REST endpoint.

        Events yielded are dicts with at least a "type" key:
          - turn_start
          - token          {"delta": str}
          - tool_call      {"name": str, "arguments": dict}
          - tool_result    {"name": str, "ok": bool, "summary": str}
          - turn_done      {"status": str}
          - error          {"detail": str}
        """
        payload: dict[str, Any] = {"prompt": prompt}
        if attachment_ids:
            payload["attachment_ids"] = attachment_ids

        async with self._http.stream(
            "POST",
            f"/api/sessions/{session_id}/prompt",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for raw_line in response.aiter_lines():
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if not data_str:
                    continue
                try:
                    yield json.loads(data_str)
                except json.JSONDecodeError:
                    yield {"type": "error", "detail": f"bad SSE payload: {data_str}"}

    # ── WebSocket streaming (alternative to SSE) ──────────────────────────────

    async def ws_stream(
        self,
        session_id: str,
        prompt: str,
        attachment_ids: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Drive a turn via REST prompt POST while subscribing to WS events.

        This is an alternative to stream_prompt for consumers that prefer WS.
        Events are the same format as stream_prompt.
        """
        ws_url = self._base.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/sessions/{session_id}/ws"

        async with websockets.connect(ws_url) as ws:
            # Fire the prompt (don't await the whole response — we'll get events via WS)
            payload: dict[str, Any] = {"prompt": prompt}
            if attachment_ids:
                payload["attachment_ids"] = attachment_ids

            import asyncio

            prompt_task = asyncio.create_task(
                self._http.post(f"/api/sessions/{session_id}/prompt", json=payload)
            )

            try:
                async for raw in ws:
                    event = json.loads(raw)
                    yield event
                    if event.get("type") in ("turn_done", "error"):
                        break
            finally:
                await prompt_task

    # ── Workflows ─────────────────────────────────────────────────────────────

    async def list_workflows(self) -> list[dict[str, Any]]:
        r = await self._http.get("/api/workflows")
        r.raise_for_status()
        return r.json()

    async def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/api/workflows/{workflow_id}")
        r.raise_for_status()
        return r.json()

    async def create_workflow(
        self,
        name: str,
        description: str = "",
        definition: dict | None = None,
    ) -> dict[str, Any]:
        r = await self._http.post(
            "/api/workflows",
            json={"name": name, "description": description, "definition": definition or {}},
        )
        r.raise_for_status()
        return r.json()

    async def delete_workflow(self, workflow_id: str) -> None:
        r = await self._http.delete(f"/api/workflows/{workflow_id}")
        r.raise_for_status()
