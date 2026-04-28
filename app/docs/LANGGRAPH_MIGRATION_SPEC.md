# qwen-coder — LangGraph Migration & Test Suite Specification

**Version:** 1.0  
**Status:** Draft  
**Audience:** Backend engineer(s) familiar with Python async and the existing codebase

---

## Overview

This document specifies two parallel workstreams:

1. **Incremental LangGraph migration** — replacing the hand-rolled agent loop, dispatcher, and session persistence with LangGraph primitives, without breaking the existing CLI or API interfaces at any step.
2. **Test suite** — establishing a test harness from scratch, prioritising the highest-risk components first.

Both workstreams are designed to be executed in order. Each phase leaves the project in a fully working, deployable state.

---

## Part 1 — LangGraph Migration

### Guiding principles

- The existing CLI and FastAPI interfaces must remain functional at the end of every phase.
- No phase requires more than one logical concern to change at once.
- New LangGraph code lives alongside old code until a phase explicitly removes the old code. Use feature flags (`USE_LANGGRAPH=true` env var) during transition.
- The `Trace` / observability system is kept intact throughout. LangGraph callbacks feed into it rather than replacing it.
- All 26 existing tool functions are kept unchanged. Only how they are invoked changes.

---

### Phase 0 — Pre-migration housekeeping

**Goal:** Fix the known code issues before introducing any new dependency. These are blocking for clean migration and should be done in a single PR.

**Tasks:**

1. **Add `directives` field to `TaskSpec`** in `app/core/state.py`:
   ```python
   @dataclass
   class TaskSpec:
       goal: str
       agent_name: str = ""
       file_paths: list[str] = field(default_factory=list)
       constraints: list[str] = field(default_factory=list)
       acceptance_criteria: list[str] = field(default_factory=list)
       allowed_tools: list[str] = field(default_factory=list)
       depends_on: list[int] = field(default_factory=list)
       predecessor: str = ""
       directives: str = ""          # <-- add this
   ```
   Remove the `spec._directives = ...` dynamic attribute hack in `app/core/orchestrator.py`. Update all references.

2. **Add `Pillow` to `requirements.txt`.**

3. **Rename `use_dispatch` to `enable_decomposition`** everywhere — `Orchestrator.__init__`, `Session.__init__`, `CreateSessionRequest`, API routes, CLI args in `main.py`. This is a naming-only change; behaviour is unchanged.

4. **Extract an `OllamaClientFactory`** in a new file `app/llm/client.py`:
   ```python
   import ollama
   from app import config

   def get_client() -> ollama.Client:
       return ollama.Client(host=config.OLLAMA_HOST)
   ```
   Replace all inline `ollama.Client(host=config.OLLAMA_HOST)` instantiations with calls to `get_client()`. This is the injection point LangGraph's Ollama integration will later replace.

5. **Add `USE_LANGGRAPH` to `app/config.py`:**
   ```python
   USE_LANGGRAPH: bool = os.getenv("USE_LANGGRAPH", "false").lower() == "true"
   ```

**Deliverable:** All existing tests (once written in Part 2) pass. The project runs identically to before.

---

### Phase 1 — Install LangGraph and wire up Ollama

**Goal:** Get LangGraph installed and confirm it can call the existing Ollama backend. No agent logic changes yet.

**New dependencies** (add to `requirements.txt`):
```
langgraph>=0.3.0
langchain-ollama>=0.3.0
langchain-core>=0.3.0
```

**Tasks:**

1. Create `app/llm/langchain_client.py`:
   ```python
   from langchain_ollama import ChatOllama
   from app import config

   def get_langchain_llm(model: str | None = None) -> ChatOllama:
       return ChatOllama(
           model=model or config.MODEL,
           base_url=config.OLLAMA_HOST,
       )
   ```

2. Write a manual smoke test (not part of the automated suite) that calls `get_langchain_llm()` with a trivial prompt and prints the response. This confirms the LangChain/Ollama handshake works in the developer's environment before any logic is migrated.

3. No changes to any agent logic or API surface.

