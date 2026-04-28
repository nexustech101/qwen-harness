from __future__ import annotations

import asyncio
import multiprocessing as mp
import os
import queue
import traceback
from dataclasses import asdict, dataclass
from typing import Any, Callable

from app.core.state import AgentResult
from app.logging.trace import TraceEvent


@dataclass(slots=True)
class RuntimeExecutionResult:
    result: AgentResult
    agent_messages: dict[str, list[dict[str, str]]]


def _safe_serialize(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_serialize(v) for k, v in value.items()}
    return str(value)


def _run_orchestrator_process(
    event_queue: mp.Queue,
    *,
    project_root: str,
    prompt: str,
    direct: bool,
    images: list[str] | None,
    config_values: dict[str, Any],
) -> None:
    from app.core.orchestrator import Orchestrator
    from app.logging.trace import Trace

    original_dir = os.getcwd()
    try:
        os.chdir(project_root)
        trace = Trace()

        def publish_event(event) -> None:
            event_queue.put(
                {
                    "type": "event",
                    "event_type": event.event_type,
                    "timestamp": event.timestamp,
                    "data": _safe_serialize(event.data),
                }
            )

        trace.subscribe_all(publish_event)
        use_dispatch = config_values["use_dispatch"] and not direct
        orchestrator = Orchestrator(
            model=config_values["model"],
            planner_model=config_values["planner_model"],
            coder_model=config_values["coder_model"],
            max_turns=config_values["max_turns"],
            project_root=project_root,
            use_dispatch=use_dispatch,
            async_dispatch=config_values["async_dispatch"],
            trace=trace,
        )
        result = orchestrator.run(prompt, images=images)
        agent_messages = {
            name: [
                {"role": message["role"], "content": message.get("content", "")}
                for message in engine._messages
            ]
            for name, engine in orchestrator._engines.items()
        }
        event_queue.put(
            {
                "type": "result",
                "result": asdict(result),
                "agent_messages": agent_messages,
            }
        )
    except Exception as exc:
        event_queue.put(
            {
                "type": "error",
                "error": str(exc),
                "exception_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        os.chdir(original_dir)


class RuntimeExecutor:
    def __init__(
        self,
        *,
        project_root: str,
        config_values: dict[str, Any],
        event_callback: Callable[[TraceEvent], None],
    ) -> None:
        self._project_root = project_root
        self._config_values = config_values
        self._event_callback = event_callback
        self._process: mp.Process | None = None

    async def run(
        self,
        *,
        prompt: str,
        direct: bool,
        images: list[str] | None,
    ) -> RuntimeExecutionResult:
        context = mp.get_context("spawn")
        event_queue = context.Queue()
        self._process = context.Process(
            target=_run_orchestrator_process,
            kwargs={
                "event_queue": event_queue,
                "project_root": self._project_root,
                "prompt": prompt,
                "direct": direct,
                "images": images,
                "config_values": self._config_values,
            },
            daemon=True,
        )
        self._process.start()

        try:
            while True:
                try:
                    payload = await asyncio.to_thread(event_queue.get, True, 0.1)
                except queue.Empty:
                    if self._process.exitcode is not None:
                        raise RuntimeError(f"Agent runtime exited with code {self._process.exitcode}")
                    continue

                message_type = payload.get("type")
                if message_type == "event":
                    self._event_callback(
                        TraceEvent(
                            event_type=payload["event_type"],
                            timestamp=payload["timestamp"],
                            data=payload.get("data", {}),
                        )
                    )
                    continue

                if message_type == "result":
                    return RuntimeExecutionResult(
                        result=AgentResult(**payload["result"]),
                        agent_messages=payload.get("agent_messages", {}),
                    )

                if message_type == "error":
                    detail = payload.get("error") or "Agent runtime failed"
                    raise RuntimeError(detail)
        except asyncio.CancelledError:
            self.cancel()
            raise
        finally:
            await asyncio.to_thread(self._join_process)
            event_queue.close()

    def cancel(self) -> None:
        process = self._process
        if process and process.is_alive():
            process.terminate()

    def _join_process(self) -> None:
        process = self._process
        if process:
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
