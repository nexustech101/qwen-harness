# Memo: LLM Harness Usage in the Backend

Audience: engineer responsible for the LLM harness runtime.

## Current Backend Integration

The backend exposes the harness through the runtime API under `/api/sessions`.

The request flow is:

1. A client creates a session with `POST /api/sessions`.
2. The backend creates an API `Session` object and, for authenticated users, stores a `chat_sessions` row.
3. A client sends work with `POST /api/sessions/{session_id}/messages`.
4. The backend records the user message, emits conversation observability events, and starts an async task.
5. `RuntimeExecutor` launches the harness `Orchestrator` in a separate process so each run gets its own working directory state.
6. Trace events from the harness are forwarded back to the API process and streamed over WebSocket.
7. The assistant result, metadata, status, and usage events are persisted for authenticated sessions.

Key backend files:

- `harness/app/api/routes/runtime_sessions.py`: HTTP runtime endpoints.
- `harness/app/api/ws.py`: WebSocket event stream.
- `harness/app/api/session_manager.py`: in-memory session state and event projection.
- `harness/app/api/runtime_executor.py`: process-isolated bridge to the harness orchestrator.
- `harness/app/api/runtime_persistence.py`: persistence boundary for chat sessions/messages/events.
- `harness/app/services/chat_service.py`: database-facing conversation persistence service.

## Data Contract Needed by the Backend

The backend depends on these harness behaviors:

- `Orchestrator.run(prompt, images=None)` returns an `AgentResult`.
- `AgentResult` includes `result`, `turns`, `reason`, `tool_calls_made`, `files_modified`, `errors`, and `elapsed_seconds`.
- The harness emits `TraceEvent` objects with stable `event_type`, `timestamp`, and JSON-safe `data`.
- Agent lifecycle events use names such as `agent_start`, `agent_done`, `tool_dispatch`, and `tool_result`.
- Sub-agent events are prefixed with `sub_` and include `agent_name` in event data.

## Recommended Harness Improvements

1. Remove reliance on process-global `cwd`.

   Several tools still infer project scope from `Path.cwd()` or `os.getcwd()`. The backend currently isolates runs in separate processes to avoid cross-session contamination. A stronger harness contract would pass `project_root` or an execution context into every tool call.

2. Add a first-class `ExecutionContext`.

   Suggested fields:

   - `session_id`
   - `project_root`
   - `workspace_root`
   - `user_id`
   - `model`
   - `request_id`
   - `attachments`
   - cancellation token

   This would make the harness easier to embed in APIs, CLIs, workers, and tests without hidden globals.

3. Make trace event schemas explicit.

   Define typed event payloads for agent lifecycle, tool dispatch/result, model calls, retries, errors, and cancellation. Stable schemas make WebSocket streaming, telemetry, and offline evaluation much easier.

4. Return structured model-call telemetry.

   The backend can store `llm_usage_events`, but the harness should emit model/provider metrics when available:

   - model name
   - provider
   - prompt token count
   - completion token count
   - latency
   - stop reason
   - retry count

5. Support cancellation cooperatively.

   The backend can terminate the runtime process, but the harness should eventually accept a cancellation token and stop cleanly between tool calls/model calls. That would preserve better final state and reduce abrupt process cleanup.

6. Separate orchestration from presentation.

   Keep console rendering and file logging attachable, but avoid making them implicit runtime side effects. The backend only needs structured events and final results.

7. Make attachment handling explicit.

   The API currently converts text attachments into prompt text and passes image paths separately. A richer harness input model should accept attachments as structured objects with `id`, `filename`, `mime_type`, `path`, and optional extracted text.

## Why This Matters

The backend is now responsible for terminal and frontend clients, but it should not know the internal mechanics of tool execution. A context-driven, typed-event harness would let users run multiple sessions concurrently, let data scientists retrieve clean training/evaluation records, and let future clients add features without threading new behavior through a monolithic runtime path.
