"""Command line interface for the project graph."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from graph.context import GraphContextManager
from graph.query import ProjectGraphQuery
from graph.store import GraphStore

COMMANDS = {
    "refresh",
    "summary",
    "find",
    "details",
    "usages",
    "hierarchy",
    "related",
    "query",
    "path",
    "explain",
    "stats",
    "report",
    "context",
}


def main() -> None:
    root, argv = _split_root(sys.argv[1:])
    store = _store(root.resolve())

    if not argv or argv[0].startswith("--"):
        find = _option_value(argv, "--find")
        graph = store.refresh()
        query = ProjectGraphQuery(graph)
        print(query.skeleton(max_files=80))
        print()
        print(_json(query.architecture_report(limit=8)))
        if find:
            print()
            print(_json(query.find_symbol(find)))
        return

    command, rest = argv[0], argv[1:]
    if command not in COMMANDS:
        _usage(f"unknown command: {command}")

    if command == "refresh":
        graph = store.refresh()
        print(f"Graph refreshed: {len(graph.files)} Python files, {len(graph.symbols)} symbols, {len(graph.edges)} edges")
        print(f"Report: {store.report_path()}")
        return

    graph = store.load_or_refresh()
    query = ProjectGraphQuery(graph)

    if command == "summary":
        print(_json(query.architecture_report()))
    elif command == "find":
        print(_json(query.find_symbol(_required(rest, "query"))))
    elif command == "details":
        print(_json(query.symbol_details(_required(rest, "symbol"))))
    elif command == "usages":
        print(_json(query.usages(_required(rest, "symbol"))))
    elif command == "hierarchy":
        print(_json(query.hierarchy(_required(rest, "symbol"))))
    elif command == "related":
        print(_json(query.related(_required(rest, "symbol"))))
    elif command == "query":
        print(query.query_graph(" ".join(rest) if rest else _usage("query requires a question")))
    elif command == "path":
        if len(rest) < 2:
            _usage("path requires source and target")
        print(_json(query.shortest_path(rest[0], rest[1])))
    elif command == "explain":
        node = _required(rest, "node")
        print(_json({"node": node, "neighbors": query.neighbors(node)}))
    elif command == "stats":
        print(_json(query.graph_stats()))
    elif command == "report":
        report = store.report_path()
        print(report.read_text(encoding="utf-8") if report.exists() else "No graph report found. Run `graphify refresh`.")
    elif command == "context":
        if not rest:
            _usage("context requires load|budget|prompt|evict")
        manager = GraphContextManager(store)
        action = rest[0]
        argument = " ".join(rest[1:])
        if action == "load":
            print(_json(manager.load(argument)))
        elif action == "budget":
            print(_json(manager.budget_summary()))
        elif action == "prompt":
            print(manager.prompt_context())
        elif action == "evict":
            print(_json(manager.evict(argument)))
        else:
            _usage("context action must be load, budget, prompt, or evict")


def _split_root(argv: list[str]) -> tuple[Path, list[str]]:
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("--"):
        return Path(argv[0]), argv[1:]
    return Path("."), argv


def _store(root: Path) -> GraphStore:
    out = root / ".graph-out"
    return GraphStore(root, out / "project_graph.json", out / "project_graph_context.json")


def _option_value(argv: list[str], name: str) -> str:
    if name not in argv:
        return ""
    index = argv.index(name)
    return argv[index + 1] if index + 1 < len(argv) else ""


def _required(argv: list[str], label: str) -> str:
    if not argv:
        _usage(f"missing {label}")
    return argv[0]


def _usage(error: str) -> str:
    print(f"error: {error}", file=sys.stderr)
    print("usage: graphify [ROOT] [refresh|summary|find|details|usages|hierarchy|related|query|path|explain|stats|report|context]", file=sys.stderr)
    raise SystemExit(2)


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)


if __name__ == "__main__":
    main()
