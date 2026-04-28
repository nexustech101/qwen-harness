import json

from app import config
from app.core.execution import ExecutionEngine, _compact_retrievable_messages
from app.core.state import AgentState


def test_dynamic_tool_categories_include_graph(monkeypatch):
    monkeypatch.setattr(config, "TOOL_SCOPE_MODE", "dynamic")
    engine = ExecutionEngine.__new__(ExecutionEngine)

    assert "graph" in engine._select_tool_categories(AgentState(phase="discover"))
    assert "graph" in engine._select_tool_categories(AgentState(phase="modify"))
    assert "graph" in engine._select_tool_categories(AgentState(phase="verify"))


def test_retrievable_tool_payloads_are_compacted_when_old():
    payload = {
        "tool_results": [
            {
                "name": "graph_summary",
                "ok": True,
                "summary": "summary",
                "data": "x" * 1000,
                "metadata": {
                    "retrievable": True,
                    "retrieval_tool": "graph_summary",
                    "retrieval_args": {"limit": 5},
                },
            }
        ]
    }
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "prompt"},
        {"role": "user", "content": json.dumps(payload)},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "b"},
        {"role": "assistant", "content": "c"},
        {"role": "user", "content": "d"},
        {"role": "assistant", "content": "e"},
    ]

    compacted = _compact_retrievable_messages(messages, keep_tail=4)
    compacted_payload = json.loads(compacted[2]["content"])

    assert "compacted: retrievable project context" in compacted_payload["tool_results"][0]["data"]
    assert compacted_payload["tool_results"][0]["summary"] == "summary"
