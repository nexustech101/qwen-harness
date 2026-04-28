"""
Task dispatcher — sequential and async execution of sub-agent tasks.

Sequential mode: tasks run one at a time, respecting depends_on ordering.
Async mode: independent tasks run concurrently via asyncio, gated by a semaphore.
"""

from __future__ import annotations

import asyncio
from functools import partial
from graphlib import TopologicalSorter, CycleError

from rich.console import Console

from app import config
from app.core.state import SubAgentResult, TaskSpec
from app.core.sub_agent import SubAgentRunner
from app.core.workspace import Workspace
from app.logging import file_logger
from app.logging.trace import Trace


class Dispatcher:
    """Dispatches TaskSpecs to SubAgentRunners sequentially or concurrently."""

    def __init__(
        self,
        model: str | None = None,
        max_turns: int | None = None,
        console: Console | None = None,
        workspace: Workspace | None = None,
        project_root: str = "",
        parent_trace: "Trace | None" = None,
    ) -> None:
        self._model = model or config.MODEL
        self._max_turns = max_turns or config.SUB_AGENT_MAX_TURNS
        self._console = console or Console()
        self._workspace = workspace
        self._project_root = project_root
        self._parent_trace = parent_trace

    def run_sequential(self, specs: list[TaskSpec]) -> list[SubAgentResult]:
        """Run tasks sequentially, respecting dependency order."""
        results: list[SubAgentResult] = []
        results_by_id: dict[str, SubAgentResult] = {}

        for spec in self._topological_sort(specs):
            # Check dependencies
            if not self._deps_satisfied(spec, results_by_id):
                file_logger.log_warning(f"Sub-agent '{spec.agent_name}' skipped: dependency failed")
                skipped = SubAgentResult(
                    success=False,
                    output="",
                    task_id=spec.task_id,
                    agent_name=spec.agent_name,
                    summary="Skipped: dependency failed",
                    errors=["Dependency task failed"],
                )
                results.append(skipped)
                results_by_id[spec.task_id] = skipped
                continue

            runner = SubAgentRunner(
                model=self._model,
                max_turns=self._max_turns,
                console=self._console,
                workspace=self._workspace,
                project_root=self._project_root,
                parent_trace=self._parent_trace,
            )
            result = runner.run(spec)
            if not result.success:
                file_logger.log_error(
                    f"Sub-agent '{spec.agent_name}' failed: "
                    f"{'; '.join(result.errors) if result.errors else 'unknown'}"
                )
            results.append(result)
            results_by_id[spec.task_id] = result

        return results

    def run_async(self, specs: list[TaskSpec]) -> list[SubAgentResult]:
        """Run independent tasks concurrently, sequential tasks in order.

        Uses asyncio with a semaphore to limit concurrent sub-agents.
        Agents sharing file targets are serialized automatically.
        """
        return asyncio.run(self._run_async_impl(specs))

    async def _run_async_impl(self, specs: list[TaskSpec]) -> list[SubAgentResult]:
        """Internal async implementation."""
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_AGENTS)
        results_by_id: dict[str, SubAgentResult] = {}
        sorted_specs = self._topological_sort(specs)

        # Group by dependency level for concurrent execution
        levels = self._build_levels(sorted_specs)

        for level in levels:
            # All tasks in a level can run concurrently
            tasks = []
            for spec in level:
                tasks.append(self._run_one_async(semaphore, spec, results_by_id))
            await asyncio.gather(*tasks)

        ordered: list[SubAgentResult] = []
        for spec in sorted_specs:
            ordered.append(
                results_by_id.get(
                    spec.task_id,
                    SubAgentResult(
                        success=False,
                        output="",
                        task_id=spec.task_id,
                        agent_name=spec.agent_name,
                        errors=["Not executed"],
                    ),
                )
            )
        return ordered

    async def _run_one_async(
        self,
        semaphore: asyncio.Semaphore,
        spec: TaskSpec,
        results_by_id: dict[str, SubAgentResult],
    ) -> None:
        """Run a single sub-agent under the semaphore."""
        async with semaphore:
            # Check dependencies
            if not self._deps_satisfied(spec, results_by_id):
                file_logger.log_warning(f"Sub-agent '{spec.agent_name}' skipped (async): dependency failed")
                results_by_id[spec.task_id] = SubAgentResult(
                    success=False,
                    output="",
                    task_id=spec.task_id,
                    agent_name=spec.agent_name,
                    summary="Skipped: dependency failed",
                    errors=["Dependency task failed"],
                )
                return

            runner = SubAgentRunner(
                model=self._model,
                max_turns=self._max_turns,
                console=self._console,
                workspace=self._workspace,
                project_root=self._project_root,
                parent_trace=self._parent_trace,
            )
            # Run in executor to avoid blocking the event loop (ollama is sync)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, partial(runner.run, spec))
            if not result.success:
                file_logger.log_error(
                    f"Sub-agent '{spec.agent_name}' failed (async): "
                    f"{'; '.join(result.errors) if result.errors else 'unknown'}"
                )
            results_by_id[spec.task_id] = result

    @staticmethod
    def _topological_sort(specs: list[TaskSpec]) -> list[TaskSpec]:
        """Sort specs by dependency order using Kahn's algorithm with cycle detection."""
        graph: dict[str, set[str]] = {}
        known_ids = {spec.task_id for spec in specs}
        for spec in specs:
            deps = set()
            for d in spec.depends_on:
                if d not in known_ids or d == spec.task_id:
                    file_logger.log_warning(
                        f"Task {spec.task_id} ({spec.agent_name}) has invalid dependency id: {d}"
                    )
                    continue
                deps.add(d)
            graph[spec.task_id] = deps

        try:
            sorter = TopologicalSorter(graph)
            order = list(sorter.static_order())
        except CycleError as e:
            file_logger.log_error(f"Cycle detected in task dependencies: {e}")
            # Fall back to original order rather than crashing
            return list(specs)

        by_id = {s.task_id: s for s in specs}
        return [by_id[i] for i in order if i in by_id]

    @staticmethod
    def _deps_satisfied(
        spec: TaskSpec,
        results_by_id: dict[str, SubAgentResult],
    ) -> bool:
        """Check if all dependencies completed successfully."""
        for dep_id in spec.depends_on:
            dep_result = results_by_id.get(dep_id)
            if dep_result is None or not dep_result.success:
                return False
        return True

    @staticmethod
    def _build_levels(specs: list[TaskSpec]) -> list[list[TaskSpec]]:
        """Group specs into dependency levels for concurrent execution."""
        levels: list[list[TaskSpec]] = []
        assigned: set[str] = set()

        while len(assigned) < len(specs):
            level: list[TaskSpec] = []
            for spec in specs:
                if spec.task_id in assigned:
                    continue
                # All deps must be in assigned set
                if all(d in assigned for d in spec.depends_on):
                    level.append(spec)
            if not level:
                # Circular dependency or error — add remaining
                for spec in specs:
                    if spec.task_id not in assigned:
                        level.append(spec)
                levels.append(level)
                break
            for spec in level:
                assigned.add(spec.task_id)
            levels.append(level)

        return levels