**Deliverable:** `USE_LANGGRAPH=true python -c "from app.llm.langchain_client import get_langchain_llm; print(get_langchain_llm().invoke('ping'))"` runs without error.

---

### Phase 2 — Replace `ExecutionEngine` with a LangGraph `StateGraph`

**Goal:** Replace the `while` loop in `app/core/execution.py` with a LangGraph `StateGraph`. The `Orchestrator` continues to work unchanged; it just receives a different concrete implementation when `USE_LANGGRAPH=true`.

#### 2.1 — Define the agent state schema

Create `app/core/agent_state.py`:

```python
from typing import Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict

class AgentGraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    files_modified: list[str]
    turn_count: int
    max_turns: int
    finish_reason: str   # "done" | "max_turns" | "deadlock" | "error"
    final_response: str
```

The `add_messages` reducer handles message appending automatically — this replaces the manual `messages.append(...)` calls in `ExecutionEngine`.

#### 2.2 — Wrap tools with `ToolNode`

Create `app/core/tool_node.py`:

```python
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool as lc_tool
from app.tools.registry import registry

def build_tool_node() -> ToolNode:
    """Wrap all registered tools in LangChain tool objects for ToolNode."""
    lc_tools = []
    for entry in registry.list_tools():
        # Wrap the existing ToolResult-returning function
        @lc_tool(entry.name, description=entry.description)
        def _wrapped(**kwargs):
            result = entry.fn(**kwargs)
            return result.data if result.success else f"ERROR: {result.error}"
        _wrapped.__name__ = entry.name
        lc_tools.append(_wrapped)
    return ToolNode(lc_tools)
```

Note: The `ToolRegistry` and all individual tool files are **not modified**. This wrapper is the only new code.

#### 2.3 — Build the agent graph

Create `app/core/lg_execution.py`:

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from app.core.agent_state import AgentGraphState
from app.core.tool_node import build_tool_node
from app.llm.langchain_client import get_langchain_llm
from app.observability.trace import Trace
from app import config


def build_agent_graph(
    system_prompt: str,
    model: str,
    max_turns: int,
    trace: Trace,
    checkpointer=None,
):
    llm = get_langchain_llm(model)
    tool_node = build_tool_node()
    bound_llm = llm.bind_tools(list(tool_node.tools_by_name.values()))

    def call_model(state: AgentGraphState) -> dict:
        trace.emit("model_call", message_count=len(state["messages"]))
        response = bound_llm.invoke(state["messages"])
        trace.emit("model_reply", content=response.content[:120] if response.content else "")
        return {
            "messages": [response],
            "turn_count": state["turn_count"] + 1,
        }

    def should_continue(state: AgentGraphState) -> str:
        last = state["messages"][-1]
        if state["turn_count"] >= state["max_turns"]:
            return "end"
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return "end"

    def emit_tool_results(state: AgentGraphState) -> dict:
        # Trace tool dispatch events after ToolNode runs
        for msg in state["messages"]:
            if hasattr(msg, "name"):  # ToolMessage
                trace.emit("tool_result", tool=msg.name, content=str(msg.content)[:200])
        return {}

    graph = StateGraph(AgentGraphState)
    graph.add_node("call_model", call_model)
    graph.add_node("tools", tool_node)
    graph.add_node("trace_tools", emit_tool_results)

    graph.set_entry_point("call_model")
    graph.add_conditional_edges("call_model", should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "trace_tools")
    graph.add_edge("trace_tools", "call_model")

    return graph.compile(checkpointer=checkpointer or MemorySaver())
