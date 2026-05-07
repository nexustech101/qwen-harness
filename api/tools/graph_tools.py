"""Project graph tools for compact structural context retrieval."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from agent.core.workspace import Workspace
from graph.query import ProjectGraphQuery
from graph.service import GraphService
from graph.store import GraphStore


def _service() -> GraphService:
    ws = Workspace(project_root=Path.cwd())
    return GraphService(GraphStore(ws.project_root, ws.graph_path(), ws.graph_context_path()))


def _store() -> GraphStore:
    return _service().store


def _query() -> tuple[GraphStore, ProjectGraphQuery]:
    service = _service()
    return service.store, service.query()


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)


@tool
def graph_refresh(
    include: Annotated[str, "Glob of code files to include; empty includes supported code files"] = "",
    exclude: Annotated[str, "Glob of files to exclude"] = "",
) -> str:
    """Build or refresh the project graph."""
    try:
        service = _service()
        result = service.ensure_fresh(reason="tool", force=True, include=include, exclude=exclude)
        return result.message
    except Exception as exc:
        return f"ERROR: Graph refresh failed: {exc}"


@tool
def graph_summary(
    limit: Annotated[int, "Maximum number of top symbols to return"] = 10,
) -> str:
    """Return a compact project graph architecture summary."""
    try:
        _store_obj, query = _query()
        report = query.architecture_report(limit=limit)
        return _json(report)
    except Exception as exc:
        return f"ERROR: Graph summary failed: {exc}"


@tool
def graph_report() -> str:
    """Return the current graph report with communities, god nodes, and surprising connections."""
    try:
        service = _service()
        return service.report()
    except Exception as exc:
        return f"ERROR: Graph report failed: {exc}"


@tool
def graph_stats() -> str:
    """Return graph node, edge, community, confidence, and extraction statistics."""
    try:
        _store_obj, graph_query = _query()
        return _json(graph_query.graph_stats())
    except Exception as exc:
        return f"ERROR: Graph stats failed: {exc}"


@tool
def graph_query(
    question: Annotated[str, "Natural language question or keyword query"],
    depth: Annotated[int, "Traversal depth"] = 2,
    mode: Annotated[str, "Traversal mode: bfs or dfs"] = "bfs",
    token_budget: Annotated[int, "Approximate max output tokens"] = 2000,
) -> str:
    """Search the graph and return a compact BFS/DFS subgraph as prompt-ready text."""
    try:
        _store_obj, graph_query_obj = _query()
        return graph_query_obj.query_graph(question, depth=depth, mode=mode, token_budget=token_budget)
    except Exception as exc:
        return f"ERROR: Graph query failed: {exc}"


@tool
def graph_shortest_path(
    source: Annotated[str, "Source node label, ID, or keyword"],
    target: Annotated[str, "Target node label, ID, or keyword"],
    max_hops: Annotated[int, "Maximum path length"] = 8,
) -> str:
    """Find the shortest graph path between two symbols or graph nodes."""
    try:
        _store_obj, graph_query_obj = _query()
        data = graph_query_obj.shortest_path(source, target, max_hops=max_hops)
        return _json(data)
    except Exception as exc:
        return f"ERROR: Graph shortest path failed: {exc}"


@tool
def graph_neighbors(
    node: Annotated[str, "Node label, ID, or keyword"],
    relation_filter: Annotated[str, "Optional relation substring filter"] = "",
    limit: Annotated[int, "Maximum neighbors"] = 50,
) -> str:
    """Return direct graph neighbors for a node with edge relation metadata."""
    try:
        _store_obj, graph_query_obj = _query()
        rows = graph_query_obj.neighbors(node, relation_filter=relation_filter, limit=limit)
        return _json(rows)
    except Exception as exc:
        return f"ERROR: Graph neighbors failed: {exc}"


@tool
def graph_community(
    community_id: Annotated[int, "Community ID"],
    limit: Annotated[int, "Maximum nodes"] = 100,
) -> str:
    """Return nodes in a detected graph community."""
    try:
        _store_obj, graph_query_obj = _query()
        rows = graph_query_obj.community(community_id, limit=limit)
        return _json(rows)
    except Exception as exc:
        return f"ERROR: Graph community failed: {exc}"


@tool
def graph_find_symbol(
    query: Annotated[str, "Symbol search text"],
    kind: Annotated[str, "Optional symbol kind filter"] = "",
    limit: Annotated[int, "Maximum matches"] = 20,
) -> str:
    """Find symbols by name, qualified name, path, or symbol id."""
    try:
        _store_obj, graph_query_obj = _query()
        matches = graph_query_obj.find_symbol(query, kind=kind, limit=limit)
        return _json(matches)
    except Exception as exc:
        return f"ERROR: Graph symbol search failed: {exc}"


@tool
def graph_symbol_details(
    symbol: Annotated[str, "Symbol id or unique symbol search text"],
) -> str:
    """Return details, callers, callees, and children for one symbol."""
    try:
        _store_obj, graph_query_obj = _query()
        details = graph_query_obj.symbol_details(symbol)
        if not details:
            return f"ERROR: Symbol not found or ambiguous: {symbol}"
        return _json(details)
    except Exception as exc:
        return f"ERROR: Graph details failed: {exc}"


@tool
def graph_usages(
    symbol: Annotated[str, "Symbol id or unique symbol search text"],
    limit: Annotated[int, "Maximum usages"] = 25,
) -> str:
    """Return call sites that use a symbol."""
    try:
        _store_obj, graph_query_obj = _query()
        usages = graph_query_obj.usages(symbol, limit=limit)
        return _json(usages)
    except Exception as exc:
        return f"ERROR: Graph usages failed: {exc}"