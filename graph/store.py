"""Workspace-backed graph persistence."""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any

from networkx.readwrite import json_graph

from graph.adapters import to_networkx
from graph.builder import build_project_graph
from graph.detect import CODE_EXTENSIONS, FileType, detect
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
        self.write_source_snapshot(self.current_source_snapshot())
        self.clear_dirty()

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

    def load_or_refresh_if_stale(self, include: str = "", exclude: str = "") -> ProjectGraph:
        if self.is_stale(include=include, exclude=exclude):
            return self.refresh(include=include, exclude=exclude)
        graph = self.load()
        if graph is not None:
            return graph
        return self.refresh(include=include, exclude=exclude)

    def source_snapshot_path(self) -> Path:
        return self.graph_path.with_name("project_graph_snapshot.json")

    def dirty_path(self) -> Path:
        return self.graph_path.with_name("project_graph_dirty.json")

    def current_source_snapshot(self, include: str = "", exclude: str = "") -> dict[str, Any]:
        """Return a compact mtime/size snapshot of graph-relevant source files."""
        files: dict[str, dict[str, int]] = {}
        detection: dict[str, Any] = {}
        try:
            detection = detect(self.project_root)
            code_files = detection.get("files", {}).get(FileType.CODE.value, [])
        except Exception as exc:
            detection = {"error": str(exc)}
            code_files = [str(path) for path in self.project_root.rglob("*") if path.suffix.lower() in CODE_EXTENSIONS]

        for raw_path in code_files:
            path = Path(raw_path)
            if not path.is_absolute():
                path = (self.project_root / path).resolve()
            if path.suffix.lower() not in CODE_EXTENSIONS:
                continue
            rel = _rel_path(path, self.project_root)
            if include and not _matches(rel, include):
                continue
            if exclude and _matches(rel, exclude):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            files[rel] = {"mtime_ns": int(stat.st_mtime_ns), "size": int(stat.st_size)}

        return {
            "version": 1,
            "project_root": str(self.project_root),
            "files": dict(sorted(files.items())),
            "detection": {
                "total_files": detection.get("total_files", len(files)),
                "warning": detection.get("warning", ""),
                "error": detection.get("error", ""),
            },
        }

    def read_source_snapshot(self) -> dict[str, Any]:
        path = self.source_snapshot_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def write_source_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.source_snapshot_path().parent.mkdir(parents=True, exist_ok=True)
        self.source_snapshot_path().write_text(json.dumps(snapshot, indent=2, ensure_ascii=True), encoding="utf-8")

    def mark_dirty(self, paths: list[str] | tuple[str, ...]) -> None:
        relevant = sorted({_rel_path(Path(path), self.project_root) for path in paths if _is_graph_relevant(path)})
        if not relevant:
            return
        current = self.read_dirty()
        existing = set(current.get("paths", []))
        current["paths"] = sorted(existing | set(relevant))
        self.dirty_path().parent.mkdir(parents=True, exist_ok=True)
        self.dirty_path().write_text(json.dumps(current, indent=2, ensure_ascii=True), encoding="utf-8")

    def read_dirty(self) -> dict[str, Any]:
        path = self.dirty_path()
        if not path.exists():
            return {"paths": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"paths": []}
        if not isinstance(data, dict):
            return {"paths": []}
        data.setdefault("paths", [])
        return data

    def clear_dirty(self) -> None:
        try:
            self.dirty_path().unlink()
        except FileNotFoundError:
            pass

    def is_stale(self, include: str = "", exclude: str = "") -> bool:
        if not self.graph_path.exists():
            return True
        dirty = self.read_dirty()
        if dirty.get("paths"):
            return True
        previous = self.read_source_snapshot()
        if not previous:
            return True
        current = self.current_source_snapshot(include=include, exclude=exclude)
        return previous.get("files", {}) != current.get("files", {})

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


def _rel_path(path: Path, root: Path) -> str:
    try:
        resolved = path if path.is_absolute() else (root / path)
        return resolved.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path).replace("\\", "/")


def _matches(rel_path: str, pattern: str) -> bool:
    if fnmatch.fnmatch(rel_path, pattern):
        return True
    if pattern.startswith("**/") and fnmatch.fnmatch(rel_path, pattern[3:]):
        return True
    return False


def _is_graph_relevant(path: str | Path) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in CODE_EXTENSIONS