```

#### 2.4 — Create `LGExecutionEngine` adapter

Add a class `LGExecutionEngine` to `app/core/lg_execution.py` that satisfies the same interface as `ExecutionEngine` (i.e., has a `run(user_message, images=None) -> AgentResult` method). `Orchestrator._run_direct` instantiates this when `config.USE_LANGGRAPH` is `True`.

```python
class LGExecutionEngine:
    def __init__(self, registry, trace, system_prompt, model=None, max_turns=None):
        self._trace = trace
        self._system_prompt = system_prompt
        self._model = model or config.MODEL
        self._max_turns = max_turns or config.MAX_TURNS
        self._graph = build_agent_graph(system_prompt, self._model, self._max_turns, trace)
        self.messages = []   # exposed for API inspection

    def run(self, user_message: str, images=None) -> AgentResult:
        import time
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.core.state import AgentResult

        start = time.monotonic()
        init_state = {
            "messages": [SystemMessage(self._system_prompt), HumanMessage(user_message)],
            "files_modified": [],
            "turn_count": 0,
            "max_turns": self._max_turns,
            "finish_reason": "",
            "final_response": "",
        }
        thread = {"configurable": {"thread_id": "main"}}
        final_state = self._graph.invoke(init_state, thread)
        self.messages = final_state["messages"]

        last = final_state["messages"][-1]
        response_text = last.content if hasattr(last, "content") else ""
        elapsed = round(time.monotonic() - start, 2)

        return AgentResult(
            result=response_text,
            turns=final_state["turn_count"],
            reason=final_state.get("finish_reason") or "done",
            tool_calls_made=0,
            files_modified=final_state.get("files_modified", []),
            errors=[],
            elapsed_seconds=elapsed,
        )
```

#### 2.5 — Route in `Orchestrator._run_direct`

```python
def _run_direct(self, prompt, images=None):
    ...
    if config.USE_LANGGRAPH:
        engine = LGExecutionEngine(
            registry=self._registry,
            trace=trace,
            system_prompt=sys_prompt,
            model=self._coder_model,
            max_turns=self._max_turns,
        )
    else:
        engine = ExecutionEngine(...)   # unchanged
    ...
```

**Deliverable:** `USE_LANGGRAPH=false` runs the original engine. `USE_LANGGRAPH=true` runs the LangGraph engine. Both respond correctly to a simple `write_file` prompt. The API and CLI are unaffected.

---

### Phase 3 — Replace in-memory `SessionManager` with LangGraph checkpointing

**Goal:** Persist session state to SQLite so sessions survive server restarts. This replaces the `MemorySaver` in Phase 2 with `SqliteSaver`.

**Tasks:**

1. Add to `requirements.txt`:
   ```
   langgraph-checkpoint-sqlite>=0.3.0
   ```

2. Add to `app/config.py`:
   ```python
   CHECKPOINT_DB: str = os.getenv("LANGGRAPH_CHECKPOINT_DB", ".qwen-coder/checkpoints.sqlite")
   ```

3. Create `app/core/checkpointer.py`:
   ```python
   from langgraph.checkpoint.sqlite import SqliteSaver
   from app import config
   import sqlite3

   _checkpointer: SqliteSaver | None = None

   def get_checkpointer() -> SqliteSaver:
       global _checkpointer
       if _checkpointer is None:
           conn = sqlite3.connect(config.CHECKPOINT_DB, check_same_thread=False)
           _checkpointer = SqliteSaver(conn)
       return _checkpointer
   ```

4. In `LGExecutionEngine`, pass `get_checkpointer()` instead of `MemorySaver()` when `config.USE_LANGGRAPH` is `True`.

5. Update `SessionManager.create()` to store a `thread_id` (the session UUID) on the `Session` object. Pass this as the `configurable.thread_id` on every graph invocation, so each session has an isolated checkpoint stream.

6. Update `SessionManager.delete()` to purge the checkpoint entries for that `thread_id` from the SQLite database.

**What is NOT changed:** The `Session` object's in-memory fields (`history`, `agents`, `uploads`, `_ws_queues`) remain as-is. Checkpointing persists graph state (messages, turn count); session metadata (project root, model choices) is still reconstructed from the `CreateSessionRequest` stored elsewhere or re-provided on reconnect.

**Deliverable:** Stop and restart the API server mid-session. The conversation history is restored from the checkpoint. The CLI is unaffected (it does not use sessions).

---

### Phase 4 — Migrate `Dispatcher` to LangGraph `Send` API

**Goal:** Replace `app/core/dispatcher.py`'s manual topological sort and asyncio semaphore with a LangGraph supervisor subgraph that uses the `Send` API to fan work to sub-agent subgraphs.

This is the most complex phase and should only begin after Phase 2 and 3 are stable in production.

#### 4.1 — Define supervisor state

```python
class SupervisorState(TypedDict):
    tasks: list[TaskSpec]
    results: Annotated[list[SubAgentResult], operator.add]
    project_root: str
