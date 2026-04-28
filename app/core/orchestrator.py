"""
Top-level orchestrator — routes simple tasks directly and optionally decomposes
complex tasks into sub-agents.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from rich.console import Console

from app import config
from app.core.dispatcher import Dispatcher
from app.core.execution import ExecutionEngine
from app.core.state import AgentResult, SubAgentResult, TaskSpec
from app.core.workspace import Workspace
from app.logging.console_renderer import ConsoleRenderer
from app.logging.trace import Trace
from app.logging import file_logger
from app.prompts.system_prompts import main_system_prompt, orchestrator_prompt
from app.tools.registry import registry

# Ensure all tools are registered
import app.tools.file_tools      # noqa: F401
import app.tools.system_tools    # noqa: F401
import app.tools.analysis_tools  # noqa: F401
import app.tools.workspace_tools # noqa: F401
import app.tools.code_tools      # noqa: F401
import app.tools.agent_tools     # noqa: F401
import app.tools.web_tools       # noqa: F401

import ollama


def _repair_json(raw: str) -> str:
    """Attempt to fix common LLM JSON mistakes."""
    repaired = re.sub(r",\s*([}\]])", r"\1", raw)
    if '"' not in repaired and "'" in repaired:
        repaired = repaired.replace("'", '"')
    return repaired


_DOMAIN_RULES = {
    "backend": {
        "keywords": ["backend", "api", "server", "fastapi", "database"],
        "goal": "Implement backend/service-side changes requested by the user.",
        "files": ["app/", "tests/"],
        "tools": [
            "list_directory", "find_files", "grep_workspace", "read_file",
            "write_file", "edit_file", "run_tests", "check_syntax",
        ],
    },
    "frontend": {
        "keywords": ["frontend", "ui", "react", "tsx", "css", "layout"],
        "goal": "Implement frontend/UI changes requested by the user.",
        "files": ["frontend/src/"],
        "tools": [
            "list_directory", "find_files", "grep_workspace", "read_file",
            "write_file", "edit_file",
        ],
    },
    "tests": {
        "keywords": ["test", "tests", "pytest", "verification", "validate"],
        "goal": "Add and run targeted tests for the requested changes.",
        "files": ["tests/", "app/"],
        "tools": [
            "list_directory", "find_files", "grep_workspace", "read_file",
            "write_file", "edit_file", "run_tests", "check_syntax",
        ],
    },
    "docs": {
        "keywords": ["docs", "documentation", "readme", "spec"],
        "goal": "Update documentation and specs to match implementation.",
        "files": ["README.md", "app/PROJECT_SPECS.md"],
        "tools": [
            "list_directory", "find_files", "read_file", "write_file", "edit_file",
        ],
    },
}


class Orchestrator:
    """Routes tasks to direct execution or sub-agent dispatch."""

    def __init__(
        self,
        model: str | None = None,
        planner_model: str | None = None,
        coder_model: str | None = None,
        max_turns: int | None = None,
        project_root: str | None = None,
        console: Console | None = None,
        use_dispatch: bool = False,
        async_dispatch: bool = False,
        trace: Trace | None = None,
    ) -> None:
        self._model = model or config.MODEL
        self._planner_model = planner_model or config.PLANNER_MODEL
        self._coder_model = coder_model or config.CODER_MODEL
        self._max_turns = max_turns or config.MAX_TURNS
        self._console = console or Console()
        self._registry = registry
        self._use_dispatch = use_dispatch
        self._async_dispatch = async_dispatch
        root_path = Path(project_root).resolve() if project_root else Path.cwd().resolve()
        self._project_root = str(root_path)
        self._workspace = Workspace(project_root=root_path)
        self._trace = trace
        self._engines: dict[str, ExecutionEngine] = {}

    def run(
        self, prompt: str, images: list[str] | None = None,
    ) -> AgentResult:
        """Run the agent on a single user prompt."""
        if self._use_dispatch:
            return self._run_with_dispatch(prompt, images=images)
        return self._run_direct(prompt, images=images)

    def _run_direct(
        self, prompt: str, images: list[str] | None = None,
    ) -> AgentResult:
        """Run the agent directly (single ExecutionEngine)."""
        self._record_prompt_context(prompt)

        if self._trace:
            trace = self._trace
        else:
            trace = Trace()
            ConsoleRenderer(trace, self._console)
        file_logger.attach_to_trace(trace)

        tools_desc = self._registry.to_prompt_format()
        sys_prompt = main_system_prompt(
            tools_desc,
            project_root=self._project_root,
            workspace_root=str(self._workspace.root),
            workspace_key=self._workspace.workspace_key,
            project_name=self._workspace.project_name,
        )

        engine = ExecutionEngine(
            registry=self._registry,
            trace=trace,
            system_prompt=sys_prompt,
            model=self._coder_model,
            max_turns=self._max_turns,
        )
        self._engines["main"] = engine
        result = engine.run(prompt, images=images)
        self._update_context_after_run(prompt, result, mode="direct")
        return result

    def _run_with_dispatch(
        self, prompt: str, images: list[str] | None = None,
    ) -> AgentResult:
        """Initialize workspace, route, maybe decompose/dispatch, aggregate."""
        start = time.monotonic()
        ws = self._workspace
        ws.ensure_exists()
        info = ws.read_info()
        self._record_prompt_context(prompt)

        mode, route_reason, rule_specs = self._rule_route(prompt)
        self._console.print(f"  [dim]router={config.ROUTER_MODE} mode={mode}[/dim]")
        file_logger.log_info(f"Router decision: mode={mode}; reason={route_reason}")

        specs: list[TaskSpec] = []
        project_spec = ""
        plan = ""

        if config.ROUTER_MODE == "planner_first" or mode == "ambiguous":
            mode, specs, project_spec, plan = self._decompose(prompt, info)
        elif config.ROUTER_MODE == "hybrid" and mode == "decompose":
            planner_mode, planner_specs, planner_project, planner_plan = self._decompose(prompt, info)
            if planner_mode == "direct":
                mode = "direct"
            elif planner_mode == "decompose" and planner_specs:
                mode = "decompose"
                specs = planner_specs
                project_spec = planner_project
                plan = planner_plan
            else:
                specs = rule_specs
                project_spec = (
                    "# Project Spec\n"
                    f"- Root: {self._project_root}\n"
                    f"- Prompt: {prompt}\n"
                )
                plan = (
                    "# Dispatch Plan\n"
                    "- Routed by hybrid rules fallback\n"
                    f"- Tasks: {len(specs)}\n"
                )
        elif mode == "decompose":
            specs = rule_specs
            project_spec = (
                "# Project Spec\n"
                f"- Root: {self._project_root}\n"
                f"- Prompt: {prompt}\n"
            )
            plan = (
                "# Dispatch Plan\n"
                f"- Routed by deterministic rules ({config.ROUTER_MODE})\n"
                f"- Tasks: {len(specs)}\n"
            )

        if mode == "direct" or not specs:
            if mode != "direct":
                self._console.print(
                    "  [yellow]decomposition produced no tasks — falling back to direct mode[/yellow]"
                )
                file_logger.log_warning(f"Decomposition produced no tasks for prompt: {prompt[:120]}")
            return self._run_direct(prompt, images=images)

        if project_spec:
            ws.write_project(project_spec)
        if plan:
            ws.write_plan(plan)
        ws.write_status(f"# Status\nDecomposed into {len(specs)} tasks. Dispatching...")

        directives_map: dict[str, str] = {}
        for spec in specs:
            name = spec.agent_name or spec.task_id
            spec.agent_name = name
            ws.write_agent_task(name, spec.to_prompt())
            if spec.directives:
                ws.write_agent_directives(name, spec.directives)
                directives_map[name] = spec.directives
            if spec.predecessor:
                ws.inherit_context(name, spec.predecessor)

            handoff = (
                f"# Handoff Snapshot\n"
                f"- task_id: {spec.task_id}\n"
                f"- agent: {name}\n"
                f"- depends_on: {', '.join(spec.depends_on) if spec.depends_on else '(none)'}\n"
                f"- goal: {spec.goal}\n"
            )
            ws.write_agent_handoff(name, handoff)

        dispatcher = Dispatcher(
            model=self._coder_model,
            max_turns=config.SUB_AGENT_MAX_TURNS,
            console=self._console,
            workspace=ws,
            project_root=self._project_root,
            parent_trace=self._trace,
        )

        if self._async_dispatch:
            results = dispatcher.run_async(specs)
        else:
            results = dispatcher.run_sequential(specs)

        status_lines = ["# Status", f"Completed {len(results)} tasks.", ""]
        for spec, result in zip(specs, results):
            name = spec.agent_name
            result.agent_name = name
            result.task_id = spec.task_id
            ws.write_agent_status(
                name,
                f"{'completed' if result.success else 'failed'}\n{result.summary}",
            )
            ws.write_agent_output(name, result.output or result.summary)
            status_lines.append(
                f"- **{spec.task_id} ({name})**: {'done' if result.success else 'FAILED'} "
                f"({result.turns_used} turns)"
            )
        ws.write_status("\n".join(status_lines))

        aggregated = self._aggregate(results, start)
        self._update_context_after_dispatch(prompt, specs, results, aggregated)
        return aggregated

    def _decompose(
        self, prompt: str, info: "WorkspaceInfo | None" = None # type: ignore
    ) -> tuple[str, list[TaskSpec], str, str]:
        """Use planner LLM to classify and optionally decompose a prompt."""
        from app.core.workspace import WorkspaceInfo

        tools_desc = self._registry.to_prompt_format()

        ctx_parts: list[str] = []
        if info and info.has_project:
            ctx_parts.append(f"### Existing project.md\n{info.project_content}")
        if info and info.has_plan:
            ctx_parts.append(f"### Existing plan.md\n{info.plan_content}")
        if info and info.status_content:
            ctx_parts.append(f"### Current status.md\n{info.status_content}")
        if info and info.context_summary:
            ctx_parts.append(f"### Context Summary\n{info.context_summary}")
        if info and info.context_log:
            ctx_parts.append(f"### Context Log Tail\n{info.context_log}")
        if info and info.agent_dirs:
            ctx_parts.append(f"### Existing agents\n{', '.join(info.agent_dirs)}")
        workspace_context = "\n\n".join(ctx_parts) if ctx_parts else ""

        sys_prompt = orchestrator_prompt(
            tools_desc=tools_desc,
            workspace_context=workspace_context,
            project_root=self._project_root,
            workspace_root=str(self._workspace.root),
            workspace_key=self._workspace.workspace_key,
            project_name=self._workspace.project_name,
        )

        client = ollama.Client(host=config.OLLAMA_HOST)

        messages: list[dict] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ]

        for attempt in range(1, config.MAX_PARSE_RETRIES + 2):
            self._console.print(
                f"  [dim]planner ({self._planner_model}) attempt {attempt}...[/dim]"
            )

            try:
                response = client.chat(
                    model=self._planner_model,
                    messages=messages,
                )
            except KeyboardInterrupt:
                raise
            except Exception as e:
                self._console.print(f"  [red]planner call failed: {e}[/red]")
                file_logger.log_error(f"Planner call failed (model={self._planner_model}): {e}")
                return "direct", [], "", ""

            content = response.message.content or ""
            mode, specs, project_spec, plan, parse_error = self._parse_decomposition(content)

            if mode == "direct":
                self._console.print("  [green]planner chose direct execution[/green]")
                return "direct", [], "", ""

            if specs:
                self._console.print(f"  [green]decomposed into {len(specs)} tasks[/green]")
                return "decompose", specs, project_spec, plan

            if attempt <= config.MAX_PARSE_RETRIES:
                self._console.print(
                    f"  [yellow]parse failed ({parse_error}), retrying...[/yellow]"
                )
                file_logger.log_warning(f"Planner parse attempt {attempt} failed: {parse_error}")
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Your response could not be parsed: {parse_error}\n\n"
                        "Respond with valid JSON inside a code block."
                    ),
                })
            else:
                self._console.print(
                    f"  [red]decomposition failed after {attempt} attempts: {parse_error}[/red]"
                )
                file_logger.log_error(f"Decomposition failed after {attempt} attempts: {parse_error}")

        return "direct", [], "", ""

    @staticmethod
    def _parse_decomposition(content: str) -> tuple[str, list[TaskSpec], str, str, str]:
        """Parse LLM decomposition response into (mode, specs, project_spec, plan, error)."""
        json_str = ""
        match = re.search(r"```json\s*(\{.*\})\s*```", content, re.DOTALL)
        if not match:
            match = re.search(r"```\s*(\{.*\})\s*```", content, re.DOTALL)
        if not match:
            match = re.search(r"(\{.*\})", content, re.DOTALL)
        if not match:
            return "", [], "", "", "No JSON object found in response"

        json_str = match.group(1).strip()

        data = None
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            repaired = _repair_json(json_str)
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError:
                return "", [], "", "", f"Invalid JSON: {e}"

        if not isinstance(data, dict):
            return "", [], "", "", "JSON root is not an object"

        mode = str(data.get("mode", "")).strip().lower()
        if mode == "direct":
            return "direct", [], "", "", ""

        project_spec = str(data.get("project_spec", ""))
        plan = str(data.get("plan", ""))

        tasks_raw = data.get("tasks", [])
        if not isinstance(tasks_raw, list):
            return "decompose", [], project_spec, plan, "tasks field is not an array"
        if not tasks_raw:
            return "decompose", [], project_spec, plan, "tasks array is empty"

        specs: list[TaskSpec] = []
        raw_deps: dict[str, list] = {}

        for i, item in enumerate(tasks_raw):
            if not isinstance(item, dict):
                continue
            goal = str(item.get("goal", "")).strip()
            if not goal:
                continue

            task_id = str(item.get("task_id", "")).strip() or f"task-{i + 1}"
            task_id = _sanitize_task_id(task_id)

            spec = TaskSpec(
                task_id=task_id,
                goal=goal,
                agent_name=str(item.get("agent_name", "")).strip() or f"agent-{i + 1}",
                file_paths=item.get("file_paths", []) if isinstance(item.get("file_paths", []), list) else [],
                constraints=item.get("constraints", []) if isinstance(item.get("constraints", []), list) else [],
                acceptance_criteria=(
                    item.get("acceptance_criteria", [])
                    if isinstance(item.get("acceptance_criteria", []), list)
                    else []
                ),
                allowed_tools=item.get("allowed_tools", []) if isinstance(item.get("allowed_tools", []), list) else [],
                depends_on=[],
                predecessor=str(item.get("predecessor", "")).strip(),
                directives=str(item.get("directives", "")).strip(),
                expected_status=str(item.get("expected_status", "completed")).strip() or "completed",
            )
            raw_deps[task_id] = item.get("depends_on", []) if isinstance(item.get("depends_on", []), list) else []
            specs.append(spec)

        if not specs:
            return "decompose", [], project_spec, plan, "No valid tasks found"

        ids = [s.task_id for s in specs]
        id_by_index = {i: t for i, t in enumerate(ids)}
        known = set(ids)

        for spec in specs:
            deps: list[str] = []
            for dep in raw_deps.get(spec.task_id, []):
                dep_id = ""
                if isinstance(dep, int):
                    dep_id = id_by_index.get(dep, "")
                elif isinstance(dep, str):
                    dep_id = dep.strip()
                if not dep_id or dep_id == spec.task_id or dep_id not in known:
                    continue
                if dep_id not in deps:
                    deps.append(dep_id)
            spec.depends_on = deps

        return "decompose", specs, project_spec, plan, ""

    def _rule_route(self, prompt: str) -> tuple[str, str, list[TaskSpec]]:
        """Deterministic router: direct default, decompose for clear independent domains."""
        lowered = prompt.lower()
        domains = self._detect_domains(lowered)

        explicit_multi = any(
            phrase in lowered
            for phrase in (
                "create agent",
                "create agents",
                "sub-agent",
                "sub agent",
                "multiple agents",
                "parallel agents",
            )
        )
        parallel_hint = any(w in lowered for w in ("parallel", "independent", "separately", "simultaneously"))

        if explicit_multi or (parallel_hint and len(domains) >= 2):
            specs = self._build_rule_specs(prompt, domains)
            if len(specs) >= 2:
                return "decompose", "independent domains detected", specs

        if self._is_ambiguous(prompt, domains):
            return "ambiguous", "prompt complexity suggests planner fallback", []

        return "direct", "single-agent default", []

    def _detect_domains(self, lowered_prompt: str) -> list[str]:
        domains: list[str] = []
        for domain, cfg in _DOMAIN_RULES.items():
            if any(k in lowered_prompt for k in cfg["keywords"]):
                domains.append(domain)
        return domains

    def _is_ambiguous(self, prompt: str, domains: list[str]) -> bool:
        if len(prompt) > 700:
            return True
        if prompt.count(" and ") >= 8 and len(domains) >= 2:
            return True
        return False

    def _build_rule_specs(self, prompt: str, domains: list[str]) -> list[TaskSpec]:
        """Build TaskSpec list deterministically from detected domains."""
        if not domains:
            return []

        selected = domains[: max(2, min(len(domains), config.MAX_DECOMPOSE_AGENTS))]
        specs: list[TaskSpec] = []

        for i, domain in enumerate(selected, 1):
            cfg = _DOMAIN_RULES[domain]
            task_id = f"task-{i}-{domain}"
            agent_name = f"{domain}-agent"
            directives = (
                f"Work under {self._project_root}/ only; never write under {self._workspace.root}/. "
                f"Focus on {domain} concerns and keep changes scoped."
            )

            spec = TaskSpec(
                task_id=task_id,
                goal=f"{cfg['goal']}\nUser prompt: {prompt}",
                agent_name=agent_name,
                file_paths=list(cfg["files"]),
                constraints=[
                    "Keep edits minimal and reversible.",
                    "Do not modify unrelated modules.",
                ],
                acceptance_criteria=[
                    "Changes compile or pass targeted checks.",
                    "Output summary clearly states what changed.",
                ],
                allowed_tools=list(cfg["tools"]),
                depends_on=[],
                predecessor=specs[-1].agent_name if specs else "",
                directives=directives,
                expected_status="completed",
            )
            specs.append(spec)

        # tests/docs typically depend on implementation tasks.
        ids = [s.task_id for s in specs]
        for spec in specs:
            if spec.task_id.endswith("-tests"):
                spec.depends_on = [i for i in ids if i != spec.task_id and not i.endswith("-docs")]
            if spec.task_id.endswith("-docs"):
                spec.depends_on = [i for i in ids if i != spec.task_id]

        return specs

    @staticmethod
    def _aggregate(results: list[SubAgentResult], start_time: float) -> AgentResult:
        """Aggregate sub-agent results into a single AgentResult."""
        all_files: list[str] = []
        all_errors: list[str] = []
        summaries: list[str] = []
        total_turns = 0
        any_success = False

        for i, r in enumerate(results):
            label = r.agent_name or r.task_id or f"Task {i + 1}"
            if r.success:
                any_success = True
                summaries.append(f"{label}: {r.summary}")
            else:
                all_errors.extend(r.errors)
                summaries.append(f"{label}: FAILED — {'; '.join(r.errors)}")
            all_files.extend(r.files_modified)
            all_files.extend(r.files_created)
            total_turns += r.turns_used

        elapsed = time.monotonic() - start_time
        combined = "\n".join(summaries)

        return AgentResult(
            result=combined,
            turns=total_turns,
            reason="done" if any_success else "error",
            tool_calls_made=0,
            files_modified=list(set(all_files)),
            errors=all_errors,
            elapsed_seconds=round(elapsed, 2),
        )

    def _record_prompt_context(self, prompt: str) -> None:
        if config.CONTEXT_MODE != "session_rolling":
            return
        self._workspace.append_context_log("Prompt", prompt)

    def _update_context_after_run(self, prompt: str, result: AgentResult, mode: str) -> None:
        if config.CONTEXT_MODE != "session_rolling":
            return

        blockers = result.errors if result.errors else []
        pending = [] if result.reason == "done" else [f"Follow-up required ({result.reason})"]
        self._workspace.update_context_summary(
            repo_facts=[f"Project root: {self._project_root}"],
            decisions=[f"Execution mode: {mode}", f"Router mode: {config.ROUTER_MODE}"],
            blockers=blockers,
            recent_outcomes=[(result.result or "(no result text)")[:300]],
            pending=pending,
        )
        self._workspace.append_context_log(
            "Run Result",
            (
                f"mode={mode}\n"
                f"reason={result.reason}\n"
                f"turns={result.turns}\n"
                f"files_modified={result.files_modified}\n"
                f"result={(result.result or '')[:800]}"
            ),
        )

    def _update_context_after_dispatch(
        self,
        prompt: str,
        specs: list[TaskSpec],
        results: list[SubAgentResult],
        aggregated: AgentResult,
    ) -> None:
        if config.CONTEXT_MODE != "session_rolling":
            return

        blockers: list[str] = []
        pending: list[str] = []
        recent: list[str] = []
        for spec, result in zip(specs, results):
            if result.success:
                recent.append(f"{spec.task_id}: {result.summary[:180]}")
            else:
                err = "; ".join(result.errors) if result.errors else "failed"
                blockers.append(f"{spec.task_id}: {err}")
                pending.append(f"Retry {spec.task_id}")

        self._workspace.update_context_summary(
            repo_facts=[f"Project root: {self._project_root}", f"Subtasks: {len(specs)}"],
            decisions=[
                f"Execution mode: decompose",
                f"Router mode: {config.ROUTER_MODE}",
                f"Planner model: {self._planner_model}",
            ],
            blockers=blockers,
            recent_outcomes=recent or ["No successful outcomes recorded"],
            pending=pending,
        )
        self._workspace.append_context_log(
            "Dispatch Result",
            (
                f"prompt={prompt[:500]}\n"
                f"tasks={[s.task_id for s in specs]}\n"
                f"reason={aggregated.reason}\n"
                f"summary={(aggregated.result or '')[:1200]}"
            ),
        )


def _sanitize_task_id(task_id: str) -> str:
    t = re.sub(r"[^a-zA-Z0-9_-]+", "-", task_id.strip().lower())
    t = re.sub(r"-+", "-", t).strip("-")
    return t or "task"
