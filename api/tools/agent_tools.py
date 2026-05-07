"""
Agent communication tools — filesystem-based orchestrator to sub-agent messaging.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from langchain_core.tools import tool

from agent.core.workspace import Workspace


def _workspace_for_cwd() -> Workspace:
    return Workspace(project_root=Path.cwd())


@tool
def workspace_read(
    file: Annotated[Literal["project", "plan", "status"], "Which spec file to read: project.md, plan.md, or status.md"],
) -> str:
    """Read a workspace-level spec file: project.md, plan.md, or status.md."""
    try:
        ws = _workspace_for_cwd()
        readers = {"project": ws.read_project, "plan": ws.read_plan, "status": ws.read_status}
        reader = readers.get(file)
        if not reader:
            return f"ERROR: Unknown file: {file}. Use: project, plan, or status"
        content = reader()
        return content or f"(No {file}.md found in workspace)"
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def agent_report(
    agent_name: Annotated[str, "Your agent name"],
    status: Annotated[str, "Current status (running, completed, blocked)"],
    message: Annotated[str, "Progress or status description"],
) -> str:
    """Report your status and progress to the orchestrator."""
    try:
        ws = _workspace_for_cwd()
        ws.write_agent_status(agent_name, f"{status}\n{message}")
        if status == "completed":
            ws.write_agent_output(agent_name, message)
        return f"Status reported: {status}"
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def agent_read(
    agent_name: Annotated[str, "Name of the agent whose file to read"],
    file: Annotated[str, "File type: task, directives, status, output, or context"],
) -> str:
    """Read a file from another agent's workspace directory."""
    try:
        ws = _workspace_for_cwd()
        readers = {
            "task": ws.read_agent_task,
            "status": ws.read_agent_status,
            "output": ws.read_agent_output,
            "context": ws.read_agent_context,
            "directives": ws.read_agent_directives,
        }
        reader = readers.get(file)
        if not reader:
            return f"ERROR: Unknown file: {file}. Use: task, status, output, context, or directives"
        content = reader(agent_name)
        return content or f"(No {file}.md found for agent '{agent_name}')"
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def send_directive(
    agent_name: Annotated[str, "Name of the agent to send the directive to"],
    directive: Annotated[str, "Directive or instruction to send"],
) -> str:
    """Send a directive/instruction to a sub-agent (writes to their directives.md)."""
    try:
        ws = _workspace_for_cwd()
        existing = ws.read_agent_directives(agent_name)
        content = (existing + "\n\n---\n\n" + directive) if existing else directive
        ws.write_agent_directives(agent_name, content)
        return f"Directive sent to '{agent_name}'"
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def request_help(
    agent_name: Annotated[str, "Your agent name"],
    blocker: Annotated[str, "Description of the blocker"],
    suggested_action: Annotated[str, "Suggested action to resolve the blocker"] = "",
) -> str:
    """Flag a blocker to the orchestrator."""
    try:
        ws = _workspace_for_cwd()
        status = f"blocked\nBLOCKER: {blocker}"
        if suggested_action:
            status += f"\nSUGGESTED: {suggested_action}"
        ws.write_agent_status(agent_name, status)
        return f"Help requested: {blocker}"
    except Exception as exc:
        return f"ERROR: {exc}"