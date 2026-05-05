"""
State dataclasses for the agent system.

Pure data structures with no dependencies on other modules.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
import uuid


class ToolCall(BaseModel):
    """Canonical internal representation of a requested tool call."""
    name: str
    arguments: dict = Field(default_factory=dict)
    call_id: str = ""

    def ensure_call_id(self) -> "ToolCall":
        if not self.call_id:
            self.call_id = uuid.uuid4().hex[:12]
        return self


class ToolResult(BaseModel):
    """Result returned by every tool execution."""
    success: bool
    data: str
    metadata: dict = Field(default_factory=dict)
    error: str | None = None
    summary: str = ""

    def as_envelope(self, call: ToolCall) -> dict:
        return {
            "call_id": call.call_id,
            "name": call.name,
            "ok": self.success,
            "summary": self.summary or (self.data[:200] if self.data else (self.error or "")),
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
        }


class AgentResult(BaseModel):
    """Final output from an agent run."""
    result: str | None
    turns: int
    reason: str  # "done", "max_turns", "error"
    tool_calls_made: int = 0
    files_modified: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    elapsed_seconds: float = 0.0


class ParseResult(BaseModel):
    """Output from the response parser."""
    mode: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reasoning: str = ""
    response: str = ""
    status: str = ""
    raw_content: str = ""
    diagnostics: dict = Field(default_factory=dict)
