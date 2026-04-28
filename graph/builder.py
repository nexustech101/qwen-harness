"""Project graph builder and relationship resolver."""

from __future__ import annotations

import fnmatch
import os
from collections import defaultdict
from pathlib import Path

from graph.adapters import add_extraction, to_networkx, update_communities
from graph.detect import FileType, detect
from graph.models import GraphEdge, ProjectGraph
from graph.parser import parse_python_file

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".eggs",
}


def build_project_graph(
    project_root: Path | str,
    include: str = "",
    exclude: str = "",
) -> ProjectGraph:
    root = Path(project_root).resolve()
    graph = ProjectGraph(project_root=str(root))
    detection = _detect_files(root)
    code_files = [
        Path(path)
        for path in detection.get("files", {}).get(FileType.CODE.value, [])
        if _included(path, root, include, exclude)
    ]
    python_files = [path for path in code_files if path.suffix.lower() == ".py"]

    for path in sorted(python_files):
        parsed = parse_python_file(path, root)
        graph.files[parsed.file.path] = parsed.file
        graph.symbols.update(parsed.symbols)
        graph.edges.extend(parsed.edges)
        graph.calls.extend(parsed.calls)

    extraction = _extract_code(code_files, root)
    if extraction:
        add_extraction(graph, extraction, root)

    _resolve_relationships(graph)
    _analyze_graph(graph, detection)
    graph.metadata.update(
        {
            "file_count": len(graph.files),
            "symbol_count": len(graph.symbols),
            "node_count": len(graph.nodes) + len(graph.symbols),
            "edge_count": len(graph.edges),
            "unresolved_call_count": sum(1 for call in graph.calls if not call.target_id),
            "detection": detection,
            "extraction_errors": extraction.get("errors", []) if extraction else [],
        }
    )
    return graph


def _detect_files(root: Path) -> dict:
    try:
        return detect(root)
    except Exception as exc:
        return {
            "files": {FileType.CODE.value: [str(path) for path in _iter_python_files(root, "**/*.py", "")]},
            "total_files": 0,
            "total_words": 0,
            "warning": f"Detection failed: {exc}",
        }


def _included(path: str | Path, root: Path, include: str, exclude: str) -> bool:
    try:
        rel = Path(path).resolve().relative_to(root).as_posix()
    except ValueError:
        rel = str(path).replace("\\", "/")
    if include and not _matches(rel, include):
        filename = Path(path).name
        if not _matches(filename, include):
            return False
    if exclude and _matches(rel, exclude):
        return False
    return True


def _extract_code(code_files: list[Path], root: Path) -> dict:
    if not code_files:
        return {"nodes": [], "edges": [], "hyperedges": [], "errors": []}
    try:
        from graph.extract import extract

        result = extract(code_files, cache_root=root)
        result.setdefault("errors", [])
        return result
    except Exception as exc:
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "errors": [f"tree-sitter extraction unavailable: {exc}"],
            "input_tokens": 0,
            "output_tokens": 0,
        }


def _analyze_graph(graph: ProjectGraph, detection: dict) -> None:
    try:
        from graph.analyze import god_nodes, surprising_connections, suggest_questions
        from graph.cluster import cluster, score_all

        G = to_networkx(graph)
        communities = cluster(G)
        update_communities(graph, communities)
        graph.metadata.update(
            {
                "cohesion": score_all(G, communities),
                "god_nodes": god_nodes(G),
                "surprising_connections": surprising_connections(G, communities),
                "suggested_questions": suggest_questions(
                    G,
                    communities,
                    {cid: f"Community {cid}" for cid in communities},
                ),
                "networkx_nodes": G.number_of_nodes(),
                "networkx_edges": G.number_of_edges(),
            }
        )
    except Exception as exc:
        graph.metadata["analysis_error"] = str(exc)


def _iter_python_files(root: Path, include: str, exclude: str) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = Path(dirpath) / filename
            rel = path.relative_to(root).as_posix()
            if include and not _matches(rel, include):
                continue
            if exclude and _matches(rel, exclude):
                continue
            files.append(path)
    return sorted(files)


def _matches(rel_path: str, pattern: str) -> bool:
    if fnmatch.fnmatch(rel_path, pattern):
        return True
    if pattern.startswith("**/") and fnmatch.fnmatch(rel_path, pattern[3:]):
        return True
    return False


