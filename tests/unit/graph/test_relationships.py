from graph.builder import build_project_graph
from graph.query import ProjectGraphQuery


def test_builder_resolves_imported_function_calls(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "helpers.py").write_text(
        "def helper(value: int) -> int:\n    return value\n",
        encoding="utf-8",
    )
    (pkg / "service.py").write_text(
        "from pkg.helpers import helper\n\n"
        "def run():\n"
        "    return helper(3)\n",
        encoding="utf-8",
    )

    graph = build_project_graph(tmp_path)
    run_id = "pkg/service.py::run"
    helper_id = "pkg/helpers.py::helper"

    assert any(edge.kind == "calls" and edge.source == run_id and edge.target == helper_id for edge in graph.edges)

    usages = ProjectGraphQuery(graph).usages(helper_id)
    assert usages[0]["caller"]["symbol_id"] == run_id


def test_builder_resolves_self_method_calls_and_hierarchy(tmp_path):
    source = tmp_path / "service.py"
    source.write_text(
        "class Service:\n"
        "    def run(self):\n"
        "        return self.prepare()\n"
        "    def prepare(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )

    graph = build_project_graph(tmp_path)
    query = ProjectGraphQuery(graph)
    hierarchy = query.hierarchy("service.py::Service.prepare")

    assert hierarchy["ancestors"][0]["symbol_id"] == "service.py::Service"
    assert hierarchy["callers"][0]["symbol_id"] == "service.py::Service.run"
