"""
Sub-agent runner — executes a TaskSpec in an isolated ExecutionEngine.

Each sub-agent gets its own message history, turn counter, and optionally
a restricted tool set. The central workspace directory
({workspace_home}/workspaces/<project-key>/.qwen-agent-<name>/) is used for
reading task specs/directives/context and writing status/output.
"""

from __future__ import annotations

from rich.console import Console

from app import config
from app.core.execution import ExecutionEngine
from app.core.state import SubAgentResult, TaskSpec
from app.core.workspace import Workspace
from app.core.console_renderer import ConsoleRenderer
from app.logging.trace import Trace, TraceEvent
from app.logging import file_logger
from app.prompts.system_prompts import sub_agent_prompt
from app.tools.registry import ToolRegistry, registry


class SubAgentRunner:
    """Runs a single sub-agent task in an isolated execution context."""

    def __init__(
        self,
        model: str | None = None,
        max_turns: int | None = None,
        console: Console | None = None,
        workspace: Workspace | None = None,
        project_root: str = "",
        parent_trace: Trace | None = None,
    ) -> None:
        self._model = model or config.MODEL
        self._max_turns = max_turns or config.SUB_AGENT_MAX_TURNS
        self._console = console or Console()
        self._workspace = workspace
        self._project_root = project_root
        self._parent_trace = parent_trace

    def run(self, spec: TaskSpec) -> SubAgentResult:
        """Execute a task spec and return the sub-agent result."""
        agent_name = spec.agent_name or "agent"

        # Build restricted tool registry if allowed_tools specified
        tool_reg = self._build_registry(spec.allowed_tools)
        tools_desc = tool_reg.to_prompt_format()

        # Read workspace context for this agent
        project_spec = ""
        directives = ""
        inherited_context = ""
        if self._workspace:
            project_spec = self._workspace.read_project()
            directives = self._workspace.read_agent_directives(agent_name) or spec.directives
            inherited_context = self._workspace.read_agent_context(agent_name)
            self._workspace.write_agent_status(agent_name, "in-progress")

        # Build prompt from markdown template (now with workspace context)
        sys_prompt = sub_agent_prompt(
            task_spec=spec.to_prompt(),
            tools_desc=tools_desc,
            agent_name=agent_name,
            project_spec=project_spec,
            directives=directives,
            inherited_context=inherited_context,
            project_root=self._project_root,
            workspace_root=str(self._workspace.root) if self._workspace else "",
            workspace_key=self._workspace.workspace_key if self._workspace else "",
            project_name=self._workspace.project_name if self._workspace else "",
        )

        # Create isolated trace + optional relay to parent (API mode)
        trace = Trace()
        if self._parent_trace:
            def _relay(event: "TraceEvent") -> None:
                self._parent_trace.emit(
                    f"sub_{event.event_type}",
                    agent_name=agent_name,
                    **event.data,
                )
            trace.subscribe_all(_relay)
        else:
            ConsoleRenderer(trace, self._console)
        file_logger.attach_to_trace(trace)

        # Create isolated execution engine
        engine = ExecutionEngine(
            registry=tool_reg,
            trace=trace,
            system_prompt=sys_prompt,
            model=self._model,
            max_turns=self._max_turns,
        )

        # Run
        agent_result = engine.run(spec.goal)

        result = SubAgentResult(
            success=agent_result.reason == "done",
            output=agent_result.result or "",
            task_id=spec.task_id,
            agent_name=agent_name,
            files_created=[],
            files_modified=list(agent_result.files_modified),
            summary=agent_result.result or "",
            turns_used=agent_result.turns,
            errors=list(agent_result.errors),
        )

        # Write status/output back to workspace
        if self._workspace:
            status = "completed" if result.success else "failed"
            self._workspace.write_agent_status(
                agent_name, f"{status}\n{result.summary}"
            )
            self._workspace.write_agent_output(
                agent_name, result.output or result.summary
            )

        return result

    @staticmethod
    def _build_registry(allowed_tools: list[str]) -> ToolRegistry:
        """Return a filtered registry if allowed_tools is specified, else full registry."""
        if not allowed_tools:
            return registry

        filtered = ToolRegistry()
        for entry in registry.list_tools():
            if entry.name in allowed_tools:
                filtered._tools[entry.name] = entry
        return filtered