def _resolve_relationships(graph: ProjectGraph) -> None:
    module_to_file = {file.module: path for path, file in graph.files.items()}
    module_to_id = {file.module: f"{path}::<module>" for path, file in graph.files.items()}
    simple_index: dict[str, list[str]] = defaultdict(list)
    file_symbols: dict[str, list[str]] = defaultdict(list)
    qual_index: dict[tuple[str, str], str] = {}

    for symbol_id, symbol in graph.symbols.items():
        simple_index[symbol.name].append(symbol_id)
        file_symbols[symbol.path].append(symbol_id)
        qual_index[(symbol.path, symbol.qualname)] = symbol_id

    import_aliases: dict[str, dict[str, str]] = defaultdict(dict)
    for file_path, file in graph.files.items():
        for item in file.imports:
            target = _resolve_import_target(item.module, item.name, file.module, module_to_file, module_to_id, graph)
            item.target = target
            if item.alias and target:
                import_aliases[file_path][item.alias] = target
            if target:
                graph.edges.append(
                    GraphEdge(
                        source=f"{file_path}::<module>",
                        target=target,
                        kind="imports",
                        metadata={"line": item.line, "module": item.module, "name": item.name},
                    )
                )

    for call in graph.calls:
        caller = graph.symbols.get(call.caller_id)
        if not caller:
            continue
        target = _resolve_call(call.expression, caller, graph, simple_index, file_symbols, qual_index, import_aliases)
        if target:
            call.target_id = target
            graph.edges.append(
                GraphEdge(
                    source=call.caller_id,
                    target=target,
                    kind="calls",
                    metadata={"line": call.line, "expression": call.expression},
                )
            )


def _resolve_import_target(
    module: str,
    name: str,
    current_module: str,
    module_to_file: dict[str, str],
    module_to_id: dict[str, str],
    graph: ProjectGraph,
) -> str:
    resolved_module = _absolute_module(module, current_module)
    if name:
        module_path = module_to_file.get(resolved_module)
        if module_path:
            exact = f"{module_path}::{name}"
            if exact in graph.symbols:
                return exact
            for symbol in graph.symbols.values():
                if symbol.path == module_path and symbol.name == name:
                    return symbol.id
        combined = f"{resolved_module}.{name}" if resolved_module else name
        return module_to_id.get(combined, "")
    return module_to_id.get(resolved_module, "")


def _absolute_module(module: str, current_module: str) -> str:
    if not module.startswith("."):
        return module
    level = len(module) - len(module.lstrip("."))
    tail = module.lstrip(".")
    parts = current_module.split(".")
    base = parts[: max(len(parts) - level, 0)]
    if tail:
        base.extend(tail.split("."))
    return ".".join(part for part in base if part)


def _resolve_call(
    expression: str,
    caller,
    graph: ProjectGraph,
    simple_index: dict[str, list[str]],
    file_symbols: dict[str, list[str]],
    qual_index: dict[tuple[str, str], str],
    import_aliases: dict[str, dict[str, str]],
) -> str:
    aliases = import_aliases.get(caller.path, {})
    if expression in aliases and aliases[expression] in graph.symbols:
        return aliases[expression]

    if "." in expression:
        first, rest = expression.split(".", 1)
        if first in aliases:
            imported = graph.symbols.get(aliases[first])
            if imported:
                if imported.kind == "module":
                    target = qual_index.get((imported.path, rest))
                    if target:
                        return target
                target = qual_index.get((imported.path, f"{imported.qualname}.{rest}"))
                if target:
                    return target
        if first == "self":
            class_qual = _enclosing_class_qual(caller.qualname)
            if class_qual:
                target = qual_index.get((caller.path, f"{class_qual}.{rest}"))
                if target:
                    return target
        target = qual_index.get((caller.path, expression))
        if target:
            return target

    for symbol_id in file_symbols.get(caller.path, []):
        symbol = graph.symbols[symbol_id]
        if symbol.name == expression:
            return symbol.id

    candidates = simple_index.get(expression, [])
    if len(candidates) == 1:
        return candidates[0]
    return ""


def _enclosing_class_qual(qualname: str) -> str:
    parts = qualname.split(".")
    if len(parts) < 2:
        return ""
    return ".".join(parts[:-1])

