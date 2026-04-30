"""Query helpers for project graphs."""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

import networkx as nx

from graph.adapters import to_networkx
from graph.models import ProjectGraph, SymbolNode
from graph.security import sanitize_label


class ProjectGraphQuery:
    def __init__(self, graph: ProjectGraph) -> None:
        self.graph = graph
        self._out_edges = defaultdict(list)
        self._in_edges = defaultdict(list)
        for edge in graph.edges:
            self._out_edges[edge.source].append(edge)
            self._in_edges[edge.target].append(edge)
        self._nx: nx.Graph | None = None

    def skeleton(self, max_files: int = 200) -> str:
        files = sorted(self.graph.files)
        lines = [f"{len(files)} Python files, {len(self.graph.symbols)} symbols"]
        for path in files[:max_files]:
            depth = path.count("/")
            lines.append(f"{'  ' * depth}- {PurePosixPath(path).name}")
        if len(files) > max_files:
            lines.append(f"... {len(files) - max_files} more files")
        return "\n".join(lines)

    def architecture_report(self, limit: int = 10) -> dict:
        import_counts = defaultdict(int)
        call_counts = defaultdict(int)
        for edge in self.graph.edges:
            if edge.kind == "imports":
                import_counts[edge.target] += 1
            if edge.kind == "calls":
                call_counts[edge.target] += 1
        ranked = sorted(
            self.graph.symbols.values(),
            key=lambda symbol: (import_counts[symbol.id] + call_counts[symbol.id], symbol.id),
            reverse=True,
        )
        return {
            "generated_at": self.graph.generated_at,
            "files": len(self.graph.files),
            "symbols": len(self.graph.symbols),
            "nodes": len(self.graph.nodes) + len(self.graph.symbols),
            "edges": len(self.graph.edges),
            "unresolved_calls": self.graph.metadata.get("unresolved_call_count", 0),
            "communities": self.graph.metadata.get("community_count", 0),
            "top_symbols": [self._compact_symbol(symbol) for symbol in ranked[:limit]],
            "god_nodes": self.graph.metadata.get("god_nodes", [])[:limit],
            "surprising_connections": self.graph.metadata.get("surprising_connections", [])[:limit],
        }

    def find_symbol(self, query: str, kind: str = "", limit: int = 20) -> list[dict]:
        needle = query.lower().strip()
        matches = []
        for symbol in self.graph.symbols.values():
            if kind and symbol.kind != kind:
                continue
            haystack = f"{symbol.id} {symbol.name} {symbol.qualname} {symbol.path}".lower()
            if not needle or needle in haystack:
                score = _symbol_match_score(symbol, needle)
                matches.append((score, self._compact_symbol(symbol)))
        return [item for _score, item in sorted(matches, key=lambda row: (-row[0], row[1]["symbol_id"]))[:limit]]

    def symbol_details(self, symbol_id_or_query: str) -> dict:
        symbol = self._resolve_symbol(symbol_id_or_query)
        if not symbol:
            return {}
        callers = [
            self._compact_symbol(self.graph.symbols[edge.source])
            for edge in self._in_edges[symbol.id]
            if edge.kind == "calls" and edge.source in self.graph.symbols
        ]
        callees = [
            self._compact_symbol(self.graph.symbols[edge.target])
            for edge in self._out_edges[symbol.id]
            if edge.kind == "calls" and edge.target in self.graph.symbols
        ]
        children = [
            self._compact_symbol(self.graph.symbols[edge.target])
            for edge in self._out_edges[symbol.id]
            if edge.kind == "contains" and edge.target in self.graph.symbols
        ]
        return {
            **self._compact_symbol(symbol),
            "parameters": [param.__dict__ for param in symbol.parameters],
            "return_annotation": symbol.return_annotation,
            "decorators": symbol.decorators,
            "doc_summary": symbol.doc_summary,
            "parent_id": symbol.parent_id,
            "callers": callers,
            "callees": callees,
            "children": children,
        }

    def usages(self, symbol_id_or_query: str, limit: int = 25) -> list[dict]:
        symbol = self._resolve_symbol(symbol_id_or_query)
        if not symbol:
            return []
        rows = []
        for edge in self._in_edges[symbol.id]:
            if edge.kind != "calls":
                continue
            caller = self.graph.symbols.get(edge.source)
            rows.append(
                {
                    "caller": self._compact_symbol(caller) if caller else {"symbol_id": edge.source},
                    "line": edge.metadata.get("line", 0),
                    "expression": edge.metadata.get("expression", ""),
                }
            )
        return rows[:limit]

    def hierarchy(self, symbol_id_or_query: str, depth: int = 3) -> dict:
        symbol = self._resolve_symbol(symbol_id_or_query)
        if not symbol:
            return {}
        ancestors = []
        current = symbol
        while current.parent_id and current.parent_id in self.graph.symbols:
            current = self.graph.symbols[current.parent_id]
            ancestors.append(self._compact_symbol(current))
        return {
            "symbol": self._compact_symbol(symbol),
            "ancestors": ancestors,
            "callers": self._walk_callers(symbol.id, depth),
            "callees": self._walk_callees(symbol.id, depth),
        }

    def related(self, symbol_id_or_query: str, limit: int = 20) -> list[dict]:
        symbol = self._resolve_symbol(symbol_id_or_query)
        if not symbol:
            return []
        related_ids: list[str] = []
        for edge in self._in_edges[symbol.id] + self._out_edges[symbol.id]:
            other = edge.source if edge.target == symbol.id else edge.target
            if other in self.graph.symbols and other not in related_ids:
                related_ids.append(other)
        return [self._compact_symbol(self.graph.symbols[sid]) for sid in related_ids[:limit]]

    def graph_stats(self) -> dict:
        G = self._networkx()
        confidences = [data.get("confidence", "EXTRACTED") for _, _, data in G.edges(data=True)]
        return {
            "generated_at": self.graph.generated_at,
            "files": len(self.graph.files),
            "symbols": len(self.graph.symbols),
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "communities": self.graph.metadata.get("community_count", 0),
            "confidence": {
                "EXTRACTED": confidences.count("EXTRACTED"),
                "INFERRED": confidences.count("INFERRED"),
                "AMBIGUOUS": confidences.count("AMBIGUOUS"),
            },
            "extraction_errors": self.graph.metadata.get("extraction_errors", []),
        }

    def query_graph(self, question: str, depth: int = 2, mode: str = "bfs", token_budget: int = 2000) -> str:
        G = self._networkx()
        terms = [term.lower() for term in question.split() if len(term) > 2]
        scored = self._score_nodes(terms)
        starts = [node_id for _, node_id in scored[:5]]
        if not starts:
            return "No matching nodes found."
        nodes, edges = self._dfs(starts, depth) if mode == "dfs" else self._bfs(starts, depth)
        header = f"Traversal: {mode.upper()} depth={depth} | Start: {starts} | {len(nodes)} nodes\n\n"
        return header + self._subgraph_to_text(nodes, edges, token_budget)

    def shortest_path(self, source: str, target: str, max_hops: int = 8) -> dict:
        G = self._networkx()
        src = self._best_node(source)
        tgt = self._best_node(target)
        if not src or not tgt:
            return {"found": False, "error": "source or target not found", "source": src, "target": tgt}
        try:
            path = nx.shortest_path(G, src, tgt, weight=self._path_weight)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return {"found": False, "source": src, "target": tgt, "path": []}
        hops = len(path) - 1
        if hops > max_hops:
            return {"found": False, "source": src, "target": tgt, "hops": hops, "error": "path exceeds max_hops"}
        return {
            "found": True,
            "source": src,
            "target": tgt,
            "hops": hops,
            "path": [
                {
                    "id": node_id,
                    "label": G.nodes[node_id].get("label", node_id),
                    "source_file": G.nodes[node_id].get("source_file", ""),
                }
                for node_id in path
            ],
        }

    def neighbors(self, label_or_id: str, relation_filter: str = "", limit: int = 50) -> list[dict]:
        G = self._networkx()
        node_id = self._best_node(label_or_id)
        if not node_id:
            return []
        rows = []
        for neighbor in G.neighbors(node_id):
            data = G.edges[node_id, neighbor]
            relation = data.get("relation", "")
            if relation_filter and relation_filter.lower() not in relation.lower():
                continue
            rows.append(
                {
                    "node_id": neighbor,
                    "label": G.nodes[neighbor].get("label", neighbor),
                    "relation": relation,
                    "confidence": data.get("confidence", ""),
                    "source_file": G.nodes[neighbor].get("source_file", ""),
                }
            )
        return rows[:limit]

    def community(self, community_id: int, limit: int = 100) -> list[dict]:
        G = self._networkx()
        rows = []
        for node_id, data in G.nodes(data=True):
            if data.get("community") == community_id:
                rows.append(
                    {
                        "node_id": node_id,
                        "label": data.get("label", node_id),
                        "source_file": data.get("source_file", ""),
                        "kind": data.get("kind", ""),
                    }
                )
        return rows[:limit]

    def _walk_callers(self, symbol_id: str, depth: int) -> list[dict]:
        return self._walk(symbol_id, depth, incoming=True)

    def _walk_callees(self, symbol_id: str, depth: int) -> list[dict]:
        return self._walk(symbol_id, depth, incoming=False)

    def _walk(self, symbol_id: str, depth: int, incoming: bool) -> list[dict]:
        seen = {symbol_id}
        frontier = [(symbol_id, 0)]
        rows = []
        while frontier:
            current, level = frontier.pop(0)
            if level >= depth:
                continue
            edges = self._in_edges[current] if incoming else self._out_edges[current]
            for edge in edges:
                if edge.kind != "calls":
                    continue
                other = edge.source if incoming else edge.target
                if other in seen or other not in self.graph.symbols:
                    continue
                seen.add(other)
                rows.append({"depth": level + 1, **self._compact_symbol(self.graph.symbols[other])})
                frontier.append((other, level + 1))
        return rows

    def _resolve_symbol(self, symbol_id_or_query: str) -> SymbolNode | None:
        if symbol_id_or_query in self.graph.symbols:
            return self.graph.symbols[symbol_id_or_query]
        matches = self.find_symbol(symbol_id_or_query, limit=2)
        if len(matches) == 1:
            return self.graph.symbols.get(matches[0]["symbol_id"])
        return None

    def _networkx(self) -> nx.Graph:
        if self._nx is None:
            self._nx = to_networkx(self.graph)
        return self._nx

    def _score_nodes(self, terms: list[str]) -> list[tuple[float, str]]:
        G = self._networkx()
        scored = []
        for node_id, data in G.nodes(data=True):
            label = str(data.get("label") or node_id).lower()
            source = str(data.get("source_file") or "").lower()
            score = sum(1 for term in terms if term in label) + sum(0.5 for term in terms if term in source)
            if node_id in self.graph.symbols:
                score += 1.5
            if any(term == node_id.lower() or term == label for term in terms):
                score += 2.0
            score -= _node_noise_penalty(node_id, data)
            if score > 0:
                scored.append((score, node_id))
        return sorted(scored, reverse=True)

    def _best_node(self, query: str) -> str:
        G = self._networkx()
        if query in G:
            return query
        scored = self._score_nodes([term.lower() for term in query.split() if term])
        return scored[0][1] if scored else ""

    def _bfs(self, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple[str, str]]]:
        G = self._networkx()
        visited = set(start_nodes)
        frontier = set(start_nodes)
        edges_seen: list[tuple[str, str]] = []
        for _ in range(max(depth, 0)):
            next_frontier: set[str] = set()
            for node_id in frontier:
                for neighbor in G.neighbors(node_id):
                    if neighbor not in visited:
                        next_frontier.add(neighbor)
                    edges_seen.append((node_id, neighbor))
            visited.update(next_frontier)
            frontier = next_frontier
        return visited, edges_seen

    def _dfs(self, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple[str, str]]]:
        G = self._networkx()
        visited: set[str] = set()
        edges_seen: list[tuple[str, str]] = []
        stack = [(node_id, 0) for node_id in reversed(start_nodes)]
        while stack:
            node_id, level = stack.pop()
            if node_id in visited or level > depth:
                continue
            visited.add(node_id)
            for neighbor in G.neighbors(node_id):
                edges_seen.append((node_id, neighbor))
                if neighbor not in visited:
                    stack.append((neighbor, level + 1))
        return visited, edges_seen

    def _subgraph_to_text(self, nodes: set[str], edges: list[tuple[str, str]], token_budget: int) -> str:
        G = self._networkx()
        char_budget = token_budget * 3
        lines = []
        for node_id in sorted(nodes, key=lambda item: G.degree(item), reverse=True):
            data = G.nodes[node_id]
            lines.append(
                "NODE "
                + sanitize_label(str(data.get("label", node_id)))
                + f" [id={node_id} src={data.get('source_file', '')} loc={data.get('source_location', '')} community={data.get('community', '')}]"
            )
        seen_edges = set()
        for source, target in edges:
            if source not in nodes or target not in nodes or (source, target) in seen_edges:
                continue
            seen_edges.add((source, target))
            data = G.edges[source, target]
            lines.append(
                f"EDGE {sanitize_label(str(G.nodes[source].get('label', source)))} "
                f"--{data.get('relation', '')} [{data.get('confidence', '')}]--> "
                f"{sanitize_label(str(G.nodes[target].get('label', target)))}"
            )
        output = "\n".join(lines)
        if len(output) > char_budget:
            output = output[:char_budget] + f"\n... (truncated to ~{token_budget} token budget)"
        return output

    def _path_weight(self, source: str, target: str, data: dict) -> float:
        G = self._networkx()
        relation = str(data.get("relation", "")).lower()
        weight = 1.0
        if relation in {"calls", "imports", "contains"}:
            weight -= 0.25
        if relation in {"mentions", "rationale", "related"}:
            weight += 1.0
        weight += _node_noise_penalty(source, G.nodes[source])
        weight += _node_noise_penalty(target, G.nodes[target])
        return max(weight, 0.1)

    @staticmethod
    def _compact_symbol(symbol: SymbolNode | None) -> dict:
        if not symbol:
            return {}
        return {
            "symbol_id": symbol.id,
            "name": symbol.name,
            "qualname": symbol.qualname,
            "kind": symbol.kind,
            "path": symbol.path,
            "line": symbol.line,
            "signature": symbol.signature,
        }


def _symbol_match_score(symbol: SymbolNode, needle: str) -> float:
    if not needle:
        return 0
    score = 0.0
    if symbol.id.lower() == needle:
        score += 8
    if symbol.name.lower() == needle:
        score += 6
    if symbol.qualname.lower() == needle:
        score += 5
    if needle in symbol.path.lower():
        score += 2
    if needle in symbol.signature.lower():
        score += 1
    return score


def _node_noise_penalty(node_id: str, data: dict) -> float:
    label = str(data.get("label") or node_id).lower()
    source = str(data.get("source_file") or "")
    kind = str(data.get("kind") or "").lower()
    penalty = 0.0
    if not source:
        penalty += 1.5
    if kind in {"entity", "identifier", "literal"} and "::" not in node_id:
        penalty += 0.75
    if any(word in label for word in ("rationale", "docstring", "comment")):
        penalty += 1.0
    if label in {"str", "int", "dict", "list", "set", "tuple", "bool", "none"}:
        penalty += 2.0
    return penalty

