# Sub-Agent Architecture

## Overview

Complex tasks are decomposed by the Orchestrator into `TaskSpec` objects, dispatched
to `SubAgentRunner` instances via the `Dispatcher`, each running in an isolated
`ExecutionEngine`. The `.qwen-coder/` workspace directory serves as persistent,
inspectable shared state between orchestrator and sub-agents.

---

## Workspace Directory (.qwen-coder/)

Filesystem-based orchestrator↔sub-agent communication layer:

```
.qwen-coder/
├── project.md                     # Project overview, goals, tech stack
├── plan.md                        # Decomposition plan + dependency graph
├── status.md                      # Overall progress tracking
├── .qwen-agent-api-routes/        # Sub-agent workspace
│   ├── task.md                    # Task spec from orchestrator
│   ├── directives.md              # Step-by-step instructions
│   ├── status.md                  # Agent's progress updates
│   ├── output.md                  # Final results
│   └── context.md                 # Inherited from predecessor agent
└── .qwen-agent-test-suite/
    ├── task.md
    ├── directives.md
    ├── status.md
    └── output.md
```

### Who writes what

| File | Written by | Read by |
|------|-----------|---------|
| `project.md` | Orchestrator | Sub-agents |
| `plan.md` | Orchestrator | Orchestrator (planning context) |
| `status.md` (root) | Orchestrator | User (inspection) |
| `task.md` | Orchestrator | Sub-agent |
| `directives.md` | Orchestrator | Sub-agent |
| `status.md` (agent) | Sub-agent | Orchestrator |
| `output.md` | Sub-agent | Orchestrator, successor agents |
| `context.md` | Orchestrator (inherit) | Successor sub-agent |

### Agent Continuity

New sub-agents can inherit context from predecessor agents via `Workspace.inherit_context()`.
This copies the predecessor's task, status, and output into the new agent's `context.md`.

---

## Component Map

```
Orchestrator (orchestrator.py)
    │
    ├─ Simple task? → _run_direct() → ExecutionEngine → AgentResult
    │
    └─ Complex task? (--dispatch / --async)
         │
         ├─ Workspace.ensure_exists() + read_info()
         │
         ├─ _decompose(prompt, workspace_info)
         │    └─ LLM call with orchestrator.md + workspace context
         │    └─ Parse JSON → (list[TaskSpec], project_spec, plan)
         │
         ├─ Write project.md, plan.md, status.md
         ├─ For each task: create .qwen-agent-<name>/ + write task.md, directives.md
         ├─ Handle predecessor context inheritance
         │
         ├─ Dispatcher.run_sequential/async(specs)
         │    └─ For each TaskSpec:
         │         SubAgentRunner.run(spec)
         │           ├─ Read workspace: project.md, directives.md, context.md
         │           ├─ Build restricted ToolRegistry (if allowed_tools set)
         │           ├─ Build prompt with full workspace context
         │           ├─ Create isolated Trace + ConsoleRenderer + ExecutionEngine
         │           ├─ engine.run(spec.goal) → AgentResult → SubAgentResult
         │           └─ Write agent status.md + output.md back to workspace
         │
         ├─ Write final status.md with results
         └─ _aggregate(results) → AgentResult
```

---

## TaskSpec (core/state.py)

The contract between orchestrator and sub-agent:

```python
@dataclass
class TaskSpec:
    goal: str                        # What to accomplish
    agent_name: str = ""             # Kebab-case name for workspace directory
    file_paths: list[str] = ...      # Relevant files
    constraints: list[str] = ...     # Rules to follow
    acceptance_criteria: list[str] = ... # How to verify done
    allowed_tools: list[str] = ...   # Tool whitelist (empty = all)
    depends_on: list[int] = ...      # Indices of prerequisite tasks
    predecessor: str = ""            # Previous agent to inherit context from
```

---

## SubAgentRunner (core/sub_agent.py)

Runs a single TaskSpec in isolation with workspace integration:

1. **Read workspace** — project.md for project context, directives.md for instructions,
   context.md for inherited predecessor state.
2. **Write status** — marks agent as "in-progress" at start.
3. **Build registry** — filtered ToolRegistry if `spec.allowed_tools` is set.
4. **Build prompt** — `sub_agent_prompt()` with task, project, directives, inherited context.
5. **Run engine** — isolated ExecutionEngine with `SUB_AGENT_MAX_TURNS`.
6. **Write results** — status.md and output.md back to workspace.
7. **Return** — `SubAgentResult` with agent_name for tracking.

---

## Dispatcher (core/dispatcher.py)

### Sequential Mode

`dispatcher.run_sequential(specs)` — runs tasks one by one, respecting `depends_on`.
Passes workspace to each SubAgentRunner for filesystem communication.

### Async Mode

`dispatcher.run_async(specs)` — uses `asyncio.run()` with:

1. **Semaphore** — `asyncio.Semaphore(config.MAX_CONCURRENT_AGENTS)` (default 3)
2. **Dependency levels** — `_build_levels()` groups by dependency depth
3. **Executor threads** — Ollama client is sync, so each agent runs in `run_in_executor`
4. **Workspace** — passed through to SubAgentRunner for file I/O

---

## Workspace Manager (core/workspace.py)

`Workspace` class manages the `.qwen-coder/` directory:

- `ensure_exists()` — creates directory if needed
- `read_info()` → `WorkspaceInfo` — snapshot of workspace state for orchestrator
- `write_project/plan/status()` — write root-level spec files
- `create_agent_dir()` — creates `.qwen-agent-<name>/`
- `write_agent_task/directives()` — orchestrator writes to agent
- `read_agent_status/output()` — orchestrator reads from agent
- `write_agent_status/output()` — sub-agent writes back
- `inherit_context(new, predecessor)` — copies predecessor output to new agent's context.md
- `list_agents()` / `agent_summary()` — enumerate and inspect agent state

---

## Configuration

```
AGENT_WORKSPACE_DIR   → .qwen-coder (directory name, configurable)
AGENT_SUB_MAX_TURNS   → 10 (per sub-agent)
AGENT_MAX_CONCURRENT  → 3 (async dispatch semaphore)
```
