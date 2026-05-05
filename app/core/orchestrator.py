"""
Orchestrator -- thin wrapper that drives a chat turn via MCPAgentClient.

The heavy lifting (LLM calls, tool execution) lives in the API server.
This orchestrator is purely a shell-side coordinator: it opens a session,
streams events, and surfaces them to the caller.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.client import MCPAgentClient


class Orchestrator:
    """Drive a single conversation session via the Agent API."""

    def __init__(self, client: MCPAgentClient, session_id: str) -> None:
        self._client = client
        self._session_id = session_id

    @property
    def session_id(self) -> str:
        return self._session_id

    async def run(
        self,
        prompt: str,
        attachment_ids: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream events for a single prompt turn."""
        return self._client.stream_prompt(
            self._session_id, prompt, attachment_ids=attachment_ids
        )

    @classmethod
    async def create(
        cls,
        client: MCPAgentClient,
        model: str,
        title: str = "New chat",
    ) -> "Orchestrator":
        """Create a new session and return a bound Orchestrator."""
        session = await client.create_session(model=model, title=title)
        return cls(client, session["id"])
