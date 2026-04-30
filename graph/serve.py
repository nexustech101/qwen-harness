# MCP stdio server - exposes graph query tools to Claude and other agents
from __future__ import annotations
import json
import sys
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graph.service import GraphService
from graph.store import GraphStore
from graph.security import sanitize_label


def _load_graph(graph_path: str) -> nx.Graph:
    try:
        resolved = Path(graph_path).resolve()
        if resolved.suffix != ".json":
            raise ValueError(f"Graph path must be a .json file, got: {graph_path!r}")
        if not resolved.exists():
            raise FileNotFoundError(f"Graph file not found: {resolved}")
        safe = resolved
        data = json.loads(safe.read_text(encoding="utf-8"))
        try:
            return json_graph.node_link_graph(data, edges="links")
        except TypeError:
            return json_graph.node_link_graph(data)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"error: graph.json is corrupted ({exc}). Re-run /graph to rebuild.", file=sys.stderr)
        sys.exit(1)


def _communities_from_graph(G: nx.Graph) -> dict[int, list[str]]:
    """Reconstruct community dict from community property stored on nodes."""
    communities: dict[int, list[str]] = {}
    for node_id, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(node_id)
    return communities


def _strip_diacritics(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _score_nodes(G: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    scored = []
    norm_terms = [_strip_diacritics(t).lower() for t in terms]
    for nid, data in G.nodes(data=True):
        norm_label = data.get("norm_label") or _strip_diacritics(data.get("label") or "").lower()
        source = (data.get("source_file") or "").lower()
        score = sum(1 for t in norm_terms if t in norm_label) + sum(0.5 for t in norm_terms if t in source)
        if score > 0:
            scored.append((score, nid))
    return sorted(scored, reverse=True)


def _bfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    visited: set[str] = set(start_nodes)
    frontier = set(start_nodes)
    edges_seen: list[tuple] = []
    for _ in range(depth):
        next_frontier: set[str] = set()
        for n in frontier:
            for neighbor in G.neighbors(n):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    edges_seen.append((n, neighbor))
        visited.update(next_frontier)
        frontier = next_frontier
    return visited, edges_seen


def _dfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    visited: set[str] = set()
    edges_seen: list[tuple] = []
    stack = [(n, 0) for n in reversed(start_nodes)]
    while stack:
        node, d = stack.pop()
        if node in visited or d > depth:
            continue
        visited.add(node)
        for neighbor in G.neighbors(node):
            if neighbor not in visited:
                stack.append((neighbor, d + 1))
                edges_seen.append((node, neighbor))
    return visited, edges_seen


def _subgraph_to_text(G: nx.Graph, nodes: set[str], edges: list[tuple], token_budget: int = 2000) -> str:
    """Render subgraph as text, cutting at token_budget (approx 3 chars/token)."""
    char_budget = token_budget * 3
    lines = []
    for nid in sorted(nodes, key=lambda n: G.degree(n), reverse=True):
        d = G.nodes[nid]
        line = f"NODE {sanitize_label(d.get('label', nid))} [src={d.get('source_file', '')} loc={d.get('source_location', '')} community={d.get('community', '')}]"
        lines.append(line)
    for u, v in edges:
        if u in nodes and v in nodes:
            raw = G[u][v]
            d = next(iter(raw.values()), {}) if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)) else raw
            line = f"EDGE {sanitize_label(G.nodes[u].get('label', u))} --{d.get('relation', '')} [{d.get('confidence', '')}]--> {sanitize_label(G.nodes[v].get('label', v))}"
            lines.append(line)
    output = "\n".join(lines)
    if len(output) > char_budget:
        output = output[:char_budget] + f"\n... (truncated to ~{token_budget} token budget)"
    return output


def _find_node(G: nx.Graph, label: str) -> list[str]:
    """Return node IDs whose label or ID matches the search term (diacritic-insensitive)."""
    term = _strip_diacritics(label).lower()
    return [nid for nid, d in G.nodes(data=True)
            if term in (d.get("norm_label") or _strip_diacritics(d.get("label") or "").lower())
            or term == nid.lower()]


