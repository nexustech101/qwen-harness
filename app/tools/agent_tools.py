"""
Agent communication tools — filesystem-based orchestrator↔sub-agent messaging.

These tools let agents read workspace specs, report progress, read other
agents' outputs, send directives, and flag blockers. All communication
goes through the central workspace directory selected for the current project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from app.core.state import ToolResult
from app.core.workspace import Workspace
from app.tools.registry import registry
# from harness.tools import schemas


def _workspace_for_cwd() -> Workspace:
    """Resolve workspace for the current project root."""
    return Workspace(project_root=Path.cwd())


# ── Read Workspace Specs ───────────────────────────────────────────────────────

@registry.tool(
    name="workspace_read",
    category="agent",
    description="Read a workspace-level spec file: project.md, plan.md, or status.md",
)
def workspace_read(
    file: Annotated[Literal["project", "plan", "status"], "Which workspace-level file to read: project.md, plan.md, or status.md"],
) -> ToolResult:
    try:
        ws = _workspace_for_cwd()
        readers = {
            "project": ws.read_project,
            "plan": ws.read_plan,
            "status": ws.read_status,
        }

        reader = readers.get(file)
        if not reader:
            return ToolResult(
                success=False, data="",
                error=f"Unknown file: {file}. Use: project, plan, or status",
            )

        content = reader()
        if not content:
            return ToolResult(
                success=True,
                data=f"(No {file}.md found in workspace)",
                metadata={"exists": False},
            )

        return ToolResult(
            success=True,
            data=content,
            metadata={"exists": True, "file": f"{file}.md"},
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Workspace read error: {e}")


# ── Agent Status Report ───────────────────────────────────────────────────────

@registry.tool(
    name="agent_report",
    category="agent",
    description="Report your status and progress to the orchestrator (writes to your status.md)",
)
def agent_report(
    agent_name: Annotated[str, "Your agent name (used to identify your status file)"],
    status: Annotated[str, "Your current status (e.g., running, completed, blocked)"],
    message: Annotated[str, "A message describing your current progress or status"],
) -> ToolResult:
    try:
        ws = _workspace_for_cwd()
        content = f"{status}\n{message}"
        ws.write_agent_status(agent_name, content)

        # Also write to output.md if completed
        if status == "completed":
            ws.write_agent_output(agent_name, message)

        return ToolResult(
            success=True,
            data=f"Status reported: {status}",
            metadata={"agent": agent_name, "status": status},
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Report error: {e}")


# ── Read Another Agent's Files ─────────────────────────────────────────────────

@registry.tool(
    name="agent_read",
    category="agent",
    description="Read a file from another agent's workspace directory (task, directives, status, output, context)",
)
def agent_read(
    agent_name: Annotated[str, "The name of the agent whose file to read"],
    file: Annotated[str, "The type of file to read (task, directives, status, output, context)"],
) -> ToolResult:
    try:
        ws = _workspace_for_cwd()
        readers = {
            "task":       ws.read_agent_task,
            "status":     ws.read_agent_status,
            "output":     ws.read_agent_output,
            "context":    ws.read_agent_context,
            "directives": ws.read_agent_directives,
        }

        reader = readers.get(file)
        if not reader:
            return ToolResult(
                success=False, data="",
                error=f"Unknown file: {file}. Use: task, status, output, context, or directives",
            )

        content = reader(agent_name)
        if not content:
            return ToolResult(
                success=True,
                data=f"(No {file}.md found for agent '{agent_name}')",
                metadata={"exists": False},
            )

        return ToolResult(
            success=True,
            data=content,
            metadata={"exists": True, "agent": agent_name, "file": file},
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Agent read error: {e}")


# ── Send Directive ─────────────────────────────────────────────────────────────

@registry.tool(
    name="send_directive",
    category="agent",
    description="Send a directive/instruction to a sub-agent (writes to their directives.md)",
)
def send_directive(
    agent_name: Annotated[str, "The name of the agent to send the directive to"],
    directive: Annotated[str, "The directive or instruction to send to the agent"],
) -> ToolResult:
    try:
        ws = _workspace_for_cwd()
        # Append to existing directives (don't overwrite)
        existing = ws.read_agent_directives(agent_name)
        if existing:
            content = existing + "\n\n---\n\n" + directive
        else:
            content = directive

        ws.write_agent_directives(agent_name, content)

        return ToolResult(
            success=True,
            data=f"Directive sent to '{agent_name}'",
            metadata={"agent": agent_name},
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Directive error: {e}")


# ── Request Help ───────────────────────────────────────────────────────────────

@registry.tool(
    name="request_help",
    category="agent",
    description="Flag a blocker to the orchestrator (writes blocked status + creates help request)",
)
def request_help(
    agent_name: Annotated[str, "The name of the agent requesting help"],
    blocker: Annotated[str, "The description of the blocker"],
    suggested_action: Annotated[str, "The suggested action to resolve the blocker"] = "",
) -> ToolResult:
    try:
        ws = _workspace_for_cwd()
        status_content = f"blocked\nBLOCKER: {blocker}"
        if suggested_action:
            status_content += f"\nSUGGESTED: {suggested_action}"

        ws.write_agent_status(agent_name, status_content)

        return ToolResult(
            success=True,
            data=f"Help requested: {blocker}",
            metadata={"agent": agent_name, "blocker": blocker},
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Help request error: {e}")
