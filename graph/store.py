"""Workspace-backed graph persistence."""

from __future__ import annotations

import json
from pathlib import Path

from networkx.readwrite import json_graph

from graph.adapters import to_networkx
from graph.builder import build_project_graph
from graph.models import ProjectGraph


class GraphStore:
    def __init__(self, project_root: Path | str, graph_path: Path | str, context_path: Path | str) -> None:
        self.project_root = Path(project_root).resolve()
        self.graph_path = Path(graph_path)
        self.context_path = Path(context_path)

    def refresh(self, include: str = "", exclude: str = "") -> ProjectGraph:
        graph = build_project_graph(self.project_root, include=include, exclude=exclude)
        self.save(graph)
        return graph

    def save(self, graph: ProjectGraph) -> None:
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        self.graph_path.write_text(json.dumps(graph.to_dict(), indent=2, ensure_ascii=True), encoding="utf-8")
        self._write_analysis_artifacts(graph)

    def load(self) -> ProjectGraph | None:
        if not self.graph_path.exists():
            return None
        data = json.loads(self.graph_path.read_text(encoding="utf-8"))
        return ProjectGraph.from_dict(data)

    def load_or_refresh(self) -> ProjectGraph:
        graph = self.load()
        if graph is not None:
            return graph
        return self.refresh()

    def read_context_state(self) -> dict:
        if not self.context_path.exists():
            return {"loaded": [], "budget_tokens": 1200}
        try:
            data = json.loads(self.context_path.read_text(encoding="utf-8"))
        except Exception:
            return {"loaded": [], "budget_tokens": 1200}
        if not isinstance(data, dict):
            return {"loaded": [], "budget_tokens": 1200}
        data.setdefault("loaded", [])
        data.setdefault("budget_tokens", 1200)
        return data

    def write_context_state(self, state: dict) -> None:
        self.context_path.parent.mkdir(parents=True, exist_ok=True)
        self.context_path.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")

    def report_path(self) -> Path:
        return self.graph_path.with_name("project_graph_report.md")

    def networkx_path(self) -> Path:
        return self.graph_path.with_name("project_graph_networkx.json")

    def _write_analysis_artifacts(self, graph: ProjectGraph) -> None:
        try:
            G = to_networkx(graph)
            data = json_graph.node_link_data(G, edges="links")
            self.networkx_path().write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
        except Exception:
            return

        try:
            from graph.report import generate

            communities = {
                int(cid): nodes
                for cid, nodes in graph.metadata.get("communities", {}).items()
            }
            labels = {cid: f"Community {cid}" for cid in communities}
            report = generate(
                G,
                communities,
                graph.metadata.get("cohesion", {}),
                labels,
                graph.metadata.get("god_nodes", []),
                graph.metadata.get("surprising_connections", []),
                graph.metadata.get("detection", {}),
                {"input": graph.metadata.get("input_tokens", 0), "output": graph.metadata.get("output_tokens", 0)},
                graph.project_root,
                suggested_questions=graph.metadata.get("suggested_questions", []),
            )
            self.report_path().write_text(report, encoding="utf-8")
        except Exception as exc:
            self.report_path().write_text(f"# Graph Report\n\nReport generation failed: {exc}\n", encoding="utf-8")

