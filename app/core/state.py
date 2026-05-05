"""
State dataclasses for the agent system.

Pure data structures with no dependencies on other modules.
"""

# @TODO: I don't want sub-agent execution anymore since I decided to go with a more practical approach 
# with locally hosted models that are quantized. It's more pragmatic to have a single executor agent 
# for managing MCP functions/tool calls (e.g. email MCP, blog post MCP, web scraping MCP, etc.)

from __future__ import annotations

# from dataclasses import dataclass, field  # Revert back to this if there are any erros in pydantic models
from pydantic import BaseModel, Field
import uuid

# I'll be using FastMCP for agent tools, so this might be redefined (or phased out more likely).
class ToolCall(BaseModel):
    """Canonical internal representation of a requested tool call."""
    name: str
    arguments: dict = Field(default_factory=dict)
    call_id: str = ""

    def ensure_call_id(self) -> "ToolCall":
        if not self.call_id:
            self.call_id = uuid.uuid4().hex[:12]
        return self

# Same as above ^^^
class ToolResult(BaseModel):
    """Result returned by every tool execution."""
    success: bool
    data: str
    metadata: dict = Field(default_factory=dict)
    error: str | None = None
    summary: str = ""

    def as_envelope(self, call: ToolCall) -> dict:
        """Machine-friendly deterministic result payload for LLM feedback."""
        return {
            "call_id": call.call_id,
            "name": call.name,
            "ok": self.success,
            "summary": self.summary or (self.data[:200] if self.data else (self.error or "")),
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
        }

# This is probably fine to keep (we'll see)
class TurnState(BaseModel):
    """State for a single turn in the agent loop."""
    turn_number: int
    phase: str = "PLANNING"
    model_response: str | None = None
    parsed_tools: list[ToolCall] | None = None
    parsed_reasoning: str | None = None
    parsed_response: str | None = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    error: str | None = None
    retry_count: int = 0

# Keep this too
class AgentState(BaseModel):
    """Persistent state across the entire agent run."""
    total_turns: int = 0
    max_turns: int = 15
    tool_call_history: list[ToolCall] = Field(default_factory=list)
    phase: str = "discover"  # discover -> modify -> verify

# And this one ^^^
class AgentResult(BaseModel):
    """Final output from an agent run."""
    result: str | None
    turns: int
    reason: str  # "done", "max_turns", "deadlock", "error"
    tool_calls_made: int = 0
    files_modified: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    elapsed_seconds: float = 0.0

# ^^^
class ParseResult(BaseModel):
    """Output from the response parser."""
    mode: str  # "native", "structured", "legacy", "array", "plain"
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reasoning: str = ""
    response: str = ""
    status: str = ""
    diagnostics: dict = Field(default_factory=dict)
    raw_content: str = ""

# ^^^
class ValidationResult(BaseModel):
    """Output from tool call validation."""
    valid: bool
    errors: list[str] = Field(default_factory=list)
    schema_mismatch: bool = False

# This is the model that will be heavily scrutinized since the agent harness scope is changing to a more deterministic execution workflow using the LLM as the executor/orchestrator (through MCP definitions)
class TaskSpec(BaseModel):
    """Specification for a sub-agent task, used as the contract between orchestrator and sub-agent."""
    task_id: str
    goal: str
    agent_name: str = ""
    file_paths: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    predecessor: str = ""  # name of a previous agent whose context to inherit
    directives: str = ""
    expected_status: str = "completed"

    def to_prompt(self) -> str:
        """Serialize this spec into a compact prompt string for the sub-agent."""
        lines = [f"**Task ID:** {self.task_id}", f"**Goal:** {self.goal}"]
        if self.depends_on:
            lines.append(f"**Depends On:** {', '.join(self.depends_on)}")
        if self.file_paths:
            lines.append(f"**Files:** {', '.join(self.file_paths)}")
        if self.constraints:
            lines.append("**Constraints:**")
            for c in self.constraints:
                lines.append(f"- {c}")
        if self.acceptance_criteria:
            lines.append("**Acceptance Criteria:**")
            for a in self.acceptance_criteria:
                lines.append(f"- {a}")
        if self.directives:
            lines.append("**Directives:**")
            lines.append(self.directives)
        return "\n".join(lines)

# Definitely depricate this since I'm moving away from sub-agents and instead having a single executor agent that handles all MCP functions/tool calls. The TaskSpec can still be useful as a data structure for defining MCP tasks, but the SubAgentResult is too specific to the previous sub-agent execution model.
class SubAgentResult(BaseModel):
    """Result returned by a sub-agent execution."""
    success: bool
    output: str
    task_id: str = ""
    agent_name: str = ""
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    summary: str = ""
    turns_used: int = 0
    errors: list[str] = Field(default_factory=list)