```

#### 4.2 — Fan-out with `Send`

```python
from langgraph.types import Send

def dispatch_node(state: SupervisorState):
    return [
        Send("sub_agent", {"spec": spec, "project_root": state["project_root"]})
        for spec in state["tasks"]
    ]
```

`Send` replaces the semaphore-gated asyncio pool. LangGraph manages concurrency through its own scheduler.

#### 4.3 — Sub-agent subgraph

Each sub-agent is itself a compiled `StateGraph` (reusing `build_agent_graph` from Phase 2) wrapped in a node:

```python
def run_sub_agent(state: dict) -> dict:
    spec: TaskSpec = state["spec"]
    engine = LGExecutionEngine(
        registry=registry,
        trace=Trace(),
        system_prompt=sub_agent_prompt(spec),
        model=config.CODER_MODEL,
        max_turns=config.SUB_AGENT_MAX_TURNS,
    )
    result = engine.run(spec.goal)
    return {"results": [SubAgentResult(
        agent_name=spec.agent_name,
        success=result.reason == "done",
        summary=result.result,
        output=result.result,
        turns_used=result.turns,
        files_modified=result.files_modified,
        files_created=[],
        errors=result.errors,
    )]}
```

#### 4.4 — Dependency ordering

Dependency constraints (`spec.depends_on`) are enforced by building dependency edges in the supervisor graph rather than via topological sort. Tasks with no dependencies are sent immediately. Tasks with dependencies are held until their upstream `Send` nodes complete.

If dependency modelling in the graph becomes complex, an acceptable fallback is to keep the topological sort from `dispatcher.py` but replace the asyncio semaphore pool with sequential `Send` dispatches in dependency order.

#### 4.5 — Feature flag

Route in `Orchestrator._run_with_dispatch`:

```python
if config.USE_LANGGRAPH:
    return self._run_with_lg_dispatch(prompt)
else:
    return self._run_with_dispatch(prompt)   # original
```

**Deliverable:** `USE_LANGGRAPH=true` with a decomposable prompt produces the same multi-agent execution as the original dispatcher, validated by the integration tests added in Part 2, Phase 4.

---

### Phase 5 — Remove legacy code

Only execute this phase after all automated tests pass with `USE_LANGGRAPH=true` and the feature has been running in the developer's own environment for at least two weeks.

**Remove:**

- `app/core/execution.py` (replaced by `app/core/lg_execution.py`)
- `app/core/dispatcher.py` (replaced by supervisor graph in `app/core/lg_dispatch.py`)
- `app/core/sub_agent.py` (logic absorbed into `run_sub_agent` node)
- `app/parsing/response_parser.py` (LangGraph/LangChain handles structured output natively via `.bind_tools`)
- `app/parsing/schema_validator.py` (same reason)
- `USE_LANGGRAPH` flag and all branch logic
- `app/llm/client.py` `get_client()` factory (replaced by `get_langchain_llm()`)

**Keep:**

- All of `app/tools/` (unchanged throughout)
- All of `app/account_api/api/` (unchanged throughout)
- All of `app/observability/` (unchanged throughout)
- All of `app/prompts/` (unchanged throughout)
- `app/core/state.py` (dataclasses remain useful)
- `app/core/workspace.py` (filesystem protocol kept for sub-agent communication)

**Deliverable:** The `USE_LANGGRAPH` env var is removed from `config.py`. The project runs with LangGraph exclusively.

---

## Part 2 — Test Suite

### Stack

```
pytest>=8.0
pytest-asyncio>=0.23
pytest-mock>=3.12
httpx>=0.27         # async test client for FastAPI
respx>=0.21         # mock HTTP in tool tests
```

Add to `requirements.txt` under a `[test]` optional group or a `requirements-dev.txt`.

### Directory layout

```
tests/
├── conftest.py                  # shared fixtures
├── unit/
│   ├── parsing/
│   │   ├── test_response_parser.py
│   │   └── test_schema_validator.py
│   ├── tools/
│   │   ├── test_file_tools.py
│   │   ├── test_path_utils.py
│   │   ├── test_web_tools.py
│   │   └── test_system_tools.py
│   ├── core/
│   │   ├── test_orchestrator_routing.py
│   │   ├── test_decomposition_parsing.py
│   │   └── test_state.py
│   └── api/
│       ├── test_models.py
│       └── test_session_manager.py
├── integration/
│   ├── test_execution_engine.py
│   ├── test_dispatcher.py
│   └── test_api_routes.py
└── fixtures/
    ├── llm_responses/           # raw LLM response strings for parser tests
    │   ├── native_tool_call.json
    │   ├── structured_json.txt
    │   ├── malformed_json.txt
    │   ├── plain_text.txt
    │   ├── think_tag_wrapped.txt
    │   └── decomposition_valid.json
    └── files/                   # scratch files for file tool tests
