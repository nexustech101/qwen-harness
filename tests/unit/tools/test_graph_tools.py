from pathlib import Path

from app import config
from app.tools.registry import registry


def _set_workspace_env(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "central-workspace"
    monkeypatch.setattr(config, "WORKSPACE_HOME", str(home))
    monkeypatch.setattr(config, "WORKSPACE_PROJECTS_DIR", str(home / "workspaces"))
    monkeypatch.setattr(config, "WORKSPACE_INDEX_FILE", str(home / "workspace_index.json"))


def test_graph_tools_register_and_query(tmp_path, monkeypatch):
    import app.tools.graph_tools  # noqa: F401

    _set_workspace_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mod.py").write_text(
        "def helper():\n    return 1\n\n"
        "def run():\n    return helper()\n",
        encoding="utf-8",
    )

    assert registry.get("graph_refresh") is not None
    assert registry.get("graph_symbol_details") is not None
    assert registry.get("graph_query") is not None
    assert registry.get("graph_report") is not None

    refresh = registry.execute("graph_refresh", {})
    assert refresh.success
    assert refresh.metadata["retrievable"] is True

    found = registry.execute("graph_find_symbol", {"query": "helper"})
    assert found.success
    assert "mod.py::helper" in found.data

    details = registry.execute("graph_symbol_details", {"symbol": "mod.py::helper"})
    assert details.success
    assert details.metadata["symbol_id"] == "mod.py::helper"

    stats = registry.execute("graph_stats", {})
    assert stats.success
    assert '"nodes"' in stats.data

    graph_query = registry.execute("graph_query", {"question": "helper run", "depth": 1})
    assert graph_query.success
    assert "NODE" in graph_query.data

    path = registry.execute("graph_shortest_path", {"source": "mod.py::run", "target": "mod.py::helper"})
    assert path.success
    assert '"found": true' in path.data

    report = registry.execute("graph_report", {})
    assert report.success
    assert "Graph Report" in report.data


def test_graph_context_load_budget_and_evict(tmp_path, monkeypatch):
    import app.tools.graph_tools  # noqa: F401

    _set_workspace_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mod.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    assert registry.execute("graph_refresh", {}).success
    loaded = registry.execute("graph_context_load", {"query": "run"})
    assert loaded.success
    assert "mod.py::run" in loaded.data

    prompt_context = registry.execute("graph_prompt_context", {})
    assert prompt_context.success
    assert "mod.py::run" in prompt_context.data

    evicted = registry.execute("graph_context_evict", {})
    assert evicted.success
    assert '"loaded_count": 0' in evicted.data
