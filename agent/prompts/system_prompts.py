"""
System prompts — loaded from markdown template files.

Prompt templates live in app/prompts/*.md and use {variable} placeholders.
"""

from __future__ import annotations

import os
from pathlib import Path

from agent import config

_PROMPTS_DIR = Path(__file__).parent


def _load_template(name: str) -> str:
    """Load a .md prompt template from the prompts directory."""
    path = _PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def _get_project_root() -> str:
    """Return the absolute path to the current project root (cwd)."""
    return str(Path.cwd().resolve())


def main_system_prompt(
    tools_desc: str,
    project_root: str = "",
    workspace_root: str = "",
    workspace_key: str = "",
    project_name: str = "",
) -> str:
    """Build the main agent system prompt from main.md template."""
    template = _load_template("main.md")
    return template.format(
        tools_desc=tools_desc,
        project_root=project_root or _get_project_root(),
        workspace_root=workspace_root or str(Path(config.WORKSPACE_PROJECTS_DIR).expanduser().resolve()),
        workspace_key=workspace_key or "",
        project_name=project_name or Path(project_root or _get_project_root()).name,
    )


def orchestrator_prompt(
    tools_desc: str,
    workspace_context: str = "",
    project_root: str = "",
    workspace_root: str = "",
    workspace_key: str = "",
    project_name: str = "",
) -> str:
    """Build the orchestrator decomposition prompt from orchestrator.md."""
    template = _load_template("orchestrator.md")
    return template.format(
        tools_desc=tools_desc,
        workspace_context=workspace_context or "(No workspace initialized yet)",
        project_root=project_root or _get_project_root(),
        workspace_root=workspace_root or "",
        workspace_key=workspace_key or "",
        project_name=project_name or Path(project_root or _get_project_root()).name,
    )


def sub_agent_prompt(
    task_spec: str,
    tools_desc: str,
    agent_name: str = "",
    project_spec: str = "",
    directives: str = "",
    inherited_context: str = "",
    project_root: str = "",
    workspace_root: str = "",
    workspace_key: str = "",
    project_name: str = "",
) -> str:
    """Build a sub-agent prompt from sub_agent.md template."""
    template = _load_template("sub_agent.md")
    return template.format(
        task_spec=task_spec,
        tools_desc=tools_desc,
        agent_name=agent_name or "agent",
        project_spec=project_spec or "(No project spec available)",
        directives=directives or "(No specific directives)",
        inherited_context=inherited_context or "(No inherited context)",
        project_root=project_root or _get_project_root(),
        workspace_root=workspace_root or "",
        workspace_key=workspace_key or "",
        project_name=project_name or Path(project_root or _get_project_root()).name,
    )
