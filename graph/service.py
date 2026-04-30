"""Shared graph lifecycle service for CLI, app tools, and MCP."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from graph.context import GraphContextManager
from graph.query import ProjectGraphQuery
from graph.store import GraphStore


@dataclass
class GraphRefreshResult:
    refreshed: bool
    reason: str
    generated_at: str = ""
    file_count: int = 0
    symbol_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    graph_path: str = ""
    report_path: str = ""
    networkx_path: str = ""
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class GraphService:
    """Small facade that keeps graph lifecycle behavior consistent."""

    def __init__(self, store: GraphStore) -> None:
        self.store = store

    @classmethod
    def for_project(cls, project_root: Path | str) -> "GraphService":
        root = Path(project_root).resolve()
        out = root / ".graph-out"
        return cls(GraphStore(root, out / "project_graph.json", out / "project_graph_context.json"))

    def ensure_fresh(
        self,
        reason: str = "auto",
        *,
        force: bool = False,
        include: str = "",
        exclude: str = "",
    ) -> GraphRefreshResult:
        stale = force or self.store.is_stale(include=include, exclude=exclude)
        if stale:
            graph = self.store.refresh(include=include, exclude=exclude)
            refreshed = True
        else:
            graph = self.store.load_or_refresh()
            refreshed = False
        return self._result(graph, reason=reason, refreshed=refreshed)

    def mark_dirty(self, paths: list[str] | tuple[str, ...]) -> None:
        self.store.mark_dirty(paths)

    def query(self) -> ProjectGraphQuery:
        graph = self.store.load_or_refresh_if_stale()
        return ProjectGraphQuery(graph)

    def report(self) -> str:
        self.ensure_fresh(reason="report")
        report_path = self.store.report_path()
        if not report_path.exists():
            self.store.refresh()
        return report_path.read_text(encoding="utf-8") if report_path.exists() else ""

    def stats(self) -> dict:
        return self.query().graph_stats()

    def context(self) -> GraphContextManager:
        return GraphContextManager(self.store)

    def _result(self, graph, *, reason: str, refreshed: bool) -> GraphRefreshResult:
        node_count = graph.metadata.get("node_count", len(graph.nodes) + len(graph.symbols))
        action = "refreshed" if refreshed else "already fresh"
        return GraphRefreshResult(
            refreshed=refreshed,
            reason=reason,
            generated_at=graph.generated_at,
            file_count=len(graph.files),
            symbol_count=len(graph.symbols),
            node_count=node_count,
            edge_count=len(graph.edges),
            graph_path=str(self.store.graph_path),
            report_path=str(self.store.report_path()),
            networkx_path=str(self.store.networkx_path()),
            message=f"Graph {action}: {len(graph.files)} files, {len(graph.symbols)} symbols, {len(graph.edges)} edges",
        )
