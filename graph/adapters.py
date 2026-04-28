"""Adapters between the typed project graph and NetworkX/extraction payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

from graph.models import GraphEdge, GraphNode, HyperEdge, ProjectGraph, SymbolNode


def graph_node_from_symbol(symbol: SymbolNode) -> GraphNode:
    label = symbol.signature or symbol.qualname or symbol.name
    return GraphNode(
        id=symbol.id,
        label=label,
        file_type=symbol.file_type or "code",
        source_file=symbol.source_file or symbol.path,
        source_location=symbol.source_location or f"L{symbol.line}",
        path=symbol.path,
        line=symbol.line,
        kind=symbol.kind,
        community=symbol.community,
        metadata={"qualname": symbol.qualname, "signature": symbol.signature},
    )


def add_extraction(project_graph: ProjectGraph, extraction: dict[str, Any], root: Path) -> None:
    """Merge graphify-style extraction JSON into a ProjectGraph."""
    for raw in extraction.get("nodes", []):
        node_id = str(raw.get("id", "")).strip()
        if not node_id:
            continue
        source_file = _relativize(str(raw.get("source_file", "")), root)
        line = _line_from_location(str(raw.get("source_location", "")))
        project_graph.nodes[node_id] = GraphNode(
            id=node_id,
            label=str(raw.get("label") or node_id),
            file_type=str(raw.get("file_type") or "code"),
            source_file=source_file,
            source_location=str(raw.get("source_location", "")),
            path=source_file,
            line=line,
            kind=str(raw.get("kind") or raw.get("file_type") or "entity"),
            metadata={
                k: v
                for k, v in raw.items()
                if k
                not in {
                    "id",
                    "label",
                    "file_type",
                    "source_file",
                    "source_location",
                    "path",
                    "line",
                    "kind",
                    "community",
                }
            },
        )

    for raw in extraction.get("edges", extraction.get("links", [])):
        source = str(raw.get("source") or raw.get("from") or "")
        target = str(raw.get("target") or raw.get("to") or "")
        if not source or not target:
            continue
        relation = str(raw.get("relation") or raw.get("kind") or "related")
        project_graph.edges.append(
            GraphEdge(
                source=source,
                target=target,
                kind=relation,
                metadata={
                    **{k: v for k, v in raw.items() if k not in {"source", "target", "from", "to"}},
                    "relation": relation,
                    "confidence": raw.get("confidence", "EXTRACTED"),
                    "source_file": _relativize(str(raw.get("source_file", "")), root),
                    "source_location": raw.get("source_location", ""),
                    "weight": raw.get("weight", 1.0),
                },
            )
        )

    for raw in extraction.get("hyperedges", []):
        hid = str(raw.get("id", "")).strip()
        nodes = [str(item) for item in raw.get("nodes", [])]
        if hid and nodes:
            project_graph.hyperedges.append(
                HyperEdge(
                    id=hid,
                    nodes=nodes,
                    label=str(raw.get("label", "")),
                    relation=str(raw.get("relation", "group")),
                    confidence=str(raw.get("confidence", "INFERRED")),
                    source_file=_relativize(str(raw.get("source_file", "")), root),
                    metadata={k: v for k, v in raw.items() if k not in {"id", "nodes", "label"}},
                )
            )


def to_networkx(project_graph: ProjectGraph, directed: bool = False) -> nx.Graph:
    G: nx.Graph = nx.DiGraph() if directed else nx.Graph()
    for symbol in project_graph.symbols.values():
        node = graph_node_from_symbol(symbol)
        _add_node(G, node)
    for node in project_graph.nodes.values():
        _add_node(G, node)
    for edge in project_graph.edges:
        if edge.source not in G or edge.target not in G:
            continue
        attrs = dict(edge.metadata)
        attrs.setdefault("relation", edge.relation)
        attrs.setdefault("confidence", edge.confidence)
        attrs.setdefault("weight", 1.0)
        attrs["_src"] = edge.source
        attrs["_tgt"] = edge.target
        G.add_edge(edge.source, edge.target, **attrs)
    if project_graph.hyperedges:
        G.graph["hyperedges"] = [item.__dict__ for item in project_graph.hyperedges]
    return G


def update_communities(project_graph: ProjectGraph, communities: dict[int, list[str]]) -> None:
    node_to_community = {node_id: cid for cid, nodes in communities.items() for node_id in nodes}
    for symbol in project_graph.symbols.values():
        symbol.community = node_to_community.get(symbol.id)
    for node in project_graph.nodes.values():
        node.community = node_to_community.get(node.id)
    project_graph.metadata["communities"] = communities
    project_graph.metadata["community_count"] = len(communities)


def to_node_link_data(project_graph: ProjectGraph) -> dict[str, Any]:
    return json_graph.node_link_data(to_networkx(project_graph), edges="links")


def _add_node(G: nx.Graph, node: GraphNode) -> None:
    metadata = {
        key: value
        for key, value in node.metadata.items()
        if key not in {"label", "file_type", "source_file", "source_location", "path", "line", "kind", "community"}
    }
    G.add_node(
        node.id,
        label=node.label,
        file_type=node.file_type,
        source_file=node.source_file,
        source_location=node.source_location,
        path=node.path,
        line=node.line,
        kind=node.kind,
        community=node.community,
        **metadata,
    )


def _line_from_location(location: str) -> int:
    if location.startswith("L"):
        try:
            return int(location[1:].split("-", 1)[0])
        except ValueError:
            return 0
    return 0


def _relativize(path: str, root: Path) -> str:
    if not path:
        return ""
    p = Path(path)
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path.replace("\\", "/")
