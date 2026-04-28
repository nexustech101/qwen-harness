from pathlib import Path

from app import config
from app.core.workspace import Workspace
from graph.store import GraphStore


def _set_workspace_env(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "central-workspace"
    monkeypatch.setattr(config, "WORKSPACE_HOME", str(home))
    monkeypatch.setattr(config, "WORKSPACE_PROJECTS_DIR", str(home / "workspaces"))
    monkeypatch.setattr(config, "WORKSPACE_INDEX_FILE", str(home / "workspace_index.json"))


def test_graph_store_writes_under_central_workspace(tmp_path, monkeypatch):
    _set_workspace_env(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    (project / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")

    ws = Workspace(project_root=project)
    store = GraphStore(project, ws.graph_path(), ws.graph_context_path())
    graph = store.refresh()
    loaded = store.load()

    assert ws.graph_path() == ws.root / "project_graph.json"
    assert ws.graph_path().exists()
    assert loaded is not None
    assert loaded.generated_at == graph.generated_at
    assert "app.py::main" in loaded.symbols
