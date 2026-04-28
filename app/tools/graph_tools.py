"""Project graph tools for compact structural context retrieval."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from app.core.state import ToolResult
from app.core.workspace import Workspace
from app.tools.registry import registry
from graph.context import GraphContextManager
from graph.query import ProjectGraphQuery
from graph.store import GraphStore


def _store() -> GraphStore:
    ws = Workspace(project_root=Path.cwd())
    return GraphStore(ws.project_root, ws.graph_path(), ws.graph_context_path())


def _query(refresh_if_missing: bool = True) -> tuple[GraphStore, ProjectGraphQuery]:
    store = _store()
    graph = store.load_or_refresh() if refresh_if_missing else store.load()
    if graph is None:
        graph = store.refresh()
    return store, ProjectGraphQuery(graph)


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)


@registry.tool(
    name="graph_refresh",
    category="graph",
    description="Build or refresh the Python project graph in the central workspace",
    idempotent=True,
)
def graph_refresh(
    include: Annotated[str, "Glob of code files to include; empty includes supported code files"] = "",
    exclude: Annotated[str, "Glob of Python files to exclude"] = "",
) -> ToolResult:
    try:
        store = _store()
        graph = store.refresh(include=include, exclude=exclude)
        return ToolResult(
            success=True,
            data=f"Graph refreshed: {len(graph.files)} files, {len(graph.symbols)} symbols, {len(graph.edges)} edges",
            metadata={
                "graph_updated_at": graph.generated_at,
                "file_count": len(graph.files),
                "symbol_count": len(graph.symbols),
                "node_count": graph.metadata.get("node_count", len(graph.nodes) + len(graph.symbols)),
                "edge_count": len(graph.edges),
                "report_path": str(store.report_path()),
                "networkx_path": str(store.networkx_path()),
                "retrievable": True,
            },
        )
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph refresh failed: {exc}")


@registry.tool(
    name="graph_summary",
    category="graph",
    description="Return a compact project graph architecture summary",
    idempotent=True,
)
def graph_summary(
    limit: Annotated[int, "Maximum number of top symbols to return"] = 10,
) -> ToolResult:
    try:
        store, query = _query()
        report = query.architecture_report(limit=limit)
        return ToolResult(
            success=True,
            data=_json(report),
            metadata={
                "graph_updated_at": query.graph.generated_at,
                "edge_count": len(query.graph.edges),
                "retrievable": True,
                "graph_path": str(store.graph_path),
            },
        )
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph summary failed: {exc}")


@registry.tool(
    name="graph_report",
    category="graph",
    description="Return the current graph report with communities, god nodes, and surprising connections",
    idempotent=True,
)
def graph_report() -> ToolResult:
    try:
        store, _graph_query = _query()
        report_path = store.report_path()
        if not report_path.exists():
            store.refresh()
        data = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
        return ToolResult(success=True, data=data, metadata={"report_path": str(report_path), "retrievable": True})
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph report failed: {exc}")


@registry.tool(
    name="graph_stats",
    category="graph",
    description="Return graph node, edge, community, confidence, and extraction statistics",
    idempotent=True,
)
def graph_stats() -> ToolResult:
    try:
        _store, graph_query = _query()
        stats = graph_query.graph_stats()
        return ToolResult(success=True, data=_json(stats), metadata={"retrievable": True})
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph stats failed: {exc}")


@registry.tool(
    name="graph_query",
    category="graph",
    description="Search the graph and return a compact BFS/DFS subgraph as prompt-ready text",
    idempotent=True,
)
def graph_query(
    question: Annotated[str, "Natural language question or keyword query"],
    depth: Annotated[int, "Traversal depth"] = 2,
    mode: Annotated[str, "Traversal mode: bfs or dfs"] = "bfs",
    token_budget: Annotated[int, "Approximate max output tokens"] = 2000,
) -> ToolResult:
    try:
        _store, graph_query_obj = _query()
        data = graph_query_obj.query_graph(question, depth=depth, mode=mode, token_budget=token_budget)
        return ToolResult(success=True, data=data, metadata={"retrievable": True})
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph query failed: {exc}")


@registry.tool(
    name="graph_shortest_path",
    category="graph",
    description="Find the shortest graph path between two symbols or graph nodes",
    idempotent=True,
)
def graph_shortest_path(
    source: Annotated[str, "Source node label, ID, or keyword"],
    target: Annotated[str, "Target node label, ID, or keyword"],
    max_hops: Annotated[int, "Maximum path length"] = 8,
) -> ToolResult:
    try:
        _store, graph_query_obj = _query()
        data = graph_query_obj.shortest_path(source, target, max_hops=max_hops)
        return ToolResult(success=True, data=_json(data), metadata={"found": data.get("found", False), "retrievable": True})
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph shortest path failed: {exc}")


@registry.tool(
    name="graph_neighbors",
    category="graph",
    description="Return direct graph neighbors for a node with edge relation metadata",
    idempotent=True,
)
def graph_neighbors(
    node: Annotated[str, "Node label, ID, or keyword"],
    relation_filter: Annotated[str, "Optional relation substring filter"] = "",
    limit: Annotated[int, "Maximum neighbors"] = 50,
) -> ToolResult:
    try:
        _store, graph_query_obj = _query()
        rows = graph_query_obj.neighbors(node, relation_filter=relation_filter, limit=limit)
        return ToolResult(success=True, data=_json(rows), metadata={"match_count": len(rows), "retrievable": True})
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph neighbors failed: {exc}")


@registry.tool(
    name="graph_community",
    category="graph",
    description="Return nodes in a detected graph community",
    idempotent=True,
)
def graph_community(
    community_id: Annotated[int, "Community ID"],
    limit: Annotated[int, "Maximum nodes"] = 100,
) -> ToolResult:
    try:
        _store, graph_query_obj = _query()
        rows = graph_query_obj.community(community_id, limit=limit)
        return ToolResult(success=True, data=_json(rows), metadata={"match_count": len(rows), "retrievable": True})
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph community failed: {exc}")


@registry.tool(
    name="graph_find_symbol",
    category="graph",
    description="Find symbols by name, qualified name, path, or symbol id",
    idempotent=True,
)
def graph_find_symbol(
    query: Annotated[str, "Symbol search text"],
    kind: Annotated[str, "Optional symbol kind filter"] = "",
    limit: Annotated[int, "Maximum matches"] = 20,
) -> ToolResult:
    try:
        _store, graph_query = _query()
        matches = graph_query.find_symbol(query, kind=kind, limit=limit)
        return ToolResult(
            success=True,
            data=_json(matches),
            metadata={
                "match_count": len(matches),
                "graph_updated_at": graph_query.graph.generated_at,
                "retrievable": True,
            },
        )
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph symbol search failed: {exc}")


@registry.tool(
    name="graph_symbol_details",
    category="graph",
    description="Return details, callers, callees, and children for one symbol",
    idempotent=True,
)
def graph_symbol_details(
    symbol: Annotated[str, "Symbol id or unique symbol search text"],
) -> ToolResult:
    try:
        _store, graph_query = _query()
        details = graph_query.symbol_details(symbol)
        if not details:
            return ToolResult(success=False, data="", error=f"Symbol not found or ambiguous: {symbol}")
        return ToolResult(
            success=True,
            data=_json(details),
            metadata={
                "symbol_id": details.get("symbol_id", ""),
                "path": details.get("path", ""),
                "line": details.get("line", 0),
                "kind": details.get("kind", ""),
                "edge_count": len(details.get("callers", [])) + len(details.get("callees", [])),
                "graph_updated_at": graph_query.graph.generated_at,
                "retrievable": True,
            },
        )
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph details failed: {exc}")


@registry.tool(
    name="graph_usages",
    category="graph",
    description="Return call sites that use a symbol",
    idempotent=True,
)
def graph_usages(
    symbol: Annotated[str, "Symbol id or unique symbol search text"],
    limit: Annotated[int, "Maximum usages"] = 25,
) -> ToolResult:
    try:
        _store, graph_query = _query()
        usages = graph_query.usages(symbol, limit=limit)
        return ToolResult(
            success=True,
            data=_json(usages),
            metadata={
                "match_count": len(usages),
                "graph_updated_at": graph_query.graph.generated_at,
                "retrievable": True,
            },
        )
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph usages failed: {exc}")


@registry.tool(
    name="graph_hierarchy",
    category="graph",
    description="Return ancestors plus caller/callee hierarchy for a symbol",
    idempotent=True,
)
def graph_hierarchy(
    symbol: Annotated[str, "Symbol id or unique symbol search text"],
    depth: Annotated[int, "Call graph traversal depth"] = 3,
) -> ToolResult:
    try:
        _store, graph_query = _query()
        data = graph_query.hierarchy(symbol, depth=depth)
        if not data:
            return ToolResult(success=False, data="", error=f"Symbol not found or ambiguous: {symbol}")
        return ToolResult(
            success=True,
            data=_json(data),
            metadata={
                "symbol_id": data.get("symbol", {}).get("symbol_id", ""),
                "edge_count": len(data.get("callers", [])) + len(data.get("callees", [])),
                "graph_updated_at": graph_query.graph.generated_at,
                "retrievable": True,
            },
        )
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph hierarchy failed: {exc}")


@registry.tool(
    name="graph_related",
    category="graph",
    description="Return nearby symbols related by contains/imports/calls edges",
    idempotent=True,
)
def graph_related(
    symbol: Annotated[str, "Symbol id or unique symbol search text"],
    limit: Annotated[int, "Maximum related symbols"] = 20,
) -> ToolResult:
    try:
        _store, graph_query = _query()
        related = graph_query.related(symbol, limit=limit)
        return ToolResult(
            success=True,
            data=_json(related),
            metadata={
                "match_count": len(related),
                "graph_updated_at": graph_query.graph.generated_at,
                "retrievable": True,
            },
        )
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph related failed: {exc}")


@registry.tool(
    name="graph_context_load",
    category="graph",
    description="Load compact graph symbol context into the graph context manager",
    idempotent=True,
)
def graph_context_load(
    query: Annotated[str, "Symbol id or search text to load"],
    limit: Annotated[int, "Maximum symbols to load"] = 5,
) -> ToolResult:
    try:
        manager = GraphContextManager(_store())
        summary = manager.load(query, limit=limit)
        return ToolResult(success=True, data=_json(summary), metadata={"retrievable": True})
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph context load failed: {exc}")


@registry.tool(
    name="graph_context_evict",
    category="graph",
    description="Evict one symbol, matching symbols, or all graph context if symbol is empty",
    idempotent=True,
)
def graph_context_evict(
    symbol: Annotated[str, "Symbol id or search text to evict; empty evicts all"] = "",
) -> ToolResult:
    try:
        manager = GraphContextManager(_store())
        summary = manager.evict(symbol)
        return ToolResult(success=True, data=_json(summary), metadata={"retrievable": True})
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph context evict failed: {exc}")


@registry.tool(
    name="graph_context_budget",
    category="graph",
    description="Return current graph context token budget and loaded symbols",
    idempotent=True,
)
def graph_context_budget() -> ToolResult:
    try:
        manager = GraphContextManager(_store())
        return ToolResult(success=True, data=_json(manager.budget_summary()), metadata={"retrievable": True})
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph context budget failed: {exc}")


@registry.tool(
    name="graph_prompt_context",
    category="graph",
    description="Render loaded graph context as compact prompt-ready text",
    idempotent=True,
)
def graph_prompt_context() -> ToolResult:
    try:
        manager = GraphContextManager(_store())
        return ToolResult(success=True, data=manager.prompt_context(), metadata={"retrievable": True})
    except Exception as exc:
        return ToolResult(success=False, data="", error=f"Graph prompt context failed: {exc}")
