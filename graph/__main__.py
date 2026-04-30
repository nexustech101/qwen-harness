"""Command line interface for the project graph."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from graph.service import GraphService

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
    "serve",
    "mcp",
}


def main() -> None:
    root, argv = _split_root(sys.argv[1:])
    service = GraphService.for_project(root.resolve())

    if not argv or argv[0] in {"--help", "-h", "help"}:
        _print(_usage_text())
        return

    if argv and argv[0].startswith("--"):
        find = _option_value(argv, "--find")
        service.ensure_fresh(reason="legacy", force=True)
        query = service.query()
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
        result = service.ensure_fresh(reason="cli", force=True)
        print(result.message)
        print(f"Report: {result.report_path}")
        return

    if command in {"serve", "mcp"}:
        from graph.serve import serve

        serve(str(root.resolve()))
        return

    query = service.query()

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
        _print(service.report() or "No graph report found. Run `graphify refresh`.")
    elif command == "context":
        if not rest:
            _usage("context requires load|budget|prompt|evict")
        manager = service.context()
        action = rest[0]
        argument_parts = rest[1:]
        limit = 5
        if "--limit" in argument_parts:
            idx = argument_parts.index("--limit")
            try:
                limit = int(argument_parts[idx + 1])
            except (IndexError, ValueError):
                _usage("context --limit requires an integer")
            del argument_parts[idx:idx + 2]
        argument = " ".join(argument_parts)
        if action == "load":
            print(_json(manager.load(argument, limit=limit)))
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
    print(_usage_text(), file=sys.stderr)
    raise SystemExit(2)


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)


def _usage_text() -> str:
    return (
        "usage: graphify [ROOT] "
        "[refresh|summary|find|details|usages|hierarchy|related|query|path|explain|stats|report|context|serve|mcp]\n"
        "\n"
        "examples:\n"
        "  graphify refresh\n"
        "  graphify summary\n"
        "  graphify find ExecutionEngine\n"
        "  graphify context load ExecutionEngine --limit 3\n"
        "  graphify mcp\n"
    )


def _print(text: str) -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        sys.stdout.buffer.write((text + ("\n" if not text.endswith("\n") else "")).encode(encoding, errors="replace"))


if __name__ == "__main__":
    main()
