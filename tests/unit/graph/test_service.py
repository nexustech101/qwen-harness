from pathlib import Path

from graph.service import GraphService
from graph.store import GraphStore


def _store(root: Path) -> GraphStore:
    return GraphStore(root, root / ".graph-out" / "project_graph.json", root / ".graph-out" / "context.json")


def test_graph_store_detects_source_staleness(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    store = _store(tmp_path)

    store.refresh()
    assert store.is_stale() is False

    source.write_text("def main():\n    return 2\n", encoding="utf-8")
    assert store.is_stale() is True


def test_graph_store_ignores_graphifyignored_files(tmp_path):
    (tmp_path / ".graphifyignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    ignored = tmp_path / "ignored.py"
    ignored.write_text("def ignored():\n    return 1\n", encoding="utf-8")
    store = _store(tmp_path)

    store.refresh()
    ignored.write_text("def ignored():\n    return 2\n", encoding="utf-8")

    assert store.is_stale() is False


def test_graph_service_refreshes_only_when_needed(tmp_path):
    (tmp_path / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    service = GraphService(_store(tmp_path))

    first = service.ensure_fresh(reason="test")
    second = service.ensure_fresh(reason="test")

    assert first.refreshed is True
    assert second.refreshed is False
    assert second.file_count == 1
