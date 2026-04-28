"""
State dataclasses for the agent system.

Pure data structures with no dependencies on other modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import uuid


@dataclass
class ToolCall:
    """Canonical internal representation of a requested tool call."""
    name: str
    arguments: dict = field(default_factory=dict)
    call_id: str = ""

    def ensure_call_id(self) -> "ToolCall":
        if not self.call_id:
            self.call_id = uuid.uuid4().hex[:12]
        return self


@dataclass
class ToolResult:
    """Result returned by every tool execution."""
    success: bool
    data: str
    metadata: dict = field(default_factory=dict)
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


@dataclass
class TurnState:
    """State for a single turn in the agent loop."""
    turn_number: int
    phase: str = "PLANNING"
    model_response: str | None = None
    parsed_tools: list[ToolCall] | None = None
    parsed_reasoning: str | None = None
    parsed_response: str | None = None
    tool_results: list[ToolResult] = field(default_factory=list)
    error: str | None = None
    retry_count: int = 0


@dataclass
class AgentState:
    """Persistent state across the entire agent run."""
    total_turns: int = 0
    max_turns: int = 15
    tool_call_history: list[ToolCall] = field(default_factory=list)
    phase: str = "discover"  # discover -> modify -> verify


@dataclass
class AgentResult:
    """Final output from an agent run."""
    result: str | None
    turns: int
    reason: str  # "done", "max_turns", "deadlock", "error"
    tool_calls_made: int = 0
    files_modified: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


@dataclass
class ParseResult:
    """Output from the response parser."""
    mode: str  # "native", "structured", "legacy", "array", "plain"
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: str = ""
    response: str = ""
    status: str = ""
    diagnostics: dict = field(default_factory=dict)
    raw_content: str = ""


@dataclass
class ValidationResult:
    """Output from tool call validation."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    schema_mismatch: bool = False


@dataclass
class TaskSpec:
    """Specification for a sub-agent task, used as the contract between orchestrator and sub-agent."""
    task_id: str
    goal: str
    agent_name: str = ""
    file_paths: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
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


@dataclass
class SubAgentResult:
    """Result returned by a sub-agent execution."""
    success: bool
    output: str
    task_id: str = ""
    agent_name: str = ""
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    summary: str = ""
    turns_used: int = 0
    errors: list[str] = field(default_factory=list)
