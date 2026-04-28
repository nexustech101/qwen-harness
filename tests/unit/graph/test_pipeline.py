import json

from graph.builder import build_project_graph
from graph.query import ProjectGraphQuery
from graph.store import GraphStore


def test_pipeline_writes_report_and_supports_graph_navigation(tmp_path):
    (tmp_path / "service.py").write_text(
        "class Service:\n"
        "    def run(self):\n"
        "        return helper()\n\n"
        "def helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    store = GraphStore(tmp_path, tmp_path / ".graph-out" / "project_graph.json", tmp_path / ".graph-out" / "context.json")
    graph = store.refresh()
    query = ProjectGraphQuery(graph)

    assert store.report_path().exists()
    assert store.networkx_path().exists()
    assert graph.metadata["node_count"] >= len(graph.symbols)
    assert query.graph_stats()["nodes"] >= len(graph.symbols)
    assert "NODE" in query.query_graph("Service run", depth=1)
    assert query.shortest_path("service.py::Service.run", "service.py::helper")["found"]

    node_link = json.loads(store.networkx_path().read_text(encoding="utf-8"))
    assert "nodes" in node_link
    assert "links" in node_link


def test_build_project_graph_records_detection_and_analysis_metadata(tmp_path):
    (tmp_path / "mod.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    graph = build_project_graph(tmp_path)

    assert graph.metadata["detection"]["total_files"] >= 1
    assert "community_count" in graph.metadata
    assert "god_nodes" in graph.metadata
