from rich.console import Console

from agent.core.console_renderer import ConsoleRenderer, _short_args
from agent.logging.trace import Trace


class _DummyLive:
    def __init__(self, *_args, **_kwargs):
        self.started = False
        self.stopped = False
        self.last = None

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def update(self, renderable):
        self.last = renderable


def test_short_args_formats_compactly():
    s = _short_args({"path": "a/b/c.py", "content": "x" * 100})
    assert s.startswith("{")
    assert "path=" in s
    assert "..." in s


def test_console_renderer_event_flow(monkeypatch):
    trace = Trace()
    console = Console(record=True, width=120)

    monkeypatch.setattr("harness.observability.console_renderer.Live", _DummyLive)

    renderer = ConsoleRenderer(trace, console)

    trace.emit("agent_start", model="qwen2.5-coder:7b", prompt="hello", max_turns=4)
    trace.emit("turn_start", turn=1, phase="discover")
    trace.emit("model_call", message_count=2, phase="discover", tool_categories=["file"])
    trace.emit("content_delta", text="partial")
    trace.emit("thinking_delta", text="think")
    trace.emit("model_reply", parse_mode="structured", elapsed_ms=100, repair_applied=False, normalize_variant="fenced")
    trace.emit("tool_dispatch", name="read_file", args={"path": "app/main.py"}, call_id="abc")
    trace.emit("tool_result", name="read_file", args={"path": "app/main.py"}, call_id="abc", success=True, summary="ok", data="ok")
    trace.emit("response_text", text="done")
    trace.emit("agent_done", reason="done", turns=1, elapsed=0.5)

    assert renderer._last_parse_mode == "structured"
    assert any("tool ->" in item for item in renderer._activity)