```

---

### Phase T0 — `conftest.py` and shared fixtures

```python
# tests/conftest.py
import pytest
from pathlib import Path
from app.tools.registry import ToolRegistry
from app.core.state import ToolResult


@pytest.fixture
def tmp_workspace(tmp_path):
    """Isolated temp directory for every test that touches the filesystem."""
    return tmp_path


@pytest.fixture
def fresh_registry():
    """A ToolRegistry instance with no tools registered — import clean."""
    return ToolRegistry()


@pytest.fixture
def populated_registry(fresh_registry):
    """Registry with all production tools registered."""
    import app.tools.file_tools
    import app.tools.system_tools
    import app.tools.analysis_tools
    import app.tools.workspace_tools
    import app.tools.code_tools
    import app.tools.agent_tools
    import app.tools.web_tools
    # Note: tools register against the module-level singleton, not fresh_registry.
    # This fixture documents the known coupling; fix once global registry is removed.
    from app.tools.registry import registry
    return registry


@pytest.fixture
def success_result():
    return ToolResult(success=True, data="ok", metadata={}, error=None)


@pytest.fixture
def failure_result():
    return ToolResult(success=False, data=None, metadata={}, error="something failed")
```

---

### Phase T1 — Response parser (highest priority)

The `ResponseParser` is the most branchy, most failure-prone component and currently has zero test coverage. Write these first.

**File:** `tests/unit/parsing/test_response_parser.py`

Cover each of the following cases with at least one test. Fixture strings live in `tests/fixtures/llm_responses/`.

| Test name | Input | Expected outcome |
|---|---|---|
| `test_native_tool_call` | Ollama native `tool_calls` in the response object | `parsed.mode == "native"`, correct tool name and args |
| `test_structured_json_single_tool` | `{"reasoning":"...","tools":[{...}],"response":"..."}` | `parsed.mode == "structured"`, one tool call extracted |
| `test_structured_json_multiple_tools` | `tools` array with two entries | two `ToolCall` objects in `parsed.tool_calls` |
| `test_structured_json_empty_tools` | `tools: []` | `parsed.mode == "structured"`, `parsed.tool_calls == []` |
| `test_legacy_json_single_tool` | `{"name":"write_file","arguments":{...}}` | `parsed.mode == "legacy"`, one tool call |
| `test_plain_text_no_tools` | Narrative prose, no JSON | `parsed.mode == "plain"`, `parsed.tool_calls == []` |
| `test_think_tag_extraction` | `<think>reasoning here</think>\n{...}` | `parsed.reasoning == "reasoning here"`, JSON still parsed |
| `test_think_tag_no_closing` | `<think>unclosed...` | Graceful: reasoning extracted or ignored, no exception |
| `test_malformed_json_trailing_comma` | `{"tools": [{...},]}` | Parser recovers via `_repair_json`, returns tool call |
| `test_malformed_json_unrecoverable` | `{"tools": [{name: broken` | `parsed.mode == "plain"`, no exception |
| `test_json_inside_code_block` | Response wrapped in ` ```json ``` ` | JSON extracted and parsed correctly |
| `test_unknown_tool_name` | Tool name not in `known_tools` | Gracefully handled; tool included or excluded per current logic |
| `test_empty_string` | `""` | `parsed.mode == "plain"`, no exception |
| `test_whitespace_only` | `"   \n  "` | Same as empty string |

**Test pattern:**

```python
from app.parsing.response_parser import ResponseParser, ParsedResponse

KNOWN_TOOLS = {"write_file", "read_file", "run_command"}

@pytest.fixture
def parser():
    return ResponseParser(known_tools=KNOWN_TOOLS)

def test_structured_json_single_tool(parser, fixtures_dir):
    raw = (fixtures_dir / "llm_responses" / "structured_json.txt").read_text()
    result = parser.parse(raw, native_calls=None)
    assert result.mode == "structured"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "write_file"
    assert "path" in result.tool_calls[0].arguments
```

---

### Phase T2 — `Orchestrator._parse_decomposition` (second priority)

The decomposition parser has its own branching logic and JSON repair. It is a `@staticmethod`, making it easy to test in isolation.

**File:** `tests/unit/core/test_decomposition_parsing.py`

| Test name | Input | Expected |
|---|---|---|
| `test_direct_mode` | `{"mode": "direct", "reasoning": "simple task"}` | Returns `("direct", [], "", "", "")` |
| `test_decompose_mode_valid` | Full valid JSON with `tasks` array | `mode == "decompose"`, `len(specs) == n`, all fields populated |
| `test_decompose_missing_tasks_key` | JSON with no `tasks` key | Returns error string, empty spec list |
| `test_decompose_empty_tasks_array` | `{"mode":"decompose","tasks":[]}` | Error: tasks array is empty |
| `test_task_missing_goal` | Task entry without `"goal"` key | That task is skipped; others are included |
| `test_dependency_out_of_bounds` | `depends_on: [99]` on a 2-task plan | Dep is stripped with a warning; no exception |
| `test_dependency_self_reference` | `depends_on: [0]` on task index 0 | Dep is stripped |
| `test_json_in_code_block` | Response with ` ```json ``` ` wrapper | JSON extracted and parsed |
| `test_json_repair_trailing_comma` | Malformed JSON with trailing comma | `_repair_json` produces valid parse |
| `test_no_json_in_response` | Pure prose | Returns error string, empty specs |
| `test_directives_field` | Task with `"directives": "..."` | `spec.directives` is populated (after Phase 0 fix) |

---

### Phase T3 — Path utilities and file tools

These touch the real filesystem but can be run safely with `tmp_path`.

**File:** `tests/unit/tools/test_path_utils.py`

| Test | What it checks |
|---|---|
| `test_safe_resolve_within_workspace` | `safe_resolve("subdir/file.txt", base)` resolves inside `base` |
| `test_safe_resolve_traversal_attack` | `safe_resolve("../../etc/passwd", base)` raises or returns `None` |
| `test_safe_resolve_absolute_path_inside` | Absolute path inside `base` is accepted |
| `test_safe_resolve_absolute_path_outside` | Absolute path outside `base` is rejected |
| `test_safe_resolve_symlink_escape` | Symlink pointing outside `base` is rejected |

**File:** `tests/unit/tools/test_file_tools.py`

Each test uses `tmp_workspace` fixture and patches the working directory via `monkeypatch.chdir(tmp_workspace)`.

| Test | What it checks |
|---|---|
| `test_write_file_creates_file` | `write_file` creates file with correct content |
| `test_write_file_creates_parent_dirs` | Nested path: parent directories created automatically |
| `test_read_file_returns_content` | `read_file` returns written content |
| `test_read_file_missing_returns_error` | Missing file returns `ToolResult(success=False)` |
| `test_read_file_truncates_at_max_bytes` | File > `MAX_READ_BYTES` is truncated |
| `test_edit_file_replaces_content` | `edit_file` patches specific line |
| `test_file_exists_true` | Returns `True` when file exists |
| `test_file_exists_false` | Returns `False` when file is absent |
| `test_list_directory_returns_entries` | Returns child entries for a directory |
| `test_list_directory_missing_returns_error` | Non-existent directory: error result |
| `test_write_outside_workspace_rejected` | Path traversal: `ToolResult(success=False)` |

---

### Phase T4 — Web tools (SSRF and URL validation)

**File:** `tests/unit/tools/test_web_tools.py`

Use `respx` to mock HTTP responses; never make real network calls in unit tests.

| Test | What it checks |
|---|---|
| `test_http_get_valid_url` | Mocked 200 response returns content |
| `test_http_get_localhost_blocked` | `http://localhost/...` is rejected (SSRF) |
| `test_http_get_127_blocked` | `http://127.0.0.1/...` is rejected |
| `test_http_get_169_blocked` | `http://169.254.169.254/...` is rejected (AWS metadata) |
| `test_http_get_private_range_blocked` | `http://192.168.1.1/...` is rejected |
| `test_http_get_non_http_scheme` | `file:///etc/passwd` is rejected |
| `test_http_get_timeout` | Mock timeout: returns `ToolResult(success=False)` |
| `test_http_get_4xx_response` | 404 response: returns error result |
| `test_http_get_content_truncated` | Response body > max bytes is truncated |

---

### Phase T5 — Session manager and API models

**File:** `tests/unit/api/test_session_manager.py`

Mock `Orchestrator` entirely — these tests verify `SessionManager`'s own logic.

| Test | What it checks |
|---|---|
| `test_create_session_returns_session` | `manager.create(...)` returns a `Session` with a UUID |
| `test_get_session_by_id` | Created session is retrievable by ID |
| `test_get_nonexistent_session_returns_none` | Unknown ID returns `None` |
| `test_list_all_sessions` | Multiple created sessions all appear in list |
| `test_delete_session_removes_it` | Deleted session is no longer in list |
| `test_delete_nonexistent_session_no_error` | Deleting an unknown ID does not raise |
| `test_session_execution_lock` | Second `run_prompt` call while first is running returns 409 or queues |
| `test_upload_mime_validation_blocked_extension` | `.exe` upload is rejected |
| `test_upload_size_limit_enforced` | File > 10 MB is rejected |
| `test_upload_stored_and_retrievable` | Valid upload stored; accessible via its ID |

**File:** `tests/unit/api/test_models.py`

Pydantic validation edge cases:

| Test | What it checks |
|---|---|
| `test_create_session_request_defaults` | `use_dispatch=False`, `async_dispatch=False` defaults |
| `test_send_prompt_request_defaults` | `direct=False`, `attachments=[]` defaults |
| `test_session_response_serialises` | `SessionResponse` round-trips through JSON |

---

### Phase T6 — FastAPI integration tests

**File:** `tests/integration/test_api_routes.py`

Use `httpx.AsyncClient` with the ASGI app directly — no real network, no Ollama connection.
Mock `Orchestrator.run` at the boundary.

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.account_api.api import create_app

@pytest.fixture
async def client():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

| Test | What it checks |
|---|---|
| `test_health_endpoint` | `GET /api/health` returns 200 with `status: "ok"` |
| `test_create_session` | `POST /api/sessions` returns session with UUID and `project_root` |
| `test_get_session` | Retrieving a created session returns matching ID |
| `test_delete_session` | Deleted session returns 404 on subsequent get |
| `test_send_prompt_accepted` | `POST /api/sessions/{id}/messages` returns 202 |
| `test_send_prompt_session_not_found` | Unknown session ID returns 404 |
| `test_send_prompt_while_running_returns_409` | Concurrent prompt returns 409 |
| `test_list_sessions_empty` | Fresh manager returns empty list |
| `test_upload_file_accepted` | Multipart upload stores file and returns `UploadMeta` |
| `test_upload_blocked_extension` | `.exe` file returns 422 |
| `test_file_tree_endpoint` | `GET /api/sessions/{id}/files` returns tree for project_root |
| `test_config_endpoint` | `GET /api/config` returns all config keys |

---

### Phase T7 — LangGraph engine tests (added during migration)

Add these as each Phase in Part 1 lands.

**File:** `tests/integration/test_execution_engine.py`

Mock the `ChatOllama` client using `unittest.mock.patch`. Provide a synthetic AIMessage with a tool call, then a second AIMessage with no tool calls (completion).

| Test | What it checks |
|---|---|
| `test_lg_engine_runs_to_completion` | Single-step task with mocked LLM terminates with `reason=="done"` |
| `test_lg_engine_calls_tool` | LLM response with a tool call results in the tool function being invoked |
| `test_lg_engine_respects_max_turns` | Mock LLM that always returns tool calls eventually stops at `max_turns` |
| `test_lg_engine_result_matches_legacy_schema` | `LGExecutionEngine.run()` returns an `AgentResult` with all required fields |
| `test_feature_flag_routes_correctly` | `USE_LANGGRAPH=false` → `ExecutionEngine`; `=true` → `LGExecutionEngine` |

**File:** `tests/integration/test_dispatcher.py`

| Test | What it checks |
|---|---|
| `test_sequential_dispatch_two_tasks` | Two independent tasks are both executed, results aggregated |
| `test_dispatch_with_dependency` | Task B with `depends_on=[0]` executes after Task A |
| `test_failed_sub_agent_in_results` | Sub-agent failure is captured in `AgentResult.errors`, does not crash |
| `test_cycle_detection` | Circular dependency raises or falls back gracefully |

---

### Running the test suite

```bash
# All unit tests (fast, no Ollama needed)
pytest tests/unit -v

# All tests including integration (requires running API but not Ollama — Ollama is mocked)
pytest tests/ -v

# Run with LangGraph engine
USE_LANGGRAPH=true pytest tests/integration/test_execution_engine.py -v

# Coverage report
pytest tests/unit --cov=app --cov-report=term-missing
```

**Target coverage after all phases:**

| Module | Target |
|---|---|
| `app/parsing/` | 95% |
| `app/tools/` | 85% |
| `app/core/orchestrator.py` | 80% |
| `app/account_api/schemas/agent.py` | 90% |
| `app/account_api/api/routes/runtime_sessions.py` | 75% |
| `app/core/lg_execution.py` | 80% |

---

## Appendix — Dependency summary

### New production dependencies (phased)

| Phase | Package | Version | Purpose |
|---|---|---|---|
| Phase 1 | `langgraph` | `>=0.3.0` | Graph-based agent runtime |
| Phase 1 | `langchain-ollama` | `>=0.3.0` | LangChain Ollama integration |
| Phase 1 | `langchain-core` | `>=0.3.0` | Base message types, tool binding |
| Phase 3 | `langgraph-checkpoint-sqlite` | `>=0.3.0` | Persistent session checkpointing |

### New dev/test dependencies

| Package | Version | Purpose |
|---|---|---|
| `pytest` | `>=8.0` | Test runner |
| `pytest-asyncio` | `>=0.23` | Async test support |
| `pytest-mock` | `>=3.12` | `mocker` fixture |
| `httpx` | `>=0.27` | Async FastAPI test client |
| `respx` | `>=0.21` | HTTP mock for web tool tests |
| `pytest-cov` | `>=5.0` | Coverage reporting |

---

## Appendix — What is deliberately out of scope

The following are intentional non-goals for this spec:

- **Frontend changes** — The React frontend consumes the same WebSocket event schema throughout. No frontend work is required.
- **Multi-model support beyond Ollama** — LangChain supports many providers but this spec does not introduce any additional providers.
- **Langflow** — As discussed in the review, Langflow's visual builder adds indirection unsuitable for a custom CLI/API agent. It is not part of this migration.
- **Streaming token-by-token responses over WebSocket via LangGraph** — The existing `_stream_chat` approach is preserved in Phases 1–3. LangGraph's `.astream_events` API can replace it in a future spec once the core migration is stable.
- **Authentication/authorisation on the API** — CORS and auth hardening are separate concerns.