def _filter_blank_stdin() -> None:
    """Filter blank lines from stdin before MCP reads it.

    Some MCP clients (Claude Desktop, etc.) send blank lines between JSON
    messages. The MCP stdio transport tries to parse every line as a
    JSONRPCMessage, so a bare newline triggers a Pydantic ValidationError.
    This installs an OS-level pipe that relays stdin while dropping blanks.
    """
    import os
    import threading

    r_fd, w_fd = os.pipe()
    saved_fd = os.dup(sys.stdin.fileno())

    def _relay() -> None:
        try:
            with open(saved_fd, "rb") as src, open(w_fd, "wb") as dst:
                for line in src:
                    if line.strip():
                        dst.write(line)
                        dst.flush()
        except Exception:
            pass

    threading.Thread(target=_relay, daemon=True).start()
    os.dup2(r_fd, sys.stdin.fileno())
    os.close(r_fd)
    sys.stdin = open(0, "r", closefd=False)


def serve(graph_path: str = ".") -> None:
    """Start the MCP server. Requires pip install mcp."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError as e:
        raise ImportError("mcp not installed. Run: pip install mcp") from e

    service = _service_from_target(graph_path)

    server = Server("graphify")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="refresh_if_stale",
                description="Refresh the project graph only when source files changed.",
                inputSchema={"type": "object", "properties": {"force": {"type": "boolean", "default": False}}},
            ),
            types.Tool(
                name="summary",
                description="Return compact graph architecture stats and top symbols.",
                inputSchema={"type": "object", "properties": {"limit": {"type": "integer", "default": 10}}},
            ),
            types.Tool(
                name="report",
                description="Return the current graph report.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="find",
                description="Find code symbols by name, qualified name, path, or ID.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "kind": {"type": "string", "default": ""},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="details",
                description="Return symbol details, callers, callees, and children.",
                inputSchema={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
            ),
            types.Tool(
                name="query_graph",
                description="Search the knowledge graph using BFS or DFS. Returns relevant nodes and edges as text context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Natural language question or keyword search"},
                        "mode": {"type": "string", "enum": ["bfs", "dfs"], "default": "bfs",
                                 "description": "bfs=broad context, dfs=trace a specific path"},
                        "depth": {"type": "integer", "default": 3, "description": "Traversal depth (1-6)"},
                        "token_budget": {"type": "integer", "default": 2000, "description": "Max output tokens"},
                    },
                    "required": ["question"],
                },
            ),
            types.Tool(
                name="context_load",
                description="Load compact symbol context into the graph context manager.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="context_budget",
                description="Return loaded graph-context token budget.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="context_prompt",
                description="Render loaded graph context as prompt-ready text.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="context_evict",
                description="Evict matching graph context, or all context when query is empty.",
                inputSchema={"type": "object", "properties": {"query": {"type": "string", "default": ""}}},
            ),
            types.Tool(
                name="get_node",
                description="Get full details for a specific node by label or ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"label": {"type": "string", "description": "Node label or ID to look up"}},
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_neighbors",
                description="Get all direct neighbors of a node with edge details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "relation_filter": {"type": "string", "description": "Optional: filter by relation type"},
                    },
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_community",
                description="Get all nodes in a community by community ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"community_id": {"type": "integer", "description": "Community ID (0-indexed by size)"}},
                    "required": ["community_id"],
                },
            ),
            types.Tool(
                name="god_nodes",
                description="Return the most connected nodes - the core abstractions of the knowledge graph.",
                inputSchema={"type": "object", "properties": {"top_n": {"type": "integer", "default": 10}}},
            ),
            types.Tool(
                name="graph_stats",
                description="Return summary statistics: node count, edge count, communities, confidence breakdown.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="shortest_path",
                description="Find the shortest path between two concepts in the knowledge graph.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source concept label or keyword"},
                        "target": {"type": "string", "description": "Target concept label or keyword"},
                        "max_hops": {"type": "integer", "default": 8, "description": "Maximum hops to consider"},
                    },
                    "required": ["source", "target"],
                },
            ),
        ]

    def _tool_refresh_if_stale(arguments: dict) -> str:
        return json.dumps(service.ensure_fresh(reason="mcp", force=bool(arguments.get("force", False))).to_dict(), indent=2)

    def _tool_summary(arguments: dict) -> str:
        return json.dumps(service.query().architecture_report(limit=int(arguments.get("limit", 10))), indent=2)

    def _tool_report(_: dict) -> str:
        return service.report()

    def _tool_find(arguments: dict) -> str:
        rows = service.query().find_symbol(
            arguments["query"],
            kind=arguments.get("kind", ""),
            limit=int(arguments.get("limit", 20)),
        )
        return json.dumps(rows, indent=2)

    def _tool_details(arguments: dict) -> str:
        return json.dumps(service.query().symbol_details(arguments["symbol"]), indent=2)

    def _tool_query_graph(arguments: dict) -> str:
        return service.query().query_graph(
            arguments["question"],
            mode=arguments.get("mode", "bfs"),
            depth=min(int(arguments.get("depth", 3)), 6),
            token_budget=int(arguments.get("token_budget", 2000)),
        )

    def _tool_get_node(arguments: dict) -> str:
        details = service.query().symbol_details(arguments["label"])
        return json.dumps(details, indent=2) if details else f"No node matching '{arguments['label']}' found."

    def _tool_get_neighbors(arguments: dict) -> str:
        return json.dumps(
            service.query().neighbors(arguments["label"], relation_filter=arguments.get("relation_filter", "")),
            indent=2,
        )

    def _tool_get_community(arguments: dict) -> str:
        return json.dumps(service.query().community(int(arguments["community_id"])), indent=2)

    def _tool_god_nodes(arguments: dict) -> str:
        nodes = service.query().graph.metadata.get("god_nodes", [])[: int(arguments.get("top_n", 10))]
        lines = ["God nodes:"]
        lines += [f"  {i}. {n['label']} - {n['degree']} edges" for i, n in enumerate(nodes, 1)]
        return "\n".join(lines)

    def _tool_graph_stats(_: dict) -> str:
        return json.dumps(service.stats(), indent=2)

    def _tool_shortest_path(arguments: dict) -> str:
        return json.dumps(
            service.query().shortest_path(arguments["source"], arguments["target"], max_hops=int(arguments.get("max_hops", 8))),
            indent=2,
        )

    def _tool_context_load(arguments: dict) -> str:
        return json.dumps(service.context().load(arguments["query"], limit=int(arguments.get("limit", 5))), indent=2)

    def _tool_context_budget(_: dict) -> str:
        return json.dumps(service.context().budget_summary(), indent=2)

    def _tool_context_prompt(_: dict) -> str:
        return service.context().prompt_context()

    def _tool_context_evict(arguments: dict) -> str:
        return json.dumps(service.context().evict(arguments.get("query", "")), indent=2)

    _handlers = {
        "refresh_if_stale": _tool_refresh_if_stale,
        "summary": _tool_summary,
        "report": _tool_report,
        "find": _tool_find,
        "details": _tool_details,
        "query_graph": _tool_query_graph,
        "get_node": _tool_get_node,
        "get_neighbors": _tool_get_neighbors,
        "get_community": _tool_get_community,
        "god_nodes": _tool_god_nodes,
        "graph_stats": _tool_graph_stats,
        "shortest_path": _tool_shortest_path,
        "context_load": _tool_context_load,
        "context_budget": _tool_context_budget,
        "context_prompt": _tool_context_prompt,
        "context_evict": _tool_context_evict,
    }

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        handler = _handlers.get(name)
        if not handler:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
        try:
            return [types.TextContent(type="text", text=handler(arguments))]
        except Exception as exc:
            return [types.TextContent(type="text", text=f"Error executing {name}: {exc}")]

    import asyncio

    async def main() -> None:
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    _filter_blank_stdin()
    asyncio.run(main())


def _service_from_target(target: str) -> GraphService:
    path = Path(target or ".").resolve()
    if path.suffix == ".json":
        graph_path = path
        out = graph_path.parent
        root = out.parent if out.name == ".graph-out" else Path.cwd().resolve()
        context_path = out / "project_graph_context.json"
        return GraphService(GraphStore(root, graph_path, context_path))
    out = path / ".graph-out"
    return GraphService(GraphStore(path, out / "project_graph.json", out / "project_graph_context.json"))


if __name__ == "__main__":
    graph_path = sys.argv[1] if len(sys.argv) > 1 else "."
    serve(graph_path)

